"""Store: tasks, spans, events, approvals round-trip."""

import time

from taknee.store import Store


def make_store(tmp_path):
    return Store(tmp_path / ".taknee" / "taknee.db")


def test_task_lifecycle(tmp_path):
    s = make_store(tmp_path)
    tid = s.create_task("fix the login bug", "/repo")
    t = s.get_task(tid)
    assert t["prompt"] == "fix the login bug"
    assert t["status"] == "created"

    s.update_task(tid, status="running", stage="localize")
    assert s.get_task(tid)["stage"] == "localize"

    s.add_usage(tid, tokens_in=100, tokens_out=50, usd=0.01)
    t = s.get_task(tid)
    assert (t["tokens_in"], t["tokens_out"], round(t["usd"], 4)) == (100, 50, 0.01)


def test_followup_runs_share_thread_but_keep_display_prompt(tmp_path):
    s = make_store(tmp_path)
    first = s.create_task("build a tutorial", "/repo")
    second = s.create_task(
        "internal continuation context", "/repo", display_prompt="add exercises",
        thread_id=first, parent_task_id=first,
    )
    s.add_message(first, "user", "build a tutorial")
    s.add_message(second, "user", "add exercises")
    task = s.get_task(second)
    assert task["display_prompt"] == "add exercises"
    assert task["thread_id"] == first
    assert [m["content"] for m in s.messages_for_thread(second)] == [
        "build a tutorial", "add exercises"
    ]


def test_spans_roundtrip_with_json(tmp_path):
    s = make_store(tmp_path)
    tid = s.create_task("t", "/r")
    parent = s.add_span(tid, "stage", "patch")
    child = s.add_span(
        tid, "llm", "patch", parent_id=parent,
        model="qwen/x", provider="groq", route_reason="cheapest healthy",
        input_data={"messages": ["..."]}, output_data={"content": "ok"},
        tokens_in=10, tokens_out=5, usd=0.001,
    )
    s.end_span(child, {"content": "final"})
    spans = s.spans_for_task(tid)
    assert len(spans) == 2
    assert spans[1]["parent_id"] == parent
    assert spans[1]["output"]["content"] == "final"  # decoded from JSON


def test_events_and_approvals(tmp_path):
    s = make_store(tmp_path)
    tid = s.create_task("t", "/r")
    s.add_event(tid, "compaction", {"items_compacted": 3})
    compaction = [e for e in s.events_for_task(tid) if e["type"] == "compaction"][0]
    assert compaction["payload"]["items_compacted"] == 3

    aid = s.add_approval(tid, "patch", [{"file": "a.py"}])
    assert s.get_approval(aid)["decision"] == "pending"
    pending = s.pending_approvals()
    assert pending and pending[0]["payload"] == [{"file": "a.py"}]
    s.resolve_approval(aid, "partial", rejected=["fp1"])
    ap = s.get_approval(aid)
    assert ap["decision"] == "partial" and ap["rejected"] == ["fp1"]
    assert s.pending_approvals() == []


def test_wal_survives_reopen(tmp_path):
    db = tmp_path / ".taknee" / "taknee.db"
    s = Store(db)
    tid = s.create_task("persist me", "/r")
    s.close()

    s2 = Store(db)  # crash-safe reopen
    assert s2.get_task(tid)["prompt"] == "persist me"
