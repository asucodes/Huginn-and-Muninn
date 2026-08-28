"""taknee setup — interactive first-run key registration wizard.

Guides users through:
  1. Detecting local Ollama and auto-registering it.
  2. Listing each free provider with sign-up URL and waiting for key paste.
  3. Validating each pasted key with a live test call.
  4. Saving keys to ~/.taknee/settings.json.
  5. Running taknee doctor to show the final health matrix.

Designed to be memorable and < 2 minutes from install to first task.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx

SETTINGS_FILE = Path.home() / ".taknee" / "settings.json"

FREE_PROVIDERS = [
    {
        "name": "groq",
        "label": "Groq Cloud",
        "signup_url": "https://console.groq.com",
        "free_offer": "30 RPM free — Llama 3.3 70B at 500 tokens/sec",
        "key_prefix": "gsk_",
    },
    {
        "name": "openrouter",
        "label": "OpenRouter",
        "signup_url": "https://openrouter.ai",
        "free_offer": "Free :free models including Qwen3 Coder 30B",
        "key_prefix": "sk-or-",
    },
    {
        "name": "gemini",
        "label": "Google AI Studio",
        "signup_url": "https://aistudio.google.com",
        "free_offer": "15 RPM free — Gemini 2.0 Flash with 1M context",
        "key_prefix": "AIza",
    },
]

BANNER = """
╔═══════════════════════════════════════════════════════════════╗
║     HUGINN & MUNINN — Free-Tier Compute Setup Wizard         ║
║     Configure your zero-cost AI providers in < 2 minutes     ║
╚═══════════════════════════════════════════════════════════════╝
"""


def _load_settings() -> dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {"providers": {}}


def _save_settings(cfg: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(cfg, indent=2))
    # Secure permissions on POSIX
    import os
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except Exception:
        pass


def _detect_ollama() -> bool:
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def _validate_key(provider: str, key: str) -> tuple[bool, str]:
    """Quick key validation — imported inline to avoid heavy provider startup."""
    try:
        from taknee import providers, settings as settings_mod
        cfg = {
            "providers": {provider: {"key": key}},
            "model": "llama-3.1-8b-instant" if provider == "groq" else None,
        }
        ok, msg = providers.test_key(provider, settings=cfg)
        return ok, msg
    except Exception as e:
        return False, str(e)


def run_setup() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print(BANNER)
    cfg = _load_settings()

    # ── Step 1: Detect Ollama ────────────────────────────────────────────────
    print("🔍 Checking for local Ollama...")
    if _detect_ollama():
        cfg.setdefault("providers", {})["ollama"] = {"enabled": True}
        _save_settings(cfg)
        print("✅ Ollama detected and registered as your offline fallback.")
    else:
        print("⚠️  Ollama not found. Install it free at https://ollama.ai for 100% offline fallback.")

    # ── Step 2: Register cloud free-tier providers ───────────────────────────
    print("\n🚀 Let's add your free cloud providers (skip any by pressing Enter).\n")

    for p in FREE_PROVIDERS:
        name = p["name"]
        label = p["label"]
        already = cfg.get("providers", {}).get(name, {}).get("key", "")
        if already:
            print(f"  ✓ {label} already configured.")
            continue

        print(f"  ┌─ {label}")
        print(f"  │  Offer: {p['free_offer']}")
        print(f"  │  Sign up FREE at: {p['signup_url']}")
        print(f"  └─ Paste your API key (or press Enter to skip): ", end="", flush=True)
        try:
            key = input().strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not key:
            print(f"     Skipped {label}.")
            continue

        print(f"     Validating key... ", end="", flush=True)
        ok, msg = _validate_key(name, key)
        if ok:
            cfg.setdefault("providers", {})[name] = {"key": key}
            _save_settings(cfg)
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
            print(f"     Key not saved. Try again with: taknee setup")

    # ── Step 3: Doctor summary ───────────────────────────────────────────────
    print("\n📊 Provider Health Matrix:\n")
    run_doctor(cfg)
    print("\n✨ Setup complete! Run `taknee` to start coding for free.\n")


def run_doctor(cfg: dict[str, Any] | None = None) -> None:
    """Show live health status of all configured providers."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if cfg is None:
        cfg = _load_settings()

    from taknee.swarm.radar import Radar
    from taknee.swarm.rotator import SwarmRotator
    radar = Radar()
    rotator = SwarmRotator(radar=radar)
    rotator.register_keys_from_dict(cfg)

    providers_cfg = cfg.get("providers", {})
    rows = []
    for p_name in ["groq", "openrouter", "gemini", "ollama"]:
        health = radar.check_provider_health(p_name)
        key_set = bool(providers_cfg.get(p_name, {}).get("key") or p_name == "ollama")
        models = [m for m in radar.get_free_models() if m.provider == p_name]
        status_icon = "🟢" if (health.healthy and key_set) else ("🟡" if key_set else "⚪")
        rows.append(f"  {status_icon} {p_name:<15} {len(models)} free models   {'[key set]' if key_set else '[no key]'}")
    print("\n".join(rows))


if __name__ == "__main__":
    run_setup()
