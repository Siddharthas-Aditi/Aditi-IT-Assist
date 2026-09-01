"""Schemas for the IT Specialist queue + structured handoff packages.

The :class:`HandoffPackage` is the typed contract a live specialist receives
when they pick up a chat. It contains **everything** the AI gathered so the
specialist never has to re-ask the user the same questions — that's the
whole point of warm handoff.

These schemas are exposed on the queue endpoints (see
``app/api/v1/specialist_queue.py``). Keeping them separate from
``schemas/chat.py`` means the chat client never accidentally depends on the
internal handoff shape.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.escalation import HandoffTrigger


class HandoffSummary(BaseModel):
    """One-screen-tall summary the specialist reads first."""

    issue_one_liner: str = Field(..., description="Plain-English one-line problem statement.")
    affected_system: str | None = None
    issue_category: str | None = None
    issue_subtype: str | None = None
    urgency: Literal["low", "medium", "high", "critical"] | None = None
    user_name: str | None = None
    user_email: str | None = None
    ai_confidence_at_handoff: float = Field(0.0, ge=0.0, le=1.0)


class StepAttempted(BaseModel):
    """One troubleshooting step that was suggested + the outcome."""

    instruction: str
    outcome: Literal["worked", "failed", "skipped", "unknown"] = "unknown"
    source_kb_title: str | None = None


class KBSourceConsulted(BaseModel):
    """A KB article the AI grounded its answer on."""

    article_id: str
    title: str
    relevance: float | None = None


class WebSourceConsulted(BaseModel):
    """An external source the AI considered (web fallback)."""

    url: str
    title: str
    trust_tier: Literal["official", "vendor", "trusted_community", "general_blog"]
    snippet: str | None = None


class ConversationTurn(BaseModel):
    """A flattened chat turn for the specialist's review pane."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime | None = None


class HandoffPackage(BaseModel):
    """The complete, structured context bundle attached to every queue entry.

    The specialist UI renders this as the "Context" pane. Everything is
    serializable + auditable.
    """

    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    ticket_id: UUID | None = None
    summary: HandoffSummary
    diagnostic_slots: dict[str, str] = Field(default_factory=dict)
    steps_attempted: list[StepAttempted] = Field(default_factory=list)
    kb_sources_consulted: list[KBSourceConsulted] = Field(default_factory=list)
    web_sources_consulted: list[WebSourceConsulted] = Field(default_factory=list)
    # Raw, unverified findings from the controlled web-research fallback (B2),
    # captured on the persisted EscalationContext. Specialist-only — never
    # shown to employees. Mirrors EscalationContext.web_research_findings /
    # EscalationContextOut.web_research_findings (list of {title, url, snippet,
    # trust_tier, provider}). None/missing (older, pre-B2 contexts) normalizes
    # to an empty list — see _package_from_context.
    web_research_findings: list[dict[str, Any]] = Field(default_factory=list)
    conversation: list[ConversationTurn] = Field(default_factory=list)
    handoff_reason: str
    handoff_triggered_by: HandoffTrigger
    specialist_queue_target: str | None = None
    supervisor_decision_trace: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Replayable list of supervisor decisions for audit.",
    )


# ── Queue response shapes ──────────────────────────────────────────────────


class QueueEntry(BaseModel):
    """One row in the specialist's queue list."""

    ticket_id: UUID
    ticket_number: str
    title: str
    priority: Literal["low", "medium", "high", "critical"]
    status: Literal[
        "new",
        "triaged",
        "in_progress",
        "waiting_for_user",
        "escalated",
        "resolved",
        "closed",
    ]
    category: str | None = None
    issue_subtype: str | None = None
    requester_name: str | None = None
    queued_at: datetime
    claimed_by_name: str | None = None
    claimed_at: datetime | None = None
    # Typed freshness of the live-chat request (see
    # specialist_queue_service.waiting_info): "waiting" = employee presumed
    # at their keyboard; "likely_left" = unclaimed past
    # LIVE_WAIT_TIMEOUT_SECONDS — the UI must not open a live chat as if
    # someone were waiting; "claimed" = already owned.
    waiting_state: Literal["waiting", "likely_left", "claimed"] = "waiting"
    waited_seconds: int = 0
    summary: HandoffSummary
    specialist_queue_target: str | None = None
    handoff_triggered_by: HandoffTrigger | None = None


class QueueListResponse(BaseModel):
    """Paginated queue list."""

    total: int
    entries: list[QueueEntry]


class ClaimRequest(BaseModel):
    """Body for the claim endpoint."""

    ticket_id: UUID


class ClaimResponse(BaseModel):
    """Response after a successful claim."""

    ticket_id: UUID
    ticket_number: str
    claimed_by_user_id: UUID
    claimed_at: datetime
    # Freshness at claim time: tells the client whether to open a live chat
    # ("waiting") or route to the ticket workspace ("likely_left").
    waiting_state: Literal["waiting", "likely_left"] = "waiting"
    waited_seconds: int = 0
    handoff_package: HandoffPackage


class ResolveRequest(BaseModel):
    """Body for the resolve endpoint."""

    ticket_id: UUID
    resolution_notes: str
    propose_knowledge_candidate: bool = Field(
        False,
        description=(
            "If true, the resolution is sent to the Knowledge Improvement queue "
            "as a candidate for SME review (NEVER auto-published)."
        ),
    )


class ResolveResponse(BaseModel):
    ticket_id: UUID
    status: Literal["resolved"]
    knowledge_candidate_id: UUID | None = None


__all__ = [
    "ClaimRequest",
    "ClaimResponse",
    "ConversationTurn",
    "HandoffPackage",
    "HandoffSummary",
    "KBSourceConsulted",
    "QueueEntry",
    "QueueListResponse",
    "ResolveRequest",
    "ResolveResponse",
    "StepAttempted",
    "WebSourceConsulted",
]
