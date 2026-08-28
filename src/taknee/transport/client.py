"""Unified transport bridge for the Swarm Mesh.

Connects SwarmRotator.pick_route() decisions to the existing providers.chat()
transport layer, auto-recording 429s back into the rotator for instant failover.

Architecture: providers.chat() is already battle-tested for multi-provider
OpenAI-compatible requests (litellm + httpx fallback). This module does NOT
rewrite it — it is a thin routing shim:
    RouteDecision -> providers.chat() -> ChatResult
"""

from __future__ import annotations

from typing import Any

from .. import providers
from ..providers import ChatResult, RateLimited, ProviderError
from ..swarm.rotator import RouteDecision, SwarmRotator


def chat_with_route(
    route: RouteDecision,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout: float = 90.0,
    settings: dict[str, Any] | None = None,
) -> ChatResult:
    """Call the LLM using a SwarmRotator RouteDecision.

    Injects the route key into settings so providers.chat() finds it.
    On 429, propagates RateLimited so the caller can rotate.
    """
    effective_settings: dict[str, Any] = dict(settings or {})
    if route.api_key and route.api_key != "ollama":
        effective_settings.setdefault("providers", {})[route.provider] = {
            "key": route.api_key
        }

    return providers.chat(
        provider=route.provider,
        model=route.model,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        settings=effective_settings,
    )


def chat_with_swarm(
    rotator: SwarmRotator,
    messages: list[dict[str, Any]],
    *,
    tier: str = "primary",
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout: float = 90.0,
    settings: dict[str, Any] | None = None,
    max_retries: int = 4,
) -> tuple[ChatResult, RouteDecision]:
    """Auto-rotating LLM call with built-in 429 failover across free providers.

    Tries up to max_retries providers. On rate-limit, records it in the
    rotator so the next pick avoids that key/provider automatically.

    Returns (ChatResult, RouteDecision) so callers log which provider won.
    Raises RuntimeError when all providers are exhausted.
    """
    est_tokens = sum(len(m.get("content", "")) // 4 for m in messages) + (max_tokens or 2048)

    for attempt in range(max_retries):
        route = rotator.pick_route(tier=tier, est_tokens=est_tokens, iteration=attempt)
        if route is None:
            raise RuntimeError(
                "SwarmRouter exhausted: no healthy free provider or local Ollama available. "
                "Add API keys via `taknee setup` or install Ollama (https://ollama.ai)."
            )
        try:
            result = chat_with_route(
                route, messages,
                tools=tools, temperature=temperature,
                max_tokens=max_tokens, timeout=timeout, settings=settings,
            )
            rotator.record_success(route.provider)
            return result, route

        except RateLimited as e:
            rotator.record_429(route.provider, route.api_key, retry_after=e.retry_after)

        except ProviderError:
            rotator.radar.record_cooldown(route.provider, 60.0)

    raise RuntimeError(
        f"All {max_retries} swarm routing attempts failed. "
        "Check provider health or add more keys via `taknee setup`."
    )
