"""Kernel HTTP API — loopback only (127.0.0.1), consumed by the extension.

The extension never talks to providers and never holds keys in its own
storage; it posts them here. Keys are never echoed back (settings.masked()).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import __version__, catalog, plugins, providers, settings as settings_mod
from .orchestrator import Orchestrator
from .router import Router
from .store import Store

app = FastAPI(title="huginn-muninn-kernel", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # loopback webviews only; kernel binds 127.0.0.1
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock = threading.Lock()
_state: dict[str, Any] = {"workspace": None, "store": None, "orchestrators": {}}
_runner_threads: dict[str, threading.Thread] = {}


def _store() -> Store:
    ws = _state["workspace"]
    if ws is None:
        raise HTTPException(400, "no workspace selected — POST /workspace first")
    with _lock:
        if _state["store"] is None:
            db = Path(ws) / ".taknee" / "taknee.db"
            _state["store"] = Store(db)
        return _state["store"]


def _reset_store() -> None:
    with _lock:
        _state["store"] = None
        _state["orchestrators"] = {}


class WorkspaceIn(BaseModel):
    path: str


class SettingsIn(BaseModel):
    allow_paid: bool | None = None
    prefer_local: bool | None = None
    ollama_base_url: str | None = None
    caps: dict[str, Any] | None = None


class KeyIn(BaseModel):
    key: str = ""


class TaskIn(BaseModel):
    prompt: str
    auto_approve: bool = False

class FollowupIn(BaseModel):
    message: str
    auto_approve: bool = False

class MessageIn(BaseModel):
    message: str


class ApprovalIn(BaseModel):
    decision: str  # accepted | rejected | partial
    accepted_ids: list[int] = []


class ByTheWayIn(BaseModel):
    question: str


class ToolCallIn(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False


# -- lifecycle ---------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
@app.get("/console", response_class=HTMLResponse)
def console() -> HTMLResponse:
    """Local test UI — the kernel is otherwise JSON-only."""
    path = Path(__file__).with_name("console.html")
    if not path.is_file():
        raise HTTPException(500, "console.html missing from the huginn_muninn package")
    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "version": __version__,
        "workspace": _state["workspace"],
        "catalog_compliant": _catalog_ok(),
    }

@app.get("/plugins")
def list_plugins() -> list[dict]:
    return plugins.list_plugins()


def _catalog_ok() -> bool:
    try:
        catalog.assert_catalog_compliance()
        return True
    except RuntimeError:
        return False


@app.post("/workspace")
def set_workspace(body: WorkspaceIn) -> dict:
    p = Path(body.path).expanduser()
    if not p.is_dir():
        raise HTTPException(400, f"not a directory: {body.path}")
    _state["workspace"] = str(p.resolve())
    _reset_store()
    return {"workspace": _state["workspace"]}


# -- settings ------------------------------------------------------------------

@app.get("/settings")
def get_settings() -> dict:
    return settings_mod.masked()


@app.post("/settings")
def update_settings(body: SettingsIn) -> dict:
    data = settings_mod.load()
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "caps" and isinstance(v, dict):
            data["caps"].update(v)
        else:
            data[k] = v
    settings_mod.save(data)
    return settings_mod.masked(data)


@app.post("/settings/providers/{name}/key")
def set_key(name: str, body: KeyIn) -> dict:
    try:
        settings_mod.set_provider_key(name, body.key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    stored = settings_mod.has_key(name)
    return {"provider": name, "key": "set" if stored else "", "saved": stored}


@app.post("/settings/providers/{name}/test")
def test_provider(name: str, body: KeyIn = KeyIn()) -> dict:
    if name not in settings_mod.PROVIDERS and name != "ollama":
        raise HTTPException(404, f"unknown provider {name}")
    label = settings_mod.PROVIDER_LABELS.get(name, name)
    raw = body.key or ""
    if raw.strip():
        cleaned = settings_mod.normalize_provider_key(name, raw)
        if not cleaned:
            hint = {
                "nim": "nvapi-",
                "openrouter": "sk-or-v1-",
                "groq": "gsk_",
            }.get(name, "a single-line API key")
            return {
                "provider": name,
                "ok": False,
                "pinged": False,
                "saved": False,
                "message": (
                    f"Did not ping {label}. Pasted {len(raw.strip())} characters "
                    f"but no {hint} key was found. Paste only the API key, not a code snippet."
                ),
            }
        settings_mod.set_provider_key(name, cleaned)
    ok, msg = providers.test_key(name)
    return {
        "provider": name,
        "ok": ok,
        "pinged": not msg.startswith("Did not ping"),
        "saved": settings_mod.has_key(name),
        "message": msg,
    }


# -- tasks -----------------------------------------------------------------------

@app.post("/tasks")
def create_task(body: TaskIn) -> dict:
    store = _store()
    task_id = store.create_task(body.prompt, _state["workspace"])
    store.add_message(task_id, "user", body.prompt)
    orch = Orchestrator(
        store, Router(), _state["workspace"], auto_approve=body.auto_approve
    )
    _state["orchestrators"][task_id] = orch

    def _run():
        try:
            orch.run(task_id)
        except Exception as e:  # kernel must never die with a task
            store.update_task(task_id, status="failed", error=str(e))
            store.add_event(task_id, "status", {"status": "failed", "error": str(e)})
            store.add_message(task_id, "assistant", f"The raven did not return: {e}")

    t = threading.Thread(target=_run, daemon=True, name=f"task-{task_id}")
    _runner_threads[task_id] = t
    t.start()
    def _watchdog():
        t.join(timeout=180)
        if t.is_alive():
            current = store.get_task(task_id)
            if current and current["status"] in ("created", "running"):
                msg = "provider call exceeded 180s and was abandoned"
                store.update_task(task_id, status="failed", error=msg)
                store.add_event(task_id, "status", {"status": "failed", "error": msg})
    threading.Thread(target=_watchdog, daemon=True, name=f"watch-{task_id}").start()
    return {"task_id": task_id}


@app.get("/tasks")
def list_tasks() -> list[dict]:
    if _state["workspace"] is None:
        return []
    store = _store()
    now = time.time()
    for task in store.list_tasks():
        if task["status"] in ("created", "running") and now - task["updated_at"] > 300:
            store.update_task(task["id"], status="failed", error="stale worker recovered after kernel/provider hang")
    return store.list_tasks()


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    t = _store().get_task(task_id)
    if t is None:
        raise HTTPException(404, "no such task")
    t["display_prompt"] = t.get("display_prompt") or t["prompt"]
    return t


@app.get("/tasks/{task_id}/spans")
def task_spans(task_id: str) -> list[dict]:
    return _store().spans_for_task(task_id)


@app.get("/tasks/{task_id}/events")
def task_events(task_id: str) -> list[dict]:
    return _store().events_for_task(task_id)

@app.get("/tasks/{task_id}/messages")
def task_messages(task_id: str) -> list[dict]:
    return _store().messages_for_thread(task_id)

def _status_reply(task: dict) -> str:
    status, stage = task.get("status"), task.get("stage")
    if status in ("running", "created"):
        return f"Huginn takes flight. Currently in {stage or 'startup'}; there will be a full report when it returns."
    if status == "awaiting_approval":
        return "The work is ready for your review. Open Review to approve or reject the proposed changes."
    if status == "done":
        return "This task is complete. Open the changed files or timeline if you want to inspect the details."
    return f"This task stopped before completion: {task.get('error') or 'no additional error was recorded.'}"


_QUESTION_STARTERS = (
    "what", "why", "how", "when", "where", "who", "which", "whose",
    "is", "are", "was", "were", "do", "does", "did",
    "can", "could", "should", "would", "will",
    "explain", "describe", "summarize", "tell me", "list", "show me",
)


def _is_question(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if t.endswith("?"):
        return True
    return any(t == s or t.startswith(s + " ") for s in _QUESTION_STARTERS)


def _thread_reply(store: Store, task_id: str, question: str) -> str:
    """Answer a question in-thread with a single LLM call.

    Questions must never enter the patch pipeline: forcing "what did we
    make here?" through retrieve→patch makes the model invent SEARCH/REPLACE
    edits for whatever retrieval surfaced (observed as no-op blocks on
    unrelated files)."""
    task = store.get_task(task_id) or {}
    thread_id = task.get("thread_id") or task_id
    runs = [t for t in store.list_tasks() if (t.get("thread_id") or t["id"]) == thread_id]
    runs_summary = "\n".join(
        f"- {(t.get('display_prompt') or t['prompt'])[:80]} [{t['status']}]"
        + (f" error: {str(t['error'])[:120]}" if t.get("error") else "")
        for t in runs
    ) or "(no runs)"
    history = store.messages_for_thread(task_id)[-12:]
    transcript = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in history) or "(no prior messages)"

    router = Router()
    last_err = "no healthy provider/model — add API keys in Settings"
    for _attempt in range(4):
        route = router.pick("utility", est_tokens=4_000) or router.pick("primary", est_tokens=4_000)
        if route is None:
            raise HTTPException(400, last_err)
        try:
            result = providers.chat(
                route.provider,
                route.model,
                [
                    {"role": "system", "content": (
                        "You are Huginn, the thought of a coding agent. Answer the user's question using only "
                        "the conversation and run summary below. Be concise and concrete; "
                        "reference files by name when relevant. You cannot edit files in this "
                        "mode — if the user asks for new work, tell them to send it as a task."
                    )},
                    {"role": "user", "content": (
                        f"Conversation so far:\n{transcript}\n\n"
                        f"Runs in this thread:\n{runs_summary}\n\n"
                        f"User asks: {question}"
                    )},
                ],
                temperature=0.2,
                max_tokens=800,
            )
            break
        except providers.ProviderError as e:
            router.record_failure(route.provider)
            last_err = f"provider error: {e}"
        except Exception as e:  # providers raise plain errors too
            router.record_failure(route.provider)
            last_err = f"could not answer in-thread: {e}"
    else:
        raise HTTPException(502, last_err)
    store.add_message(task_id, "user", question)
    store.add_message(task_id, "assistant", result.content)
    store.add_usage(task_id, result.tokens_in, result.tokens_out, result.usd)
    return result.content


@app.post("/tasks/{task_id}/messages")
def task_message(task_id: str, body: MessageIn) -> dict:
    store = _store()
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(404, "no such task")
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "empty message")
    lowered = text.lower()
    if any(word in lowered for word in ("status", "what happened", "progress", "did it finish", "how is it going")):
        store.add_message(task_id, "user", text)
        reply = _status_reply(task)
        store.add_message(task_id, "assistant", reply)
        return {"kind": "reply", "message": reply}
    if _is_question(text):
        reply = _thread_reply(store, task_id, text)
        return {"kind": "reply", "message": reply}
    return {"kind": "followup", "task_id": task_id}

@app.post("/tasks/{task_id}/followups")
def followup_task(task_id: str, body: FollowupIn) -> dict:
    store = _store()
    previous = store.get_task(task_id)
    if previous is None:
        raise HTTPException(404, "no such task")
    history = store.messages_for_task(task_id)
    context = "\n".join(f"{m['role']}: {m['content']}" for m in history[-8:])
    prompt = (
        "Continue the prior task in the same workspace.\n"
        f"Prior conversation:\n{context}\n\nUser follow-up:\n{body.message}"
    )
    new_id = store.create_task(
        prompt, _state["workspace"], display_prompt=body.message,
        thread_id=previous.get("thread_id") or task_id, parent_task_id=task_id,
    )
    store.add_message(new_id, "user", body.message)
    orch = Orchestrator(store, Router(), _state["workspace"], auto_approve=body.auto_approve)
    _state["orchestrators"][new_id] = orch
    def _run():
        try:
            orch.run(new_id)
        except Exception as e:
            store.update_task(new_id, status="failed", error=str(e))
            store.add_message(new_id, "assistant", f"The raven did not return: {e}")
    t = threading.Thread(target=_run, daemon=True, name=f"followup-{new_id}")
    _runner_threads[new_id] = t
    t.start()
    return {"task_id": new_id}


# -- approvals --------------------------------------------------------------------

@app.get("/approvals")
def pending_approvals() -> list[dict]:
    if _state["workspace"] is None:
        return []
    return _store().pending_approvals()


@app.post("/approvals/{approval_id}/resolve")
def resolve_approval(approval_id: int, body: ApprovalIn) -> dict:
    store = _store()
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(404, "no such approval")
    task_id = approval["task_id"]
    orch = _state["orchestrators"].get(task_id)
    if orch is None:
        # kernel restarted — reconstruct the runner from durable task state (req 6)
        orch = Orchestrator(store, Router(), _state["workspace"])
        _state["orchestrators"][task_id] = orch

    def _run():
        try:
            orch.resume(task_id, approval_id, body.decision, body.accepted_ids)
        except Exception as e:
            store.update_task(task_id, status="failed", error=str(e))

    threading.Thread(target=_run, daemon=True, name=f"resume-{task_id}").start()
    return {"task_id": task_id, "resumed": True}


# -- isolated /bytheway (req 7.c) --------------------------------------------

@app.post("/bytheway")
def bytheway(body: ByTheWayIn) -> dict:
    """One isolated question: retrieval + a single LLM call, no task bank.

    Does not create a task or touch any running orchestrator's memory, so the
    original context is unchanged when the user returns to it.
    """
    from . import retrieval

    ws = _state["workspace"]
    if ws is None:
        raise HTTPException(400, "no workspace selected — POST /workspace first")
    question = body.question.strip()
    if question.lower().startswith("/bytheway"):
        question = question.split(None, 1)[-1] if " " in question else ""
    if not question:
        raise HTTPException(400, "empty /bytheway question")

    idx = retrieval.Index(Path(ws))
    if not idx.load() or idx.stale_files():
        idx.build()
        idx.save()
    hits = idx.search(question, k=6)
    repo = idx.repo_map(token_budget=400)
    chunks = "\n\n".join(f"{c.header()}\n{c.text[:1500]}" for c, _s, _r in hits) or "(no hits)"

    router = Router()
    route = router.pick("utility", est_tokens=4_000) or router.pick("primary", est_tokens=4_000)
    if route is None:
        raise HTTPException(400, "no healthy provider/model — add API keys in Settings")

    result = providers.chat(
        route.provider,
        route.model,
        [
            {
                "role": "system",
                "content": (
                    "Answer this isolated question about the workspace. "
                    "You have no prior conversation and no task memory. Be concise."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nRepo map:\n{repo}\n\nRetrieved:\n{chunks}",
            },
        ],
        temperature=0.2,
        max_tokens=800,
    )
    return {
        "answer": result.content,
        "model": route.model,
        "provider": route.provider,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "usd": result.usd,
    }


# -- direct tool calls (for the console / tests) -----------------------------

@app.get("/tools")
def list_tools() -> dict:
    from . import tools

    items = []
    for name, schema in tools.TOOL_SCHEMAS.items():
        if name not in tools.READ_ONLY | tools.SIDE_EFFECT:
            continue
        fn = schema["function"]
        items.append(
            {
                "name": name,
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
                "side_effect": name in tools.SIDE_EFFECT,
            }
        )
    return {"tools": items, "workspace": _state["workspace"]}


@app.post("/tools")
def call_tool(body: ToolCallIn) -> dict:
    from . import retrieval, tools

    ws = _state["workspace"]
    if ws is None:
        raise HTTPException(400, "no workspace selected — POST /workspace first")
    if body.name not in tools.DISPATCH:
        raise HTTPException(404, f"unknown tool {body.name}")
    if tools.needs_approval(body.name) and not body.approved:
        return {
            "name": body.name,
            "needs_approval": True,
            "blocked": True,
            "message": "side-effect tool requires approved=true",
        }

    index_ref = None
    if body.name == "retrieve":
        index_ref = retrieval.Index(Path(ws))
        if not index_ref.load() or index_ref.stale_files():
            index_ref.build()
            index_ref.save()

    output = tools.execute(
        body.name, body.arguments, workspace=ws, index_ref=index_ref
    )
    return {"name": body.name, "output": output, "blocked": False}


# -- Free-Tier Radar & V2 Autonomous Endpoints -------------------------------

@app.get("/radar/models")
def get_radar_models(refresh: bool = False) -> dict:
    from .swarm.radar import Radar
    radar = Radar()
    models = radar.get_free_models(force_refresh=refresh)
    return {
        "models": [m.to_dict() for m in models],
        "count": len(models),
    }


@app.get("/radar/status")
def get_radar_status() -> dict:
    from .swarm.radar import Radar
    from .swarm.rotator import SwarmRotator
    radar = Radar()
    cfg = settings_mod.load()
    rotator = SwarmRotator(radar=radar)
    rotator.register_keys_from_dict(cfg)

    statuses = []
    for p in ["groq", "openrouter", "gemini", "ollama", "nim", "cerebras"]:
        st = radar.check_provider_health(p)
        statuses.append(st.to_dict())
    return {"providers": statuses, "free_first": True}


@app.get("/radar/deals")
def get_radar_deals(refresh: bool = False) -> dict:
    from .radar.community_feed import CommunityFeedScraper
    scraper = CommunityFeedScraper()
    deals = scraper.get_deals(force_refresh=refresh)
    return {
        "deals": [d.to_dict() for d in deals],
        "count": len(deals),
    }


@app.get("/radar/deltas")
def get_radar_deltas() -> dict:
    from .radar.changelog_tracker import ChangelogTracker
    tracker = ChangelogTracker()
    deltas = tracker.detect_new_models()
    return {
        "new_models": [d.to_dict() for d in deltas],
        "count": len(deltas),
    }

