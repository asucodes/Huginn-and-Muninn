"""Auto-Learning Project Memory Manager (Claude Code parity).

Automatically discovers, persists, and maintains project facts:
  - working test & build commands
  - architecture & directory layout conventions
  - project quirks and fixes discovered during agent runs
  - compatibility with AGENTS.md, .taknee/memory.json, and CLAUDE.md

Injects a compact, always-updated memory digest into every agent prompt.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectMemory:
    test_commands: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)
    architecture_notes: list[str] = field(default_factory=list)
    quirks: list[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryManager:
    """Reads, updates, and persists workspace memory across agent runs."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.taknee_dir = self.workspace / ".taknee"
        self.memory_file = self.taknee_dir / "memory.json"
        self.agents_md = self.taknee_dir / "AGENTS.md"
        self.memory: ProjectMemory = ProjectMemory()
        self.load()

    def load(self) -> ProjectMemory:
        """Loads memory from .taknee/memory.json and scans root AGENTS.md / CLAUDE.md."""
        # 1. Load structured JSON memory if present
        if self.memory_file.exists():
            try:
                data = json.loads(self.memory_file.read_text(encoding="utf-8"))
                self.memory = ProjectMemory(
                    test_commands=data.get("test_commands", []),
                    build_commands=data.get("build_commands", []),
                    conventions=data.get("conventions", []),
                    architecture_notes=data.get("architecture_notes", []),
                    quirks=data.get("quirks", []),
                    last_updated=data.get("last_updated", time.time()),
                )
            except Exception:
                self.memory = ProjectMemory()

        # 2. Ingest existing AGENTS.md or CLAUDE.md files from project root
        self._ingest_root_doc("AGENTS.md")
        self._ingest_root_doc("CLAUDE.md")
        return self.memory

    def _ingest_root_doc(self, filename: str) -> None:
        doc = self.workspace / filename
        if not doc.exists():
            return
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                s = line.strip().strip("`$").strip()
                if not s or s.startswith("#"):
                    continue
                if any(s.startswith(k) for k in ("pytest", "npm test", "cargo test", "go test", "jest", "vitest", "python -m unittest")):
                    self.record_discovery("test_commands", s, auto_save=False)
                elif any(s.startswith(k) for k in ("npm run build", "cargo build", "make", "tsc")):
                    self.record_discovery("build_commands", s, auto_save=False)
        except Exception:
            pass

    def record_discovery(self, category: str, fact: str, auto_save: bool = True) -> bool:
        """Records a new learned fact in the given category (deduplicated)."""
        fact = fact.strip()
        if not fact:
            return False

        target_list: list[str]
        if category in ("test", "test_commands", "test_cmd"):
            target_list = self.memory.test_commands
        elif category in ("build", "build_commands", "build_cmd"):
            target_list = self.memory.build_commands
        elif category in ("convention", "conventions", "style"):
            target_list = self.memory.conventions
        elif category in ("architecture", "architecture_notes", "layout"):
            target_list = self.memory.architecture_notes
        elif category in ("quirk", "quirks", "gotcha"):
            target_list = self.memory.quirks
        else:
            target_list = self.memory.conventions

        if fact not in target_list:
            target_list.append(fact)
            self.memory.last_updated = time.time()
            if auto_save:
                self.save()
            return True
        return False

    def record_test_result(self, cmd: str, passed: bool) -> None:
        """Remembers successful test commands at the top of the test commands list."""
        cmd = cmd.strip()
        if not cmd:
            return
        if passed:
            if cmd in self.memory.test_commands:
                self.memory.test_commands.remove(cmd)
            self.memory.test_commands.insert(0, cmd)
            self.save()

    def get_preferred_test_cmd(self, default: str = "pytest -q") -> str:
        """Returns the most recent working test command."""
        return self.memory.test_commands[0] if self.memory.test_commands else default

    def export_digest(self) -> str:
        """Exports a token-efficient summary digest for system prompts."""
        lines = []
        if self.memory.test_commands:
            lines.append(f"Test command: {self.memory.test_commands[0]}")
        if self.memory.build_commands:
            lines.append(f"Build command: {self.memory.build_commands[0]}")
        for c in self.memory.conventions[:4]:
            lines.append(f"Convention: {c}")
        for a in self.memory.architecture_notes[:4]:
            lines.append(f"Architecture: {a}")
        for q in self.memory.quirks[:3]:
            lines.append(f"Quirk: {q}")
        return "\n".join(lines)

    def export_markdown(self) -> str:
        """Generates a full AGENTS.md document."""
        sections = ["# Project Memory (Auto-Maintained by Huginn & Muninn)\n"]
        if self.memory.test_commands:
            sections.append("## Testing\n```bash\n" + "\n".join(self.memory.test_commands) + "\n```\n")
        if self.memory.build_commands:
            sections.append("## Build & Run\n```bash\n" + "\n".join(self.memory.build_commands) + "\n```\n")
        if self.memory.architecture_notes:
            sections.append("## Architecture\n" + "\n".join(f"- {a}" for a in self.memory.architecture_notes) + "\n")
        if self.memory.conventions:
            sections.append("## Conventions\n" + "\n".join(f"- {c}" for c in self.memory.conventions) + "\n")
        if self.memory.quirks:
            sections.append("## Known Quirks & Workarounds\n" + "\n".join(f"- {q}" for q in self.memory.quirks) + "\n")
        return "\n".join(sections)

    def save(self) -> None:
        """Persists memory to .taknee/memory.json and writes .taknee/AGENTS.md."""
        self.taknee_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file.write_text(json.dumps(self.memory.to_dict(), indent=2), encoding="utf-8")
        self.agents_md.write_text(self.export_markdown(), encoding="utf-8")
