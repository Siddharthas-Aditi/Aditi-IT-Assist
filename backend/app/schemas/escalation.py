"""Schemas for chat-escalation artifacts and the specialist triage view.

These DTOs are the typed contract between the persisted escalation artifacts
(``transcript_snapshots`` + ``escalation_contexts``) and the frontend:

* :class:`TranscriptSnapshotOut` — the immutable AI ↔ employee transcript.
* :class:`EscalationContextOut`   — the structured handoff payload.
* :class:`SpecialistHandoffView`  — the **composite** the specialist UI renders:
  a concise summary + attempted steps + KB signals FIRST, the full transcript
  SECOND (collapsible). This is the "summary-first, transcript-second" contract.
* :class:`ResolutionComparisonIn` — body for capturing what the specialist
  actually did, for AI/KB improvement comparison.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TranscriptRole = Literal["employee", "assistant", "system", "specialist"]


class TranscriptMessageOut(BaseModel):
    """One message in an immutable transcript snapshot."""

    seq: int = Field(..., description="0-based authoritative ordering.")
    role: TranscriptRole
    content: str
    message_type: str | None = None
    timestamp: datetime | None = None


class TranscriptSnapshotOut(BaseModel):
    """Immutable ordered snapshot of the pre-escalation AI conversation."""

    id: UUID
    chat_session_id: str
    captured_at: datetime
    message_count: int
    context_version: str
    messages: list[TranscriptMessageOut] = Field(default_factory=list)


class AttemptedStepOut(BaseModel):
    """A troubleshooting step the AI suggested + its outcome."""

    instruction: str
    outcome: Literal["worked", "failed", "skipped", "unknown"] = "unknown"
    source_kb_title: str | None = None


class KBArticleRefOut(BaseModel):
    """A KB article the AI grounded on (or attempted to)."""

    article_id: str
    title: str
    relevance: float | None = None


class EscalationContextOut(BaseModel):
    """Structured handoff payload for an escalated chat → ticket."""

    id: UUID
    ticket_id: UUID
    transcript_snapshot_id: UUID | None = None
    chat_session_id: str
    escalation_created_at: datetime

    issue_summary: str | None = None
    user_problem_statement: str | None = None
    detected_intent: str | None = None
    category: str | None = None
    subcategory: str | None = None
    affected_system: str | None = None
    urgency: str | None = None
    sentiment: str | None = None

    ai_attempted_steps: list[AttemptedStepOut] = Field(default_factory=list)
    user_feedback_on_steps: list[dict] = Field(default_factory=list)
    kb_articles_referenced: list[KBArticleRefOut] = Field(default_factory=list)
    kb_gap_tags: list[str] = Field(default_factory=list)
    ai_confidence: float | None = None
    ai_resolution_status: str = "unresolved"

    escalation_reason: str | None = None
    live_support_required: bool = False
    specialist_queue_target: str | None = None
    handoff_triggered_by: str | None = None
    diagnostic_slots: dict = Field(default_factory=dict)
    context_version: str = "1.0"

    # Resolution comparison (populated post-resolution).
    specialist_resolution_summary: str | None = None
    specialist_resolution_steps: list[str] = Field(default_factory=list)
    final_resolution_category: str | None = None
    ai_vs_specialist_resolution_gap: str | None = None
    kb_candidate_flag: bool = False
    resolution_compared_at: datetime | None = None


class SpecialistHandoffView(BaseModel):
    """Composite the specialist reads on pickup — summary first, transcript second.

    Designed so the UI renders sections in this order: Overview → AI Handoff
    Summary → Troubleshooting Already Attempted → KB Signals / Knowledge Gaps →
    Full Conversation Transcript (collapsible).
    """

    ticket_id: UUID
    ticket_number: str
    # Overview
    issue_summary: str
    category: str | None = None
    subcategory: str | None = None
    affected_system: str | None = None
    urgency: str | None = None
    ai_confidence: float | None = None
    ai_resolution_status: str = "unresolved"
    escalation_reason: str | None = None
    escalation_created_at: datetime | None = None
    # AI handoff detail
    user_problem_statement: str | None = None
    detected_intent: str | None = None
    steps_attempted: list[AttemptedStepOut] = Field(default_factory=list)
    # KB signals
    kb_articles_referenced: list[KBArticleRefOut] = Field(default_factory=list)
    kb_gap_tags: list[str] = Field(default_factory=list)
    # Full transcript (rendered collapsible / secondary)
    transcript: TranscriptSnapshotOut | None = None
    # True when no persisted escalation context exists yet (degraded view).
    has_structured_context: bool = True


class ResolutionComparisonIn(BaseModel):
    """Body for capturing the specialist's actual resolution for comparison."""

    specialist_resolution_summary: str = Field(..., min_length=1)
    specialist_resolution_steps: list[str] = Field(default_factory=list)
    final_resolution_category: str | None = None
    ai_vs_specialist_resolution_gap: str | None = None
    kb_candidate_flag: bool = False


__all__ = [
    "AttemptedStepOut",
    "EscalationContextOut",
    "KBArticleRefOut",
    "ResolutionComparisonIn",
    "SpecialistHandoffView",
    "TranscriptMessageOut",
    "TranscriptRole",
    "TranscriptSnapshotOut",
]
