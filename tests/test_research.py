"""Deterministic research-write grader — the checks that failed both GAIA evals.

Run 1 was the spec pasted into a file. Run 2 was crowd.loc.gov + System A/B/C
+ 2023-06-15. File existence is not in this module's success condition.
"""

from taknee import research

GAIA_PROMPT = """Create gaia_brief.md with this contract:
- ISO retrieval date
- Every URL actually fetched
- Top 3 publicly reported GAIA systems and scores
- One paragraph on why scores are not comparable across writeups
- A table: system | score | date of score | source URL
Hard rules: do not invent numbers; if unverified write UNKNOWN; list only pages that were fetched; stop after a real file exists.
Target entity: the Meta / Hugging Face GAIA benchmark for general AI assistants (arXiv 2311.12983), not ESA Gaia.
"""

HF = "https://huggingface.co/spaces/gaia-benchmark/leaderboard"
EVIDENCE = (
    f"URL: {HF}\n"
    "GAIA leaderboard. HAL Generalist Agent + Claude Sonnet 4.5 74.55% "
    "(September 2025). Human respondents 92%."
)


def test_classifies_gaia_brief_as_research_write():
    assert research.is_research_write(GAIA_PROMPT)
    assert research.is_gaia_assistant_task(GAIA_PROMPT)
    assert research.requested_files(GAIA_PROMPT) == ["gaia_brief.md"]


def test_coding_and_generic_create_are_not_research_writes():
    assert not research.is_research_write("make greet say hello with the name")
    assert not research.is_research_write("search the web and create solutions/README.md")


def test_search_queries_are_not_the_instruction_block():
    queries = research.search_queries(GAIA_PROMPT)
    assert queries
    assert GAIA_PROMPT not in queries
    assert all(len(q) < len(GAIA_PROMPT) for q in queries)
    assert any("huggingface" in q.lower() or "gaia" in q.lower() for q in queries)


def test_entity_lock_drops_loc_and_esa_and_seeds_hf():
    found = [
        "https://gaia.crowd.loc.gov/",
        "https://sci.esa.int/gaia",
        "https://example.com/blog",
    ]
    urls = research.select_fetch_urls(GAIA_PROMPT, found)
    assert not any("crowd.loc.gov" in u for u in urls)
    assert not any("esa.int" in u for u in urls)
    assert any("huggingface.co" in u or "arxiv.org" in u for u in urls)


def test_run1_template_echo_fails():
    body = GAIA_PROMPT  # plan-as-output
    grade = research.grade_research_write(
        prompt=GAIA_PROMPT,
        path="giai brief.md",
        body=body,
        search_count=0,
        fetch_count=0,
        fetched_urls=[],
        fetched_text="",
        today="2026-08-28",
    )
    assert not grade.ok
    joined = " ".join(grade.reasons).lower()
    assert "echo" in joined or "instruction" in joined
    assert "web_search" in joined
    assert "giai brief.md" in " ".join(grade.reasons) or "gaia_brief.md" in " ".join(grade.reasons)


def test_run2_fabrication_fails():
    body = """Date: 2023-06-15
Sources: https://gaia.crowd.loc.gov/
System A 85 · System B 78 · System C 92
"""
    grade = research.grade_research_write(
        prompt=GAIA_PROMPT,
        path="gaia_brief.md",
        body=body,
        search_count=1,
        fetch_count=1,
        fetched_urls=[HF],
        fetched_text=EVIDENCE,
        today="2026-08-28",
    )
    assert not grade.ok
    joined = " ".join(grade.reasons).lower()
    assert "system a" in joined or "placeholder" in joined
    assert "crowd.loc.gov" in joined or "wrong-entity" in joined
    assert "2023-06-15" in joined


def test_grounded_brief_passes():
    body = f"""# GAIA snapshot
Retrieval date: 2026-08-28
Fetched:
- {HF}

| system | score | date of score | source URL |
| HAL Generalist Agent + Claude Sonnet 4.5 | 74.55% | 2025-09-01 | {HF} |

Scores are not comparable across writeups because scaffolding, validation vs test splits, and self-reported numbers differ.
"""
    grade = research.grade_research_write(
        prompt=GAIA_PROMPT,
        path="gaia_brief.md",
        body=body,
        search_count=1,
        fetch_count=1,
        fetched_urls=[HF],
        fetched_text=EVIDENCE + " 2025-09-01",
        today="2026-08-28",
    )
    assert grade.ok, grade.reasons


def test_unknown_without_invented_scores_is_acceptable():
    body = """Retrieval date: 2026-08-28
Fetched pages did not include a stable top-3 ranking I could quote.
Top systems: UNKNOWN
"""
    grade = research.grade_research_write(
        prompt=GAIA_PROMPT,
        path="gaia_brief.md",
        body=body,
        search_count=2,
        fetch_count=2,
        fetched_urls=[HF],
        fetched_text=EVIDENCE,
        today="2026-08-28",
    )
    assert grade.ok, grade.reasons


def test_prioritizes_explicit_prompt_urls():
    prompt = """Write ./kernel_org_brief.md
Rules:
- Forbidden in the file: "System A"
Process:
1. Search or open https://www.kernel.org/
"""
    queries = research.search_queries(prompt)
    assert "System A" not in queries

    urls = research.select_fetch_urls(prompt, ["https://other-searched-url.com"])
    assert urls[0] == "https://www.kernel.org/"
