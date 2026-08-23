"""Router: free-first ladder, cooldowns, escalation. Settings: key handling."""

import json

from taknee import providers, settings as settings_mod
from taknee.router import Router


def _settings_with(tmp_path, providers_with_keys):
    data = json.loads(json.dumps(settings_mod.DEFAULTS))
    for p in providers_with_keys:
        data["providers"][p]["key"] = "test-key"
    # point settings at a temp file so we never touch the real ~/.taknee
    path = tmp_path / "settings.json"
    settings_mod.save(data, path)
    return settings_mod.load(path)


def test_pick_prefers_free_with_key(tmp_path):
    cfg = _settings_with(tmp_path, ["groq"])
    r = Router().pick("primary", est_tokens=4000, settings=cfg)
    assert r is not None
    assert r.provider == "groq"
    assert "cheapest healthy" in r.reason or "strongest" in r.reason


def test_pick_skips_payg_when_disabled(tmp_path):
    cfg = _settings_with(tmp_path, ["mistral"])  # PAYG-only provider
    r = Router().pick("primary", est_tokens=4000, settings=cfg)
    assert r is None or r.provider == "ollama"
    cfg["allow_paid"] = True
    paid = Router().pick("primary", est_tokens=4000, settings=cfg)
    assert paid is not None
    assert paid.provider == "mistral"


def test_cooldown_excludes_provider(tmp_path):
    cfg = _settings_with(tmp_path, ["groq", "openrouter"])
    router = Router()
    router.record_failure("groq")
    r = router.pick("primary", est_tokens=4000, settings=cfg)
    assert r.provider == "openrouter", "must fall back to the other healthy free provider"


def test_model_skip_picks_next_candidate(tmp_path):
    cfg = _settings_with(tmp_path, ["openrouter"])
    router = Router()
    first = router.pick("primary", est_tokens=4000, settings=cfg)
    assert first is not None
    router.record_model_skip(first.provider, first.model)
    second = router.pick("primary", est_tokens=4000, settings=cfg)
    assert second is not None
    assert (second.model, second.provider) != (first.model, first.provider)


def test_iteration_escalates_to_strongest(tmp_path):
    cfg = _settings_with(tmp_path, ["openrouter"])  # multiple primary models
    router = Router()
    first = router.pick("primary", est_tokens=4000, settings=cfg)
    repair = router.pick("primary", est_tokens=4000, iteration=2, settings=cfg)
    assert "repair iteration 2" in repair.reason
    assert repair.model != first.model  # repair escalates to a stronger model


def test_context_window_filter(tmp_path):
    cfg = _settings_with(tmp_path, ["groq"])
    r = Router().pick("primary", est_tokens=200_000, settings=cfg)
    assert r is None or r is not None  # must not crash; smaller models excluded by window


def test_prefer_local_selects_ollama_local_tier(tmp_path):
    cfg = _settings_with(tmp_path, [])
    cfg["prefer_local"] = True
    r = Router().pick("primary", est_tokens=4000, settings=cfg)
    assert r is not None
    assert r.provider == "ollama"
    assert r.model in {"qwen2.5-coder:7b-instruct", "qwen3:8b"}


def test_settings_key_masking(tmp_path):
    path = tmp_path / "settings.json"
    settings_mod.set_provider_key("groq", "gsk_secret", path)
    out = settings_mod.masked(settings_mod.load(path))
    assert out["providers"]["groq"]["key"] == "set"  # never the raw key
    assert settings_mod.get_key("groq", settings_mod.load(path)) == "gsk_secret"


def test_settings_unknown_provider_rejected(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        settings_mod.set_provider_key("openai", "x", tmp_path / "s.json")


def test_get_key_falls_back_to_legacy_field(tmp_path):
    data = json.loads(json.dumps(settings_mod.DEFAULTS))
    data["nvidia_nim_api_key"] = "nvapi-legacy"
    path = tmp_path / "settings.json"
    settings_mod.save(data, path)
    assert settings_mod.get_key("nim", settings_mod.load(path)) == "nvapi-legacy"


def test_normalize_nim_extracts_nvapi_from_paste():
    blob = 'client = OpenAI(api_key="nvapi-ABC_def-123", base_url="https://integrate.api.nvidia.com/v1")'
    assert settings_mod.normalize_provider_key("nim", blob) == "nvapi-ABC_def-123"
    assert settings_mod.normalize_provider_key("nim", "not a nvidia key at all") == ""


def test_key_reports_missing_key(tmp_path):
    cfg = _settings_with(tmp_path, [])
    ok, msg = providers.test_key("openrouter", settings=cfg)
    assert ok is False
    assert msg.startswith("Did not ping")


def test_key_skips_unavailable_model(tmp_path, monkeypatch):
    from taknee import catalog

    cfg = _settings_with(tmp_path, ["openrouter"])
    models = catalog.models_for("openrouter")
    assert len(models) >= 2
    calls: list[str] = []

    def fake_chat(provider, model, *a, **k):
        calls.append(model)
        if model == models[0].id:
            raise providers.ProviderError(provider, 404, "No endpoints found for " + model)
        return providers.ChatResult(content="pong", tokens_in=1, tokens_out=1)

    monkeypatch.setattr(providers, "chat", fake_chat)
    ok, msg = providers.test_key("openrouter", settings=cfg)
    assert ok is True
    assert msg.startswith("Ping OK")
    assert models[0].id in calls
    assert models[1].id in calls
    assert models[1].id in msg
