"""Settings + API key storage.

Keys are written by the Settings screen (extension) into ~/.taknee/settings.json.
Keys are never logged and never returned in full by the API (see masked()).
0600 perms are applied where the OS supports them.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

SETTINGS_DIR = Path.home() / ".taknee"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

PROVIDERS = ("groq", "openrouter", "nim", "mistral", "cerebras", "deepinfra")
_LEGACY_KEY_FIELDS = {
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "nim": "nvidia_nim_api_key",
}

_KEY_PATTERNS = {
    "nim": re.compile(r"nvapi-[A-Za-z0-9_-]+"),
    "openrouter": re.compile(r"sk-or-v1-[A-Za-z0-9]+"),
    "groq": re.compile(r"gsk_[A-Za-z0-9]+"),
}

PROVIDER_LABELS = {
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "nim": "NVIDIA NIM",
    "mistral": "Mistral",
    "cerebras": "Cerebras",
    "deepinfra": "DeepInfra",
    "ollama": "Ollama",
}


def normalize_provider_key(provider: str, raw: str) -> str:
    """Pull a real key out of a paste (snippet, quotes, extra whitespace)."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return ""
    pat = _KEY_PATTERNS.get(provider)
    if pat:
        m = pat.search(text)
        if m:
            return m.group(0)
        if provider in _KEY_PATTERNS:
            return ""
    line = text.splitlines()[0].strip().strip('"').strip("'")
    if not line or any(c.isspace() for c in line) or len(line) > 512:
        return ""
    return line

DEFAULTS: dict[str, Any] = {
    "providers": {p: {"key": ""} for p in PROVIDERS},
    "ollama_base_url": "http://127.0.0.1:11434/v1",
    "allow_paid": False,  # PAYG providers only used when explicitly enabled
    "prefer_local": False,
    "caps": {
        "max_seconds": 2400.0,  # margin under the 2700s eval ceiling
        "max_usd": 0.40,        # margin under the $0.50 eval ceiling
        "max_steps": 120,
        "max_llm_calls": 200,
        "fingerprint_limit": 3,  # same (stage,fingerprint) repeated N times = stuck
        "empty_patch_limit": 3,
    },
}


def load(path: Path | None = None) -> dict[str, Any]:
    p = path or SETTINGS_PATH
    data = json.loads(json.dumps(DEFAULTS))  # deep copy
    if p.exists():
        try:
            stored = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return data
        _merge(data, stored)
    return data


def save(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or SETTINGS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:  # POSIX best effort; Windows ignores this
        os.chmod(p, 0o600)
    except OSError:
        pass


def set_provider_key(provider: str, key: str, path: Path | None = None) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    data = load(path)
    data["providers"][provider]["key"] = normalize_provider_key(provider, key)
    save(data, path)
    return data


def get_key(provider: str, data: dict[str, Any] | None = None) -> str:
    data = data if data is not None else load()
    if provider == "ollama":
        return "ollama"  # local, no key
    nested = data.get("providers", {}).get(provider, {}).get("key", "")
    if nested:
        return nested
    return (data.get(_LEGACY_KEY_FIELDS.get(provider, ""), "") or "").strip()


def has_key(provider: str, data: dict[str, Any] | None = None) -> bool:
    if provider == "ollama":
        return True
    return bool(get_key(provider, data))


def masked(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """View of settings safe to return to the UI: keys become 'set'/'', never raw."""
    data = data if data is not None else load()
    out = json.loads(json.dumps(data))
    for name, entry in out.get("providers", {}).items():
        entry["key"] = "set" if entry.get("key") else ""
    return out


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> None:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
