"""Patch parsing and application — SEARCH/REPLACE blocks (aider-style).

Why SEARCH/REPLACE instead of unified diffs: aider's published benchmarks show
weak/small models apply S/R blocks far more reliably — exact anchors instead
of drifting line numbers. We keep the applier strict:
  exact match -> whitespace-tolerant match -> recorded failure (never crash),
and one repair retry belongs to the orchestrator, not here.

Review payloads are derived from the same blocks so HITL hunks (req 10) and
agent patches share one representation.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

BLOCK_RE = re.compile(
    r"^```(?P<header>[^\r\n`]*)\r?\n"
    r"(?:(?P<body_path>[^\r\n`<]+)\r?\n)?"
    r"<<<<<<< SEARCH\r?\n(?P<search>.*?)(?:\r?\n)?=======\r?\n"
    r"(?P<replace>.*?)\r?\n>>>>>>> REPLACE[^\r\n]*\r?\n```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)

_FENCE_LANGUAGES = {
    "bash", "c", "cpp", "csharp", "css", "go", "html", "java", "javascript",
    "json", "jsx", "markdown", "md", "python", "py", "rust", "shell", "sql",
    "text", "toml", "ts", "tsx", "typescript", "yaml", "yml",
}


@dataclass
class PatchBlock:
    file: str
    search: str
    replace: str

    @property
    def fingerprint(self) -> str:
        return f"{self.file}|{hash_text(self.search)}|{hash_text(self.replace)}"


@dataclass
class ApplyReport:
    applied: list[PatchBlock] = field(default_factory=list)
    failed: list[tuple[PatchBlock, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def diff(self, files: dict[str, str], originals: dict[str, str]) -> str:
        out = []
        for path in sorted(files):
            if path in originals:
                d = difflib.unified_diff(
                    originals[path].splitlines(keepends=True),
                    files[path].splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
                out.extend(d)
        return "".join(out)


def parse(text: str) -> list[PatchBlock]:
    blocks: list[PatchBlock] = []
    for m in BLOCK_RE.finditer(text):
        header = m.group("header").strip()
        body_path = (m.group("body_path") or "").strip()
        # A language-tagged fence needs its path on the next line.  Without a
        # path it is almost certainly prose, not a patch for a file called
        # "python" or "json".
        path = body_path or header
        if not path or (header.lower() in _FENCE_LANGUAGES and not body_path):
            continue
        blocks.append(PatchBlock(path, m.group("search"), m.group("replace")))
    return blocks


def hash_text(s: str) -> str:
    import hashlib

    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:10]


def _fuzzy_find(content: str, search: str) -> int | None:
    """Anchor location: exact first, then whitespace-insensitive line compare
    (catches indentation drift and internal spacing like 'f( )' vs 'f()')."""
    i = content.find(search)
    if i >= 0:
        return i
    key = lambda l: re.sub(r"\s+", "", l)  # noqa: E731
    tgt = [key(l) for l in search.splitlines()]
    lines = content.splitlines(keepends=True)
    window = len(tgt)
    for start in range(0, len(lines) - window + 1):
        if [key(l) for l in lines[start : start + window]] == tgt:
            return sum(len(l) for l in lines[:start])
    return None


def apply_blocks(
    blocks: list[PatchBlock],
    read_file,  # (path) -> str
    write_file,  # (path, content) -> None
    originals: dict[str, str] | None = None,
) -> ApplyReport:
    """Apply blocks; failed blocks are reported, never raised."""
    report = ApplyReport()
    originals = originals if originals is not None else {}
    staged: dict[str, str] = {}

    for b in blocks:
        try:
            base = staged.get(b.file)
            if base is None:
                base = read_file(b.file)
                if b.file not in originals:
                    originals[b.file] = base if base is not None else ""
        except FileNotFoundError:
            report.failed.append((b, "file not found"))
            continue
        except OSError as e:
            report.failed.append((b, f"read error: {e}"))
            continue

        if base is None or not (b.search or "").strip():
            # Empty SEARCH writes the whole file (create or overwrite).
            # content.find("") is 0, so the fuzzy path would prepend — never that.
            if b.file not in originals:
                originals[b.file] = base if base is not None else ""
            try:
                write_file(b.file, b.replace)
            except Exception as e:
                report.failed.append((b, f"write error: {e}"))
                continue
            staged[b.file] = b.replace
            report.applied.append(b)
            continue

        pos = _fuzzy_find(base, b.search)
        if pos is None:
            report.failed.append((b, "SEARCH anchor not found"))
            continue
        end = pos + len(b.search)
        new = base[:pos] + b.replace + base[end:]
        try:
            write_file(b.file, new)
        except Exception as e:  # jailed writers may refuse; record, don't crash
            report.failed.append((b, f"write error: {e}"))
            continue
        staged[b.file] = new
        report.applied.append(b)

    return report


def blocks_to_review_payload(blocks: list[PatchBlock]) -> list[dict]:
    """Hunk list for the approval UI (req 10): one entry per block."""
    return [
        {
            "id": i,
            "file": b.file,
            "search": b.search,
            "replace": b.replace,
            "fingerprint": b.fingerprint,
        }
        for i, b in enumerate(blocks)
    ]


def select_blocks(blocks: list[PatchBlock], accepted_ids: list[int]) -> tuple[list[PatchBlock], list[PatchBlock]]:
    """Split into (accepted, rejected) after the user's hunk-level decision."""
    accepted = [b for i, b in enumerate(blocks) if i in accepted_ids]
    rejected = [b for i, b in enumerate(blocks) if i not in accepted_ids]
    return accepted, rejected
