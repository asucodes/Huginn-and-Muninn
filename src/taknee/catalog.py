"""Model catalog — the compliance artifact for the "<=80B total params" rule.

Every model the system may call (chat, embedding, reranker) must appear in
MODELS with its *published total* parameter count (for MoE: total, not active).
Anything not in MODELS is refused. BANNED documents the refusals we expect to
be asked about, with the reason.

Param counts are from publisher model cards (HF) as of 2026-08; re-verify
before adding entries. See docs/02-research-findings.md for sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_TOTAL_PARAMS = 80_000_000_000

TIERS = ("primary", "utility", "embed", "rerank", "local")


@dataclass(frozen=True)
class ModelEntry:
    id: str
    total_params: int
    context_window: int
    tier: str
    providers: tuple[str, ...] = field(default_factory=tuple)
    native_tools: bool = True
    # USD per 1M tokens on PAYG providers; free tiers cost 0 at the margin.
    price_in: float = 0.0
    price_out: float = 0.0
    note: str = ""


MODELS: dict[str, ModelEntry] = {
    "qwen/qwen3-coder-30b-a3b-instruct": ModelEntry(
        id="qwen/qwen3-coder-30b-a3b-instruct",
        total_params=30_500_000_000,  # MoE: 30.5B total / ~3B active
        context_window=262_144,
        tier="primary",
        providers=("openrouter", "deepinfra", "fireworks"),
        price_in=0.12,
        price_out=0.50,
        note="primary coder; native tool calls; 256K native ctx",
    ),
    "mistralai/devstral-small-2-24b-instruct": ModelEntry(
        id="mistralai/devstral-small-2-24b-instruct",
        total_params=24_000_000_000,
        context_window=131_072,
        tier="primary",
        providers=("mistral", "openrouter"),
        price_in=0.10,
        price_out=0.30,
        note="agentic SWE model; best SWE-bench per param",
    ),
    "qwen/qwen3-next-80b-a3b-instruct": ModelEntry(
        id="qwen/qwen3-next-80b-a3b-instruct",
        total_params=80_000_000_000,  # HF card: 80B total / 3B active — exactly at the cap
        context_window=262_144,
        tier="primary",
        providers=("openrouter",),
        price_in=0.20,
        price_out=0.60,
        note="legal at exactly 80B total; verify card before eval",
    ),
    "meta-llama/llama-3.3-70b-instruct": ModelEntry(
        id="meta-llama/llama-3.3-70b-instruct",
        total_params=70_000_000_000,
        context_window=131_072,
        tier="primary",
        providers=("groq", "openrouter"),
        price_in=0.59,
        price_out=0.79,
        note="free on Groq; general fallback",
    ),
    "openai/gpt-oss-20b": ModelEntry(
        id="openai/gpt-oss-20b",
        total_params=21_000_000_000,  # MoE total; 120b sibling is banned
        context_window=131_072,
        tier="utility",
        providers=("groq", "openrouter"),
        price_in=0.05,
        price_out=0.15,
    ),
    "qwen/qwen3-8b": ModelEntry(
        id="qwen/qwen3-8b",
        total_params=8_000_000_000,
        context_window=40_960,
        tier="utility",
        providers=("openrouter", "groq"),
    ),
    # NVIDIA NIM ids (build.nvidia.com) — distinct from OpenRouter slugs
    "nvidia/llama-3.1-nemotron-nano-8b-v1": ModelEntry(
        id="nvidia/llama-3.1-nemotron-nano-8b-v1",
        total_params=8_000_000_000,
        context_window=131_072,
        tier="utility",
        providers=("nim",),
        note="hosted NIM ping/utility model",
    ),
    "meta/llama-3.3-70b-instruct": ModelEntry(
        id="meta/llama-3.3-70b-instruct",
        total_params=70_000_000_000,
        context_window=131_072,
        tier="primary",
        providers=("nim",),
        note="NIM llama 3.3 (slug is meta/, not meta-llama/)",
    ),
    # local tier (Ollama) — must run comfortably on 16GB RAM / 8GB VRAM
    "qwen2.5-coder:7b-instruct": ModelEntry(
        id="qwen2.5-coder:7b-instruct",
        total_params=7_000_000_000,
        context_window=32_768,
        tier="local",
        providers=("ollama",),
        native_tools=True,
    ),
    "qwen3:8b": ModelEntry(
        id="qwen3:8b",
        total_params=8_000_000_000,
        context_window=40_960,
        tier="local",
        providers=("ollama",),
    ),
    # local embeddings / rerank (run in-process or via Ollama; CPU is fine)
    "qwen3-embedding-0.6b": ModelEntry(
        id="qwen3-embedding-0.6b",
        total_params=600_000_000,
        context_window=32_768,
        tier="embed",
        providers=("local",),
        native_tools=False,
    ),
    "qwen3-reranker-0.6b": ModelEntry(
        id="qwen3-reranker-0.6b",
        total_params=600_000_000,
        context_window=32_768,
        tier="rerank",
        providers=("local",),
        native_tools=False,
    ),
}

BANNED: dict[str, str] = {
    "qwen/qwen3-coder-480b-a35b-instruct": "480B total MoE — illegal even though only 35B active",
    "deepseek-ai/deepseek-v3": "671B total MoE",
    "deepseek-ai/deepseek-r1": "671B total MoE",
    "openai/gpt-oss-120b": "116.8B total MoE (20b sibling is legal)",
    "nvidia/nemotron-120b": ">80B total",
    "anthropic/claude-*": "closed weights, undisclosed size, subscription — all banned",
    "openai/gpt-5*": "closed weights, undisclosed size",
    "google/gemini-*": "closed weights, undisclosed size",
    "zai/glm-4.5-air": "106B total MoE — verify newer GLM cards before allowing any",
}

# providers with a free tier we route to first (cost -> 0); "local" = in-process/Ollama
FREE_PROVIDERS = ("ollama", "groq", "openrouter", "nim")
PAYG_PROVIDERS = ("mistral", "cerebras", "deepinfra", "fireworks", "together")


import fnmatch


def entry(model_id: str) -> ModelEntry | None:
    return MODELS.get(model_id)


def is_allowed(model_id: str, allow_custom: bool = False) -> tuple[bool, str]:
    """Returns (allowed, reason). A model must not be banned and within limits."""
    for pat, reason in BANNED.items():
        if fnmatch.fnmatch(model_id, pat) or model_id == pat:
            return False, f"banned: {reason}"
    m = MODELS.get(model_id)
    if m is None:
        if allow_custom:
            return True, "ok"
        return False, "not in catalog — add with published total params first"
    if m.total_params > MAX_TOTAL_PARAMS:
        return False, f"{m.total_params/1e9:.1f}B total > 80B cap"
    return True, "ok"


def models_for(provider: str, tier: str | None = None) -> list[ModelEntry]:
    out = [
        m
        for m in MODELS.values()
        if provider in m.providers and (tier is None or m.tier == tier)
    ]
    return sorted(out, key=lambda m: m.total_params)


def assert_catalog_compliance() -> None:
    """Fail fast at kernel startup if any catalog entry violates the cap."""
    for m in MODELS.values():
        if m.total_params > MAX_TOTAL_PARAMS:
            raise RuntimeError(f"catalog violation: {m.id} exceeds 80B total")
        if m.tier not in TIERS:
            raise RuntimeError(f"catalog violation: {m.id} unknown tier {m.tier}")
