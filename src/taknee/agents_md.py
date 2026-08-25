"""AGENTS.md parsing (req 9).

Extracts the structured facts the system must obey and remember:
  - test command  (used by VERIFY as the done-check)
  - build command
  - style rules   (enforced by the reviewer stage, pinned across compaction)
  - folder conventions / free-form instructions

Deliberately tolerant: headings vary by project, so we match common phrasings
and fall back to code blocks / bullet commands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TEST_HINTS = ("test", "pytest", "jest", "vitest", "mocha", "go test", "cargo test", "unittest")
BUILD_HINTS = ("build", "make", "compile", "npm run build", "tsc", "webpack", "cargo build")
STYLE_HINTS = ("style", "lint", "format", "convention", "prettier", "ruff", "black", "eslint")


@dataclass
class ProjectRules:
    test_cmd: str = ""
    build_cmd: str = ""
    style_rules: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    raw: str = ""

    def pinned_digest(self) -> str:
        """The always-in-context summary (survives compaction)."""
        lines = []
        if self.test_cmd:
            lines.append(f"test: {self.test_cmd}")
        if self.build_cmd:
            lines.append(f"build: {self.build_cmd}")
        for r in self.style_rules:
            lines.append(f"style: {r}")
        return "\n".join(lines)


_HEADING = re.compile(r"^#{1,6}\s*(.+?)\s*$", re.MULTILINE)
_SHELL_LINE = re.compile(r"^(?:\$ |```[a-z]*\n)?([A-Za-z][\w./-]*(?: +[\w./=,-]+){0,6})\s*$", re.MULTILINE)


def parse(text: str) -> ProjectRules:
    rules = ProjectRules(raw=text)
    sections = _split_sections(text)

    for title, body in sections:
        t = title.lower()
        cmds = _shell_commands(body)
        if _hits(t, TEST_HINTS) and cmds:
            rules.test_cmd = rules.test_cmd or cmds[0]
        elif _hits(t, BUILD_HINTS) and cmds:
            rules.build_cmd = rules.build_cmd or cmds[0]
        elif _hits(t, STYLE_HINTS):
            rules.style_rules.extend(_bullets(body) or cmds)
        else:
            rules.instructions.append(f"[{title}] {body.strip()[:400]}")

    # fallback: first shell-looking line mentioning a test runner anywhere
    if not rules.test_cmd:
        for line in text.splitlines():
            s = line.strip().strip("`$").strip()
            if any(s.startswith(h.split()[0]) and h in s for h in TEST_HINTS) and " " in s:
                rules.test_cmd = s
                break
    return rules


def load_for_workspace(root) -> ProjectRules:
    """Read AGENTS.md (or agents.md) from a workspace root (Path)."""
    for name in ("AGENTS.md", "agents.md"):
        p = root / name
        if p.exists():
            return parse(p.read_text(encoding="utf-8", errors="replace"))
    return ProjectRules()


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), text[m.end() : end]))
    if not out and text.strip():
        out = [("root", text)]
    return out


def _hits(title: str, hints: tuple[str, ...]) -> bool:
    """Whole-word hint match — 'convention' must not swallow 'conventions' headings."""
    return any(re.search(rf"\b{re.escape(h)}\b", title) for h in hints)


def _shell_commands(body: str) -> list[str]:
    """Commands from fenced/whole lines AND inline `backticks` (bullet style)."""
    out = [c for c in _SHELL_LINE.findall(body) if _looks_like_cmd(c)]
    inline = re.findall(r"`([^`\n]+)`", body)
    out += [c for c in inline if _looks_like_cmd(c) and c not in out]
    return out[:4]


def _looks_like_cmd(c: str) -> bool:
    first = c.split()[0]
    return (
        first in {"pytest", "make", "npm", "pnpm", "yarn", "cargo", "go", "tsc", "ruff", "black", "python", "uv", "jest", "vitest", "eslint", "prettier"}
        or "/" in first
        or first.endswith(".sh")
    )


def _bullets(body: str) -> list[str]:
    return [l.lstrip(" -*").strip() for l in body.splitlines() if l.strip().startswith(("-", "*", "•"))][:8]
