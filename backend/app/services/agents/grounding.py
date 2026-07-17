"""Retrieval grounding guardrails — keep answers on-topic and on-subtype.

The keyword retriever returns *candidate* articles. On its own it has two
failure modes that produced the "inbox full → password reset / Windows Update"
bug:

1. **Cross-domain contamination** — an article from an unrelated issue family
   (``access/permissions`` password reset, ``device-management/intune`` Windows
   Update, ``hardware/audio``) scores points on a shared generic word and leaks
   into an Outlook answer.
2. **Wrong subtype** — even within ``email/outlook``, a generic "Outlook issues"
   article outranks the focused "mailbox full" article, so the resolver answers
   the wrong question.

This module applies, *after* retrieval and *before* resolution:

- a hard **domain guard** that rejects articles whose category family differs
  from the current issue family (unless the playbook explicitly allows it), and
- a **subtype-aware rerank** that boosts articles whose subcategory/keywords
  match the identified subtype and symptom.

Everything is returned with a structured trace so the chat-debugging view and
logs can explain *why* an article was kept, reranked, or rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agents.diagnostic_state import DiagnosticContext


@dataclass
class GroundedArticle:
    """A retrieved article after grounding, with its relevance breakdown."""

    article: dict
    relevance: float
    subtype_match: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class GroundingResult:
    """Output of the grounding pass."""

    kept: list[GroundedArticle] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # [{title, category, reason}]
    top_relevance: float = 0.0
    has_subtype_match: bool = False
    same_family_only: bool = True

    def kept_articles(self) -> list[dict]:
        return [g.article for g in self.kept]

    def trace(self) -> dict:
        """Compact, serializable trace for observability / admin debug view."""
        return {
            "kept": [
                {
                    "id": g.article.get("id"),
                    "title": g.article.get("title"),
                    "category": g.article.get("category"),
                    "subcategory": g.article.get("subcategory") or g.article.get("subtype"),
                    "relevance": round(g.relevance, 3),
                    "subtype_match": g.subtype_match,
                    "reasons": g.reasons,
                }
                for g in self.kept
            ],
            "rejected": self.rejected,
            "top_relevance": round(self.top_relevance, 3),
            "has_subtype_match": self.has_subtype_match,
        }


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "you",
    "your",
    "this",
    "that",
    "have",
    "has",
    "are",
    "was",
    "not",
    "but",
    "issue",
    "issues",
    "problem",
    "help",
    "please",
    "cant",
    "can't",
    "cannot",
    "what",
    "when",
    "how",
    "why",
    "from",
    "into",
}


def _family(category: str | None) -> str:
    """Top-level issue family from a slashed category (``email/outlook`` → ``email``)."""
    if not category:
        return ""
    return category.split("/", 1)[0].strip().lower()


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in (text or "").lower().replace("/", " ").replace("-", " ").split()
        if len(t) > 2 and t not in _STOPWORDS
    }


def _article_subtype(article: dict) -> str | None:
    return article.get("subcategory") or article.get("subtype") or article.get("issue_type")


def _article_text(article: dict) -> str:
    parts = [
        str(article.get("title", "")),
        str(_article_subtype(article) or ""),
        " ".join(str(t) for t in (article.get("tags") or [])),
        " ".join(str(k) for k in (article.get("keywords") or [])),
        str(article.get("short_summary") or ""),
        str(article.get("content") or article.get("snippet") or "")[:600],
    ]
    return " ".join(parts)


def ground_results(
    articles: list[dict],
    diag_ctx: DiagnosticContext,
    *,
    allowed_families: set[str] | None = None,
) -> GroundingResult:
    """Filter and rerank retrieved articles for the current issue.

    Args:
        articles: Raw retrieved article dicts (already scored by the retriever).
        diag_ctx: Current diagnostic context (category, subtype, symptom...).
        allowed_families: Extra category families the playbook permits beyond the
            issue's own family. Use for cross-cutting cases (rare).

    Returns:
        ``GroundingResult`` with kept (reranked) and rejected articles + trace.
    """
    current_family = _family(diag_ctx.issue_category)
    allowed = {current_family} | (allowed_families or set())

    subtype = diag_ctx.issue_subtype or diag_ctx.issue_subcategory or ""
    subtype_norm = subtype.replace("_", "-").lower()
    subtype_tokens = _tokens(subtype.replace("-", " "))
    symptom_tokens = _tokens(
        f"{diag_ctx.symptom or ''} {diag_ctx.exact_problem_statement or ''} "
        f"{diag_ctx.error_message or ''}".replace("-", " ")
    )
    system_token = (diag_ctx.normalized_system or "").replace("_", " ").lower()

    result = GroundingResult(same_family_only=not allowed_families)

    for art in articles:
        art_family = _family(art.get("category"))
        art_text_lower = _article_text(art).lower()
        # A strong system/product match (e.g. "sixth sense", "outlook") overrides
        # the family guard. The same product can be filed under a different
        # category family in the KB (Sixth Sense lives under software/other), so
        # the system signal — not the category — must decide relevance.
        system_hit = bool(system_token) and system_token in art_text_lower

        # ── Domain guard (system match exempts) ──────────────────
        if current_family and art_family and art_family not in allowed and not system_hit:
            result.rejected.append(
                {
                    "id": art.get("id"),
                    "title": art.get("title"),
                    "category": art.get("category"),
                    "reason": f"cross-domain: '{art_family}' not in allowed {sorted(allowed)}",
                }
            )
            continue

        reasons: list[str] = []
        relevance = 0.0
        art_subtype = (_article_subtype(art) or "").replace("_", "-").lower()
        art_tokens = _tokens(_article_text(art))

        # ── Subtype match (strongest signal) ─────────────────────
        subtype_match = bool(subtype_norm) and (
            art_subtype == subtype_norm or (subtype_tokens and subtype_tokens.issubset(art_tokens))
        )
        if subtype_match:
            relevance += 0.55
            reasons.append(f"subtype match: {subtype_norm}")

        # ── Symptom token overlap ────────────────────────────────
        if symptom_tokens:
            overlap = len(symptom_tokens & art_tokens) / len(symptom_tokens)
            relevance += 0.30 * overlap
            if overlap:
                reasons.append(f"symptom overlap {overlap:.2f}")

        # ── System / product mention (strong signal) ─────────────
        if system_hit:
            relevance += 0.35
            reasons.append(f"system match: {system_token}")

        # ── Same-category baseline ───────────────────────────────
        if art.get("category") == diag_ctx.issue_category:
            relevance += 0.10
            reasons.append("same category")

        # Blend in the retriever's own score as a small prior.
        retriever_score = float(art.get("score") or 0.0)
        relevance = min(1.0, relevance + 0.10 * retriever_score)

        result.kept.append(
            GroundedArticle(
                article=art,
                relevance=round(relevance, 3),
                subtype_match=subtype_match,
                reasons=reasons,
            )
        )

    # Rerank: subtype matches first, then by relevance.
    result.kept.sort(key=lambda g: (g.subtype_match, g.relevance), reverse=True)
    result.has_subtype_match = any(g.subtype_match for g in result.kept)
    result.top_relevance = result.kept[0].relevance if result.kept else 0.0
    return result
