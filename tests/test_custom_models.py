"""Tests for user-customizable models and live model discovery."""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from taknee import api, catalog, providers, settings as settings_mod


def _reset():
    api._state.update({"workspace": None, "store": None, "orchestrators": {}, "v2_rotator": None})


class TestCustomModelSettings:
    def test_save_and_retrieve_custom_model(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_mod.set_provider_config("groq", key="gsk_test123", model="custom-groq-model-1", path=settings_file)
        
        cfg = settings_mod.load(settings_file)
        assert cfg["providers"]["groq"]["key"] == "gsk_test123"
        assert cfg["providers"]["groq"]["model"] == "custom-groq-model-1"
        assert settings_mod.get_provider_model("groq", cfg) == "custom-groq-model-1"

        # Masked view preserves model name
        m = settings_mod.masked(cfg)
        assert m["providers"]["groq"]["key"] == "set"
        assert m["providers"]["groq"]["model"] == "custom-groq-model-1"

    def test_catalog_allows_custom_unbanned_model(self):
        ok, msg = catalog.is_allowed("my-custom-fine-tuned-model-v2", allow_custom=True)
        assert ok is True

        banned_ok, _ = catalog.is_allowed("anthropic/claude-3-7-sonnet", allow_custom=True)
        assert banned_ok is False


class TestProviderCustomModelExecution:
    def test_test_key_uses_custom_model(self, tmp_path):
        cfg = {
            "providers": {
                "groq": {"key": "gsk_testkey123", "model": "my-special-model"}
            }
        }
        mock_result = providers.ChatResult(content="pong", tokens_in=5, tokens_out=5, usd=0.0)
        with patch("taknee.providers.chat", return_value=mock_result) as mock_chat:
            ok, msg = providers.test_key("groq", settings=cfg)
            assert ok is True
            assert "my-special-model" in msg
            # Verify chat was called with the custom model
            mock_chat.assert_called_once()
            assert mock_chat.call_args[0][1] == "my-special-model"


class TestModelsEndpoint:
    def test_get_provider_models_endpoint(self):
        _reset()
        client = TestClient(api.app)
        with patch("taknee.providers.fetch_live_models", return_value=["model-a", "model-b"]):
            r = client.get("/settings/providers/groq/models")
            assert r.status_code == 200
            data = r.json()
            assert data["provider"] == "groq"
            assert "model-a" in data["models"]

    def test_set_provider_config_endpoint(self, tmp_path):
        _reset()
        client = TestClient(api.app)
        r = client.post("/settings/providers/groq/config", json={"key": "gsk_live123", "model": "llama-3.1-8b-instant"})
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "groq"
        assert data["saved"] is True
        assert data["model"] == "llama-3.1-8b-instant"
