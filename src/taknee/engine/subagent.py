"""Subagent Delegation Engine (Claude Code parity).

Spawns lightweight, isolated subagents for deep code exploration,
multi-file grepping, and research queries.

Benefits:
  - Context isolation: Child agent reads 10+ files; parent context receives ONLY the summary.
  - Zero context pollution: Intermediate raw file contents are discarded.
  - Speed: Runs on ultra-fast utility tiers (Groq 500 t/s, Gemini Flash 1M).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..swarm.cache_optimizer import PromptCachePacker
from ..swarm.rotator import SwarmRotator
from ..transport.client import chat_with_swarm

SUBAGENT_MAX_STEPS = 6

SUBAGENT_SYSTEM_PROMPT = """\
You are an exploratory subagent spawned by Huginn to investigate a specific codebase question or research goal.
Explore using tools (read_file, search_code, list_dir, web_fetch).
When you have the answer, call submit_research with a clear, concise, and structured summary.
Be direct and quote relevant line numbers, file paths, and function signatures.
Do not modify any files.\
"""

SUBAGENT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Relative path to file."}
            }, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search code across the workspace.",
            "parameters": {"type": "object", "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Subdirectory to search in."},
            }, "required": ["pattern"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Relative path to list."},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch live web documentation or API URL.",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string"}
            }, "required": ["url"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_research",
            "description": "Submit your research findings back to the main agent. Ends the subagent loop.",
            "parameters": {"type": "object", "properties": {
                "findings": {"type": "string", "description": "Structured findings with file paths, symbol names, and concise explanation."}
            }, "required": ["findings"]},
        },
    },
]


@dataclass
class SubagentResult:
    findings: str
    steps_used: int
    cost_usd: float


class SubagentDelegator:
    """Executes isolated subagent exploration runs."""

    def __init__(self, workspace: Path, rotator: SwarmRotator, dispatch_tool_fn):
        self.workspace = workspace.resolve()
        self.rotator = rotator
        self.dispatch_tool_fn = dispatch_tool_fn
        self.packer = PromptCachePacker()

    def run(self, goal: str, scope_hint: str = "", sandbox: Any = None) -> SubagentResult:
        """Runs the child exploration loop in an isolated context."""
        history: list[dict[str, Any]] = []
        total_cost = 0.0
        steps = 0

        scratchpad = f"RESEARCH GOAL: {goal}"
        if scope_hint:
            scratchpad += f"\nSCOPE HINT: Focus on '{scope_hint}'"

        while steps < SUBAGENT_MAX_STEPS:
            steps += 1
            packed = self.packer.pack(
                system_instruction=SUBAGENT_SYSTEM_PROMPT,
                project_rules="",
                repo_map="",
                conversation_history=history,
                current_scratchpad=scratchpad,
            )

            result, _route = chat_with_swarm(
                self.rotator,
                packed.messages,
                tier="utility",  # Fast & free: Groq 500 t/s / Gemini Flash
                tools=SUBAGENT_TOOL_SCHEMAS,
                max_tokens=2048,
            )
            total_cost += result.usd

            if result.content:
                history.append({"role": "assistant", "content": result.content})

            if not result.tool_calls:
                # If model produced direct summary without tool call, return it
                return SubagentResult(
                    findings=result.content or "Subagent completed without findings.",
                    steps_used=steps,
                    cost_usd=total_cost,
                )

            for tc in result.tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    args = {}

                if name == "submit_research":
                    findings = args.get("findings") or result.content or "Investigation finished."
                    return SubagentResult(
                        findings=findings,
                        steps_used=steps,
                        cost_usd=total_cost,
                    )

                # Dispatch read-only tool in sandbox
                obs = self.dispatch_tool_fn(name, args, sandbox, "")
                history.append({"role": "tool", "content": obs, "tool_call_id": tc.get("id", "")})

        return SubagentResult(
            findings=f"Subagent investigated '{goal}' (completed {steps} exploration steps).",
            steps_used=steps,
            cost_usd=total_cost,
        )
