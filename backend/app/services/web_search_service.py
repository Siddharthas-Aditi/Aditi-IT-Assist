"""Web search fallback when KB has no guidance."""

import logging
import os
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


class WebSearchService:
    """Search web for guidance when KB is empty."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize web search service.

        Args:
            api_key: Optional Tavily API key (from env if not provided)
        """
        # Using Tavily API (free tier: 1000 calls/month)
        # Get key from: https://tavily.com
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.info("TAVILY_API_KEY not set. Web search will be disabled.")

    async def search(
        self,
        query: str,
        category: str,  # e.g., "outlook", "access"
        system: str,  # e.g., "Windows", "Mac"
    ) -> list[WebSearchResult]:
        """
        Search web for guidance.

        Args:
            query: User's problem (e.g., "mailbox full can't send")
            category: Issue category (e.g., "outlook")
            system: Affected system (e.g., "Windows 10")

        Returns:
            Top 3 results ranked by trust, or empty list if search disabled
        """
        if not self.enabled:
            logger.debug("Web search disabled (no API key)")
            return []

        # Build focused search query
        search_query = f"{category} {system} {query} help solution"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": search_query,
                        "max_results": 10,  # Get more, rank them
                        "topic": "IT Help",
                    },
                )
                response.raise_for_status()

            data = response.json()
            raw_results = data.get("results", [])

            # Convert to WebSearchResult
            results = [
                WebSearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r.get("content", ""),
                    domain=_extract_domain(r["url"]),
                    trust_level=_assess_trust(r["url"]),
                )
                for r in raw_results
            ]

            # Rank by trust (higher trust first)
            results.sort(
                key=lambda x: _trust_score(x.trust_level),
                reverse=True,
            )

            # Return top 3
            limited = results[:3]
            logger.info(
                "web_search_completed",
                query=search_query[:50],
                results_count=len(limited),
                top_trust=limited[0].trust_level.value if limited else None,
            )
            return limited

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return _extract_domain(url)

    def _assess_trust(self, url: str) -> DomainTrust:
        """Assess trustworthiness of domain."""
        return _assess_trust(url)

    def _trust_score(self, trust_level: DomainTrust) -> int:
        """Map trust level to score for sorting."""
        return _trust_score(trust_level)
