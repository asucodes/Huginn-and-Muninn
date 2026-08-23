"""Router — deterministic, explainable, free-first model/provider selection.

Signals (req 3.a): stage tier, estimated context tokens, repair iteration,
provider cooldowns from live 429/5xx feedback, remaining task budget,
allow_paid/prefer_local settings. Every decision returns a human-readable
route_reason which the UI shows (route chip + span detail) — routing is never
hidden (req 3.b).

Rejected: an LLM meta-router — circular, costs money, hides the decision
(see docs/decisions.md D3 and docs/05-decision-log.md ADR-4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import catalog, settings as settings_mod

# preference order within a tier when everything is healthy:
# free & fast first, then free, then PAYG (only if allow_paid)
_PROVIDER_ORDER = ("ollama", "groq", "openrouter", "nim", "mistral", "cerebras", "deepinfra", "together")
FREE = {"ollama", "groq", "openrouter", "nim"}
DEFAULT_COOLDOWN_S = 45.0


@dataclass
class Route:
    model: str
    provider: str
    reason: str
    tier: str

    def as_span_meta(self) -> dict:
        return {"model": self.model, "provider": self.provider, "route_reason": self.reason}


class Router:
    def __init__(self, cooldown_s: float = DEFAULT_COOLDOWN_S):
        self.cooldown_s = cooldown_s
        self._cooldowns: dict[str, float] = {}  # provider -> until ts
        self._skip_models: set[tuple[str, str]] = set()  # (provider, model) 404/unavailable

    # -- feedback from the call layer ------------------------------------

    def record_failure(self, provider: str, retry_after: float | None = None) -> None:
        until = time.time() + (retry_after if retry_after else self.cooldown_s)
        self._cooldowns[provider] = max(self._cooldowns.get(provider, 0), until)

    def record_success(self, provider: str) -> None:
        self._cooldowns.pop(provider, None)

    def record_model_skip(self, provider: str, model: str) -> None:
        """Don't pick this model again this process (404 / not deployed)."""
        self._skip_models.add((provider, model))

    def cooling(self, provider: str) -> bool:
        until = self._cooldowns.get(provider, 0)
        if until and until <= time.time():
            del self._cooldowns[provider]
            return False
        return bool(until)

    def cooling_providers(self) -> list[str]:
        return [p for p in list(self._cooldowns) if self.cooling(p)]

    # -- the decision ------------------------------------------------------

    def pick(
        self,
        tier: str = "primary",
        est_tokens: int = 8_000,
        iteration: int = 0,
        settings: dict | None = None,
        allow_paid: bool | None = None,
    ) -> Route | None:
        """Pick model+provider for a stage.

        iteration>0 (repair retries) biases toward *largest* remaining model —
        harder attempts get the strongest eligible model, not another cheap one.
        """
        cfg = settings if settings is not None else settings_mod.load()
        paid_ok = cfg.get("allow_paid", False) if allow_paid is None else allow_paid
        prefer_local = cfg.get("prefer_local", False)

        candidates: list[tuple[catalog.ModelEntry, str]] = []
        for provider in _PROVIDER_ORDER:
            if provider == "ollama" and not prefer_local:
                continue  # local is a fallback, not the default lane
            if provider not in FREE and not paid_ok:
                continue
            if not settings_mod.has_key(provider, cfg):
                continue
            if self.cooling(provider):
                continue
            model_tier = "local" if provider == "ollama" else tier
            for m in catalog.models_for(provider, model_tier):
                if (provider, m.id) in self._skip_models:
                    continue
                if m.context_window >= est_tokens + 2_048:  # leave answer headroom
                    candidates.append((m, provider))

        if not candidates:
            # No configured API lane is healthy: local hardware is the final
            # zero-cost recovery path, regardless of the preference toggle.
            for m in catalog.models_for("ollama", "local"):
                if m.context_window >= est_tokens + 2_048:
                    candidates.append((m, "ollama"))

        if not candidates:
            return None

        cooling_note = (
            f", cooling={','.join(self.cooling_providers())}" if self.cooling_providers() else ""
        )
        if iteration == 0:
            # cheapest-healthy: $0-price (free-tier) models first, then fewest params
            candidates.sort(key=lambda item: (item[0].price_in > 0, item[0].total_params))
            m, provider = candidates[0]
            reason = (
                f"{tier} stage, est {est_tokens} tok, iteration 0 -> cheapest healthy: "
                f"{m.id} ({m.total_params/1e9:.1f}B) @ {provider}{cooling_note}"
            )
            return Route(m.id, provider, reason, tier)

        # repair iterations: strongest healthy candidate (params desc)
        candidates.sort(key=lambda item: item[0].total_params, reverse=True)
        m, provider = candidates[0]
        reason = (
            f"{tier} stage, est {est_tokens} tok, repair iteration {iteration} -> "
            f"strongest healthy: {m.id} ({m.total_params/1e9:.1f}B) @ {provider}{cooling_note}"
        )
        return Route(m.id, provider, reason, tier)

    def fallback_chain(
        self,
        tier: str = "primary",
        est_tokens: int = 8_000,
        settings: dict | None = None,
    ) -> list[Route]:
        """Ordered list of healthy candidates for a stage (used on failures)."""
        routes: list[Route] = []
        seen: set[str] = set()
        for iteration in (0, 1):
            r = self.pick(tier, est_tokens, iteration, settings)
            if r and (r.model, r.provider) not in seen:
                seen.add((r.model, r.provider))
                routes.append(r)
        return routes


def provider_of(m: catalog.ModelEntry) -> str:
    for p in _PROVIDER_ORDER:
        if p in m.providers:
            return p
    return m.providers[0] if m.providers else "?"
