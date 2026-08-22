"""Catalog compliance: every allowed model must be <=80B total params."""

import pytest

from taknee import catalog


def test_all_models_within_cap():
    for m in catalog.MODELS.values():
        assert m.total_params <= catalog.MAX_TOTAL_PARAMS, m.id


def test_compliance_passes():
    catalog.assert_catalog_compliance()


def test_banned_models_refused():
    for model in ("qwen/qwen3-coder-480b-a35b-instruct", "deepseek-ai/deepseek-v3",
                  "openai/gpt-oss-120b", "nvidia/nemotron-120b"):
        ok, reason = catalog.is_allowed(model)
        assert not ok, model
        assert "banned" in reason


def test_unknown_model_refused():
    ok, reason = catalog.is_allowed("some/random-model")
    assert not ok
    assert "catalog" in reason


def test_moe_counts_total_not_active():
    m = catalog.MODELS["qwen/qwen3-coder-30b-a3b-instruct"]
    assert m.total_params > 30_000_000_000  # 30.5B TOTAL, not the 3B active


def test_models_for_provider():
    groq = catalog.models_for("groq")
    assert groq, "Groq must have at least one model"
    assert all("groq" in m.providers for m in groq)


def test_nim_has_hosted_models():
    nim = catalog.models_for("nim")
    assert nim, "NVIDIA NIM must have at least one catalog model"
    assert all("nim" in m.providers for m in nim)
    ids = {m.id for m in nim}
    assert "meta/llama-3.3-70b-instruct" in ids
    assert "qwen/qwen2.5-coder-32b-instruct" not in ids  # retired by NIM
    assert "qwen/qwen3-4b" not in catalog.MODELS


def test_local_tier_fits_16gb_budget():
    for m in catalog.models_for("ollama"):
        assert m.total_params <= 9_000_000_000, "local tier must fit 8GB VRAM Q4"
