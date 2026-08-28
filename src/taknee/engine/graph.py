"""Autonomous Milestone Graph — the V2 agent execution engine.

Replaces the rigid linear orchestrator.py pipeline with a 3-milestone
event-driven ReAct loop inside a sandboxed Git worktree.

Architectural inspiration:
  - mini-SWE-agent bounded loop pattern (MIT, SWE-agent/mini-swe-agent)
  - OpenAI Codex Harness max_steps cap and session state (Apache-2.0, openai/codex)
  - OpenHands EventStream action/observation pattern (MIT, All-Hands-AI/OpenHands)

The core user-visible improvements over V1 orchestrator.py:
  1. Agent can READ multiple files, explore callers, and search code before patching.
  2. Agent runs tests automatically in an isolated Git worktree; retries on failure.
  3. User sees a clean unified diff and approves before any change hits their workspace.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import patches, tools
from ..engine.sandbox import GitWorktreeSandbox
from ..index.repo_map import build_repo_map
from ..store import Store
from ..swarm.cache_optimizer import PromptCachePacker
from ..swarm.rotator import SwarmRotator
from ..transport.client import chat_with_swarm

MAX_STEPS = 25  # Hard cap per OpenAI Harness / mini-SWE-agent best practice
SYSTEM_PROMPT = """\
You are Huginn, an autonomous coding agent.
You operate inside an isolated Git worktree — you cannot corrupt the user's workspace.
Think step-by-step. Use tools to explore code before patching.
Prefer minimal, precise changes. Always run the test command to verify your work.
When your task is done and tests pass, call submit_task with a concise summary.\
"""


@dataclass
class TaskPlan:
    strategy: str
    files_to_edit: list[str] = field(default_factory=list)
    test_cmd: str = "pytest -q"


@dataclass
class MilestoneResult:
    task_id: str
    status: str          # "approved" | "rejected" | "failed" | "pending_review"
    diff: str = ""
    summary: str = ""
    steps_used: int = 0
    cost_usd: float = 0.0


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file in the workspace.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Relative path to the file."}
            }, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a pattern (ripgrep or grep) across the workspace. Returns matching lines.",
            "parameters": {"type": "object", "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Subdirectory to search in (optional, defaults to all)."},
            }, "required": ["pattern"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_patch",
            "description": "Apply SEARCH/REPLACE edits to one or more files.",
            "parameters": {"type": "object", "properties": {
                "hunks": {"type": "array", "items": {"type": "object", "properties": {
                    "path": {"type": "string"},
                    "search": {"type": "string"},
                    "replace": {"type": "string"},
                }, "required": ["path", "search", "replace"]}},
            }, "required": ["hunks"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the project's test suite inside the sandbox. Returns exit code and output.",
            "parameters": {"type": "object", "properties": {
                "cmd": {"type": "string", "description": "Test command to run (e.g. 'pytest -q')."}
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_task",
            "description": "Signal that the task is complete and tests pass. Ends the agent loop.",
            "parameters": {"type": "object", "properties": {
                "summary": {"type": "string", "description": "Brief summary of what was changed and why."}
            }, "required": ["summary"]},
        },
    },
]


class MilestoneGraph:
    """3-milestone autonomous execution engine for coding tasks.

    Milestone 1 — PLAN: Build repo map, understand task, produce TaskPlan.
    Milestone 2 — SANDBOX REACT: Iterative read/search/patch/test loop (capped at MAX_STEPS).
    Milestone 3 — PROOF: Generate unified diff, await human approval, merge or prune.
    """

    def __init__(
        self,
        workspace: Path,
        rotator: SwarmRotator,
        store: Store,
        project_rules: str = "",
    ):
        self.workspace = workspace
        self.rotator = rotator
        self.store = store
        self.project_rules = project_rules
        self.packer = PromptCachePacker()

    def run(self, task_id: str, task_prompt: str, test_cmd: str = "pytest -q") -> MilestoneResult:
        """Execute a full autonomous task through all 3 milestones."""
        # ── MILESTONE 1: PLAN ──────────────────────────────────────────────────
        repo_map = build_repo_map(self.workspace, token_budget=1500)
        plan = self._plan(task_id, task_prompt, repo_map)

        # ── MILESTONE 2: SANDBOX REACT LOOP ───────────────────────────────────
        with GitWorktreeSandbox(self.workspace, task_id=task_id) as sandbox:
            result = self._react_loop(task_id, task_prompt, plan, sandbox, repo_map, test_cmd)
            if result.status != "pending_review":
                return result  # Failed inside sandbox

            result.diff = sandbox.unified_diff()

            # ── MILESTONE 3: PROOF (Human In The Loop) ────────────────────────
            # Record in store for the UI to surface the diff
            self.store.add_event(task_id, "awaiting_approval", {"diff": result.diff[:8000]})

            # Return pending_review — the API layer handles the approval gate
            # On approval: caller calls sandbox.merge(); on rejection: sandbox.prune()
            return result

    def _plan(self, task_id: str, prompt: str, repo_map: str) -> TaskPlan:
        """Milestone 1: Ask the LLM to produce a task strategy given the repo map."""
        packed = self.packer.pack(
            system_instruction=SYSTEM_PROMPT,
            project_rules=self.project_rules,
            repo_map=repo_map,
            conversation_history=[],
            current_scratchpad=(
                f"TASK: {prompt}\n\n"
                "Return a JSON object with keys: strategy (string), files_to_edit (list of paths), "
                "test_cmd (string). Respond with ONLY the JSON, no prose."
            ),
        )
        result, route = chat_with_swarm(
            self.rotator, packed.messages, tier="utility", max_tokens=512
        )
        try:
            data = json.loads(result.content.strip().lstrip("```json").rstrip("```").strip())
            return TaskPlan(
                strategy=data.get("strategy", prompt),
                files_to_edit=data.get("files_to_edit", []),
                test_cmd=data.get("test_cmd", "pytest -q"),
            )
        except Exception:
            return TaskPlan(strategy=prompt)

    def _react_loop(
        self, task_id: str, prompt: str, plan: TaskPlan,
        sandbox: GitWorktreeSandbox, repo_map: str, test_cmd: str,
    ) -> MilestoneResult:
        """Milestone 2: Bounded ReAct tool loop inside the sandbox."""
        history: list[dict[str, str]] = []
        total_cost = 0.0
        steps = 0

        while steps < MAX_STEPS:
            steps += 1
            packed = self.packer.pack(
                system_instruction=SYSTEM_PROMPT,
                project_rules=self.project_rules,
                repo_map=repo_map,
                conversation_history=history,
                current_scratchpad=f"TASK: {prompt}\nSTRATEGY: {plan.strategy}",
            )
            result, route = chat_with_swarm(
                self.rotator, packed.messages, tier="primary",
                tools=TOOL_SCHEMAS, max_tokens=4096,
            )
            total_cost += result.usd

            # Handle text content (agent thinking)
            if result.content:
                history.append({"role": "assistant", "content": result.content})

            # Handle tool calls
            if not result.tool_calls:
                # No tool call — agent may be confused; nudge it
                history.append({"role": "user", "content": "Call a tool to make progress. Use submit_task when done."})
                continue

            for tc in result.tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    args = {}

                observation = self._dispatch_tool(name, args, sandbox, test_cmd)

                if name == "submit_task":
                    return MilestoneResult(
                        task_id=task_id, status="pending_review",
                        summary=args.get("summary", "Task completed"),
                        steps_used=steps, cost_usd=total_cost,
                    )

                history.append({"role": "tool", "content": observation, "tool_call_id": tc.get("id", "")})

        return MilestoneResult(
            task_id=task_id, status="failed",
            summary=f"Exceeded MAX_STEPS ({MAX_STEPS}). Partial changes in worktree.",
            steps_used=steps, cost_usd=total_cost,
        )

    def _dispatch_tool(self, name: str, args: dict[str, Any], sandbox: GitWorktreeSandbox, test_cmd: str) -> str:
        """Execute a tool call inside the sandbox and return the observation string."""
        if name == "read_file":
            try:
                return sandbox.read_file(args["path"])[:8000]
            except Exception as e:
                return f"ERROR: {e}"

        if name == "search_code":
            pattern = args.get("pattern", "")
            path = args.get("path", ".")
            _, output = sandbox.run(f'grep -rn "{pattern}" {path}')
            return output or "(no matches)"

        if name == "write_patch":
            results = []
            for hunk in args.get("hunks", []):
                path = hunk.get("path", "")
                search = hunk.get("search", "")
                replace = hunk.get("replace", "")
                try:
                    original = sandbox.read_file(path)
                    patched, count, error = patches.apply_patch(original, search, replace)
                    if error:
                        results.append(f"PATCH FAILED on {path}: {error}")
                    else:
                        sandbox.write_file(path, patched)
                        results.append(f"OK: {count} hunk(s) applied to {path}")
                except Exception as e:
                    results.append(f"ERROR on {path}: {e}")
            return "\n".join(results)

        if name == "run_tests":
            cmd = args.get("cmd", test_cmd)
            exit_code, output = sandbox.run(cmd, timeout=120.0)
            status = "PASS" if exit_code == 0 else "FAIL"
            return f"[{status}] exit={exit_code}\n{output}"

        return f"Unknown tool: {name}"
