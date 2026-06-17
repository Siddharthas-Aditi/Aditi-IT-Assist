"""Web search fallback when KB has no guidance."""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DomainTrust(str, Enum):
    """Trustworthiness level of a source."""
    OFFICIAL = "official"      # microsoft.com, apple.com, etc.
    VENDOR = "vendor"          # Dell, Lenovo, etc.
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


class WebSearchService:
    """Search web for guidance when KB is empty."""

    def __init__(self, api_key: Optional[str] = None):
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
        system: str,    # e.g., "Windows", "Mac"
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
            # Call Tavily API
            import httpx

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
                    domain=self._extract_domain(r["url"]),
                    trust_level=self._assess_trust(r["url"]),
                )
                for r in raw_results
            ]

            # Rank by trust (higher trust first)
            results.sort(
                key=lambda x: self._trust_score(x.trust_level),
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
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return "unknown"

    def _assess_trust(self, url: str) -> DomainTrust:
        """Assess trustworthiness of domain."""
        domain = self._extract_domain(url).lower()

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

    def _trust_score(self, trust_level: DomainTrust) -> int:
        """Map trust level to score for sorting."""
        scores = {
            DomainTrust.OFFICIAL: 100,
            DomainTrust.VENDOR: 80,
            DomainTrust.TRUSTED_COMMUNITY: 60,
            DomainTrust.GENERAL_BLOG: 30,
        }
        return scores.get(trust_level, 0)
