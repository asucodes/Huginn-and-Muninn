"""Provider adapters — one call path for every provider.

Transport: LiteLLM (MIT) when installed — the standard OpenAI-compatible
multi-provider library, so we don't hand-maintain N provider quirks. A thin
raw-httpx fallback keeps the kernel runnable without it. On top of the
transport, OUR rules always apply:
  - every model id is validated against catalog.py before any request
  - 429 raises RateLimited -> router cools the provider down and falls back
  - usage returns with every call so cost accounting is exact
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import catalog, settings as settings_mod

try:  # optional transport — imported lazily; litellm's import is slow (~30s+)
    litellm = None  # sentinel; real import happens on first call

    def _get_litellm():
        global litellm
        if litellm is None:
            import litellm as _lm  # type: ignore
            litellm = _lm
        return litellm
except ImportError:  # pragma: no cover
    _get_litellm = None

ENDPOINTS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "nim": "https://integrate.api.nvidia.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "together": "https://api.together.xyz/v1",
}

# litellm's provider prefix for each of our provider names
LITELLM_PREFIX = {
    "groq": "groq/",
    "openrouter": "openrouter/",
    "nim": "nvidia_nim/",
    "mistral": "mistral/",
    "cerebras": "cerebras/",
    "deepinfra": "deepinfra/",
    "together": "together_ai/",
    "ollama": "ollama/",
}

# OpenRouter asks for these; some keys 404 without a referer.
EXTRA_HEADERS = {
    "openrouter": {
        "HTTP-Referer": "https://github.com/taknee",
        "X-Title": "Huginn & Muninn",
    },
}

_UNAVAILABLE = ("no endpoints", "not found", "does not exist", "unknown model", "model_not_found")


class ProviderError(Exception):
    def __init__(self, provider: str, status: int, message: str):
        super().__init__(f"[{provider}] HTTP {status}: {message}")
        self.provider = provider
        self.status = status


class RateLimited(ProviderError):
    def __init__(self, provider: str, retry_after: float | None):
        super().__init__(provider, 429, f"rate limited (retry-after={retry_after})")
        self.retry_after = retry_after


@dataclass
class ChatResult:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    raw: Any = None


def _base_url(provider: str, cfg: dict[str, Any]) -> str:
    if provider == "ollama":
        return cfg.get("ollama_base_url", "http://127.0.0.1:11434/v1")
    if provider not in ENDPOINTS:
        raise ProviderError(provider, 0, "unknown provider")
    return ENDPOINTS[provider]


def chat(
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout: float = 120.0,
    settings: dict[str, Any] | None = None,
    client: httpx.Client | None = None,
    transport: str = "auto",
) -> ChatResult:
    """One chat completion. Raises ProviderError/RateLimited; never retries."""
    allowed, reason = catalog.is_allowed(model)
    if not allowed:
        raise ProviderError(provider, 0, f"model refused by catalog: {reason}")

    cfg = settings if settings is not None else settings_mod.load()
    key = settings_mod.get_key(provider, cfg)
    entry = catalog.entry(model)
    price_in = entry.price_in if entry else 0.0
    price_out = entry.price_out if entry else 0.0

    if transport != "httpx" and _get_litellm is not None:
        try:
            return _chat_litellm(
                provider, model, messages, key, tools, temperature, max_tokens, timeout,
                price_in, price_out, cfg,
            )
        except ImportError:  # litellm listed but not installed — fall through
            pass
    return _chat_httpx(
        provider, model, messages, key, tools, temperature, max_tokens, timeout,
        price_in, price_out, cfg, client,
    )


def _chat_litellm(provider, model, messages, key, tools, temperature, max_tokens,
                  timeout, price_in, price_out, cfg) -> ChatResult:
    litellm = _get_litellm()
    try:
        extra = EXTRA_HEADERS.get(provider)
        resp = litellm.completion(
            model=f"{LITELLM_PREFIX.get(provider, '')}{model}",
            messages=messages,
            temperature=temperature,
            tools=tools,
            max_tokens=max_tokens,
            timeout=timeout,
            api_key=key or None,
            base_url=cfg.get("ollama_base_url") if provider == "ollama" else None,
            extra_headers=extra,
            drop_params=True,  # providers differ; catalog gates what matters
        )
    except Exception as e:  # litellm raises many shapes; normalize
        name = type(e).__name__
        if "RateLimit" in name:
            raise RateLimited(provider, None) from e
        raise ProviderError(provider, 0, f"{name}: {e}") from e
    usage = getattr(resp, "usage", None)
    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    msg = resp.choices[0].message if resp.choices else None
    return ChatResult(
        content=getattr(msg, "content", "") or "",
        tool_calls=[tc.model_dump() for tc in getattr(msg, "tool_calls", []) or []],
        tokens_in=int(tokens_in),
        tokens_out=int(tokens_out),
        usd=(int(tokens_in) / 1e6) * price_in + (int(tokens_out) / 1e6) * price_out,
        raw=resp,
    )


def _chat_httpx(provider, model, messages, key, tools, temperature, max_tokens,
                timeout, price_in, price_out, cfg, client) -> ChatResult:
    base = _base_url(provider, cfg)
    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
    if max_tokens:
        payload["max_tokens"] = max_tokens

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    headers.update(EXTRA_HEADERS.get(provider, {}))
    own = client is None
    c = client or httpx.Client(timeout=timeout)
    try:
        resp = c.post(f"{base}/chat/completions", json=payload, headers=headers)
    finally:
        if own:
            c.close()

    if resp.status_code == 429:
        ra = resp.headers.get("retry-after")
        raise RateLimited(provider, float(ra) if ra and ra.replace(".", "").isdigit() else None)
    if resp.status_code >= 400:
        raise ProviderError(provider, resp.status_code, resp.text[:500])

    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}
    tokens_in = int(usage.get("prompt_tokens") or 0)
    tokens_out = int(usage.get("completion_tokens") or 0)
    return ChatResult(
        content=message.get("content") or "",
        tool_calls=message.get("tool_calls") or [],
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        usd=(tokens_in / 1e6) * price_in + (tokens_out / 1e6) * price_out,
        raw=data,
    )


def _unavailable(err: ProviderError) -> bool:
    msg = str(err).lower()
    if err.status in (404, 400) and any(s in msg for s in _UNAVAILABLE):
        return True
    return err.status in (0, 404) and any(s in msg for s in _UNAVAILABLE)


def test_key(provider: str, settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Cheap connectivity/key check used by the Settings screen.

    Messages always say whether the provider was actually pinged.
    """
    label = settings_mod.PROVIDER_LABELS.get(provider, provider)
    cfg = settings if settings is not None else settings_mod.load()
    if not settings_mod.has_key(provider, cfg):
        hint = "NVIDIA keys start with nvapi-" if provider == "nim" else "paste the key into the box"
        return False, f"Did not ping {label}. No API key is saved ({hint})."
    models = catalog.models_for(provider)
    if not models:
        return False, f"Did not ping {label}. No catalog models for {provider}."
    last = "no model responded"
    tried: list[str] = []
    for m in models:
        tried.append(m.id)
        try:
            result = chat(
                provider, m.id,
                [{"role": "user", "content": "ping"}],
                max_tokens=4, timeout=20, settings=cfg, transport="httpx",
            )
            n = result.tokens_in + result.tokens_out
            return True, f"Ping OK - {label} responded via {m.id} ({n} tokens)."
        except RateLimited:
            return True, f"Ping OK - {label} key is valid (rate limited on {m.id})."
        except ProviderError as e:
            last = str(e)
            if e.status in (401, 403):
                return False, f"Ping failed - {label} HTTP {e.status} (invalid or expired key) on {m.id}."
            if _unavailable(e):
                continue
            code = e.status or "error"
            return False, f"Ping failed - {label} HTTP {code} on {m.id}: {e}"
        except httpx.HTTPError as e:
            return False, f"Ping failed - {label} network error: {e}"
    return False, (
        f"Ping failed - {label} key was sent but no live model answered "
        f"(tried {', '.join(tried)}). Last error: {last}"
    )


def now() -> float:
    return time.time()
