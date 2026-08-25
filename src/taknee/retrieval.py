"""Retrieval v1 — per-workspace index: AST-ish chunks + lexical scoring.

Design (docs/06-plan-of-record.md D5):
  - chunks respect function/class boundaries (never whole-file dumps)
  - identifier-aware matching (camelCase/snake_case split) — code's real vocab
  - one import-hop expansion = cheap "execution flow" signal
  - index lives in <workspace>/.taknee/ — per-workspace isolation by construction

v2 (Day 4-5) adds local embeddings + reranker + LSP hooks behind the same
search() interface; scores here are fused with Reciprocal Rank Fusion then.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", ".taknee", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".hg", ".svn"}
TEXT_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".kt", ".sh", ".md", ".toml", ".yaml", ".yml", ".json", ".txt",
}

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PY_DEF = re.compile(r"^(async\s+def|def|class)\s+([A-Za-z_]\w*)", re.MULTILINE)
_JS_DEF = re.compile(r"^(export\s+)?(async\s+)?(function|class)\s+([A-Za-z_]\w*)|^(\s{2,})([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_IMPORT = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.,\s]+)|const\s+\w+\s*=\s*require\(['\"]([\w./-]+)['\"]\)|import\s+.*?from\s+['\"]([\w./@-]+)['\"])",
    re.MULTILINE,
)


@dataclass
class Chunk:
    path: str
    name: str
    line_start: int
    line_end: int
    text: str
    idents: set[str] = field(default_factory=set)

    def header(self) -> str:
        return f"{self.path}:{self.line_start}-{self.line_end} {self.name}"


class Index:
    """All state is derived from files under root; nothing outside can enter."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.file_hashes: dict[str, str] = {}
        self.chunks: list[Chunk] = []
        self.imports: dict[str, set[str]] = {}  # file -> set of local files

    # -- build ------------------------------------------------------------

    def build(self) -> int:
        """(Re)build the index; returns number of files indexed."""
        self.file_hashes.clear()
        self.chunks.clear()
        self.imports.clear()
        for path in _walk(self.root):
            rel = _rel(path, self.root)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self.file_hashes[rel] = _hash(text)
            self.chunks.extend(chunk_file(rel, text))
        self._build_imports()
        return len(self.file_hashes)

    def update_file(self, rel: str, text: str | None) -> None:
        """Incremental: re-chunk one file (text=None removes it)."""
        self.chunks = [c for c in self.chunks if c.path != rel]
        if text is None:
            self.file_hashes.pop(rel, None)
        else:
            self.file_hashes[rel] = _hash(text)
            self.chunks.extend(chunk_file(rel, text))
        self._build_imports()

    def _build_imports(self) -> None:
        self.imports = {f: set() for f in self.file_hashes}
        by_stem: dict[str, str] = {}
        for f in self.file_hashes:
            by_stem.setdefault(Path(f).stem, f)
        for f in list(self.file_hashes):
            try:
                text = (self.root / f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _IMPORT.finditer(text):
                for g in m.groups():
                    if not g:
                        continue
                    stem = g.split(",")[0].strip().split(".")[-1].strip()
                    target = by_stem.get(stem)
                    if target and target != f:
                        self.imports[f].add(target)

    # -- query ------------------------------------------------------------

    def search(self, query: str, k: int = 8) -> list[tuple[Chunk, float, str]]:
        """Score = BM25-lite over identifiers + Jaccard overlap + import-hop boost."""
        q = identifiers(query)
        if not q:
            return []
        scored: list[tuple[Chunk, float]] = []
        df: dict[str, int] = {}
        for c in self.chunks:
            for t in c.idents:
                df[t] = df.get(t, 0) + 1
        n = max(1, len(self.chunks))
        for c in self.chunks:
            bm = sum(
                _idf(t, df, n) * (c.text.lower().count(t) + 3 * (t in c.idents))
                for t in q
                if t in c.idents
            )
            jac = len(q & c.idents) / max(1, len(q | c.idents))
            s = bm / 10 + 2.5 * jac
            if s > 0:
                scored.append((c, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:k]

        # one import hop: files importing a top-hit's file get a second chance
        hop_bonus: dict[str, float] = {}
        if top:
            top_files = {c.path for c, _ in top[:3]}
            for f, targets in self.imports.items():
                if targets & top_files:
                    hop_bonus[f] = 1.2
            out: list[tuple[Chunk, float]] = []
            for c, s in scored:
                if c.path in hop_bonus and (c, s) not in top:
                    out.append((c, s + hop_bonus[c.path]))
            top = sorted(top + out, key=lambda x: x[1], reverse=True)[:k]

        reasons = {c.path: "import-hop" for c in hop_bonus}
        return [(c, round(s, 3), reasons.get(c.path, "direct")) for c, s in top]

    def repo_map(self, token_budget: int = 1200) -> str:
        """Skeleton view for planning: files with symbol names, budget-fitted."""
        per_file: dict[str, list[str]] = {}
        for c in self.chunks:
            per_file.setdefault(c.path, []).append(c.name)
        lines = [f"{p}: {', '.join(sorted(set(per_file[p])))}" for p in sorted(per_file)]
        out, used = [], 0
        for line in lines:
            cost = len(line) // 4 + 1
            if used + cost > token_budget:
                break
            out.append(line)
            used += cost
        return "\n".join(out)

    # -- persistence --------------------------------------------------------

    def save(self) -> None:
        d = self.root / ".taknee"
        d.mkdir(exist_ok=True)
        data = {
            "hashes": self.file_hashes,
            "chunks": [
                {
                    "path": c.path, "name": c.name, "line_start": c.line_start,
                    "line_end": c.line_end, "text": c.text, "idents": sorted(c.idents),
                }
                for c in self.chunks
            ],
            "imports": {f: sorted(v) for f, v in self.imports.items()},
        }
        (d / "index.json").write_text(json.dumps(data), encoding="utf-8")

    def load(self) -> bool:
        p = self.root / ".taknee" / "index.json"
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        self.file_hashes = data.get("hashes", {})
        self.chunks = [
            Chunk(c["path"], c["name"], c["line_start"], c["line_end"], c["text"], set(c["idents"]))
            for c in data.get("chunks", [])
        ]
        self.imports = {f: set(v) for f, v in data.get("imports", {}).items()}
        return True

    def stale_files(self) -> list[str]:
        """Files changed/added/removed on disk since the last build."""
        current: dict[str, str] = {}
        for path in _walk(self.root):
            rel = _rel(path, self.root)
            try:
                current[rel] = _hash(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        return [f for f, h in current.items() if self.file_hashes.get(f) != h] + [
            f for f in self.file_hashes if f not in current
        ]


# -- chunking ---------------------------------------------------------------

def chunk_file(rel: str, text: str) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    marks = _PY_DEF.findall(text) and _py_spans(lines) or _js_spans(lines)
    if not marks:  # fallback: windows with overlap
        marks = []
        step, size = 70, 80
        for start in range(0, max(1, len(lines) - step + 1), step):
            marks.append((f"L{start+1}", start, min(start + size, len(lines))))
    out = []
    for name, s, e in marks:
        body = "\n".join(lines[s:e])
        out.append(Chunk(rel, name, s + 1, e, body, identifiers(body)))
    return out


def _py_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    marks = []
    for i, line in enumerate(lines):
        m = re.match(r"^(async\s+def|def|class)\s+([A-Za-z_]\w*)", line)
        if m:
            marks.append((m.group(2), i, i + 60))  # cap def bodies at 60 lines
    if not marks:
        return []
    spans = []
    for j, (name, s, e) in enumerate(marks):
        nxt = marks[j + 1][1] if j + 1 < len(marks) else len(lines)
        spans.append((name, s, min(e, nxt if nxt > s else e)))
    return spans


def _js_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    marks = []
    for i, line in enumerate(lines):
        m = re.match(r"^(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_]\w*)", line)
        if m:
            marks.append((m.group(1), i, i + 60))
    if not marks:
        return []
    spans = []
    for j, (name, s, e) in enumerate(marks):
        nxt = marks[j + 1][1] if j + 1 < len(marks) else len(lines)
        spans.append((name, s, min(e, nxt if nxt > s else e)))
    return spans


# -- helpers ------------------------------------------------------------------

def identifiers(text: str) -> set[str]:
    out: set[str] = set()
    for w in _WORD.findall(text):
        out.add(w.lower())
        for part in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", w):
            if len(part) > 2:
                out.add(part.lower())
    return {t for t in out if len(t) > 2 and t not in {"the", "and", "for", "not", "def", "class", "return", "import"}}


def _idf(t: str, df: dict[str, int], n: int) -> float:
    import math

    return math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]


def _walk(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if SKIP_DIRS & set(p.parts):
            continue
        if p.suffix.lower() in TEXT_EXT or p.name.upper() in {"AGENTS.MD", "MAKEFILE"}:
            yield p


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()
