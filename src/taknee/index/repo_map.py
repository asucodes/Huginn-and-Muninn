"""Repo Map Builder — compact, token-budgeted symbol summary of the codebase.

Uses Python stdlib `ast` module for zero-dependency Python parsing,
with graceful fallback to simple file listing for other languages.

Architecture inspired by Aider repomap concept (Apache-2.0, Aider-AI/aider).
This is a simplified, dependency-free adaptation — no Tree-sitter or ctags needed.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import NamedTuple

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".taknee", "out", "dist", ".pytest_cache"}
SKIP_EXTS = {".pyc", ".pyo", ".lock", ".png", ".jpg", ".svg", ".ico", ".woff", ".bin"}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java", ".c", ".cpp", ".cs"}


class Symbol(NamedTuple):
    file: str      # relative path
    kind: str      # "def" | "class" | "method"
    name: str
    line: int


def extract_python_symbols(source: str, relpath: str) -> list[Symbol]:
    """Extracts function and class definitions from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    symbols: list[Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            symbols.append(Symbol(relpath, "def", node.name, node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(relpath, "class", node.name, node.lineno))
    symbols.sort(key=lambda s: s.line)
    return symbols


def build_repo_map(root: Path, token_budget: int = 2000) -> str:
    """Builds a compact symbol map of the repository within a token budget.

    Returns a plain-text tree of files and their top-level symbols,
    suitable for inclusion in a system prompt to orient an agent.

    The map is pruned to stay within token_budget (4 chars ≈ 1 token).
    """
    root = root.resolve()
    char_budget = token_budget * 4
    lines: list[str] = []
    char_count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            relpath = str(fpath.relative_to(root)).replace("\\", "/")
            ext = fpath.suffix.lower()

            if ext in SKIP_EXTS:
                continue
            if ext not in CODE_EXTS and ext not in {".md", ".toml", ".json"}:
                continue

            # File header line
            file_line = f"{relpath}"
            if char_count + len(file_line) + 1 > char_budget:
                lines.append("  ... (budget reached)")
                return "\n".join(lines)

            symbols: list[Symbol] = []
            if ext == ".py":
                try:
                    source = fpath.read_text(errors="replace")
                    symbols = extract_python_symbols(source, relpath)
                except Exception:
                    pass

            lines.append(file_line)
            char_count += len(file_line) + 1

            for sym in symbols[:12]:  # Cap per-file to avoid map bloat
                sym_line = f"  {'class' if sym.kind == 'class' else 'def'} {sym.name}  (L{sym.line})"
                if char_count + len(sym_line) + 1 > char_budget:
                    lines.append("  ...")
                    return "\n".join(lines)
                lines.append(sym_line)
                char_count += len(sym_line) + 1

    return "\n".join(lines) if lines else "(empty repository)"
