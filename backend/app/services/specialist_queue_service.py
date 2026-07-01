"""Specialist queue service — list, atomic-claim, release, note, resolve.

The queue is a view over the existing ``tickets`` table, filtered to:

* ``source = 'chat'`` (queue entries come from chat escalation), AND
* ``status in ('new', 'triaged', 'in_progress', 'waiting_for_user', 'escalated')``.

Atomic claim
------------
Two specialists must NOT pick up the same chat. We enforce this with a
single ``UPDATE tickets SET assigned_to=:user, status='in_progress' WHERE
id=:id AND (assigned_to IS NULL OR assigned_to=:user)`` and check the row
count. Postgres makes that atomic; our DB-level constraint is the source
of truth, not application-level locks.

Knowledge candidates on resolve
-------------------------------
When a specialist closes a ticket they may opt to send the resolution to the
Knowledge Improvement queue. The service calls
:meth:`KnowledgeImprovementService.record_specialist_resolution` — which
creates a candidate, NOT a published article. SMEs review separately.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select, update

from app.core.logging import get_logger
from app.models.escalation import EscalationContext
from app.models.ticket import Ticket
from app.schemas.specialist_queue import (
    ConversationTurn,
    HandoffPackage,
    HandoffSummary,
    KBSourceConsulted,
    QueueEntry,
    StepAttempted,
)
from app.services.knowledge.improvement import KnowledgeImprovementService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.auth import User

logger = get_logger(__name__)


_QUEUE_STATUSES: tuple[str, ...] = (
    "new", "triaged", "in_progress", "waiting_for_user", "escalated",
)


class SpecialistQueueService:
    """Operational queue for live IT specialists."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Listing ────────────────────────────────────────────────────────

    async def list_queue(
        self,
        *,
        only_unclaimed: bool = False,
        for_user_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[QueueEntry]:
        """Return queue entries with structured summaries.

        Args:
            only_unclaimed: If True, exclude rows already claimed by anyone.
            for_user_id: If set, ALSO include rows assigned to this specialist
                so they can see what they're already working on.
        """
        clauses = [
            Ticket.source == "chat",
            Ticket.status.in_(_QUEUE_STATUSES),
        ]
        if only_unclaimed:
            if for_user_id is not None:
                clauses.append(
                    or_(Ticket.assigned_to.is_(None), Ticket.assigned_to == for_user_id)
                )
            else:
                clauses.append(Ticket.assigned_to.is_(None))

        stmt = (
            select(Ticket)
            .where(and_(*clauses))
            .order_by(
                # Priority desc (critical first), then oldest first within a tier.
                Ticket.priority.desc(),
                Ticket.created_at.asc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tickets = list(result.scalars().all())
        return [self._to_queue_entry(t) for t in tickets]

    # ── Atomic claim ───────────────────────────────────────────────────

    async def claim(
        self, ticket_id: uuid.UUID, *, claimer: User,
    ) -> Ticket:
        """Atomically claim a queue entry for this specialist.

        Returns the updated :class:`Ticket`. Raises :class:`PermissionError`
        if another specialist already owns it.
        """
        now = datetime.now(UTC)
        stmt = (
            update(Ticket)
            .where(
                and_(
                    Ticket.id == ticket_id,
                    Ticket.source == "chat",
                    or_(Ticket.assigned_to.is_(None), Ticket.assigned_to == claimer.id),
                )
            )
            .values(
                assigned_to=claimer.id,
                status="in_progress",
                # Stamp first response only if not already set (COALESCE is a
                # function — NOT a binary operator, so use func.coalesce here).
                first_response_at=func.coalesce(Ticket.first_response_at, now),
            )
            .returning(Ticket)
        )
        result = await self.db.execute(stmt)
        ticket = result.scalar_one_or_none()
        if ticket is None:
            # Either the row doesn't exist, or someone else got there first.
            existing = await self.db.get(Ticket, ticket_id)
            if existing is None:
                raise LookupError(f"Ticket {ticket_id} not found")
            if existing.assigned_to and existing.assigned_to != claimer.id:
                raise PermissionError(
                    f"Ticket {existing.ticket_number} is already claimed by "
                    f"another specialist"
                )
            raise PermissionError("Ticket is not claimable in its current state")

        logger.info(
            "specialist_queue_claimed",
            ticket_id=str(ticket.id),
            ticket_number=ticket.ticket_number,
            claimer_id=str(claimer.id),
        )
        return ticket

    async def release(self, ticket_id: uuid.UUID, *, by_user: User) -> Ticket:
        """Release a claim — only the claimer (or admin) may do this."""
        ticket = await self.db.get(Ticket, ticket_id)
        if ticket is None:
            raise LookupError(f"Ticket {ticket_id} not found")
        if ticket.assigned_to != by_user.id:
            raise PermissionError("Only the current claimer may release this ticket")
        ticket.assigned_to = None
        ticket.status = "triaged"
        await self.db.flush()
        return ticket

    # ── Resolve ────────────────────────────────────────────────────────

    async def resolve(
        self,
        ticket_id: uuid.UUID,
        *,
        by_user: User,
        resolution_notes: str,
        propose_knowledge_candidate: bool,
    ) -> tuple[Ticket, uuid.UUID | None]:
        """Mark resolved + optionally propose a knowledge candidate.

        The candidate is a *draft* for SME review — this does NOT write to
        ``knowledge_articles`` directly.
        """
        ticket = await self.db.get(Ticket, ticket_id)
        if ticket is None:
            raise LookupError(f"Ticket {ticket_id} not found")
        if ticket.assigned_to != by_user.id:
            raise PermissionError("Only the current claimer may resolve this ticket")

        now = datetime.now(UTC)
        ticket.status = "resolved"
        ticket.resolved_at = now
        ticket.resolution_notes = resolution_notes

        candidate_id: uuid.UUID | None = None
        if propose_knowledge_candidate:
            improvement = KnowledgeImprovementService(self.db)
            candidate = await improvement.record_specialist_resolution(
                title=f"Specialist resolution: {ticket.title}",
                body=resolution_notes,
                proposed_by_agent="specialist_queue",
                steps=[],  # specialists can edit / add steps in the review UI
                category=ticket.category,
                subtype=ticket.subcategory,
                ticket_id=ticket.id,
                proposed_by_user_id=by_user.id,
            )
            candidate_id = candidate.id

        # Baseline resolution-comparison capture: record what the specialist did
        # onto the escalation context so AI-suggested vs specialist-actual can be
        # compared later (human-reviewed improvement, NOT self-learning). A richer
        # structured comparison can be submitted via the dedicated endpoint.
        from app.services.escalation_service import EscalationService

        await EscalationService(self.db).record_resolution_comparison(
            ticket_id=ticket.id,
            specialist_resolution_summary=resolution_notes,
            specialist_resolution_steps=[],
            final_resolution_category=ticket.category,
            ai_vs_specialist_resolution_gap=None,
            kb_candidate_flag=propose_knowledge_candidate,
            actor=by_user,
        )

        await self.db.flush()
        logger.info(
            "specialist_queue_resolved",
            ticket_id=str(ticket.id),
            resolver_id=str(by_user.id),
            candidate_id=str(candidate_id) if candidate_id else None,
        )
        return ticket, candidate_id

    # ── Handoff package ────────────────────────────────────────────────

    async def build_handoff_package(
        self,
        ticket: Ticket,
        *,
        session_state: dict | None = None,
    ) -> HandoffPackage:
        """Assemble the typed context bundle attached to a queue entry.

        Primary source is the **persisted** escalation context + transcript
        snapshot (so the package survives a process restart and is never the
        data-starved version that the old in-memory-only lookup produced). If no
        persisted context exists yet, falls back to the live in-memory session
        state, then the ticket's own fields. Nothing here invents data.
        """
        context = await self._get_escalation_context(ticket.id)
        if context is not None:
            return self._package_from_context(ticket, context)

        # Fallback: live in-memory state (pre-persistence) or ticket-only.
        state = session_state or {}
        diag = state.get("diagnostic_context") or {}

        summary = HandoffSummary(
            issue_one_liner=(
                ticket.ai_summary
                or diag.get("exact_problem_statement")
                or ticket.title
            ),
            affected_system=diag.get("affected_system"),
            issue_category=ticket.category,
            issue_subtype=diag.get("issue_subtype") or ticket.subcategory,
            urgency=ticket.urgency,
            ai_confidence_at_handoff=ticket.ai_confidence or 0.0,
        )

        return HandoffPackage(
            session_id=str(ticket.session_id) if ticket.session_id else "",
            ticket_id=ticket.id,
            summary=summary,
            diagnostic_slots={
                k: str(v) for k, v in diag.items() if isinstance(v, (str, int, float, bool)) and v
            },
            handoff_reason=diag.get("escalation_reason") or "AI exhausted grounded steps",
            handoff_triggered_by=(
                "user_request"
                if diag.get("live_agent_requested")
                else "exhausted_grounded_steps"
            ),
        )

    async def _get_escalation_context(
        self, ticket_id: uuid.UUID
    ) -> EscalationContext | None:
        stmt = select(EscalationContext).where(
            EscalationContext.ticket_id == ticket_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _package_from_context(
        self, ticket: Ticket, context: EscalationContext
    ) -> HandoffPackage:
        """Build the typed handoff package from the persisted escalation context."""
        summary = HandoffSummary(
            issue_one_liner=context.issue_summary or ticket.ai_summary or ticket.title,
            affected_system=context.affected_system,
            issue_category=context.category or ticket.category,
            issue_subtype=context.subcategory or ticket.subcategory,
            urgency=context.urgency,  # type: ignore[arg-type]
            ai_confidence_at_handoff=context.ai_confidence or ticket.ai_confidence or 0.0,
        )

        steps = [
            StepAttempted(
                instruction=s.get("instruction", ""),
                outcome=s.get("outcome", "unknown"),
                source_kb_title=s.get("source_kb_title"),
            )
            for s in (context.ai_attempted_steps or [])
        ]
        kb_sources = [
            KBSourceConsulted(
                article_id=r.get("article_id") or "",
                title=r.get("title") or "Untitled article",
                relevance=r.get("relevance"),
            )
            for r in (context.kb_articles_referenced or [])
        ]

        conversation: list[ConversationTurn] = []
        snapshot = context.transcript_snapshot
        if snapshot is not None:
            for m in snapshot.messages or []:
                role = m.get("role")
                # ConversationTurn only models user/assistant AI turns.
                if role == "employee":
                    role = "user"
                if role in ("user", "assistant"):
                    conversation.append(
                        ConversationTurn(role=role, content=m.get("content", ""))
                    )

        handoff_triggered_by = context.handoff_triggered_by or "exhausted_grounded_steps"
        valid_triggers = {
            "user_request", "ai_low_confidence", "exhausted_grounded_steps",
            "loop_detected", "repeated_failure", "policy_block", "missing_data",
        }
        if handoff_triggered_by not in valid_triggers:
            handoff_triggered_by = "exhausted_grounded_steps"

        return HandoffPackage(
            session_id=context.chat_session_id,
            ticket_id=ticket.id,
            summary=summary,
            diagnostic_slots={
                k: str(v) for k, v in (context.diagnostic_slots or {}).items() if v
            },
            steps_attempted=steps,
            kb_sources_consulted=kb_sources,
            conversation=conversation,
            handoff_reason=context.escalation_reason or "AI exhausted grounded steps",
            handoff_triggered_by=handoff_triggered_by,  # type: ignore[arg-type]
            supervisor_decision_trace=context.supervisor_decision_trace or [],
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _to_queue_entry(self, ticket: Ticket) -> QueueEntry:
        return QueueEntry(
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            title=ticket.title,
            priority=ticket.priority,  # type: ignore[arg-type]
            status=ticket.status,  # type: ignore[arg-type]
            category=ticket.category,
            issue_subtype=ticket.subcategory,
            queued_at=ticket.created_at,
            claimed_at=ticket.first_response_at,
            summary=HandoffSummary(
                issue_one_liner=ticket.ai_summary or ticket.title,
                affected_system=None,
                issue_category=ticket.category,
                issue_subtype=ticket.subcategory,
                urgency=ticket.urgency,  # type: ignore[arg-type]
                ai_confidence_at_handoff=ticket.ai_confidence or 0.0,
            ),
        )


__all__ = ["SpecialistQueueService"]
