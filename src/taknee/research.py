"""Research-write harness: search, fetch, bind claims, then write.

The coding pipeline (retrieve → localize → patch → apply → verify) treats a
new file plus a skipped test command as success. That is how a research brief
becomes plan-as-output or a fabricated leaderboard: the model never has to
observe a page, and nobody reads the file back.

This module is the missing control system for that task class. The model does
not pick the next tool. The harness owns queries, fetches, entity lock, the
clock, and the done-check. File existence is not success.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

# Coaching sentences from the GAIA eval spec. A body that still contains these
# is the instruction outline, not a brief.
TEMPLATE_ECHO_PHRASES = (
    "every url actually fetched",
    "top 3 publicly reported",
    "if unverified write unknown",
    "do not invent numbers",
    "hard rules:",
    "stop after a real file exists",
    "iso retrieval date",
    "one paragraph on why scores are not comparable",
    "list only pages that were fetched",
    "do not treat file existence as success",
)

PLACEHOLDER_SYSTEMS = re.compile(r"\bSystem\s+[ABC]\b", re.I)
SCORE_RE = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*%")
ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
URL_RE = re.compile(r"https?://[^\s)\]>\"'<>]+")
FILE_RE = re.compile(r"\b([A-Za-z0-9_./-]+\.(?:md|txt|html))\b")

# Eval run 2 invented this date and this LoC hostname. Reject unless a fetched
# page itself contains them.
FABRICATED_DATES = ("2023-06-15",)

GAIA_ASSISTANT_HINTS = (
    "2311.12983",
    "gaia-benchmark",
    "gaia_brief",
    "general ai assistant",
    "hugging face gaia",
    "huggingface gaia",
    "meta / hugging face gaia",
    "meta/hugging face gaia",
)

GAIA_WRONG_HOSTS = (
    "crowd.loc.gov",
    "cosmos.esa.int",
    "sci.esa.int",
    "gea.esac.esa.int",
    "gaia.esa.int",
    "esa.int",
    "gaiainc.com",
    "gaia.com",
)

GAIA_RIGHT_HOSTS = (
    "huggingface.co",
    "hf.space",
    "arxiv.org",
    "ai.meta.com",
)

GAIA_SEED_URLS = (
    "https://huggingface.co/gaia-benchmark",
    "https://huggingface.co/spaces/gaia-benchmark/leaderboard",
    "https://huggingface.co/datasets/gaia-benchmark/results_public",
    "https://arxiv.org/abs/2311.12983",
)

GAIA_QUERIES = (
    "GAIA benchmark Hugging Face leaderboard general AI assistants",
    "GAIA a benchmark for general AI assistants arXiv 2311.12983",
    "site:huggingface.co gaia-benchmark leaderboard",
)

STRONG_RESEARCH_HINTS = (
    "leaderboard",
    "do not invent",
    "if unverified",
    "urls actually fetched",
    "source url",
    "publicly reported",
    "live page",
    "retrieval date",
    "fetched",
    "snapshot",
    "do not treat file existence",
)


@dataclass
class Grade:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def iso_today() -> str:
    return date.today().isoformat()


def is_gaia_assistant_task(prompt: str) -> bool:
    """True only for the Meta/HF GAIA assistant benchmark, not ESA Gaia."""
    p = prompt.lower()
    if "2311.12983" in p or "gaia_brief" in p or "gaia-benchmark" in p:
        return True
    if "gaia" in p and any(
        h in p
        for h in (
            "leaderboard",
            "hugging face",
            "huggingface",
            "general ai",
            "assistant",
            "meta",
        )
    ):
        return True
    return False


def is_research_write(prompt: str) -> bool:
    """A write whose claims must be bound to live search+fetch observations."""
    p = prompt.lower()
    if not FILE_RE.search(prompt):
        return False
    if is_gaia_assistant_task(prompt):
        return True
    return any(h in p for h in STRONG_RESEARCH_HINTS)


def requested_files(prompt: str) -> list[str]:
    seen: list[str] = []
    for match in FILE_RE.findall(prompt):
        name = match.replace("\\", "/").lstrip("./")
        if name not in seen:
            seen.append(name)
    return seen


def search_queries(prompt: str) -> list[str]:
    """Harness-owned queries. Never dump the instruction block into the search box."""
    if is_gaia_assistant_task(prompt):
        return list(GAIA_QUERIES)
    queries: list[str] = []
    # Avoid quoted strings that are forbidden/prohibited instructions (e.g. Forbidden: "System A")
    for match in re.finditer(r'(?:(forbidden|not|never|avoid|no|like|without|placeholder)\s+[^."\n]{0,20})?"([^"]{3,120})"', prompt, re.IGNORECASE):
        neg = match.group(1)
        q = match.group(2).strip()
        if not neg and len(q) >= 4 and q not in queries:
            queries.append(q)
    for path in requested_files(prompt):
        stem = re.sub(r"[_-]+", " ", Path(path).stem).strip()
        if stem and stem not in queries:
            queries.append(stem)
    if not queries:
        first = re.split(r"[.\n]", prompt, maxsplit=1)[0].strip()
        queries.append(first[:160] or prompt[:160])
    return [q for q in queries if q][:4]


def urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(".,;:)>\"'")
        if url not in urls:
            urls.append(url)
    return urls


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_wrong_entity_url(prompt: str, url: str) -> bool:
    if not is_gaia_assistant_task(prompt):
        return False
    host = _host(url)
    return any(bad == host or host.endswith("." + bad) or bad in host for bad in GAIA_WRONG_HOSTS)


def select_fetch_urls(prompt: str, found: list[str]) -> list[str]:
    """Keep on-entity URLs; prioritize explicit prompt URLs; seed GAIA pages if needed."""
    kept: list[str] = []
    # 1. Explicit URLs written in the prompt get top priority
    for url in urls_from_text(prompt):
        if url not in kept and not is_wrong_entity_url(prompt, url):
            kept.append(url)
    # 2. URLs discovered from web search
    for url in found:
        if is_wrong_entity_url(prompt, url):
            continue
        if url not in kept:
            kept.append(url)
    if is_gaia_assistant_task(prompt):
        preferred = [
            u for u in kept if any(h in _host(u) or h in u.lower() for h in GAIA_RIGHT_HOSTS)
        ]
        kept = preferred or kept
        for seed in GAIA_SEED_URLS:
            if seed not in kept:
                kept.append(seed)
    return kept[:6]


def _prompt_echo(prompt: str, body: str) -> bool:
    body_l = body.lower()
    if any(phrase in body_l for phrase in TEMPLATE_ECHO_PHRASES):
        return True
    prompt_lines = [ln.strip() for ln in prompt.splitlines() if len(ln.strip()) > 40]
    if len(prompt_lines) < 2:
        return False
    hits = sum(1 for ln in prompt_lines if ln.lower() in body_l)
    return hits >= max(2, len(prompt_lines) // 3)


def _score_in_evidence(token: str, evidence: str) -> bool:
    t = token.strip().rstrip("%")
    if t and t in evidence:
        return True
    try:
        value = float(t)
    except ValueError:
        return False
    as_pct = f"{value:g}%"
    if as_pct in evidence:
        return True
    if 0 < value <= 1:
        pct = f"{value * 100:.2f}".rstrip("0").rstrip(".")
        return pct in evidence or f"{pct}%" in evidence
    return False


def _norm_url(u: str) -> str:
    u = u.strip().rstrip("/")
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u


def _url_was_fetched(url: str, fetched_urls: list[str]) -> bool:
    if url in fetched_urls:
        return True
    norm_url = _norm_url(url)
    norm_fetched = [_norm_url(f) for f in fetched_urls]
    if norm_url in norm_fetched:
        return True
    return any(norm_url.startswith(f) or f.startswith(norm_url) for f in norm_fetched if f)


def grade_research_write(
    *,
    prompt: str,
    path: str,
    body: str,
    search_count: int,
    fetch_count: int,
    fetched_urls: list[str],
    fetched_text: str,
    today: str | None = None,
) -> Grade:
    """Deterministic done-check. Existence of `path` is assumed; content is not trusted."""
    reasons: list[str] = []
    today = today or iso_today()
    body = body or ""
    evidence = fetched_text or ""

    if search_count < 1:
        reasons.append("research write with zero web_search spans")
    if fetch_count < 1:
        reasons.append("research write with zero web_fetch spans")
    if not body.strip():
        reasons.append("wrote an empty file")

    wanted = requested_files(prompt)
    if wanted:
        got = Path(path.replace("\\", "/")).name.lower()
        allowed = {Path(w.replace("\\", "/")).name.lower() for w in wanted}
        if got not in allowed:
            reasons.append(f"wrote {path}, prompt asked for {wanted[0]}")

    if _prompt_echo(prompt, body):
        reasons.append("template echo: body repeats the instruction spec")

    if PLACEHOLDER_SYSTEMS.search(body):
        reasons.append("placeholder systems System A/B/C")

    body_l = body.lower()
    for fabricated in FABRICATED_DATES:
        if fabricated in body and fabricated not in evidence:
            reasons.append(f"fabricated snapshot date {fabricated}")

    if is_gaia_assistant_task(prompt):
        for bad in GAIA_WRONG_HOSTS:
            if bad in body_l:
                reasons.append(f"wrong-entity host {bad}")
        has_right = any(h in body_l for h in GAIA_RIGHT_HOSTS)
        if not has_right and "unknown" not in body_l:
            reasons.append("GAIA brief cites neither huggingface/gaia-benchmark nor UNKNOWN")

    for url in urls_from_text(body):
        if is_wrong_entity_url(prompt, url):
            reasons.append(f"wrong-entity URL {url}")
        elif not _url_was_fetched(url, fetched_urls):
            reasons.append(f"cited unfetched URL {url}")

    dates = ISO_DATE_RE.findall(body)
    if today not in body:
        if not dates and "unknown" not in body_l:
            reasons.append(f"missing ISO retrieval date (expected {today} or UNKNOWN)")
        for d in dates:
            if d != today and d not in evidence:
                reasons.append(f"stale retrieval date {d} not present in fetched sources")

    if "unknown" not in body_l:
        for score in SCORE_RE.findall(body):
            if not _score_in_evidence(score, evidence):
                reasons.append(f"score {score}% not present in fetched pages")

    # de-dupe while keeping order
    uniq: list[str] = []
    for r in reasons:
        if r not in uniq:
            uniq.append(r)
    return Grade(ok=not uniq, reasons=uniq)
