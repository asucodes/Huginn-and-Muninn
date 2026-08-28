"""Community Deal Feed Scraper — Reddit, HN, OpenRouter changelog.

Polls public, unauthenticated APIs to surface new free LLM deals,
API launches, and promotional credit announcements in real-time.

Sources:
  - Reddit JSON API (r/LocalLLaMA, r/SideProject, r/MachineLearning)
  - Hacker News Algolia search API
  - OpenRouter blog RSS feed (new free model announcements)
  - Provider status/incident RSS feeds (Groq, Mistral, DeepSeek)
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Any

import httpx

# Keywords that indicate a free tier / credits deal post
DEAL_KEYWORDS = {"free", "credits", "launch", "api key", "token", "promo", "discount", "trial", "beta", "giveaway"}

REDDIT_SUBREDDITS = "LocalLLaMA+SideProject+MachineLearning+AIAssistants"
REDDIT_SEARCH_URL = "https://www.reddit.com/r/{subs}/search.json"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
OPENROUTER_RSS = "https://openrouter.ai/blog/rss.xml"

# Provider status/blog RSS feeds (public Atom/RSS, no auth needed)
PROVIDER_FEEDS = {
    "groq": "https://groq.com/feed/",
    "mistral": "https://mistral.ai/news/rss.xml",
}

USER_AGENT = "Huginn-and-Muninn/2.0 AI-deal-radar (open-source; github.com/asucodes/Huginn-and-Muninn)"


@dataclass
class Deal:
    title: str
    url: str
    source: str          # e.g. "reddit/LocalLLaMA", "hackernews", "openrouter/blog"
    provider_hint: str   # detected provider name or "" if unknown
    credits_hint: str    # e.g. "$10 free", "100K tokens/day"
    relevance: float     # 0.0 - 1.0
    found_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score(text: str) -> float:
    """Compute a 0.0-1.0 relevance score based on keyword density."""
    text_lower = text.lower()
    matches = sum(1 for kw in DEAL_KEYWORDS if kw in text_lower)
    return min(1.0, matches / max(1, len(DEAL_KEYWORDS) / 2))


def _detect_provider(text: str) -> str:
    providers = ["groq", "openrouter", "deepseek", "mistral", "cerebras", "gemini", "ollama", "z.ai", "zhipu"]
    text_lower = text.lower()
    for p in providers:
        if p in text_lower:
            return p
    return ""


def _extract_credits_hint(text: str) -> str:
    import re
    patterns = [
        r"\$\d[\d,]*\s*(?:free|credit|bonus)",
        r"\d[\d,]*[kKmM]?\s*(?:token|request)s?(?:\s+(?:free|per day|\/day))?",
        r"free\s+tier",
    ]
    text_lower = text.lower()
    for p in patterns:
        m = re.search(p, text_lower)
        if m:
            return m.group(0).strip()
    return ""


class CommunityFeedScraper:
    """Polls community APIs for free AI API deal announcements."""

    def __init__(self, cache_ttl_s: float = 600.0, http_timeout_s: float = 8.0):
        self.cache_ttl_s = cache_ttl_s
        self.http_timeout_s = http_timeout_s
        self._deals_cache: list[Deal] = []
        self._last_scan_ts: float = 0.0

    def get_deals(self, force_refresh: bool = False) -> list[Deal]:
        now = time.time()
        if force_refresh or (now - self._last_scan_ts > self.cache_ttl_s):
            self.scan_all()
        return sorted(self._deals_cache, key=lambda d: d.relevance, reverse=True)

    def scan_all(self) -> list[Deal]:
        headers = {"User-Agent": USER_AGENT}
        all_deals: list[Deal] = []
        with httpx.Client(timeout=self.http_timeout_s, headers=headers, follow_redirects=True) as client:
            all_deals.extend(self._fetch_reddit(client))
            all_deals.extend(self._fetch_hn(client))
            all_deals.extend(self._fetch_github_ai_repos(client))
            all_deals.extend(self._fetch_openrouter_rss(client))
            all_deals.extend(self._fetch_provider_rss(client))

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique: list[Deal] = []
        for d in all_deals:
            if d.url not in seen_urls:
                seen_urls.add(d.url)
                unique.append(d)

        self._deals_cache = [d for d in unique if d.relevance > 0.1]
        self._last_scan_ts = time.time()
        return self._deals_cache

    def _fetch_reddit(self, client: httpx.Client) -> list[Deal]:
        try:
            resp = client.get(
                REDDIT_SEARCH_URL.format(subs=REDDIT_SUBREDDITS),
                params={"q": "free OR credits OR launch OR API", "restrict_sr": "1",
                        "sort": "new", "limit": 50},
            )
            if resp.status_code != 200:
                return []
            posts = resp.json().get("data", {}).get("children", [])
            deals = []
            for p in posts:
                d = p.get("data", {})
                title = d.get("title", "")
                body = d.get("selftext", "")
                combined = f"{title} {body}"
                score = _score(combined)
                if score > 0.1:
                    url = f"https://reddit.com{d.get('permalink', '')}"
                    deals.append(Deal(
                        title=title, url=url,
                        source=f"reddit/{d.get('subreddit', 'unknown')}",
                        provider_hint=_detect_provider(combined),
                        credits_hint=_extract_credits_hint(combined),
                        relevance=score,
                    ))
            return deals
        except Exception:
            return []

    def _fetch_hn(self, client: httpx.Client) -> list[Deal]:
        try:
            resp = client.get(
                HN_SEARCH_URL,
                params={
                    "query": "free LLM API",
                    "tags": "(story,show_hn)",
                    "hitsPerPage": 25,
                },
            )
            if resp.status_code != 200:
                return []
            deals = []
            for hit in resp.json().get("hits", []):
                title = hit.get("title", "")
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                score = _score(title)
                if score > 0.05:
                    deals.append(
                        Deal(
                            title=title,
                            url=url,
                            source="hackernews",
                            provider_hint=_detect_provider(title),
                            credits_hint=_extract_credits_hint(title),
                            relevance=max(score, 0.4),
                        )
                    )
            return deals
        except Exception:
            return []

    def _fetch_github_ai_repos(self, client: httpx.Client) -> list[Deal]:
        try:
            resp = client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": "free llm api OR openrouter OR groq",
                    "sort": "updated",
                    "order": "desc",
                    "per_page": 15,
                },
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": USER_AGENT},
            )
            if resp.status_code != 200:
                return []
            deals = []
            for item in resp.json().get("items", []):
                name = item.get("full_name", "")
                desc = item.get("description") or ""
                url = item.get("html_url", "")
                combined = f"{name} {desc}"
                score = _score(combined)
                deals.append(
                    Deal(
                        title=f"{name}: {desc[:80]}" if desc else name,
                        url=url,
                        source="github",
                        provider_hint=_detect_provider(combined),
                        credits_hint=_extract_credits_hint(combined),
                        relevance=max(score, 0.3),
                    )
                )
            return deals
        except Exception:
            return []

    def _fetch_openrouter_rss(self, client: httpx.Client) -> list[Deal]:
        try:
            resp = client.get(OPENROUTER_RSS)
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.content)
            deals = []
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el = item.find("link")
                title = title_el.text if title_el is not None else ""
                link = link_el.text if link_el is not None else ""
                score = _score(title)
                if score > 0.05:
                    deals.append(
                        Deal(
                            title=title,
                            url=link,
                            source="openrouter/blog",
                            provider_hint="openrouter",
                            credits_hint=_extract_credits_hint(title),
                            relevance=max(score, 0.5),
                        )
                    )
            return deals
        except Exception:
            return []

    def _fetch_provider_rss(self, client: httpx.Client) -> list[Deal]:
        deals = []
        for provider, rss_url in PROVIDER_FEEDS.items():
            try:
                resp = client.get(rss_url)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    title = title_el.text if title_el is not None else ""
                    link = link_el.text if link_el is not None else ""
                    score = _score(title)
                    if score > 0.05:
                        deals.append(
                            Deal(
                                title=title,
                                url=link,
                                source=f"provider/{provider}",
                                provider_hint=provider,
                                credits_hint=_extract_credits_hint(title),
                                relevance=max(score, 0.5),
                            )
                        )
            except Exception:
                continue
        return deals

    def scan_all(self) -> list[Deal]:
        headers = {"User-Agent": USER_AGENT}
        all_deals: list[Deal] = []
        with httpx.Client(timeout=self.http_timeout_s, headers=headers, follow_redirects=True) as client:
            all_deals.extend(self._fetch_hn(client))
            all_deals.extend(self._fetch_github_ai_repos(client))
            all_deals.extend(self._fetch_openrouter_rss(client))
            all_deals.extend(self._fetch_provider_rss(client))

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique: list[Deal] = []
        for d in all_deals:
            if d.url not in seen_urls:
                seen_urls.add(d.url)
                unique.append(d)

        self._deals_cache = [d for d in unique if d.relevance > 0.1]
        self._last_scan_ts = time.time()
        return self._deals_cache

