"""Kernel HTTP API smoke tests (no provider keys, no network)."""

from fastapi.testclient import TestClient

from taknee import api


def _reset():
    api._state.update({"workspace": None, "store": None, "orchestrators": {}, "v2_rotator": None})


def test_health_ok():
    _reset()
    r = TestClient(api.app).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["catalog_compliant"] is True


def test_lists_empty_without_workspace():
    _reset()
    c = TestClient(api.app)
    assert c.get("/tasks").json() == []
    assert c.get("/approvals").json() == []


def test_workspace_then_empty_tasks(tmp_path):
    _reset()
    c = TestClient(api.app)
    r = c.post("/workspace", json={"path": str(tmp_path)})
    assert r.status_code == 200
    assert c.get("/tasks").json() == []
    assert c.get("/approvals").json() == []
    _reset()


def test_bytheway_requires_workspace():
    _reset()
    r = TestClient(api.app).post("/bytheway", json={"question": "where is greet?"})
    assert r.status_code == 400


def test_console_page():
    r = TestClient(api.app).get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Huginn" in r.text and "Muninn" in r.text
    # chat shell + composer markers for the conversation view
    assert "Message Huginn" in r.text
    assert "Run details" in r.text


def test_tools_list_includes_read_and_write():
    _reset()
    r = TestClient(api.app).get("/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert "read_file" in names
    assert "write_file" in names
    write = next(t for t in r.json()["tools"] if t["name"] == "write_file")
    assert write["side_effect"] is True


def test_tool_call_requires_workspace():
    _reset()
    r = TestClient(api.app).post("/tools", json={"name": "list_files", "arguments": {}})
    assert r.status_code == 400


def test_tool_call_list_files(tmp_path):
    _reset()
    c = TestClient(api.app)
    assert c.post("/workspace", json={"path": str(tmp_path)}).status_code == 200
    (tmp_path / "hello.txt").write_text("hi", encoding="utf-8")
    r = c.post("/tools", json={"name": "list_files", "arguments": {"path": "."}})
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is False
    assert "hello.txt" in body["output"]
    _reset()


def test_side_effect_blocked_without_approval(tmp_path):
    _reset()
    c = TestClient(api.app)
    c.post("/workspace", json={"path": str(tmp_path)})
    r = c.post(
        "/tools",
        json={"name": "write_file", "arguments": {"file_path": "x.txt", "content": "no"}},
    )
    assert r.status_code == 200
    assert r.json()["blocked"] is True
    assert not (tmp_path / "x.txt").exists()
    _reset()


def test_status_message_replies_without_starting_new_run(tmp_path):
    _reset()
    c = TestClient(api.app)
    c.post("/workspace", json={"path": str(tmp_path)})
    store = api._store()
    tid = store.create_task("build a tutorial", str(tmp_path))
    store.add_message(tid, "user", "build a tutorial")
    store.update_task(tid, status="running", stage="patch")
    before = len(store.list_tasks())
    r = c.post(f"/tasks/{tid}/messages", json={"message": "what is the status?"})
    assert r.status_code == 200
    assert r.json()["kind"] == "reply"
    assert "patch" in r.json()["message"]
    assert len(store.list_tasks()) == before
    _reset()


def test_question_message_answers_in_thread_without_new_run(tmp_path, monkeypatch):
    """Questions must be answered by one LLM call, never the patch pipeline."""
    _reset()
    c = TestClient(api.app)
    c.post("/workspace", json={"path": str(tmp_path)})
    store = api._store()
    tid = store.create_task("create me a python tutorial", str(tmp_path))
    store.add_message(tid, "user", "create me a python tutorial")
    store.update_task(tid, status="done", stage="done")
    before = len(store.list_tasks())

    class _Route:
        model, provider, reason, tier = "m", "groq", "test", "utility"

    class _Router:
        def pick(self, *a, **k):
            return _Route()

    def fake_chat(provider, model, messages, **k):
        class R:
            content = "We made tutorial.md and exercises.py."
            tokens_in, tokens_out, usd = 10, 5, 0.0
        return R()

    monkeypatch.setattr(api, "Router", _Router)
    monkeypatch.setattr(api.providers, "chat", fake_chat)

    r = c.post(f"/tasks/{tid}/messages", json={"message": "what things did we make here"})
    assert r.status_code == 200
    assert r.json()["kind"] == "reply"
    assert "tutorial.md" in r.json()["message"]
    # answered in place: no new task, and the transcript has both turns
    assert len(store.list_tasks()) == before
    roles = [m["role"] for m in store.messages_for_thread(tid)][-2:]
    assert roles == ["user", "assistant"]
    _reset()


def test_imperative_message_still_becomes_followup(tmp_path):
    _reset()
    c = TestClient(api.app)
    c.post("/workspace", json={"path": str(tmp_path)})
    store = api._store()
    tid = store.create_task("create a pass manager", str(tmp_path))
    store.update_task(tid, status="done", stage="done")
    r = c.post(f"/tasks/{tid}/messages", json={"message": "now add tests for it"})
    assert r.status_code == 200
    assert r.json() == {"kind": "followup", "task_id": tid}
    _reset()


def test_task_api_exposes_display_prompt(tmp_path):
    _reset()
    c = TestClient(api.app)
    c.post("/workspace", json={"path": str(tmp_path)})
    store = api._store()
    tid = store.create_task("internal context", str(tmp_path), display_prompt="add exercises")
    assert c.get(f"/tasks/{tid}").json()["display_prompt"] == "add exercises"
    _reset()


def test_radar_models_endpoint():
    c = TestClient(api.app)
    r = c.get("/radar/models")
    assert r.status_code == 200
    data = r.json()
    assert "models" in data
    assert data["count"] >= 4
    model_ids = [m["id"] for m in data["models"]]
    assert any("groq" in m["provider"] for m in data["models"])


def test_radar_status_endpoint():
    c = TestClient(api.app)
    r = c.get("/radar/status")
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert len(data["providers"]) >= 4
    prov_names = {p["provider"] for p in data["providers"]}
    assert "groq" in prov_names
    assert "openrouter" in prov_names


def test_radar_deals_endpoint():
    c = TestClient(api.app)
    r = c.get("/radar/deals")
    assert r.status_code == 200
    data = r.json()
    assert "deals" in data

