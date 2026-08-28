"""Unit tests for Taknee V2 Swarm Radar, Rotator, and Prompt Cache Packer."""

import pytest
from unittest.mock import MagicMock
import httpx

from taknee.swarm.radar import Radar, FreeModel, VERIFIED_FREE_MODELS
from taknee.swarm.rotator import SwarmRotator, KeyPool
from taknee.swarm.cache_optimizer import PromptCachePacker


class TestRadar:
    def test_verified_models_available_offline(self):
        radar = Radar(cache_ttl_s=3600.0)
        models = radar.get_free_models()
        assert len(models) >= len(VERIFIED_FREE_MODELS)
        providers = {m.provider for m in models}
        assert "openrouter" in providers
        assert "groq" in providers
        assert "ollama" in providers

    def test_provider_health_check_and_cooldown(self):
        radar = Radar()
        status_ok = radar.check_provider_health("groq")
        assert status_ok.healthy is True
        assert status_ok.active_rate_limit is False

        # Record a 30s cooldown
        radar.record_cooldown("groq", duration_s=30.0)
        status_cooling = radar.check_provider_health("groq")
        assert status_cooling.healthy is False
        assert status_cooling.active_rate_limit is True
        assert status_cooling.cooldown_remaining_s > 0

        # Clear cooldown
        radar.clear_cooldown("groq")
        status_recovered = radar.check_provider_health("groq")
        assert status_recovered.healthy is True

    def test_openrouter_probe_parser(self):
        radar = Radar()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "qwen/qwen3-coder:free",
                    "name": "Qwen 3 Coder Free",
                    "context_length": 262144,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "openai/gpt-4o",
                    "name": "GPT-4o Paid",
                    "context_length": 128000,
                    "pricing": {"prompt": "0.000005", "completion": "0.000015"},
                },
            ]
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        free_models = radar._probe_openrouter(mock_client)
        assert len(free_models) == 1
        assert free_models[0].id == "qwen/qwen3-coder:free"
        assert free_models[0].is_free is True


class TestSwarmRotator:
    def test_key_pool_round_robin_and_rate_limiting(self):
        pool = KeyPool(provider="groq")
        pool.add_key("gsk_key_1", label="key1")
        pool.add_key("gsk_key_2", label="key2")

        # Initial calls should rotate between key 1 and 2
        k1 = pool.get_healthy_key()
        k2 = pool.get_healthy_key()
        assert k1 == "gsk_key_1"
        assert k2 == "gsk_key_2"

        # Rate-limit key 1
        pool.record_rate_limit("gsk_key_1", cooldown_s=60.0)
        # Next call should strictly return key 2
        assert pool.get_healthy_key() == "gsk_key_2"
        assert pool.get_healthy_key() == "gsk_key_2"

    def test_rotator_failover_across_providers(self):
        rotator = SwarmRotator()
        rotator.register_key("groq", "gsk_groq_test")
        rotator.register_key("openrouter", "sk-or-v1-test")

        # 1. First choice should be fast Groq
        route1 = rotator.pick_route(tier="primary")
        assert route1 is not None
        assert route1.provider == "groq"
        assert route1.api_key == "gsk_groq_test"

        # 2. Simulate 429 on Groq
        rotator.record_429("groq", "gsk_groq_test", retry_after=30.0)

        # 3. Next route must instantly failover to OpenRouter without throwing an error
        route2 = rotator.pick_route(tier="primary")
        assert route2 is not None
        assert route2.provider == "openrouter"
        assert route2.api_key == "sk-or-v1-test"

    def test_rotator_offline_ollama_fallback(self):
        rotator = SwarmRotator()
        # No cloud keys registered -> must fallback to local Ollama
        route = rotator.pick_route(tier="primary")
        assert route is not None
        assert route.provider == "ollama"
        assert route.is_local is True


class TestPromptCachePacker:
    def test_deterministic_prefix_hash(self):
        packer = PromptCachePacker()
        system_prompt = "You are Huginn, a sovereign coding agent."
        rules = "test: uv run pytest\nstyle: ruff"
        repo_map = "src/taknee/router.py: pick_route\nsrc/taknee/store.py: Store"

        # Turn 1
        turn1 = packer.pack(
            system_instruction=system_prompt,
            project_rules=rules,
            repo_map=repo_map,
            conversation_history=[],
            current_scratchpad="Implement test 1",
        )

        # Turn 2 (scratchpad changes, prefix stays identical)
        turn2 = packer.pack(
            system_instruction=system_prompt,
            project_rules=rules,
            repo_map=repo_map,
            conversation_history=[{"role": "user", "content": "Implement test 1"}],
            current_scratchpad="Implement test 2",
        )

        # Prefix hashes MUST match to guarantee prompt caching
        assert turn1.prefix_hash == turn2.prefix_hash
        assert turn1.cacheable_tokens > 0
        assert len(turn1.messages) >= 2
