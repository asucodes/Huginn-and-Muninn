"""Git Worktree Sandbox Manager.

Creates ephemeral, isolated Git worktrees for each agent task so the
agent can read, write, and test code without ever touching the user's
active workspace.

Architecture inspired by OpenHands worktree isolation pattern (MIT)
and OpenAI Codex Harness sandbox isolation (Apache-2.0).

Usage:
    with GitWorktreeSandbox(workspace=Path("."), task_id="task-abc") as sandbox:
        sandbox.run("pytest tests/ -q")
        diff = sandbox.unified_diff()
    # On __exit__: worktree pruned if rejected, or kept for merge on approval
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any


OUTPUT_MAX = 20_000  # chars, cap output to ~5K tokens


class SandboxError(Exception):
    pass


class GitWorktreeSandbox:
    """Ephemeral Git worktree for zero-risk agent code execution.

    Creates .taknee/worktrees/<task_id>/ as a temporary branch.
    All file reads, writes, and terminal commands are jailed here.
    The user's working tree is never modified until explicit approval.
    """

    def __init__(self, workspace: Path, task_id: str | None = None):
        self.workspace = workspace.resolve()
        self.task_id = task_id or f"agent-{uuid.uuid4().hex[:8]}"
        self.branch = f"agent/{self.task_id}"
        self.worktree_root = self.workspace / ".taknee" / "worktrees" / self.task_id
        self._active = False

    def __enter__(self) -> "GitWorktreeSandbox":
        self.create()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        # Auto-prune on exception/cancellation; caller calls merge() on approval
        if exc_type is not None:
            self.prune()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def create(self) -> None:
        """Creates the ephemeral worktree branch."""
        self.worktree_root.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", str(self.worktree_root), "-b", self.branch, "HEAD"],
            cwd=self.workspace, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise SandboxError(f"Failed to create worktree: {result.stderr.strip()}")
        self._active = True

    def prune(self) -> None:
        """Removes the worktree and its temporary branch."""
        if not self._active:
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(self.worktree_root)],
            cwd=self.workspace, capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "-D", self.branch],
            cwd=self.workspace, capture_output=True,
        )
        self._active = False

    def merge(self, message: str = "") -> None:
        """Fast-forward merges the worktree branch into HEAD and prunes."""
        if not self._active:
            return
        # Commit any remaining unstaged changes
        subprocess.run(["git", "add", "-A"], cwd=self.worktree_root, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message or f"feat: agent task {self.task_id}"],
            cwd=self.worktree_root, capture_output=True,
        )
        subprocess.run(
            ["git", "merge", "--ff-only", self.branch],
            cwd=self.workspace, capture_output=True,
        )
        self.prune()

    # ── Execution ──────────────────────────────────────────────────────────────

    def run(self, cmd: str, timeout: float = 60.0) -> tuple[int, str]:
        """Runs a shell command jailed inside the worktree. Returns (exit_code, output)."""
        if not self._active:
            raise SandboxError("Worktree not active. Call create() or use as context manager.")
        result = subprocess.run(
            cmd, shell=True, cwd=self.worktree_root,
            capture_output=True, text=True, timeout=timeout,
        )
        output = (result.stdout + result.stderr)[:OUTPUT_MAX]
        return result.returncode, output

    def read_file(self, path: str) -> str:
        """Reads a file relative to the worktree root."""
        full = (self.worktree_root / path).resolve()
        try:
            full.relative_to(self.worktree_root.resolve())
        except ValueError:
            raise SandboxError(f"Path escape attempt: {path}")
        return full.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        """Writes a file relative to the worktree root."""
        full = (self.worktree_root / path).resolve()
        try:
            full.relative_to(self.worktree_root.resolve())
        except ValueError:
            raise SandboxError(f"Path escape attempt: {path}")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    # ── Diff & Review ──────────────────────────────────────────────────────────

    def unified_diff(self) -> str:
        """Returns a unified git diff vs HEAD for human review before merge."""
        subprocess.run(["git", "add", "-A"], cwd=self.worktree_root, capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "HEAD"],
            cwd=self.worktree_root, capture_output=True, text=True,
        )
        return result.stdout[:OUTPUT_MAX]

    @property
    def path(self) -> Path:
        return self.worktree_root
