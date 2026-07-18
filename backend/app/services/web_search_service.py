"""Web search fallback when KB has no guidance."""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class DomainTrust(StrEnum):
    """Trustworthiness level of a source."""

    OFFICIAL = "official"  # microsoft.com, apple.com, etc.
    VENDOR = "vendor"  # Dell, Lenovo, etc.
    TRUSTED_COMMUNITY = "trusted_community"  # stackoverflow, reddit
    GENERAL_BLOG = "general_blog"  # Medium, personal blogs


@dataclass
class WebSearchResult:
    """Result from a web search."""

    title: str
    url: str
    snippet: str
    domain: str
    trust_level: DomainTrust


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return "unknown"


def _assess_trust(url: str) -> DomainTrust:
    """Assess trustworthiness of domain."""
    domain = _extract_domain(url).lower()

    # Official vendor sites
    if any(
        vendor in domain
        for vendor in [
            "microsoft",
            "apple",
            "google",
            "dell",
            "hp",
            "lenovo",
            "amazon",
            "aws",
            "azure",
            "office.com",
            "support.microsoft",
            "github.com",
            "docs.microsoft",
            "learn.microsoft",
        ]
    ):
        return DomainTrust.OFFICIAL

    # Trusted communities
    if any(
        community in domain
        for community in [
            "stackoverflow.com",
            "reddit.com",
            "superuser.com",
            "serverfault.com",
            "askubuntu.com",
        ]
    ):
        return DomainTrust.TRUSTED_COMMUNITY

    # General blogs
    return DomainTrust.GENERAL_BLOG


def _trust_score(trust_level: DomainTrust) -> int:
    """Map trust level to score for sorting."""
    scores = {
        DomainTrust.OFFICIAL: 100,
        DomainTrust.VENDOR: 80,
        DomainTrust.TRUSTED_COMMUNITY: 60,
        DomainTrust.GENERAL_BLOG: 30,
    }
    return scores.get(trust_level, 0)


class WebSearchProvider(Protocol):
    async def search(self, query: str, *, category: str, system: str) -> list[WebSearchResult]: ...


def _rank_and_limit(results: list[WebSearchResult], limit: int = 3) -> list[WebSearchResult]:
    results.sort(key=lambda x: _trust_score(x.trust_level), reverse=True)
    return results[:limit]


class GoogleProgrammableSearchProvider:
    """Google Custom Search JSON API (Programmable Search Engine)."""

    def __init__(self, api_key: str, cx: str) -> None:
        self.api_key = api_key
        self.cx = cx

    async def search(self, query: str, *, category: str, system: str) -> list[WebSearchResult]:
        if not (self.api_key and self.cx):
            return []
        q = f"{category} {system} {query} help solution".strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"key": self.api_key, "cx": self.cx, "q": q, "num": 10},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # network/timeout/http error → degrade to empty
            logger.warning("google_search_failed error=%s", exc)
            return []
        items = data.get("items", []) or []
        results = [
            WebSearchResult(
                title=it.get("title", ""),
                url=it.get("link", ""),
                snippet=it.get("snippet", ""),
                domain=_extract_domain(it.get("link", "")),
                trust_level=_assess_trust(it.get("link", "")),
            )
            for it in items
            if it.get("link")
        ]
        return _rank_and_limit(results)


class TavilySearchProvider:
    """Tavily search API (kept as an alternative provider)."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, *, category: str, system: str) -> list[WebSearchResult]:
        if not self.api_key:
            return []
        q = f"{category} {system} {query} help solution".strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": q,
                        "max_results": 10,
                        "topic": "IT Help",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("tavily_search_failed error=%s", exc)
            return []
        items = data.get("results", []) or []
        results = [
            WebSearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                domain=_extract_domain(r.get("url", "")),
                trust_level=_assess_trust(r.get("url", "")),
            )
            for r in items
            if r.get("url")
        ]
        return _rank_and_limit(results)


def get_web_search_provider() -> WebSearchProvider | None:
    """Return the configured provider, or None when web research is off/unconfigured."""
    if not settings.FEATURE_WEB_RESEARCH:
        return None
    if settings.WEB_SEARCH_PROVIDER == "google":
        if settings.GOOGLE_SEARCH_API_KEY and settings.GOOGLE_SEARCH_CX:
            return GoogleProgrammableSearchProvider(
                settings.GOOGLE_SEARCH_API_KEY, settings.GOOGLE_SEARCH_CX
            )
        return None
    if settings.WEB_SEARCH_PROVIDER == "tavily":
        if settings.TAVILY_API_KEY:
            return TavilySearchProvider(settings.TAVILY_API_KEY)
        return None
    return None
