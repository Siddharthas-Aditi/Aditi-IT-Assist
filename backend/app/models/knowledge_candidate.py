"""KnowledgeCandidate — review-gated upstream of the production KB.

A candidate is a *draft* knowledge improvement that the system creates from
real signals (specialist resolutions, unresolved sessions, negative feedback,
web-fallback hits). Candidates NEVER auto-publish — an SME / KB owner has to
review, edit, and promote them through the existing
:class:`KnowledgeArticle` lifecycle. This is the governance boundary that
keeps the assistant from quietly drifting its own knowledge base.

Why a separate table
--------------------
We could in principle reuse ``knowledge_articles`` with a ``status='draft'``
flag, but that conflates *human-authored* drafts with *system-generated*
candidates. They have different governance, different review queues, and
different freshness/decay rules. Keeping them in a sibling table lets the
admin UI show them in their own pane and makes the audit trail unambiguous.

Lifecycle
---------
Candidate states form a small state machine:

    proposed  →  triaged  →  approved  →  promoted    (happy path)
       │           │            │
       │           ├────────────┴──→  rejected
       └──→ duplicate (merged into an existing article)

The ``promoted_article_id`` FK points at the resulting ``knowledge_articles``
row when a candidate becomes a real article — preserving the audit chain.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CANDIDATE_STATES = (
    "proposed",   # freshly generated, awaiting first-pass triage
    "triaged",    # a human has looked at it and queued it for review
    "approved",   # ready to be promoted to a real article
    "promoted",   # promoted; promoted_article_id set
    "rejected",   # rejected with a reason
    "duplicate",  # merged into an existing article
)

CANDIDATE_SOURCES = (
    "specialist_resolution",   # specialist closed an issue with steps worth keeping
    "unresolved_session",      # session ended without resolution — KB gap
    "negative_feedback",       # user feedback flagged the answer as unhelpful
    "web_fallback",            # web research surfaced content not yet in KB
    "missing_subtype",         # supervisor noticed no specialist owns this subtype
    "manual",                  # SME / admin entered a candidate by hand
)


class KnowledgeCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reviewable, system-generated draft for the KB.

    Candidates are immutable once promoted/rejected — to revise, create a new
    candidate. The audit history is preserved through ``promoted_article_id``
    and the ``review_notes`` JSONB column.
    """

    __tablename__ = "knowledge_candidates"

    # ── Provenance ──────────────────────────────────────────────────────
    source: Mapped[str] = mapped_column(
        Enum(*CANDIDATE_SOURCES, name="knowledge_candidate_source"),
        index=True,
    )
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    source_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=True, index=True,
    )
    source_feedback_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # The agent (supervisor, specialist, knowledge_improvement) that proposed
    # this candidate. Joins on registry.AGENT_REGISTRY for analytics.
    proposed_by_agent: Mapped[str] = mapped_column(String(80), index=True)
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )

    # ── Content (draft) ─────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    # Structured suggested steps — same shape as KnowledgeArticle.resolution_steps
    # so the editor UI can render them identically.
    resolution_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Classification (mirrors KnowledgeArticle)
    category: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_subtype: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    affected_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Review state ────────────────────────────────────────────────────
    state: Mapped[str] = mapped_column(
        Enum(*CANDIDATE_STATES, name="knowledge_candidate_state"),
        default="proposed",
        index=True,
    )
    triaged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    triaged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    review_notes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_articles.id"), nullable=True,
    )

    # Set when a candidate is approved and promoted into a real article.
    promoted_article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_articles.id"), nullable=True,
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Quality signals ────────────────────────────────────────────────
    # Aggregated over the source signals: how confident is the system that
    # this candidate is worth a human's attention?
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    times_seen: Mapped[int] = mapped_column(default=1)  # bumped on duplicate proposals
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
