"""SEARCH/REPLACE parsing and application."""

from taknee import patches

SAMPLE = """I'll make the change now.

```src/app.py
<<<<<<< SEARCH
def greet(name):
    return "hi"
=======
def greet(name):
    return f"hello, {name}"
>>>>>>> REPLACE
```

And a second one:

```src/util.py
<<<<<<< SEARCH
x = 1
=======
x = 2
>>>>>>> REPLACE
```"""


def test_parse():
    blocks = patches.parse(SAMPLE)
    assert len(blocks) == 2
    assert blocks[0].file == "src/app.py"
    assert 'return "hi"' in blocks[0].search
    assert "hello" in blocks[0].replace


def test_parse_ignores_text_outside_blocks():
    blocks = patches.parse("no blocks here, just prose ```code``` maybe")
    assert blocks == []


def test_parse_accepts_language_fence_then_path():
    reply = """```python
src/app.py
<<<<<<< SEARCH
x = 1
=======
x = 2
>>>>>>> REPLACE
```"""
    blocks = patches.parse(reply)
    assert len(blocks) == 1
    assert blocks[0].file == "src/app.py"
    assert blocks[0].search == "x = 1"
    assert blocks[0].replace == "x = 2"


def _apply(blocks, files):
    return patches.apply_blocks(
        blocks,
        read_file=lambda p: files[p],
        write_file=lambda p, c: files.__setitem__(p, c),
    )


def test_apply_exact():
    files = {"src/app.py": 'def greet(name):\n    return "hi"\n'}
    report = _apply(patches.parse(SAMPLE)[:1], files)
    assert report.ok
    assert "hello" in files["src/app.py"]


def test_apply_fuzzy_whitespace():
    block = patches.PatchBlock("a.py", "def f():\n    return 1", "def f():\n    return 2")
    files = {"a.py": "def f( ):\n\treturn 1\n"}  # drifted spacing/tab
    report = _apply([block], files)
    assert report.ok, report.failed
    assert "return 2" in files["a.py"]


def test_empty_search_overwrites_existing_file():
    files = {"brief.md": "old outline\n"}
    block = patches.PatchBlock("brief.md", "", "# new brief\n")
    report = _apply([block], files)
    assert report.ok, report.failed
    assert files["brief.md"] == "# new brief\n"


def test_apply_missing_anchor_reports_not_crashes():
    block = patches.PatchBlock("a.py", "def missing():", "x")
    files = {"a.py": "def present():\n    pass\n"}
    report = _apply([block], files)
    assert not report.ok
    assert report.failed[0][1] == "SEARCH anchor not found"
    assert files["a.py"] == "def present():\n    pass\n"  # untouched


def test_missing_file_with_imagined_search_is_created():
    block = patches.PatchBlock(
        "src/app.js", "// placeholder that never existed", "export const ready = true;\n"
    )
    files = {}
    report = patches.apply_blocks(
        [block],
        read_file=lambda path: files.get(path),
        write_file=lambda path, content: files.__setitem__(path, content),
    )
    assert report.ok
    assert files["src/app.js"] == "export const ready = true;\n"


def test_apply_write_error_recorded():
    def boom(p, c):
        raise OSError("disk on fire")

    report = patches.apply_blocks(
        [patches.PatchBlock("a.py", "x", "y")],
        read_file=lambda p: "x",
        write_file=boom,
    )
    assert report.failed and "disk on fire" in report.failed[0][1]


def test_review_payload_and_selection():
    blocks = patches.parse(SAMPLE)
    payload = patches.blocks_to_review_payload(blocks)
    assert len(payload) == 2 and payload[0]["file"] == "src/app.py"
    accepted, rejected = patches.select_blocks(blocks, [0])
    assert accepted == [blocks[0]] and rejected == [blocks[1]]


def test_diff_report():
    files = {"a.py": "one\ntwo\n"}
    originals = {"a.py": "one\n"}
    report = patches.ApplyReport()
    d = report.diff(files, originals)
    assert "+two" in d


def test_parse_relaxed_search_replace():
    text = """Here is the change:
<<<<<<< SEARCH
old line
=======
new line
>>>>>>> REPLACE
"""
    blocks = patches.parse(text, default_file="config.py")
    assert len(blocks) == 1
    assert blocks[0].file == "config.py"
    assert blocks[0].search == "old line"
    assert blocks[0].replace == "new line"


def test_parse_code_fence_with_filename():
    text = """```./kernel_org_brief.md
# kernel.org snapshot
- Latest stable: 7.2.1
```"""
    blocks = patches.parse(text)
    assert len(blocks) == 1
    assert blocks[0].file == "./kernel_org_brief.md"
    assert "# kernel.org snapshot" in blocks[0].replace


def test_parse_fallback_default_file_for_raw_markdown():
    text = """# kernel.org snapshot
- Retrieval date: 2026-08-28
- Fetched URLs: https://www.kernel.org/
- Latest stable: 7.2.1
"""
    blocks = patches.parse(text, default_file="kernel_org_brief.md")
    assert len(blocks) == 1
    assert blocks[0].file == "kernel_org_brief.md"
    assert "Latest stable: 7.2.1" in blocks[0].replace
