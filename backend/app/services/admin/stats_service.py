"""Real system-overview counters for the admin dashboard.

Replaces the previous hardcoded-zero stub. Every value is a live aggregate and
every rate is divide-by-zero safe.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.auth import User
from app.models.knowledge import KnowledgeArticle
from app.models.support import SupportSession
from app.models.ticket import Ticket
from app.schemas.admin import SystemStats

OPEN_TICKET_STATUSES = ("new", "triaged", "in_progress", "waiting_for_user", "escalated")


class AdminStatsService:
    """Computes the admin overview counters."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_system_stats(self) -> SystemStats:
        total_users = await self._count(select(func.count(User.id)))
        active_users = await self._count(
            select(func.count(User.id)).where(User.is_active.is_(True))
        )
        total_tickets = await self._count(select(func.count(Ticket.id)))
        open_tickets = await self._count(
            select(func.count(Ticket.id)).where(Ticket.status.in_(OPEN_TICKET_STATUSES))
        )
        published_articles = await self._count(
            select(func.count(KnowledgeArticle.id)).where(
                KnowledgeArticle.status == "published"
            )
        )
        draft_articles = await self._count(
            select(func.count(KnowledgeArticle.id)).where(
                KnowledgeArticle.status == "draft"
            )
        )
        since = datetime.now(UTC) - timedelta(hours=24)
        audit_24h = await self._count(
            select(func.count(AuditEvent.id)).where(AuditEvent.created_at >= since)
        )
        total_sessions = await self._count(select(func.count(SupportSession.id)))
        resolved_sessions = await self._count(
            select(func.count(SupportSession.id)).where(SupportSession.status == "resolved")
        )

        resolution_rate = (
            round(resolved_sessions / total_sessions * 100, 1) if total_sessions else 0.0
        )

        return SystemStats(
            total_users=total_users,
            active_users=active_users,
            total_tickets=total_tickets,
            open_tickets=open_tickets,
            published_articles=published_articles,
            draft_articles=draft_articles,
            audit_events_24h=audit_24h,
            total_sessions=total_sessions,
            resolution_rate=resolution_rate,
        )

    async def _count(self, stmt) -> int:
        return (await self.db.execute(stmt)).scalar() or 0
