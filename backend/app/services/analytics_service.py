"""Analytics service — aggregates metrics for IT dashboards."""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remote_support import RemoteSupportSession
from app.models.support import SupportSession
from app.models.ticket import Ticket

logger = structlog.get_logger()


class AnalyticsService:
    """Computes real-time and historical analytics for IT management dashboards."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_dashboard_summary(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict:
        """Get high-level dashboard metrics."""
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)

        return {
            "ticket_metrics": await self._ticket_metrics(start_date, end_date),
            "ai_metrics": await self._ai_metrics(start_date, end_date),
            "sla_metrics": await self._sla_metrics(start_date, end_date),
            "remote_support_metrics": await self._remote_support_metrics(start_date, end_date),
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        }

    async def _ticket_metrics(self, start: datetime, end: datetime) -> dict:
        """Compute ticket volume and status distribution."""
        # Total tickets in period
        total_stmt = select(func.count(Ticket.id)).where(
            and_(Ticket.created_at >= start, Ticket.created_at <= end)
        )
        total_result = await self.db.execute(total_stmt)
        total = total_result.scalar() or 0

        # Status distribution
        status_stmt = (
            select(Ticket.status, func.count(Ticket.id))
            .where(and_(Ticket.created_at >= start, Ticket.created_at <= end))
            .group_by(Ticket.status)
        )
        status_result = await self.db.execute(status_stmt)
        status_dist = {row[0]: row[1] for row in status_result.all()}

        # Priority distribution
        priority_stmt = (
            select(Ticket.priority, func.count(Ticket.id))
            .where(and_(Ticket.created_at >= start, Ticket.created_at <= end))
            .group_by(Ticket.priority)
        )
        priority_result = await self.db.execute(priority_stmt)
        priority_dist = {row[0]: row[1] for row in priority_result.all()}

        # Category distribution
        category_stmt = (
            select(Ticket.category, func.count(Ticket.id))
            .where(
                and_(Ticket.created_at >= start, Ticket.created_at <= end, Ticket.category.isnot(None))
            )
            .group_by(Ticket.category)
            .order_by(func.count(Ticket.id).desc())
            .limit(10)
        )
        category_result = await self.db.execute(category_stmt)
        category_dist = {row[0]: row[1] for row in category_result.all()}

        return {
            "total": total,
            "status_distribution": status_dist,
            "priority_distribution": priority_dist,
            "category_distribution": category_dist,
        }

    async def _ai_metrics(self, start: datetime, end: datetime) -> dict:
        """Compute AI resolution effectiveness metrics."""
        # Sessions with AI resolution
        ai_resolved_stmt = select(func.count(SupportSession.id)).where(
            and_(
                SupportSession.created_at >= start,
                SupportSession.created_at <= end,
                SupportSession.status == "resolved",
                SupportSession.confidence_score.isnot(None),
            )
        )
        ai_resolved_result = await self.db.execute(ai_resolved_stmt)
        ai_resolved = ai_resolved_result.scalar() or 0

        # Total sessions
        total_sessions_stmt = select(func.count(SupportSession.id)).where(
            and_(SupportSession.created_at >= start, SupportSession.created_at <= end)
        )
        total_sessions_result = await self.db.execute(total_sessions_stmt)
        total_sessions = total_sessions_result.scalar() or 0

        # Average confidence
        avg_conf_stmt = select(func.avg(SupportSession.confidence_score)).where(
            and_(
                SupportSession.created_at >= start,
                SupportSession.created_at <= end,
                SupportSession.confidence_score.isnot(None),
            )
        )
        avg_conf_result = await self.db.execute(avg_conf_stmt)
        avg_confidence = avg_conf_result.scalar()

        # Escalation count
        escalated_stmt = select(func.count(SupportSession.id)).where(
            and_(
                SupportSession.created_at >= start,
                SupportSession.created_at <= end,
                SupportSession.status == "escalated",
            )
        )
        escalated_result = await self.db.execute(escalated_stmt)
        escalated = escalated_result.scalar() or 0

        resolution_rate = (ai_resolved / total_sessions * 100) if total_sessions > 0 else 0
        escalation_rate = (escalated / total_sessions * 100) if total_sessions > 0 else 0

        return {
            "total_sessions": total_sessions,
            "ai_resolved": ai_resolved,
            "resolution_rate": round(resolution_rate, 1),
            "escalation_rate": round(escalation_rate, 1),
            "avg_confidence": round(avg_confidence, 2) if avg_confidence else None,
        }

    async def _sla_metrics(self, start: datetime, end: datetime) -> dict:
        """Compute SLA compliance metrics.

        ``compliance_rate`` is a *real* rate over tickets resolved in the period
        that carried a resolution target: the share resolved on or before that
        target. It is ``None`` (rendered as "No data") when there is nothing to
        measure, so the UI never shows ``NaN%``.
        """
        now = datetime.now(timezone.utc)

        # SLA at risk (open, within 1 hour of breach)
        at_risk_stmt = select(func.count(Ticket.id)).where(
            and_(
                Ticket.status.in_(["new", "triaged", "in_progress", "waiting_for_user"]),
                Ticket.sla_resolution_target.isnot(None),
                Ticket.sla_resolution_target <= now + timedelta(hours=1),
                Ticket.sla_resolution_target > now,
            )
        )
        at_risk = (await self.db.execute(at_risk_stmt)).scalar() or 0

        # SLA breached (open, past target)
        breached_stmt = select(func.count(Ticket.id)).where(
            and_(
                Ticket.status.in_(["new", "triaged", "in_progress", "waiting_for_user"]),
                Ticket.sla_resolution_target.isnot(None),
                Ticket.sla_resolution_target < now,
            )
        )
        breached = (await self.db.execute(breached_stmt)).scalar() or 0

        # Compliance over tickets RESOLVED in the period that had a target.
        resolved_with_target_stmt = select(func.count(Ticket.id)).where(
            and_(
                Ticket.resolved_at.isnot(None),
                Ticket.resolved_at >= start,
                Ticket.resolved_at <= end,
                Ticket.sla_resolution_target.isnot(None),
            )
        )
        resolved_with_target = (await self.db.execute(resolved_with_target_stmt)).scalar() or 0

        resolved_on_time_stmt = select(func.count(Ticket.id)).where(
            and_(
                Ticket.resolved_at.isnot(None),
                Ticket.resolved_at >= start,
                Ticket.resolved_at <= end,
                Ticket.sla_resolution_target.isnot(None),
                Ticket.resolved_at <= Ticket.sla_resolution_target,
            )
        )
        resolved_on_time = (await self.db.execute(resolved_on_time_stmt)).scalar() or 0

        compliance_rate = (
            round(resolved_on_time / resolved_with_target * 100, 1)
            if resolved_with_target > 0
            else None
        )

        return {
            "at_risk": at_risk,
            "breached": breached,
            "resolved_with_target": resolved_with_target,
            "resolved_on_time": resolved_on_time,
            "compliance_rate": compliance_rate,
        }

    async def _remote_support_metrics(self, start: datetime, end: datetime) -> dict:
        """Compute remote support usage metrics."""
        total_stmt = select(func.count(RemoteSupportSession.id)).where(
            and_(
                RemoteSupportSession.created_at >= start,
                RemoteSupportSession.created_at <= end,
            )
        )
        total_result = await self.db.execute(total_stmt)
        total = total_result.scalar() or 0

        completed_stmt = select(func.count(RemoteSupportSession.id)).where(
            and_(
                RemoteSupportSession.created_at >= start,
                RemoteSupportSession.created_at <= end,
                RemoteSupportSession.status == "completed",
            )
        )
        completed_result = await self.db.execute(completed_stmt)
        completed = completed_result.scalar() or 0

        return {
            "total_sessions": total,
            "completed_sessions": completed,
        }

    async def get_agent_workload(self) -> list[dict]:
        """Get current workload distribution across IT agents."""
        stmt = (
            select(
                Ticket.assigned_to,
                func.count(Ticket.id).label("ticket_count"),
            )
            .where(
                Ticket.status.in_(["new", "triaged", "in_progress", "waiting_for_user"]),
                Ticket.assigned_to.isnot(None),
            )
            .group_by(Ticket.assigned_to)
        )
        result = await self.db.execute(stmt)
        return [
            {"agent_id": str(row[0]), "active_tickets": row[1]}
            for row in result.all()
        ]
