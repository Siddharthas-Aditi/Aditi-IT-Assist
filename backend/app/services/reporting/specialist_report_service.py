"""Per-specialist performance report aggregation (C1).

Aggregates ticket-lifecycle metrics (volume, reopen rate, average resolution
time, SLA violations) and feedback metrics (CSAT, dissatisfaction count) per
assigned agent for a given time window, plus a team-totals row.

RBAC (leads/admins only) is enforced at the API layer, not here — this
service is a pure aggregation over whatever window it is asked to compute.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.auth import User
from app.models.ticket import Ticket, TicketEvent
from app.schemas.reporting import SpecialistReport, SpecialistReportRow
from app.services.feedback_analytics_service import FeedbackAnalyticsService

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

# Ticket.status values a ticket can be reopened *into* (see TICKET_STATUSES
# in app/models/ticket.py). Anything other than resolved/closed counts.
_ACTIVE_STATUSES = {"new", "triaged", "in_progress", "waiting_for_user", "escalated"}
# Ticket.status values a ticket can be reopened *from*.
_CLOSED_STATUSES = {"resolved", "closed"}


def _avg_hours(deltas_seconds: list[float]) -> float | None:
    """Average a list of second-deltas into hours, or None if empty."""
    if not deltas_seconds:
        return None
    return round(sum(deltas_seconds) / len(deltas_seconds) / 3600.0, 2)


class SpecialistReportService:
    """Builds the per-specialist performance report for a time window."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.feedback = FeedbackAnalyticsService(db)

    async def build_report(self, *, start: datetime, end: datetime) -> SpecialistReport:
        """Aggregate ticket + feedback metrics per agent for [start, end]."""
        tickets_by_agent = await self._resolved_tickets_by_agent(start, end)
        reopened = await self._reopened_counts(start, end)

        agent_ids = set(tickets_by_agent) | set(reopened)
        names = await self._agent_names(agent_ids)

        rows: list[SpecialistReportRow] = [
            await self._build_row(
                agent_id,
                tickets_by_agent.get(agent_id, []),
                reopened.get(agent_id, 0),
                names,
                start,
                end,
            )
            # Stable, human-friendly ordering by display name.
            for agent_id in sorted(agent_ids, key=lambda a: names.get(a, ("", None))[0])
        ]

        totals = self._totals(rows)
        return SpecialistReport(period_start=start, period_end=end, rows=rows, totals=totals)

    async def _build_row(
        self,
        agent_id: str,
        tickets: list[Ticket],
        reopened_count: int,
        names: dict[str, tuple[str, str | None]],
        start: datetime,
        end: datetime,
    ) -> SpecialistReportRow:
        resolution_seconds = [
            (t.resolved_at - t.created_at).total_seconds()
            for t in tickets
            if t.resolved_at and t.created_at
        ]
        sla_violations = sum(
            1
            for t in tickets
            if t.sla_resolution_target and t.resolved_at and t.resolved_at > t.sla_resolution_target
        )
        feedback = await self.feedback.get_agent_summary(
            uuid.UUID(agent_id), from_dt=start, to_dt=end
        )
        name, email = names.get(agent_id, ("Unknown", None))
        return SpecialistReportRow(
            agent_id=agent_id,
            agent_name=name,
            agent_email=email,
            total_tickets=len(tickets),
            reopened=reopened_count,
            avg_resolution_hours=_avg_hours(resolution_seconds),
            sla_violations=sla_violations,
            csat_avg=feedback.csat_avg,
            dsat=feedback.negative_count,
            feedback_responses=feedback.sessions_with_feedback,
        )

    async def _resolved_tickets_by_agent(
        self, start: datetime, end: datetime
    ) -> dict[str, list[Ticket]]:
        """Tickets resolved in [start, end], grouped by assignee."""
        stmt = select(Ticket).where(
            Ticket.assigned_to.is_not(None),
            Ticket.resolved_at.is_not(None),
            Ticket.resolved_at >= start,
            Ticket.resolved_at <= end,
        )
        tickets = list((await self.db.execute(stmt)).scalars().all())
        by_agent: dict[str, list[Ticket]] = {}
        for ticket in tickets:
            by_agent.setdefault(str(ticket.assigned_to), []).append(ticket)
        return by_agent

    async def _reopened_counts(self, start: datetime, end: datetime) -> dict[str, int]:
        """Count reopen events (closed -> active) per assignee in range."""
        stmt = (
            select(TicketEvent, Ticket.assigned_to)
            .join(Ticket, TicketEvent.ticket_id == Ticket.id)
            .where(
                TicketEvent.event_type == "status_changed",
                TicketEvent.created_at >= start,
                TicketEvent.created_at <= end,
                Ticket.assigned_to.is_not(None),
            )
        )
        counts: dict[str, int] = {}
        for event, assigned_to in (await self.db.execute(stmt)).all():
            old = (event.old_value or "").lower()
            new = (event.new_value or "").lower()
            if old in _CLOSED_STATUSES and new in _ACTIVE_STATUSES:
                key = str(assigned_to)
                counts[key] = counts.get(key, 0) + 1
        return counts

    async def _agent_names(self, agent_ids: set[str]) -> dict[str, tuple[str, str | None]]:
        """Map agent id (str) -> (display name, email)."""
        if not agent_ids:
            return {}
        stmt = select(User).where(User.id.in_([uuid.UUID(a) for a in agent_ids]))
        return {
            str(user.id): (user.full_name or user.email, user.email)
            for user in (await self.db.execute(stmt)).scalars().all()
        }

    def _totals(self, rows: list[SpecialistReportRow]) -> SpecialistReportRow:
        """Team-totals row: sums for counts, means-of-means for the rate fields."""
        res_hours = [r.avg_resolution_hours for r in rows if r.avg_resolution_hours is not None]
        csats = [r.csat_avg for r in rows if r.csat_avg is not None]
        return SpecialistReportRow(
            agent_id=None,
            agent_name="Team totals",
            total_tickets=sum(r.total_tickets for r in rows),
            reopened=sum(r.reopened for r in rows),
            avg_resolution_hours=(round(sum(res_hours) / len(res_hours), 2) if res_hours else None),
            sla_violations=sum(r.sla_violations for r in rows),
            csat_avg=(round(sum(csats) / len(csats), 2) if csats else None),
            dsat=sum(r.dsat for r in rows),
            feedback_responses=sum(r.feedback_responses for r in rows),
        )
