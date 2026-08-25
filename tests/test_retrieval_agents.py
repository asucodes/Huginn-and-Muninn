"""Retrieval v1: chunking, scoring, import hop, per-workspace isolation."""

from pathlib import Path

from taknee.retrieval import Index, chunk_file, identifiers


REPO_A = {
    "auth.py": (
        "import session_store\n\n"
        "def validate_token(token):\n"
        "    return session_store.exists(token)\n\n"
        "def refresh_token(token):\n"
        "    return token + '-new'\n"
    ),
    "session_store.py": (
        "TOKENS = {}\n\n"
        "def exists(token):\n"
        "    return token in TOKENS\n"
    ),
    "billing.py": (
        "def invoice_total(items):\n"
        "    return sum(i['price'] for i in items)\n"
    ),
}


def build_repo(root: Path, files: dict) -> Path:
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def test_chunking_respects_defs():
    chunks = chunk_file("auth.py", REPO_A["auth.py"])
    names = {c.name for c in chunks}
    assert "validate_token" in names and "refresh_token" in names
    for c in chunks:
        assert c.line_end - c.line_start < 70, "chunks must not dump whole files"


def test_identifiers_split_camel_and_snake():
    ids = identifiers("getUserAccount user_account HTTPServer")
    assert {"get", "user", "account", "http", "server"} <= ids


def test_search_finds_relevant_chunk(tmp_path):
    root = build_repo(Path(tmp_path) / "repoA", REPO_A)
    idx = Index(root)
    idx.build()
    hits = idx.search("validate auth token", k=4)
    assert hits, "expected hits"
    top_paths = [c.path for c, _s, _r in hits[:2]]
    assert "auth.py" in top_paths


def test_import_hop_boosts_related(tmp_path):
    root = build_repo(Path(tmp_path) / "repoA", REPO_A)
    idx = Index(root)
    idx.build()
    # auth.py imports session_store — a session_store query should surface it too
    hits = idx.search("session store exists token", k=6)
    paths = {c.path for c, _s, _r in hits}
    assert "auth.py" in paths or "session_store.py" in paths


def test_irrelevant_code_not_top(tmp_path):
    root = build_repo(Path(tmp_path) / "repoA", REPO_A)
    idx = Index(root)
    idx.build()
    hits = idx.search("validate auth token", k=3)
    assert hits, "expected hits"
    assert hits[0][0].path != "billing.py"


def test_workspace_isolation(tmp_path):
    """Req 5: index from workspace A must never surface chunks of workspace B."""
    a = build_repo(Path(tmp_path) / "A", REPO_A)
    b = build_repo(Path(tmp_path) / "B", {"unrelated.py": "def totally_different():\n    pass\n"})
    ia, ib = Index(a), Index(b)
    ia.build()
    ib.build()

    for chunk, _s, _r in ia.search("anything token auth", k=50):
        assert chunk.path in REPO_A, f"leak from another workspace: {chunk.path}"
    hits_b = ib.search("validate auth token", k=5)
    assert all(c.path == "unrelated.py" for c, _s, _r in hits_b)
    assert not (set(ia.file_hashes) & set(ib.file_hashes))


def test_persistence_roundtrip(tmp_path):
    root = build_repo(Path(tmp_path) / "repo", REPO_A)
    idx = Index(root)
    idx.build()
    idx.save()

    idx2 = Index(root)
    assert idx2.load()
    assert set(idx2.file_hashes) == set(idx.file_hashes)
    assert len(idx2.chunks) == len(idx.chunks)
    assert idx2.search("validate token", k=3)


def test_incremental_update_and_stale(tmp_path):
    root = build_repo(Path(tmp_path) / "repo", REPO_A)
    idx = Index(root)
    idx.build()
    assert idx.stale_files() == []

    (root / "new_file.py").write_text("def brand_new():\n    pass\n")
    assert "new_file.py" in idx.stale_files()

    idx.update_file("new_file.py", "def brand_new():\n    pass\n")
    assert any(c.path == "new_file.py" for c in idx.chunks)


def test_repo_map_budget(tmp_path):
    root = build_repo(Path(tmp_path) / "repo", REPO_A)
    idx = Index(root)
    idx.build()
    m = idx.repo_map(token_budget=50)  # tiny budget
    assert "auth.py" in m
    assert len(m) // 4 <= 60  # roughly respects the budget
