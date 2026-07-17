"""Escalation service — creates + serves the chat→ticket handoff artifacts.

At escalation time this service captures two linked, immutable artifacts from the
(currently in-memory) chat session state:

* a :class:`TranscriptSnapshot` — the ordered Employee ↔ AI conversation, copied
  verbatim so later session mutations can never alter it, and
* an :class:`EscalationContext` — the structured handoff payload (issue summary,
  attempted steps, KB signals + gap tags, escalation reason, routing).

It also assembles the :class:`SpecialistHandoffView` the specialist UI reads
(summary first, transcript second) and records the post-resolution
AI-vs-specialist comparison.

Persistence lives HERE (the service layer) — workflow nodes stay side-effect free.
Creation is **idempotent per ticket**: a second call returns the existing context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.escalation import (
    AI_RESOLUTION_STATUSES,
    ESCALATION_CONTEXT_VERSION,
    EscalationContext,
    TranscriptSnapshot,
)
from app.models.ticket import Ticket
from app.schemas.escalation import (
    AttemptedStepOut,
    EscalationContextOut,
    KBArticleRefOut,
    SpecialistHandoffView,
    TranscriptMessageOut,
    TranscriptSnapshotOut,
)
from app.services.agents.kb_gap_tags import derive_kb_gap_tags

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.auth import User

logger = get_logger(__name__)

# Map LangChain message ``.type`` (or dict ``role``) → transcript role label.
_ROLE_MAP = {
    "human": "employee",
    "user": "employee",
    "employee": "employee",
    "ai": "assistant",
    "assistant": "assistant",
    "system": "system",
    "specialist": "specialist",
}


def extract_transcript(messages: list[Any] | None) -> list[dict]:
    """Convert a workflow message list into an ordered transcript array. Pure.

    Accepts LangChain message objects (``.content`` / ``.type``) or plain dicts
    (``content`` / ``role``). Preserves order, assigns an authoritative 0-based
    ``seq``, and normalizes role labels. Empty-content messages are skipped.
    """
    out: list[dict] = []
    for msg in messages or []:
        if isinstance(msg, dict):
            content = msg.get("content")
            raw_role = msg.get("role") or msg.get("type") or "unknown"
            msg_type = msg.get("message_type")
            ts = msg.get("timestamp")
        else:
            content = getattr(msg, "content", None)
            raw_role = getattr(msg, "type", None) or "unknown"
            msg_type = getattr(msg, "message_type", None)
            ts = None
        if not content:
            continue
        out.append(
            {
                "seq": len(out),
                "role": _ROLE_MAP.get(str(raw_role).lower(), "system"),
                "content": str(content),
                "message_type": msg_type,
                "timestamp": ts,
            }
        )
    return out


def _normalize_steps(raw_steps: list | None, *, default_outcome: str) -> list[dict]:
    """Normalize attempted-step entries into typed dicts."""
    steps: list[dict] = []
    for step in raw_steps or []:
        if isinstance(step, dict):
            steps.append(
                {
                    "instruction": str(step.get("instruction") or step.get("step") or step),
                    "outcome": step.get("outcome", default_outcome),
                    "source_kb_title": step.get("source_kb_title"),
                }
            )
        else:
            steps.append(
                {
                    "instruction": str(step),
                    "outcome": default_outcome,
                    "source_kb_title": None,
                }
            )
    return steps


def _normalize_kb_refs(citations: list | None, knowledge_results: list | None) -> list[dict]:
    """Best-effort normalization of KB citations/results into typed refs."""
    source = citations or knowledge_results or []
    refs: list[dict] = []
    for item in source:
        if isinstance(item, dict):
            article_id = str(
                item.get("article_id") or item.get("id") or item.get("knowledge_article_id") or ""
            )
            title = str(item.get("title") or item.get("name") or "Untitled article")
            relevance = item.get("relevance") or item.get("score")
            refs.append(
                {
                    "article_id": article_id,
                    "title": title,
                    "relevance": float(relevance) if relevance is not None else None,
                }
            )
        elif item:
            refs.append({"article_id": "", "title": str(item), "relevance": None})
    return refs


class EscalationService:
    """Create + serve the chat-escalation handoff artifacts."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Creation ─────────────────────────────────────────────────────────

    async def create_escalation_artifacts(
        self,
        *,
        ticket: Ticket,
        chat_session_id: str,
        state: dict | None,
        requester: User | None = None,
        repeated_escalation: bool = False,
    ) -> EscalationContext:
        """Create (or return existing) transcript snapshot + escalation context.

        Idempotent per ticket: if an escalation context already exists for this
        ticket, it is returned unchanged (no duplicate snapshot).
        """
        existing = await self._get_context_by_ticket(ticket.id)
        if existing is not None:
            return existing

        state = state or {}
        diag = state.get("diagnostic_context") or {}
        handoff = state.get("handoff_summary") or {}

        # 1. Immutable transcript snapshot (a copy — never a reference).
        messages = extract_transcript(state.get("messages"))
        snapshot = TranscriptSnapshot(
            ticket_id=ticket.id,
            chat_session_id=chat_session_id,
            user_id=requester.id if requester else None,
            captured_at=datetime.now(UTC),
            message_count=len(messages),
            messages=messages,
            context_version=ESCALATION_CONTEXT_VERSION,
        )
        self.db.add(snapshot)
        await self.db.flush()  # assign snapshot.id

        # 2. Structured escalation context.
        steps_raw = (
            state.get("steps_attempted")
            or diag.get("failed_steps")
            or diag.get("attempted_steps")
            or handoff.get("steps_attempted")
            or []
        )
        # failed_steps imply a "failed" outcome; generic lists are "unknown".
        default_outcome = "failed" if diag.get("failed_steps") else "unknown"
        attempted_steps = _normalize_steps(steps_raw, default_outcome=default_outcome)

        problem_statement = (
            diag.get("exact_problem_statement")
            or handoff.get("issue_description")
            or ticket.ai_summary
        )
        has_problem_statement = bool(problem_statement)

        specialist_only_signal = bool(
            diag.get("blocked_account_flag") == "yes" or diag.get("requires_privileged_action")
        )
        escalation_reason = (
            state.get("escalation_reason")
            or diag.get("escalation_reason")
            or "Automated troubleshooting exhausted — requires IT specialist"
        )

        kb_refs = _normalize_kb_refs(
            state.get("knowledge_citations"), state.get("knowledge_results")
        )
        kb_gap_tags = derive_kb_gap_tags(
            knowledge_results=state.get("knowledge_results"),
            has_problem_statement=has_problem_statement,
            steps_attempted=steps_raw,
            escalation_reason=escalation_reason,
            repeated_escalation=repeated_escalation,
            specialist_only_signal=specialist_only_signal,
        )

        live_requested = bool(diag.get("live_agent_requested"))
        ai_status = "user_requested_human" if live_requested else "unresolved"
        if ai_status not in AI_RESOLUTION_STATUSES:  # defensive
            ai_status = "unresolved"

        supervisor = state.get("supervisor_decision") or {}
        queue_target = supervisor.get("specialist") or supervisor.get("agent") or ticket.category

        context = EscalationContext(
            ticket_id=ticket.id,
            transcript_snapshot_id=snapshot.id,
            chat_session_id=chat_session_id,
            user_id=requester.id if requester else None,
            escalation_created_at=datetime.now(UTC),
            issue_summary=ticket.ai_summary or problem_statement,
            user_problem_statement=problem_statement,
            detected_intent=(diag.get("last_response_type") or diag.get("detected_intent")),
            category=ticket.category or state.get("issue_category"),
            subcategory=ticket.subcategory or state.get("issue_subtype"),
            affected_system=diag.get("affected_system") or diag.get("normalized_system"),
            urgency=ticket.urgency or state.get("urgency"),
            sentiment=diag.get("sentiment"),
            ai_attempted_steps=attempted_steps,
            user_feedback_on_steps=diag.get("user_feedback_on_steps") or [],
            kb_articles_referenced=kb_refs,
            kb_gap_tags=kb_gap_tags,
            web_research_findings=state.get("web_research_findings"),
            ai_confidence=state.get("resolution_confidence") or ticket.ai_confidence,
            ai_resolution_status=ai_status,
            escalation_reason=escalation_reason,
            live_support_required=True,
            specialist_queue_target=queue_target,
            handoff_triggered_by=("user_request" if live_requested else "exhausted_grounded_steps"),
            supervisor_decision_trace=state.get("supervisor_decision_trace") or [],
            diagnostic_slots={
                k: v
                for k, v in diag.items()
                if isinstance(v, (str, int, float, bool)) and v not in (None, "")
            },
            context_version=ESCALATION_CONTEXT_VERSION,
        )
        self.db.add(context)
        await self.db.flush()

        await self._audit_creation(context, snapshot, requester)
        logger.info(
            "escalation_artifacts_created",
            ticket_id=str(ticket.id),
            ticket_number=ticket.ticket_number,
            snapshot_id=str(snapshot.id),
            context_id=str(context.id),
            message_count=len(messages),
            kb_gap_tags=kb_gap_tags,
        )
        return context

    # ── Specialist read view ─────────────────────────────────────────────

    async def get_handoff_view(self, ticket_id: uuid.UUID) -> SpecialistHandoffView | None:
        """Assemble the summary-first / transcript-second specialist view.

        Degrades gracefully: if no structured context was persisted (e.g. an old
        ticket), returns a view built from the ticket alone with
        ``has_structured_context=False`` rather than failing.
        """
        ticket = await self.db.get(Ticket, ticket_id)
        if ticket is None:
            return None

        context = await self._get_context_by_ticket(ticket_id)
        if context is None:
            return SpecialistHandoffView(
                ticket_id=ticket.id,
                ticket_number=ticket.ticket_number,
                issue_summary=ticket.ai_summary or ticket.title,
                category=ticket.category,
                subcategory=ticket.subcategory,
                urgency=ticket.urgency,
                ai_confidence=ticket.ai_confidence,
                escalation_reason=None,
                has_structured_context=False,
            )

        transcript = None
        snapshot = context.transcript_snapshot
        if snapshot is not None:
            transcript = TranscriptSnapshotOut(
                id=snapshot.id,
                chat_session_id=snapshot.chat_session_id,
                captured_at=snapshot.captured_at,
                message_count=snapshot.message_count,
                context_version=snapshot.context_version,
                messages=[TranscriptMessageOut(**m) for m in (snapshot.messages or [])],
            )

        return SpecialistHandoffView(
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            issue_summary=context.issue_summary or ticket.ai_summary or ticket.title,
            category=context.category,
            subcategory=context.subcategory,
            affected_system=context.affected_system,
            urgency=context.urgency,
            ai_confidence=context.ai_confidence,
            ai_resolution_status=context.ai_resolution_status,
            escalation_reason=context.escalation_reason,
            escalation_created_at=context.escalation_created_at,
            user_problem_statement=context.user_problem_statement,
            detected_intent=context.detected_intent,
            steps_attempted=[AttemptedStepOut(**s) for s in (context.ai_attempted_steps or [])],
            kb_articles_referenced=[
                KBArticleRefOut(**r) for r in (context.kb_articles_referenced or [])
            ],
            kb_gap_tags=context.kb_gap_tags or [],
            web_research_findings=context.web_research_findings,
            transcript=transcript,
            has_structured_context=True,
        )

    async def get_context_out(self, ticket_id: uuid.UUID) -> EscalationContextOut | None:
        """Return the raw structured context DTO (analytics / admin use)."""
        context = await self._get_context_by_ticket(ticket_id)
        if context is None:
            return None
        return self._to_context_out(context)

    # ── Resolution comparison (post-resolution) ──────────────────────────

    async def record_resolution_comparison(
        self,
        *,
        ticket_id: uuid.UUID,
        specialist_resolution_summary: str,
        specialist_resolution_steps: list[str],
        final_resolution_category: str | None,
        ai_vs_specialist_resolution_gap: str | None,
        kb_candidate_flag: bool,
        actor: User | None = None,
    ) -> EscalationContext | None:
        """Capture what the specialist actually did, for AI/KB improvement.

        Stores structured data only — there is NO uncontrolled self-learning.
        Returns None if the ticket has no escalation context (nothing to compare).
        """
        context = await self._get_context_by_ticket(ticket_id)
        if context is None:
            return None

        context.specialist_resolution_summary = specialist_resolution_summary
        context.specialist_resolution_steps = specialist_resolution_steps
        context.final_resolution_category = final_resolution_category
        context.ai_vs_specialist_resolution_gap = ai_vs_specialist_resolution_gap
        context.kb_candidate_flag = kb_candidate_flag
        context.resolution_compared_at = datetime.now(UTC)
        await self.db.flush()

        await self._audit_comparison(context, actor)
        logger.info(
            "escalation_resolution_comparison_recorded",
            ticket_id=str(ticket_id),
            context_id=str(context.id),
            kb_candidate_flag=kb_candidate_flag,
        )
        return context

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _get_context_by_ticket(self, ticket_id: uuid.UUID) -> EscalationContext | None:
        stmt = select(EscalationContext).where(EscalationContext.ticket_id == ticket_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _to_context_out(self, c: EscalationContext) -> EscalationContextOut:
        return EscalationContextOut(
            id=c.id,
            ticket_id=c.ticket_id,
            transcript_snapshot_id=c.transcript_snapshot_id,
            chat_session_id=c.chat_session_id,
            escalation_created_at=c.escalation_created_at,
            issue_summary=c.issue_summary,
            user_problem_statement=c.user_problem_statement,
            detected_intent=c.detected_intent,
            category=c.category,
            subcategory=c.subcategory,
            affected_system=c.affected_system,
            urgency=c.urgency,
            sentiment=c.sentiment,
            ai_attempted_steps=[AttemptedStepOut(**s) for s in (c.ai_attempted_steps or [])],
            user_feedback_on_steps=c.user_feedback_on_steps or [],
            kb_articles_referenced=[KBArticleRefOut(**r) for r in (c.kb_articles_referenced or [])],
            kb_gap_tags=c.kb_gap_tags or [],
            web_research_findings=c.web_research_findings,
            ai_confidence=c.ai_confidence,
            ai_resolution_status=c.ai_resolution_status,
            escalation_reason=c.escalation_reason,
            live_support_required=c.live_support_required,
            specialist_queue_target=c.specialist_queue_target,
            handoff_triggered_by=c.handoff_triggered_by,
            diagnostic_slots=c.diagnostic_slots or {},
            context_version=c.context_version,
            specialist_resolution_summary=c.specialist_resolution_summary,
            specialist_resolution_steps=c.specialist_resolution_steps or [],
            final_resolution_category=c.final_resolution_category,
            ai_vs_specialist_resolution_gap=c.ai_vs_specialist_resolution_gap,
            kb_candidate_flag=c.kb_candidate_flag,
            resolution_compared_at=c.resolution_compared_at,
        )

    async def _audit_creation(
        self,
        context: EscalationContext,
        snapshot: TranscriptSnapshot,
        actor: User | None,
    ) -> None:
        try:
            from app.services.audit_service import AuditService

            await AuditService(self.db).log(
                action="chat.escalation_package_created",
                resource_type="escalation_context",
                actor=actor,
                resource_id=str(context.id),
                description=(
                    f"Escalation package created for ticket {context.ticket_id} "
                    f"(snapshot {snapshot.id}, {snapshot.message_count} messages)"
                ),
                new_value={
                    "ticket_id": str(context.ticket_id),
                    "transcript_snapshot_id": str(snapshot.id),
                    "message_count": snapshot.message_count,
                    "kb_gap_tags": context.kb_gap_tags,
                    "handoff_triggered_by": context.handoff_triggered_by,
                },
                severity="info",
            )
        except Exception as exc:  # audit must never break the escalation path
            logger.warning("escalation_audit_failed", error=str(exc))

    async def _audit_comparison(self, context: EscalationContext, actor: User | None) -> None:
        try:
            from app.services.audit_service import AuditService

            await AuditService(self.db).log(
                action="chat.escalation_resolution_compared",
                resource_type="escalation_context",
                actor=actor,
                resource_id=str(context.id),
                description=(
                    f"Specialist resolution comparison recorded for ticket {context.ticket_id}"
                ),
                new_value={
                    "ticket_id": str(context.ticket_id),
                    "kb_candidate_flag": context.kb_candidate_flag,
                    "final_resolution_category": context.final_resolution_category,
                },
                severity="info",
            )
        except Exception as exc:
            logger.warning("escalation_comparison_audit_failed", error=str(exc))


__all__ = ["EscalationService", "extract_transcript"]
