"""AGENTS.md parsing: test/build/style extraction (req 9)."""

from taknee.agents_md import parse


SAMPLE = """# Taknee project rules

## Build and test
- Python 3.11+ via uv. Never call a global python.
- Kernel tests: `uv run pytest -q`

## Style
- Small modules, typed public functions
- No silent except blocks

## Folder conventions
src/taknee is the kernel; apps/extension is UI only.
"""


def test_extracts_test_command():
    rules = parse(SAMPLE)
    assert rules.test_cmd == "uv run pytest -q"


def test_extracts_style_rules():
    rules = parse(SAMPLE)
    assert any("typed" in r for r in rules.style_rules)
    assert any("except" in r for r in rules.style_rules)


def test_instructions_kept():
    rules = parse(SAMPLE)
    assert any("kernel" in i for i in rules.instructions)


def test_pinned_digest_compact():
    rules = parse(SAMPLE)
    digest = rules.pinned_digest()
    assert "pytest" in digest and "typed" in digest
    assert len(digest) < 300  # sized to pin into any context


def test_empty_and_garbage_safe():
    rules = parse("")
    assert rules.test_cmd == "" and rules.pinned_digest() == ""
    rules2 = parse("no headings at all\njust text")
    assert rules2 is not None


def test_build_command_variant():
    text = "# Build\n\n```bash\nnpm run build\n```\n"
    rules = parse(text)
    assert "npm" in rules.build_cmd
