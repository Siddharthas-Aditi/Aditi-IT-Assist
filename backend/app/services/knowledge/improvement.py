"""Knowledge improvement candidate service.

Converts every legitimate "the KB might need an update" signal into a
:class:`KnowledgeCandidate` row, deduplicates against recent candidates, and
exposes review-queue operations for SMEs.

Signal types this service ingests
---------------------------------
* :func:`record_specialist_resolution` — a specialist (or human IT specialist)
  closed an issue with steps worth keeping.
* :func:`record_unresolved_session` — a session ended escalated, with no
  matching KB article.
* :func:`record_negative_feedback` — explicit thumbs-down or rating<=2.
* :func:`record_web_fallback_used` — the controlled web-research agent ran;
  surface the external content for SME review.
* :func:`record_missing_subtype` — supervisor noticed no specialist owns a
  detected subtype.

Governance
----------
* Nothing here writes to :class:`KnowledgeArticle`. Promotion is a separate
  explicit operation (see :func:`promote_candidate`) and requires the caller
  to have the ``knowledge:write`` permission — the service does NOT check
  permissions itself (the route does); we encode the contract in the
  docstrings + tests.
* Candidates are deduplicated by ``(category, issue_subtype, source)`` over
  a rolling 30-day window. Repeat hits bump ``times_seen`` instead of
  spawning new rows — so reviewers see one ranked queue, not noise.

This service is intentionally thin around SQLAlchemy: routes call it,
specialists call it via the workflow node, tests call it directly. It does
NOT mutate workflow state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, select

from app.core.logging import get_logger
from app.models.knowledge_candidate import KnowledgeCandidate

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# Rolling window for deduplication; tunable in config later.
_DEDUP_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class CandidateDraft:
    """All the fields a caller might want to populate on a new candidate.

    Required: ``source``, ``title``, ``body``. Everything else is best-effort —
    the service fills in defaults where it can.
    """

    source: str
    title: str
    body: str
    proposed_by_agent: str
    category: str | None = None
    subcategory: str | None = None
    issue_subtype: str | None = None
    affected_system: str | None = None
    summary: str | None = None
    resolution_steps: list[dict] | None = None
    source_session_id: uuid.UUID | None = None
    source_ticket_id: uuid.UUID | None = None
    source_feedback_id: uuid.UUID | None = None
    source_url: str | None = None
    proposed_by_user_id: uuid.UUID | None = None
    tags: list[str] | None = None
    confidence: float = 0.5


class KnowledgeImprovementService:
    """Create + manage knowledge improvement candidates.

    Every public method is async + transactional in the calling layer's
    session. The service does NOT commit — the caller decides the unit of
    work (typically the route handler).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Ingestion ──────────────────────────────────────────────────────

    async def propose(self, draft: CandidateDraft) -> KnowledgeCandidate:
        """Create a candidate from a draft, or bump an existing duplicate.

        Deduplication is conservative: same ``source`` + same ``category`` +
        same ``issue_subtype`` within the rolling window is treated as the
        same candidate. This keeps the SME queue manageable when a single
        gap surfaces across many sessions.
        """
        dup = await self._find_recent_duplicate(draft)
        now = datetime.now(UTC)
        if dup is not None:
            dup.times_seen += 1
            dup.last_seen_at = now
            # Bump confidence slightly on repeat hits (capped at 0.95).
            dup.confidence = min(0.95, max(dup.confidence, draft.confidence) + 0.05)
            await self.db.flush()
            logger.info(
                "knowledge_candidate_deduplicated",
                candidate_id=str(dup.id),
                times_seen=dup.times_seen,
                source=draft.source,
            )
            return dup

        candidate = KnowledgeCandidate(
            source=draft.source,
            title=draft.title,
            body=draft.body,
            summary=draft.summary,
            resolution_steps=draft.resolution_steps,
            category=draft.category,
            subcategory=draft.subcategory,
            issue_subtype=draft.issue_subtype,
            affected_system=draft.affected_system,
            tags=draft.tags,
            proposed_by_agent=draft.proposed_by_agent,
            proposed_by_user_id=draft.proposed_by_user_id,
            source_session_id=draft.source_session_id,
            source_ticket_id=draft.source_ticket_id,
            source_feedback_id=draft.source_feedback_id,
            source_url=draft.source_url,
            confidence=draft.confidence,
            state="proposed",
            last_seen_at=now,
        )
        self.db.add(candidate)
        await self.db.flush()
        logger.info(
            "knowledge_candidate_proposed",
            candidate_id=str(candidate.id),
            source=draft.source,
            subtype=draft.issue_subtype,
            agent=draft.proposed_by_agent,
        )
        return candidate

    # Convenience wrappers — each is a thin facade over :func:`propose` with
    # the source pre-filled. They live here so callers can stay readable
    # ("record_unresolved_session(...)") instead of building a CandidateDraft.

    async def record_specialist_resolution(
        self,
        *,
        title: str,
        body: str,
        proposed_by_agent: str,
        steps: list[dict],
        category: str | None = None,
        subtype: str | None = None,
        ticket_id: uuid.UUID | None = None,
        proposed_by_user_id: uuid.UUID | None = None,
    ) -> KnowledgeCandidate:
        return await self.propose(CandidateDraft(
            source="specialist_resolution",
            title=title, body=body,
            resolution_steps=steps,
            category=category, issue_subtype=subtype,
            proposed_by_agent=proposed_by_agent,
            proposed_by_user_id=proposed_by_user_id,
            source_ticket_id=ticket_id,
            confidence=0.75,  # human-confirmed resolutions are high signal
        ))

    async def record_unresolved_session(
        self,
        *,
        session_id: uuid.UUID,
        category: str | None,
        subtype: str | None,
        problem_statement: str,
        proposed_by_agent: str = "knowledge_improvement",
    ) -> KnowledgeCandidate:
        return await self.propose(CandidateDraft(
            source="unresolved_session",
            title=f"Unresolved: {subtype or category or 'unknown issue'}",
            body=problem_statement,
            category=category,
            issue_subtype=subtype,
            proposed_by_agent=proposed_by_agent,
            source_session_id=session_id,
            confidence=0.5,
        ))

    async def record_negative_feedback(
        self,
        *,
        feedback_id: uuid.UUID,
        category: str | None,
        subtype: str | None,
        comment: str,
        proposed_by_agent: str = "knowledge_improvement",
    ) -> KnowledgeCandidate:
        return await self.propose(CandidateDraft(
            source="negative_feedback",
            title=f"Negative feedback on {subtype or category or 'unknown'}",
            body=comment,
            category=category,
            issue_subtype=subtype,
            proposed_by_agent=proposed_by_agent,
            source_feedback_id=feedback_id,
            confidence=0.55,
        ))

    async def record_web_fallback_used(
        self,
        *,
        url: str,
        snippet: str,
        category: str | None,
        subtype: str | None,
        proposed_by_agent: str = "web_research",
    ) -> KnowledgeCandidate:
        return await self.propose(CandidateDraft(
            source="web_fallback",
            title=f"External source: {category or subtype or 'unknown'}",
            body=snippet,
            source_url=url,
            category=category,
            issue_subtype=subtype,
            proposed_by_agent=proposed_by_agent,
            confidence=0.45,  # external content always needs human eyes
        ))

    async def record_missing_subtype(
        self,
        *,
        subtype: str,
        category: str | None,
        sample_problem: str,
        proposed_by_agent: str = "supervisor",
    ) -> KnowledgeCandidate:
        return await self.propose(CandidateDraft(
            source="missing_subtype",
            title=f"No specialist for subtype: {subtype}",
            body=(
                f"Supervisor observed an unhandled subtype.\n"
                f"Category: {category}\nSubtype: {subtype}\n"
                f"Example problem: {sample_problem}"
            ),
            category=category,
            issue_subtype=subtype,
            proposed_by_agent=proposed_by_agent,
            confidence=0.6,
        ))

    # ── Review queue ───────────────────────────────────────────────────

    async def list_for_review(
        self, *, state: str = "proposed", limit: int = 50,
    ) -> list[KnowledgeCandidate]:
        stmt = (
            select(KnowledgeCandidate)
            .where(KnowledgeCandidate.state == state)
            .order_by(
                KnowledgeCandidate.confidence.desc(),
                KnowledgeCandidate.times_seen.desc(),
                KnowledgeCandidate.created_at.desc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def triage(
        self, candidate_id: uuid.UUID, *, by_user_id: uuid.UUID,
    ) -> KnowledgeCandidate:
        candidate = await self._get(candidate_id)
        candidate.state = "triaged"
        candidate.triaged_by = by_user_id
        candidate.triaged_at = datetime.now(UTC)
        await self.db.flush()
        return candidate

    async def reject(
        self, candidate_id: uuid.UUID, *, by_user_id: uuid.UUID, reason: str,
    ) -> KnowledgeCandidate:
        candidate = await self._get(candidate_id)
        candidate.state = "rejected"
        candidate.reviewed_by = by_user_id
        candidate.reviewed_at = datetime.now(UTC)
        candidate.rejected_reason = reason
        await self.db.flush()
        logger.info(
            "knowledge_candidate_rejected",
            candidate_id=str(candidate.id),
            reason=reason,
        )
        return candidate

    async def mark_duplicate(
        self,
        candidate_id: uuid.UUID,
        *,
        by_user_id: uuid.UUID,
        duplicate_of_article: uuid.UUID,
    ) -> KnowledgeCandidate:
        candidate = await self._get(candidate_id)
        candidate.state = "duplicate"
        candidate.reviewed_by = by_user_id
        candidate.reviewed_at = datetime.now(UTC)
        candidate.duplicate_of = duplicate_of_article
        await self.db.flush()
        return candidate

    async def approve_for_promotion(
        self, candidate_id: uuid.UUID, *, by_user_id: uuid.UUID,
    ) -> KnowledgeCandidate:
        """Mark candidate approved. Does NOT create the article.

        Promotion is a separate operation (see :func:`promote_candidate`) so
        the SME can edit the candidate before it becomes a real article. The
        two-step flow is deliberate — once promoted, the audit chain is
        immutable.
        """
        candidate = await self._get(candidate_id)
        candidate.state = "approved"
        candidate.reviewed_by = by_user_id
        candidate.reviewed_at = datetime.now(UTC)
        await self.db.flush()
        return candidate

    async def link_promoted_article(
        self, candidate_id: uuid.UUID, article_id: uuid.UUID,
    ) -> KnowledgeCandidate:
        """Link a promoted candidate to its resulting article.

        Called by the KB management service after a candidate-derived article
        has been created and accepted. Two operations split to keep this
        service decoupled from KB write paths.
        """
        candidate = await self._get(candidate_id)
        candidate.state = "promoted"
        candidate.promoted_article_id = article_id
        candidate.promoted_at = datetime.now(UTC)
        await self.db.flush()
        return candidate

    # ── Internals ──────────────────────────────────────────────────────

    async def _get(self, candidate_id: uuid.UUID) -> KnowledgeCandidate:
        stmt = select(KnowledgeCandidate).where(KnowledgeCandidate.id == candidate_id)
        result = await self.db.execute(stmt)
        candidate = result.scalar_one_or_none()
        if candidate is None:
            raise LookupError(f"Knowledge candidate {candidate_id} not found")
        return candidate

    async def _find_recent_duplicate(
        self, draft: CandidateDraft,
    ) -> KnowledgeCandidate | None:
        cutoff = datetime.now(UTC) - _DEDUP_WINDOW
        stmt = select(KnowledgeCandidate).where(
            and_(
                KnowledgeCandidate.source == draft.source,
                KnowledgeCandidate.category == draft.category,
                KnowledgeCandidate.issue_subtype == draft.issue_subtype,
                KnowledgeCandidate.state.in_(("proposed", "triaged", "approved")),
                KnowledgeCandidate.created_at >= cutoff,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()


__all__ = [
    "CandidateDraft",
    "KnowledgeImprovementService",
]
