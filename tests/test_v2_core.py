"""Tests for V2 new modules: transport bridge, sandbox, repo_map, radar changelog."""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# ── Transport Bridge ───────────────────────────────────────────────────────────

class TestTransportBridge:
    def test_chat_with_swarm_ollama_fallback(self):
        """With no cloud keys, should route to Ollama fallback cleanly."""
        from taknee.swarm.radar import Radar
        from taknee.swarm.rotator import SwarmRotator
        radar = Radar()
        rotator = SwarmRotator(radar=radar)
        # No keys registered -> should pick Ollama as fallback
        route = rotator.pick_route(tier="primary")
        assert route is not None
        assert route.provider == "ollama"
        assert route.is_local is True

    def test_chat_with_route_injects_key(self):
        """chat_with_route should inject api_key into settings before calling providers.chat."""
        from taknee.swarm.rotator import RouteDecision
        from taknee.transport.client import chat_with_route
        from taknee.providers import ChatResult

        route = RouteDecision(
            provider="groq",
            model="llama-3.1-8b-instant",
            api_key="gsk_test_key",
            tier="utility",
            reason="test",
        )
        fake_result = ChatResult(content="pong", tokens_in=5, tokens_out=1, usd=0.0)

        with patch("taknee.transport.client.providers.chat", return_value=fake_result) as mock_chat:
            result = chat_with_route(route, [{"role": "user", "content": "ping"}])
            assert result.content == "pong"
            call_kwargs = mock_chat.call_args
            # Key should be injected into settings kwarg
            settings_arg = call_kwargs.kwargs.get("settings") or {}
            assert settings_arg.get("providers", {}).get("groq", {}).get("key") == "gsk_test_key"

    def test_chat_with_swarm_rotates_on_429(self):
        """Should retry on a different provider after a 429 is recorded."""
        from taknee.swarm.radar import Radar
        from taknee.swarm.rotator import SwarmRotator
        from taknee.providers import RateLimited, ChatResult
        from taknee.transport.client import chat_with_swarm

        radar = Radar()
        rotator = SwarmRotator(radar=radar)
        rotator.register_key("groq", "gsk_key_1")
        rotator.register_key("openrouter", "sk-or-key-1")

        call_count = [0]

        def fake_chat_fn(route, messages, **kwargs):
            call_count[0] += 1
            if route.provider == "groq":
                raise RateLimited("groq", retry_after=30.0)
            return ChatResult(content="ok", tokens_in=5, tokens_out=2, usd=0.0)

        with patch("taknee.transport.client.chat_with_route", side_effect=lambda route, msgs, **kw: fake_chat_fn(route, msgs, **kw)):
            result, winning_route = chat_with_swarm(
                rotator, [{"role": "user", "content": "hello"}], tier="primary"
            )
            assert winning_route.provider == "openrouter"
            assert result.content == "ok"


# ── Git Worktree Sandbox ───────────────────────────────────────────────────────

class TestGitWorktreeSandbox:
    def test_sandbox_creates_and_prunes_worktree(self, tmp_path):
        """Create a git repo, spin up a sandbox, verify worktree created and pruned."""
        # Init a real git repo in tmp_path
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "README.md").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        from taknee.engine.sandbox import GitWorktreeSandbox
        sandbox = GitWorktreeSandbox(workspace=tmp_path, task_id="test-001")
        sandbox.create()
        assert sandbox.path.exists()

        # Run a command inside the sandbox
        exit_code, output = sandbox.run("echo hello-from-sandbox")
        assert exit_code == 0
        assert "hello-from-sandbox" in output

        # Write and read a file
        sandbox.write_file("test_output.txt", "sandbox content")
        content = sandbox.read_file("test_output.txt")
        assert content == "sandbox content"

        # Prune removes worktree dir
        sandbox.prune()
        assert not sandbox.path.exists()

    def test_sandbox_path_jail(self, tmp_path):
        """Path traversal attempts should raise SandboxError."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "f.txt").write_text("x")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        from taknee.engine.sandbox import GitWorktreeSandbox, SandboxError
        sandbox = GitWorktreeSandbox(workspace=tmp_path, task_id="test-002")
        sandbox.create()
        with pytest.raises(SandboxError):
            sandbox.read_file("../../../../etc/passwd")
        sandbox.prune()


# ── Repo Map Builder ───────────────────────────────────────────────────────────

class TestRepoMap:
    def test_repo_map_includes_python_symbols(self, tmp_path):
        (tmp_path / "main.py").write_text("class Foo:\n    def bar(self): pass\ndef baz(): pass\n")
        from taknee.index.repo_map import build_repo_map
        result = build_repo_map(tmp_path, token_budget=2000)
        assert "main.py" in result
        assert "Foo" in result
        assert "baz" in result

    def test_repo_map_respects_token_budget(self, tmp_path):
        # Create 100 Python files
        for i in range(100):
            (tmp_path / f"module_{i}.py").write_text(f"def func_{i}(): pass\n" * 20)
        from taknee.index.repo_map import build_repo_map
        result = build_repo_map(tmp_path, token_budget=200)
        # Result should be within ~4x the token budget in chars
        assert len(result) <= 200 * 4 + 200  # some slack for "..." lines


# ── Changelog Tracker ─────────────────────────────────────────────────────────

class TestChangelogTracker:
    def test_detects_new_free_models(self, tmp_path):
        from taknee.radar.changelog_tracker import ChangelogTracker
        from taknee.swarm.radar import Radar, FreeModel

        radar = Radar()
        tracker = ChangelogTracker(radar=radar, snapshot_path=tmp_path / "snapshot.json")

        # First scan: saves snapshot of current models
        deltas1 = tracker.detect_new_models()
        # All current models are "new" because there was no prior snapshot
        assert len(deltas1) > 0

        # Second scan: no new models (same catalog)
        deltas2 = tracker.detect_new_models()
        assert len(deltas2) == 0  # Nothing new appeared
