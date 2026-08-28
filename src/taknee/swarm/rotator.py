"""Swarm Rotator — Multi-key pool and zero-latency failover balancer across free providers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .radar import FreeModel, Radar

# Default provider execution preference (fastest free-tier first)
SWARM_PROVIDER_PREFERENCE = (
    "groq",        # 1. 500 t/s Llama 3.3 (ultra fast AST & planning)
    "openrouter",  # 2. Free Qwen 3 Coder 30B & Llama 3.3
    "gemini",      # 3. Google AI Studio 1M context free quota
    "nim",         # 4. NVIDIA NIM free tier
    "cerebras",    # 5. Cerebras fast inference
    "ollama",      # 6. Local zero-cost offline fallback
)


@dataclass
class KeyEntry:
    key: str
    label: str = "default"
    rate_limited_until: float = 0.0
    total_calls: int = 0
    total_failures: int = 0


@dataclass
class KeyPool:
    provider: str
    keys: list[KeyEntry] = field(default_factory=list)
    current_idx: int = 0

    def add_key(self, key_str: str, label: str = "key") -> None:
        cleaned = key_str.strip()
        if cleaned and not any(k.key == cleaned for k in self.keys):
            self.keys.append(KeyEntry(key=cleaned, label=label))

    def get_healthy_key(self) -> str | None:
        if not self.keys:
            return None
        now = time.time()
        # Round-robin starting from current_idx
        for i in range(len(self.keys)):
            idx = (self.current_idx + i) % len(self.keys)
            k = self.keys[idx]
            if k.rate_limited_until <= now:
                self.current_idx = (idx + 1) % len(self.keys)
                k.total_calls += 1
                return k.key
        return None

    def record_rate_limit(self, key_str: str, cooldown_s: float = 30.0) -> None:
        now = time.time()
        for k in self.keys:
            if k.key == key_str:
                k.rate_limited_until = now + cooldown_s
                k.total_failures += 1


@dataclass
class RouteDecision:
    provider: str
    model: str
    api_key: str
    tier: str
    reason: str
    speed_tps: float = 50.0
    context_window: int = 131_072
    is_local: bool = False

    def as_span_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "tier": self.tier,
            "route_reason": self.reason,
            "is_local": self.is_local,
        }


class SwarmRotator:
    """Balances traffic across multiple free-tier keys and gateways."""

    def __init__(self, radar: Radar | None = None):
        self.radar = radar or Radar()
        self._pools: dict[str, KeyPool] = {p: KeyPool(provider=p) for p in SWARM_PROVIDER_PREFERENCE}
        self._local_base_url = "http://127.0.0.1:11434/v1"

    def register_key(self, provider: str, key_str: str, label: str = "default") -> None:
        """Registers a key into the provider's key pool."""
        if provider not in self._pools:
            self._pools[provider] = KeyPool(provider=provider)
        self._pools[provider].add_key(key_str, label=label)

    def register_keys_from_dict(self, cfg: dict[str, Any]) -> None:
        """Loads keys from a standard settings dictionary."""
        providers_dict = cfg.get("providers", {})
        for name, p_data in providers_dict.items():
            # Support single key or array of keys
            key = p_data.get("key", "")
            if key:
                self.register_key(name, key, label="primary")
            keys_list = p_data.get("keys", [])
            for i, extra_key in enumerate(keys_list):
                if extra_key:
                    self.register_key(name, extra_key, label=f"key-{i+1}")

    def pick_route(
        self,
        tier: str = "primary",
        est_tokens: int = 8_000,
        iteration: int = 0,
        prefer_local: bool = False,
    ) -> RouteDecision | None:
        """Selects the optimal healthy provider, model, and key for an agent stage."""
        available_models = self.radar.get_free_models()

        if prefer_local:
            local_models = [m for m in available_models if m.provider == "ollama"]
            if local_models:
                m = local_models[0]
                return RouteDecision(
                    provider="ollama",
                    model=m.id,
                    api_key="ollama",
                    tier=tier,
                    reason=f"Local-first preference: {m.id} via Ollama",
                    is_local=True,
                )

        # Iterate through provider preference order
        for provider in SWARM_PROVIDER_PREFERENCE:
            if provider == "ollama":
                continue  # Ollama is used as final fallback

            pool = self._pools.get(provider)
            if not pool or not pool.keys:
                continue

            health = self.radar.check_provider_health(provider)
            if not health.healthy:
                continue

            key = pool.get_healthy_key()
            if not key:
                continue

            # Find matching model in radar
            candidates = [
                m
                for m in available_models
                if m.provider == provider and (m.tier == tier or tier == "any") and m.context_window >= est_tokens + 2048
            ]
            if not candidates:
                # Fallback to any model for this provider with sufficient context
                candidates = [
                    m for m in available_models if m.provider == provider and m.context_window >= est_tokens + 2048
                ]

            if candidates:
                # On repair iterations, choose largest model; on iteration 0, choose fastest
                if iteration > 0:
                    candidates.sort(key=lambda m: m.context_window, reverse=True)
                else:
                    candidates.sort(key=lambda m: m.speed_tps, reverse=True)

                chosen = candidates[0]
                return RouteDecision(
                    provider=provider,
                    model=chosen.id,
                    api_key=key,
                    tier=tier,
                    reason=f"Swarm Tier {tier} -> {chosen.name} @ {provider} ({chosen.speed_tps:.0f} t/s, 0 cost)",
                    speed_tps=chosen.speed_tps,
                    context_window=chosen.context_window,
                    is_local=False,
                )

        # Ultimate fallback: local Ollama
        for m in available_models:
            if m.provider == "ollama" and m.context_window >= est_tokens + 2048:
                return RouteDecision(
                    provider="ollama",
                    model=m.id,
                    api_key="ollama",
                    tier="local",
                    reason=f"Zero-cost local fallback: {m.id} via Ollama",
                    is_local=True,
                )

        return None

    def record_429(self, provider: str, key_str: str, retry_after: float | None = None) -> None:
        """Handles a 429 rate limit by cooling down the specific key and provider."""
        cooldown = retry_after if retry_after and retry_after > 0 else 30.0
        pool = self._pools.get(provider)
        if pool:
            pool.record_rate_limit(key_str, cooldown)
        self.radar.record_cooldown(provider, cooldown)

    def record_success(self, provider: str) -> None:
        """Restores provider health upon successful completion."""
        self.radar.clear_cooldown(provider)
