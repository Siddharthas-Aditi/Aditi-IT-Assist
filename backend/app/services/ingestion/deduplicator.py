"""Duplicate detection for ingestion candidates.

Compares a candidate's title, tags, and product against the existing
published/approved knowledge article pool.

Detection methods:
1. **Title similarity** — ``difflib.SequenceMatcher`` ratio ≥ 0.70
2. **Tag overlap**      — ≥ 2 shared tags
3. **Product match**    — same ``product_or_system`` + same ``category``

All three methods are run and results are deduplicated by article ID.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass
class DuplicateMatch:
    """An existing KB article that is potentially a duplicate."""

    article_id: str
    title: str
    category: str | None
    similarity_score: float  # 0.0 – 1.0
    match_reason: str  # e.g. "title_similarity:0.85", "tag_overlap:3"


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


async def find_duplicates(
    *,
    title: str | None,
    tags: list[str],
    product_or_system: str | None,
    category: str | None,
    db: AsyncSession,
) -> list[DuplicateMatch]:
    """Return a list of potentially duplicate articles from the knowledge base.

    Queries only ``published`` and ``approved`` articles.
    Returns at most 5 matches ordered by descending similarity score.
    """
    from sqlalchemy import or_, select

    from app.models.knowledge import KnowledgeArticle

    # Load candidate articles — only those in actionable statuses
    stmt = select(
        KnowledgeArticle.id,
        KnowledgeArticle.title,
        KnowledgeArticle.category,
        KnowledgeArticle.tags,
        KnowledgeArticle.product_or_system,
    ).where(
        or_(
            KnowledgeArticle.status == "published",
            KnowledgeArticle.status == "approved",
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    matches: dict[str, DuplicateMatch] = {}

    normalised_title = _normalise(title or "")
    normalised_tags = {t.lower().strip() for t in tags if t}

    for row in rows:
        row_id = str(row.id)
        row_title = row.title or ""
        row_tags = {t.lower().strip() for t in (row.tags or []) if t}
        row_category = row.category
        row_product = row.product_or_system

        # ── Method 1: title similarity ──────────────────────────────────────
        if normalised_title and row_title:
            ratio = difflib.SequenceMatcher(None, normalised_title, _normalise(row_title)).ratio()
            if ratio >= 0.70 and row_id not in matches:
                matches[row_id] = DuplicateMatch(
                    article_id=row_id,
                    title=row_title,
                    category=row_category,
                    similarity_score=round(ratio, 3),
                    match_reason=f"title_similarity:{ratio:.2f}",
                )
            elif ratio >= 0.70 and ratio > matches[row_id].similarity_score:
                matches[row_id].similarity_score = round(ratio, 3)
                matches[row_id].match_reason = f"title_similarity:{ratio:.2f}"

        # ── Method 2: tag overlap ───────────────────────────────────────────
        if normalised_tags and row_tags:
            overlap = len(normalised_tags & row_tags)
            if overlap >= 2:
                score = min(overlap / max(len(normalised_tags), 1), 1.0)
                if row_id not in matches or score > matches[row_id].similarity_score:
                    matches[row_id] = DuplicateMatch(
                        article_id=row_id,
                        title=row_title,
                        category=row_category,
                        similarity_score=round(score, 3),
                        match_reason=f"tag_overlap:{overlap}",
                    )

        # ── Method 3: product + category exact match ────────────────────────
        if (
            product_or_system
            and row_product
            and product_or_system.lower() == row_product.lower()
            and category
            and row_category
            and category == row_category
        ) and row_id not in matches:
            matches[row_id] = DuplicateMatch(
                article_id=row_id,
                title=row_title,
                category=row_category,
                similarity_score=0.60,
                match_reason="product_category_match",
            )

    # Sort by score desc, limit to 5
    sorted_matches = sorted(matches.values(), key=lambda m: m.similarity_score, reverse=True)
    return sorted_matches[:5]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation for fuzzy title comparison."""
    import re

    return re.sub(r"[^\w\s]", "", text.lower()).strip()
