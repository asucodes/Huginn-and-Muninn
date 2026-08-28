"""Tests for Auto-Learning Memory and Subagent Delegation."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from taknee.memory import MemoryManager, ProjectMemory
from taknee.engine.subagent import SubagentDelegator, SubagentResult
from taknee.engine.graph import MilestoneGraph
from taknee.swarm.rotator import SwarmRotator, RouteDecision
from taknee.providers import ChatResult


class TestMemoryManager:
    def test_record_discovery_and_save(self, tmp_path):
        mgr = MemoryManager(tmp_path)
        assert mgr.record_discovery("convention", "Use type hints on all public functions")
        assert mgr.record_discovery("test", "pytest -v tests/unit")
        assert mgr.record_discovery("architecture", "FastAPI routers reside in src/api")
        assert mgr.record_discovery("quirk", "Windows requires utf-8 encoding parameter")

        # Duplicate should return False
        assert not mgr.record_discovery("convention", "Use type hints on all public functions")

        # Verify disk persistence
        assert (tmp_path / ".taknee" / "memory.json").exists()
        assert (tmp_path / ".taknee" / "AGENTS.md").exists()

        # Reload in a new manager
        mgr2 = MemoryManager(tmp_path)
        assert "pytest -v tests/unit" in mgr2.memory.test_commands
        assert "Use type hints on all public functions" in mgr2.memory.conventions
        assert "FastAPI routers reside in src/api" in mgr2.memory.architecture_notes
        assert "Windows requires utf-8 encoding parameter" in mgr2.memory.quirks

    def test_ingest_claude_md_and_agents_md(self, tmp_path):
        # Create a legacy CLAUDE.md at repo root
        (tmp_path / "CLAUDE.md").write_text(
            "# Guidelines\n\n```bash\npytest -q --disable-warnings\nnpm run build\n```\n",
            encoding="utf-8"
        )
        mgr = MemoryManager(tmp_path)
        assert "pytest -q --disable-warnings" in mgr.memory.test_commands
        assert "npm run build" in mgr.memory.build_commands

    def test_record_test_result_prioritization(self, tmp_path):
        mgr = MemoryManager(tmp_path)
        mgr.record_discovery("test", "pytest tests/slow")
        mgr.record_discovery("test", "pytest -q tests/fast")

        # Fast test passed -> becomes preferred test command
        mgr.record_test_result("pytest -q tests/fast", passed=True)
        assert mgr.get_preferred_test_cmd() == "pytest -q tests/fast"


class TestSubagentDelegator:
    def test_subagent_run_submits_research(self, tmp_path):
        rotator = MagicMock(spec=SwarmRotator)
        mock_dispatch = MagicMock(return_value="class SessionManager:\n    pass")

        subagent = SubagentDelegator(tmp_path, rotator, mock_dispatch)

        # Mock the chat_with_swarm return value
        mock_chat_result = ChatResult(
            content="",
            tool_calls=[{
                "id": "call_1",
                "function": {
                    "name": "submit_research",
                    "arguments": json.dumps({"findings": "Found SessionManager in src/auth.py (L10-L40)"}),
                }
            }],
            tokens_in=100,
            tokens_out=25,
            usd=0.0001,
        )
        route = RouteDecision("groq", "llama-3.1-8b-instant", "key", "utility", "fast")

        with patch("taknee.engine.subagent.chat_with_swarm", return_value=(mock_chat_result, route)):
            res = subagent.run("Find where SessionManager is defined", scope_hint="src/auth")
            assert "Found SessionManager in src/auth.py" in res.findings
            assert res.steps_used == 1
            assert res.cost_usd > 0


class TestGraphMemoryAndSubagentDispatch:
    def test_graph_dispatches_record_memory_and_delegate_research(self, tmp_path):
        rotator = MagicMock(spec=SwarmRotator)
        store = MagicMock()

        g = MilestoneGraph.__new__(MilestoneGraph)
        g.workspace = tmp_path
        g.rotator = rotator
        g.store = store
        g.memory = MemoryManager(tmp_path)
        g.subagents = MagicMock()
        g.subagents.run.return_value = SubagentResult(
            findings="Auth token validation is in verify_jwt()",
            steps_used=2,
            cost_usd=0.0002,
        )

        mock_sandbox = MagicMock()

        # 1. Test record_memory
        res_mem = g._dispatch_tool("record_memory", {"category": "convention", "fact": "No wildcard imports"}, mock_sandbox, "")
        assert "Recorded new memory" in res_mem
        assert "No wildcard imports" in g.memory.memory.conventions

        # 2. Test delegate_research
        res_sub = g._dispatch_tool("delegate_research", {"goal": "Check JWT validation"}, mock_sandbox, "")
        assert "Auth token validation is in verify_jwt()" in res_sub
        assert "[SUBAGENT FINDINGS" in res_sub
