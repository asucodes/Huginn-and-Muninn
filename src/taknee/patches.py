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


RELAXED_BLOCK_RE = re.compile(
    r"(?:```+[^\r\n`]*\r?\n)?"
    r"(?:(?:File|Path|Filename)?:\s*(?P<named_path>[^\r\n`<]+)\r?\n)?"
    r"(?:(?P<body_path>[^\r\n`<]+)\r?\n)?"
    r"<{3,}\s*SEARCH\r?\n(?P<search>.*?)(?:\r?\n)?={3,}\r?\n"
    r"(?P<replace>.*?)\r?\n>{3,}\s*REPLACE",
    re.DOTALL | re.IGNORECASE,
)

_FILE_EXTENSIONS = (
    ".py", ".md", ".txt", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".sh", ".bash", ".sql", ".rs", ".go",
)


_PLACEHOLDER_FILENAMES = {
    "<exact-filename>", "<filename>", "<file-name>", "<exact_filename>",
    "<path>", "<file_path>", "<relative/file/path>", "<exact-file-name>",
    "exact-filename", "filename", "file", "path", "exact_filename", "<full file>",
}


def _is_valid_path(p: str) -> bool:
    if not p:
        return False
    p = p.strip()
    if p.lower() in _PLACEHOLDER_FILENAMES:
        return False
    if p.endswith(":") or p.endswith("?") or p.endswith("!"):
        return False
    if " " in p:
        return False
    if any(p.endswith(ext) for ext in _FILE_EXTENSIONS) or "/" in p or "\\" in p:
        return True
    return False


def parse(text: str, default_file: str | None = None) -> list[PatchBlock]:
    """Parse SEARCH/REPLACE blocks with strict, relaxed, and fallback heuristics."""
    if not text or not text.strip():
        return []

    blocks: list[PatchBlock] = []
    # 1. Strict aider-style block format
    for m in BLOCK_RE.finditer(text):
        header = m.group("header").strip()
        body_path = (m.group("body_path") or "").strip()
        path = body_path or header
        if path.lower() in _PLACEHOLDER_FILENAMES:
            path = default_file or ""
        if not path or (header.lower() in _FENCE_LANGUAGES and not body_path):
            if default_file:
                path = default_file
            else:
                continue
        blocks.append(PatchBlock(path, m.group("search"), m.group("replace")))
    if blocks:
        return blocks

    # 2. Relaxed SEARCH/REPLACE format
    for m in RELAXED_BLOCK_RE.finditer(text):
        named = (m.group("named_path") or "").strip()
        body = (m.group("body_path") or "").strip()
        path = ""
        if _is_valid_path(named):
            path = named
        elif _is_valid_path(body):
            path = body
        else:
            path = default_file or ""
        if path.lower() in _FENCE_LANGUAGES or path.lower() in _PLACEHOLDER_FILENAMES:
            path = default_file or ""
        if path:
            blocks.append(PatchBlock(path, m.group("search"), m.group("replace")))
    if blocks:
        return blocks

    # 3. Code fence with path header (e.g. ```./kernel_org_brief.md\n...\n```)
    fence_matches = list(re.finditer(r"```+([^\r\n`]*)\r?\n(.*?)```+", text, re.DOTALL))
    for fm in fence_matches:
        hdr = fm.group(1).strip()
        body = fm.group(2)
        # Check if header contains a recognizable filename
        target_path = None
        for token in hdr.split():
            clean_tok = token.strip("./\\\"'")
            if any(token.endswith(ext) for ext in _FILE_EXTENSIONS) or "/" in token or "\\" in token:
                target_path = token
                break
        if not target_path and default_file:
            target_path = default_file
        if target_path and target_path.lower() not in _FENCE_LANGUAGES:
            blocks.append(PatchBlock(target_path, "", body if body.endswith("\n") else body + "\n"))
    if blocks:
        return blocks

    # 4. Fallback for single requested file when output is raw content or single markdown block
    if default_file:
        content = text.strip()
        # If wrapped in single outer code fence, unwrap it
        if content.startswith("```") and content.endswith("```"):
            lines = content.splitlines()
            if len(lines) >= 2:
                content = "\n".join(lines[1:-1]).strip()
        if content:
            blocks.append(PatchBlock(default_file, "", content + "\n"))

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
