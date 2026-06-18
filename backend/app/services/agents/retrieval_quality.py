"""Retrieval quality analyzer — detect when KB results are mismatched to the issue.

Instead of blindly using whatever KB returned, this analyzer checks:
1. Do the retrieved articles actually match the diagnosed issue?
2. Are they the right family but wrong subtype?
3. Should we fall back to web search even though we have KB results?

This enables intelligent collaboration: retrieval → quality check → resolution decision.
"""

from dataclasses import dataclass

from app.core.logging import get_logger
from app.services.agents.diagnostic_state import DiagnosticContext

logger = get_logger(__name__)


@dataclass
class RetrievalQuality:
    """Assessment of whether KB results match the diagnosed issue."""

    is_relevant: bool          # True if articles are relevant to the issue
    has_exact_match: bool      # True if exact subtype match found
    confidence: float          # 0.0–1.0 confidence in relevance
    mismatch_reason: str       # Why relevance is low (if applicable)
    should_try_web_search: bool  # True if should try web search despite KB results
    matched_subtype_count: int # How many articles matched exact issue_subtype


class RetrievalQualityAnalyzer:
    """Analyzes whether retrieved KB articles actually help with the diagnosed issue."""

    def __init__(self,
                 articles: list[dict],
                 diag_ctx: DiagnosticContext):
        """
        Args:
            articles: Knowledge articles retrieved from KB
            diag_ctx: Diagnostic context (category, subcategory, subtype, etc.)
        """
        self.articles = articles
        self.diag_ctx = diag_ctx

    def analyze(self) -> RetrievalQuality:
        """Assess whether retrieved articles are relevant to the diagnosed issue."""

        # ── 0 articles = definitely not relevant ──
        if not self.articles:
            return RetrievalQuality(
                is_relevant=False,
                has_exact_match=False,
                confidence=0.0,
                mismatch_reason="No KB articles retrieved",
                should_try_web_search=True,
                matched_subtype_count=0,
            )

        # ── Check for exact subtype match ──
        issue_subtype = (self.diag_ctx.issue_subtype or "").replace("_", "-").lower()
        matched = self._count_subtype_matches(issue_subtype)

        # ── Exact match found ──
        if matched > 0:
            return RetrievalQuality(
                is_relevant=True,
                has_exact_match=True,
                confidence=0.85,
                mismatch_reason="",
                should_try_web_search=False,
                matched_subtype_count=matched,
            )

        # ── Same category but different subtype (risky) ──
        category = self.diag_ctx.issue_category or ""
        same_category = [
            a for a in self.articles
            if (a.get("category") or "").lower() == category.lower()
        ]

        if same_category and issue_subtype:
            # We have articles in the right category, but wrong subtype
            # E.g., VPN article but user has internet connectivity issue
            return RetrievalQuality(
                is_relevant=False,
                has_exact_match=False,
                confidence=0.3,
                mismatch_reason=(
                    f"Found {len(same_category)} {category} articles "
                    f"but none match subtype '{issue_subtype}' — "
                    f"articles cover: {', '.join(set(a.get('subcategory', 'unknown') for a in same_category))}"
                ),
                should_try_web_search=True,  # ← KEY: Even though KB returned results, try web
                matched_subtype_count=0,
            )

        # ── Different category entirely ──
        return RetrievalQuality(
            is_relevant=False,
            has_exact_match=False,
            confidence=0.1,
            mismatch_reason="Retrieved articles are from unrelated categories",
            should_try_web_search=True,
            matched_subtype_count=0,
        )

    def _count_subtype_matches(self, issue_subtype: str) -> int:
        """Count how many articles match the exact issue subtype."""
        count = 0
        for art in self.articles:
            art_subtype = (
                art.get("subcategory") or
                art.get("subtype") or
                art.get("issue_type") or ""
            ).replace("_", "-").lower()
            if art_subtype == issue_subtype:
                count += 1
        return count
