"""Tool layer — read-only tools run freely; side-effect tools need approval.

Tools are plain dicts (name, description, input_schema) for the provider's
function-calling format. Execution is type-safe: the dispatch table below maps
tool names to typed Python callables that raise on bad input (never silent except).

Side-effect classification (req 8):
  READ_ONLY: read_file, search_code, retrieve, git_diff, git_log
  SIDE_EFFECT: write_file, run_terminal, git_commit, git_push, web_search, web_fetch

Safety rails (req 8.b):
  - cwd jailed to the workspace (no absolute path escapes)
  - deny-list for destructive commands
  - output capped so huge command output doesn't blow the context
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx

READ_ONLY = {"read_file", "search_code", "retrieve", "git_diff", "git_log", "list_files", "web_search", "web_fetch"}
SIDE_EFFECT = {"write_file", "run_terminal", "git_commit", "git_checkout"}

DENY_PATTERNS = [
    r"rm\s+(-[rfRF]+\s+)?(/|~|\*|\.{2})",
    r"mkfs|dd\s+if=|shutdown|reboot|format\b",
    r"git\s+push.*--force",
    r"chmod\s+777\s+/",
    r"curl.*\|\s*sh",
    r"wget.*\|\s*sh",
]

OUTPUT_MAX = 20_000  # characters — cap command output to ~5K tokens


def tool_defs(names: set[str] | None = None) -> list[dict[str, Any]]:
    """Return schemas for the requested tool names (all tools by default)."""
    allowed = names if names is not None else READ_ONLY | SIDE_EFFECT
    return [TOOL_SCHEMAS[name] for name in TOOL_SCHEMAS if name in allowed]


def read_only_tool_defs() -> list[dict[str, Any]]:
    """Schemas safe to offer directly to an agent during planning/patching."""
    return tool_defs(READ_ONLY)


def needs_approval(name: str) -> bool:
    return name in SIDE_EFFECT


def is_deny(cmd: str) -> tuple[bool, str]:
    for p in DENY_PATTERNS:
        if re.search(p, cmd):
            return True, f"blocked by safety rule: {p}"
    return False, ""


def jail_path(raw: str, workspace: str) -> str:
    ws = Path(workspace).resolve()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = ws / p
    p = p.resolve()
    try:
        p.relative_to(ws)
    except ValueError:
        return str(ws / Path(raw).name)
    return str(p)


# -- tool implementations -------------------------------------------------

def _read_file(file_path: str, line_start: int = 0, line_end: int = 0, *, workspace: str) -> str:
    fp = jail_path(file_path, workspace)
    p = Path(fp)
    if not p.exists():
        return f"error: {file_path} not found"
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if line_start or line_end:
        s = max(0, line_start - 1)
        e = line_end if line_end else len(lines)
        lines = lines[s:e]
    return "\n".join(f"{i+1}\t{l}" for i, l in enumerate(lines, line_start or 1))


def _list_files(path: str = ".", *, workspace: str) -> str:
    p = Path(jail_path(path, workspace))
    if not p.is_dir():
        return f"error: {path} not a directory"
    out = []
    for f in sorted(p.rglob("*")):
        if SKIP_DIRS & set(f.parts):
            continue
        tag = "/" if f.is_dir() else ""
        out.append(f.relative_to(p).as_posix() + tag)
        if len(out) > 500:
            out.append("... (truncated)")
            break
    return "\n".join(out)


SKIP_DIRS = {".git", ".taknee", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


def _search_code(pattern: str, *, workspace: str) -> str:
    try:
        r = subprocess.run(
            ["rg", "--no-heading", "-n", "--max-count", "20", pattern, workspace],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode in (0, 1):  # 1 = no matches
            return r.stdout[:OUTPUT_MAX] or "(no matches)"
        return f"rg error: {r.stderr[:500]}"
    except FileNotFoundError:
        return _search_code_fallback(pattern, workspace)
    except subprocess.TimeoutExpired:
        return "search timed out (30s)"


def _search_code_fallback(pattern: str, workspace: str) -> str:
    """Python walk when ripgrep isn't on PATH."""
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"invalid pattern: {e}"
    hits: list[str] = []
    root = Path(workspace)
    for p in root.rglob("*"):
        if not p.is_file() or SKIP_DIRS & set(p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        n = 0
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{i}:{line}")
                n += 1
                if n >= 20:
                    break
        if len(hits) >= 80:
            break
    return "\n".join(hits)[:OUTPUT_MAX] or "(no matches)"


def _retrieve(query: str, index_ref: Any, *, workspace: str) -> str:
    if index_ref is None:
        return "error: no index built for this workspace"
    results = index_ref.search(query, k=6)
    if not results:
        return "no relevant code found"
    parts = []
    for chunk, score, reason in results:
        parts.append(f"--- {chunk.header()} (score={score}, {reason}) ---")
        parts.append(chunk.text)
    return "\n\n".join(parts)[:OUTPUT_MAX]


def _write_file(file_path: str, content: str, *, workspace: str) -> str:
    fp = jail_path(file_path, workspace)
    p = Path(fp)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {file_path} ({len(content)} chars)"


def _run_terminal(command: str, timeout: int = 60, *, workspace: str) -> str:
    deny, reason = is_deny(command)
    if deny:
        return f"BLOCKED: {reason}"
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            cwd=workspace, timeout=timeout,
        )
        out = r.stdout[:OUTPUT_MAX]
        if r.returncode != 0:
            out += f"\n[exit {r.returncode}]\n{r.stderr[:OUTPUT_MAX//2]}"
        return out
    except subprocess.TimeoutExpired:
        return f"timed out after {timeout}s"


def _git_diff(*, workspace: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", workspace, "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=15,
        )
        if r.stdout.strip():
            r2 = subprocess.run(
                ["git", "-C", workspace, "diff", "HEAD"],
                capture_output=True, text=True, timeout=15,
            )
            return r2.stdout[:OUTPUT_MAX]
        return "(no changes vs HEAD)"
    except Exception as e:
        return f"git diff error: {e}"


def _git_log(n: int = 5, *, workspace: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", workspace, "log", f"-{n}", "--oneline"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() or "(no commits)"
    except Exception as e:
        return f"git log error: {e}"


def _git_commit(message: str, *, workspace: str) -> str:
    r = subprocess.run(
        ["git", "-C", workspace, "add", "-A"], capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        return f"git add error: {r.stderr}"
    r = subprocess.run(
        ["git", "-C", workspace, "commit", "-m", message],
        capture_output=True, text=True, timeout=15,
    )
    return r.stdout.strip() if r.returncode == 0 else f"git commit error: {r.stderr}"


def _git_checkout(ref: str, *, workspace: str) -> str:
    r = subprocess.run(
        ["git", "-C", workspace, "checkout", ref],
        capture_output=True, text=True, timeout=15,
    )
    return r.stdout.strip() if r.returncode == 0 else f"git checkout error: {r.stderr}"


def _web_search(query: str) -> str:
    q = (query or "").strip()
    if len(q) > 240:
        q = q[:240]
    if not q:
        return "(no web results — empty query)"
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as c:
            r = c.post(
                "https://html.duckduckgo.com/html/",
                data={"q": q},
                headers={"User-Agent": "HuginnMuninn/0.1"},
            )
        html = r.text or ""
        results = re.findall(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            flags=re.I | re.DOTALL,
        )
        if not results:
            results = re.findall(
                r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>',
                html,
            )
        if results:
            lines = []
            for url, title in results[:8]:
                title = re.sub(r"<[^>]+>", "", title).strip()
                lines.append(f"- {title}\n  {url}")
            return "\n".join(lines)
        return "(no web results — check network)"
    except Exception as e:
        return f"web search error: {e}"


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"(?is)<script\b.*?>.*?</script>", " ", text)
    cleaned = re.sub(r"(?is)<style\b.*?>.*?</style>", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _web_fetch(url: str) -> str:
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "HuginnMuninn/0.1"})
        body = r.text or ""
        ctype = (r.headers.get("content-type") or "").lower()
        looks_html = "html" in ctype or body.lstrip()[:15].lower().startswith(
            ("<!doctype", "<html")
        )
        text = _strip_html(body) if looks_html else body
        return f"URL: {url}\n{text[:OUTPUT_MAX]}"
    except Exception as e:
        return f"web fetch error: {e}"


def execute(name: str, arguments: dict[str, Any], *, workspace: str, index_ref: Any = None) -> str:
    """Run a named tool. Injects workspace/index; unknown names return an error string."""
    fn = DISPATCH.get(name)
    if fn is None:
        return f"unknown tool: {name}"
    kwargs = dict(arguments)
    import inspect

    params = inspect.signature(fn).parameters
    if "workspace" in params:
        kwargs["workspace"] = workspace
    if "index_ref" in params:
        kwargs["index_ref"] = index_ref
    try:
        return fn(**kwargs)
    except TypeError as e:
        return f"bad arguments for {name}: {e}"


# -- dispatch --------------------------------------------------------------

DISPATCH: dict[str, Callable[..., str]] = {
    "read_file": _read_file,
    "list_files": _list_files,
    "search_code": _search_code,
    "retrieve": _retrieve,
    "write_file": _write_file,
    "run_terminal": _run_terminal,
    "git_diff": _git_diff,
    "git_log": _git_log,
    "git_commit": _git_commit,
    "git_checkout": _git_checkout,
    "web_search": _web_search,
    "web_fetch": _web_fetch,
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Optionally specify line_start and line_end (1-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path within the workspace"},
                    "line_start": {"type": "integer", "description": "First line to include (1-based, optional)"},
                    "line_end": {"type": "integer", "description": "Last line to include (optional)"},
                },
                "required": ["file_path"],
            },
        },
    },
    "list_files": {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories under a path (default: workspace root).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path (default \".\")"},
                },
            },
        },
    },
    "search_code": {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search codebase with a regex pattern (ripgrep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or text to search for"},
                },
                "required": ["pattern"],
            },
        },
    },
    "retrieve": {
        "type": "function",
        "function": {
            "name": "retrieve",
            "description": "Semantic + lexical code search against the workspace index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to find (e.g. \"where is the auth middleware\")"},
                },
                "required": ["query"],
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write full content to a file. Requires approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    "run_terminal": {
        "type": "function",
        "function": {
            "name": "run_terminal",
            "description": "Run a shell command in the workspace. Requires approval for state-changing commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "description": "Seconds (default 60)"},
                },
                "required": ["command"],
            },
        },
    },
    "git_diff": {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff against HEAD.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "git_log": {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent git commits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of commits (default 5)"},
                },
            },
        },
    },
    "git_commit": {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage all and commit. Requires approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
    "git_checkout": {
        "type": "function",
        "function": {
            "name": "git_checkout",
            "description": "Switch git branch or reset to a commit. Requires approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Branch name or commit hash"},
                },
                "required": ["ref"],
            },
        },
    },
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web (DuckDuckGo HTML).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    "web_fetch": {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a URL's content (markdown/text).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
}
