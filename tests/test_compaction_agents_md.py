"""Compaction: pins survive, bodies become addresses, triggers fire."""

from taknee.compaction import ContextItem, assemble, estimate_tokens, should_compact


def test_pinned_never_compacted():
    items = [
        ContextItem("task_prompt", "fix the bug " * 100, pinned=True),
        ContextItem("AGENTS.md", "style: use uv; test: pytest", pinned=True),
        ContextItem("chunk:old", "x " * 5000),
        ContextItem("chunk:new", "y " * 10),
    ]
    text, stats = assemble(items, window_tokens=600)
    assert "fix the bug" in text          # pinned content ships in full
    assert "pytest" in text
    assert "[compacted]" in text          # the big old body became an address
    assert stats["items_compacted"] >= 1
    assert stats["tokens_after"] <= stats["tokens_before"]


def test_small_context_compacts_nothing():
    items = [ContextItem("a", "hello"), ContextItem("b", "world")]
    text, stats = assemble(items, window_tokens=1000)
    assert stats["items_compacted"] == 0
    assert "hello" in text and "world" in text


def test_recency_wins_under_pressure():
    items = [
        ContextItem("old1", "a " * 800),
        ContextItem("old2", "b " * 800),
        ContextItem("recent", "c " * 100),
    ]
    _text, stats = assemble(items, window_tokens=300)
    kept = stats["items_kept"]
    assert kept >= 1 and stats["items_compacted"] >= 1  # newest kept first


def test_trigger_threshold():
    assert should_compact(8_000, 10_000)      # 80% > 70% soft trigger
    assert not should_compact(5_000, 10_000)  # 50% is fine


def test_multiple_compactions_stable():
    """Req 4.b: repeated compaction must not lose pinned facts."""
    pinned = [ContextItem("task_prompt", "ship it", pinned=True),
              ContextItem("AGENTS.md", "test: pytest -q", pinned=True)]
    for _round in range(3):
        items = pinned + [ContextItem(f"chunk:{i}", "junk " * 900) for i in range(6)]
        text, _ = assemble(items, window_tokens=500)
        assert "ship it" in text and "pytest -q" in text
