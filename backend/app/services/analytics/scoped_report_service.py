"""Scoped analytics reports — all queries enforced server-side.

Every public method takes ``viewer_permissions: frozenset[str]`` and scopes
data based on which analytics permission the caller holds:

* ``analytics:view_all``  — full org data (IT_LEAD, IT_ADMIN, SECURITY_AUDITOR)
* ``analytics:view_team`` — same as view_all in the current data model; a
  dedicated team-membership table does not yet exist. Flag as data-gap for
  future team-based scoping.
* ``analytics:view_own``  — caller's own sessions/tickets only (EMPLOYEE, IT_AGENT)

Scoping is enforced here, not at the API layer. The API layer handles
authentication and passes the resolved permission set; this service enforces
authorisation at the query level.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select

from app.core.permissions import P
from app.models.agent_action_ledger import AgentActionLedger
from app.models.feedback import ConversationFeedback
from app.models.knowledge import KnowledgeArticle
from app.models.support import SupportSession
from app.models.ticket import Ticket
from app.schemas.analytics import (
    AgentWorkloadRow,
    EscalationRateReport,
    FeedbackSentimentReport,
    KBArticleEffectivenessRow,
    KBEffectivenessReport,
    ResolutionTrendPoint,
    ResolutionTrendReport,
    SLAComplianceReport,
    WorkloadReport,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

_ESCALATED_STATUS = "escalated"


class PermissionDenied(Exception):
    """Raised when caller lacks the required analytics permission."""


def _require(viewer_permissions: frozenset[str], *needed: P) -> None:
    """Raise PermissionDenied if none of the needed permissions are held."""
    if not any(p.value in viewer_permissions for p in needed):
        have = sorted(viewer_permissions)
        need = [p.value for p in needed]
        raise PermissionDenied(f"Missing required permission: need one of {need}, have {have}")


def _window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    s = start or now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    e = end or now
    if s.tzinfo is None:
        s = s.replace(tzinfo=UTC)
    if e.tzinfo is None:
        e = e.replace(tzinfo=UTC)
    return s, e


class ScopedReportService:
    """All six RBAC-scoped analytics reports.

    Pass the caller's resolved permission set (from AuthService.get_user_permissions)
    on every call. Each method raises PermissionDenied rather than returning empty
    data on an unauthorized call, so the API layer can translate to 403.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── 1. Resolution time trends ──────────────────────────────────────────

    async def resolution_time_trends(
        self,
        viewer_permissions: frozenset[str],
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        viewer_user_id: uuid.UUID | None = None,
    ) -> ResolutionTrendReport:
        """Daily avg resolution hours over the window.

        Scoping:
        - view_all: all tickets
        - view_own: only tickets assigned to viewer_user_id
        """
        _require(viewer_permissions, P.ANALYTICS_VIEW_ALL, P.ANALYTICS_VIEW_TEAM)
        start_dt, end_dt = _window(start, end)

        base = and_(
            Ticket.created_at >= start_dt,
            Ticket.created_at <= end_dt,
            Ticket.resolved_at.is_not(None),
        )
        own_only = (
            P.ANALYTICS_VIEW_OWN.value in viewer_permissions
            and P.ANALYTICS_VIEW_ALL.value not in viewer_permissions
            and P.ANALYTICS_VIEW_TEAM.value not in viewer_permissions
        )

        stmt = select(
            func.date_trunc("day", Ticket.created_at).label("day"),
            func.avg(func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600).label(
                "avg_hours"
            ),
            func.count(Ticket.id).label("cnt"),
        ).where(base)

        if own_only and viewer_user_id is not None:
            stmt = stmt.where(Ticket.assigned_to == viewer_user_id)

        stmt = stmt.group_by("day").order_by("day")
        rows = (await self._db.execute(stmt)).all()

        points = [
            ResolutionTrendPoint(
                date=str(row.day.date()),
                avg_resolution_hours=float(row.avg_hours) if row.avg_hours else None,
                ticket_count=int(row.cnt),
            )
            for row in rows
        ]

        # Overall average across the window
        overall_stmt = select(
            func.avg(func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600)
        ).where(base)
        if own_only and viewer_user_id is not None:
            overall_stmt = overall_stmt.where(Ticket.assigned_to == viewer_user_id)
        overall = (await self._db.execute(overall_stmt)).scalar()

        return ResolutionTrendReport(
            points=points,
            overall_avg_hours=float(overall) if overall else None,
            window_start=start_dt,
            window_end=end_dt,
        )

    # ── 2. Escalation rate ─────────────────────────────────────────────────

    async def escalation_rate(
        self,
        viewer_permissions: frozenset[str],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> EscalationRateReport:
        """Fraction of AI support sessions that escalated in the window."""
        _require(viewer_permissions, P.ANALYTICS_VIEW_ALL, P.ANALYTICS_VIEW_TEAM)
        start_dt, end_dt = _window(start, end)

        window_filter = and_(
            SupportSession.created_at >= start_dt,
            SupportSession.created_at <= end_dt,
        )

        total = (
            await self._db.execute(select(func.count(SupportSession.id)).where(window_filter))
        ).scalar_one()

        escalated = (
            await self._db.execute(
                select(func.count(SupportSession.id)).where(
                    and_(window_filter, SupportSession.status == _ESCALATED_STATUS)
                )
            )
        ).scalar_one()

        avg_conf = (
            await self._db.execute(
                select(func.avg(SupportSession.confidence_score)).where(
                    and_(window_filter, SupportSession.status == _ESCALATED_STATUS)
                )
            )
        ).scalar()

        return EscalationRateReport(
            total_sessions=int(total),
            escalated_sessions=int(escalated),
            escalation_rate=round(escalated / total, 4) if total else None,
            avg_confidence_at_escalation=float(avg_conf) if avg_conf else None,
            window_start=start_dt,
            window_end=end_dt,
        )

    # ── 3. KB article effectiveness ────────────────────────────────────────

    async def kb_effectiveness(
        self,
        viewer_permissions: frozenset[str],
    ) -> KBEffectivenessReport:
        """Published KB articles ranked by successful_resolution_count.

        Data gap: per-session citation-to-outcome linking not yet persisted.
        Uses the denormalised counter on KnowledgeArticle as proxy.
        """
        _require(viewer_permissions, P.ANALYTICS_VIEW_ALL, P.ANALYTICS_VIEW_TEAM)

        stmt = (
            select(KnowledgeArticle)
            .where(KnowledgeArticle.status == "published")
            .order_by(KnowledgeArticle.successful_resolution_count.desc())
        )
        articles = list((await self._db.execute(stmt)).scalars().all())

        rows = [
            KBArticleEffectivenessRow(
                article_id=str(a.id),
                title=a.title,
                category=a.category,
                successful_resolutions=a.successful_resolution_count or 0,
                quality_score=float(a.quality_score) if a.quality_score else None,
            )
            for a in articles
        ]

        zero_res = sum(1 for r in rows if r.successful_resolutions == 0)

        return KBEffectivenessReport(
            articles=rows,
            total_published=len(rows),
            articles_with_zero_resolutions=zero_res,
        )

    # ── 4. Agent / specialist workload ─────────────────────────────────────

    async def agent_workload(
        self,
        viewer_permissions: frozenset[str],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> WorkloadReport:
        """Ticket counts + agentic dispatch counts per agent in the window."""
        _require(
            viewer_permissions,
            P.ANALYTICS_VIEW_ALL,
            P.ANALYTICS_VIEW_TEAM,
            P.ANALYTICS_VIEW_AGENT_PERF,
        )
        start_dt, end_dt = _window(start, end)

        # Open tickets per assigned agent (no time filter — current snapshot)
        open_stmt = (
            select(Ticket.assigned_to, func.count(Ticket.id).label("cnt"))
            .where(
                and_(
                    Ticket.assigned_to.is_not(None),
                    Ticket.status.in_(["open", "in_progress", "pending"]),
                )
            )
            .group_by(Ticket.assigned_to)
        )
        open_rows = (await self._db.execute(open_stmt)).all()
        open_map: dict[str, int] = {str(r.assigned_to): int(r.cnt) for r in open_rows}

        # Resolved tickets in window per agent
        res_stmt = (
            select(Ticket.assigned_to, func.count(Ticket.id).label("cnt"))
            .where(
                and_(
                    Ticket.assigned_to.is_not(None),
                    Ticket.resolved_at >= start_dt,
                    Ticket.resolved_at <= end_dt,
                )
            )
            .group_by(Ticket.assigned_to)
        )
        res_rows = (await self._db.execute(res_stmt)).all()
        res_map: dict[str, int] = {str(r.assigned_to): int(r.cnt) for r in res_rows}

        # Agentic dispatches from agent_action_ledger in window
        disp_stmt = (
            select(AgentActionLedger.specialist_name, func.count(AgentActionLedger.id).label("cnt"))
            .where(
                and_(
                    AgentActionLedger.created_at >= start_dt,
                    AgentActionLedger.created_at <= end_dt,
                )
            )
            .group_by(AgentActionLedger.specialist_name)
        )
        disp_rows = (await self._db.execute(disp_stmt)).all()
        disp_map: dict[str, int] = {r.specialist_name: int(r.cnt) for r in disp_rows}

        # Merge by agent_id (UUID string)
        all_agent_ids = set(open_map) | set(res_map)

        # Fetch agent names
        import uuid as _uuid

        from app.models.auth import User

        agent_uuids = [_uuid.UUID(a) for a in all_agent_ids if a]
        name_map: dict[str, str] = {}
        if agent_uuids:
            user_rows = (
                (await self._db.execute(select(User).where(User.id.in_(agent_uuids))))
                .scalars()
                .all()
            )
            name_map = {str(u.id): u.full_name for u in user_rows}

        # Merge specialist dispatch counts by name → try matching to agent names
        # (specialist_name is a registry slug, not a user UUID; report both separately)
        agent_rows = [
            AgentWorkloadRow(
                agent_id=agent_id,
                agent_name=name_map.get(agent_id, agent_id),
                open_tickets=open_map.get(agent_id, 0),
                resolved_this_window=res_map.get(agent_id, 0),
                agentic_dispatches=0,  # dispatches are per-specialist-slug, not user id
            )
            for agent_id in sorted(all_agent_ids)
        ]

        # Append agentic dispatch rows (by specialist slug)
        for slug, cnt in sorted(disp_map.items()):
            # Check if slug matches an existing agent row by name — if not, add it
            matched = any(r.agent_name == slug for r in agent_rows)
            if not matched:
                agent_rows.append(
                    AgentWorkloadRow(
                        agent_id=slug,
                        agent_name=slug,
                        agentic_dispatches=cnt,
                    )
                )
            else:
                for r in agent_rows:
                    if r.agent_name == slug:
                        object.__setattr__(r, "agentic_dispatches", cnt)

        return WorkloadReport(agents=agent_rows, window_start=start_dt, window_end=end_dt)

    # ── 5. SLA compliance ──────────────────────────────────────────────────

    async def sla_compliance(
        self,
        viewer_permissions: frozenset[str],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> SLAComplianceReport:
        """SLA compliance rate for tickets created in the window."""
        _require(viewer_permissions, P.ANALYTICS_VIEW_ALL, P.ANALYTICS_VIEW_TEAM)
        start_dt, end_dt = _window(start, end)

        window_filter = and_(
            Ticket.created_at >= start_dt,
            Ticket.created_at <= end_dt,
        )
        now = datetime.now(UTC)

        total = (
            await self._db.execute(select(func.count(Ticket.id)).where(window_filter))
        ).scalar_one()

        breached = (
            await self._db.execute(
                select(func.count(Ticket.id)).where(
                    and_(
                        window_filter,
                        Ticket.sla_resolution_target.is_not(None),
                        Ticket.resolved_at.is_(None),
                        Ticket.sla_resolution_target < now,
                    )
                )
            )
        ).scalar_one()

        at_risk = (
            await self._db.execute(
                select(func.count(Ticket.id)).where(
                    and_(
                        window_filter,
                        Ticket.sla_resolution_target.is_not(None),
                        Ticket.resolved_at.is_(None),
                        Ticket.sla_resolution_target >= now,
                    )
                )
            )
        ).scalar_one()

        resolved_on_time = (
            await self._db.execute(
                select(func.count(Ticket.id)).where(
                    and_(
                        window_filter,
                        Ticket.resolved_at.is_not(None),
                        Ticket.sla_resolution_target.is_not(None),
                        Ticket.resolved_at <= Ticket.sla_resolution_target,
                    )
                )
            )
        ).scalar_one()

        within_sla = int(resolved_on_time)
        compliance_rate = round(within_sla / total, 4) if total else None

        return SLAComplianceReport(
            total_tickets=int(total),
            within_sla=within_sla,
            breached=int(breached),
            at_risk=int(at_risk),
            compliance_rate=compliance_rate,
            window_start=start_dt,
            window_end=end_dt,
        )

    # ── 6. Feedback sentiment ──────────────────────────────────────────────

    async def feedback_sentiment(
        self,
        viewer_permissions: frozenset[str],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> FeedbackSentimentReport:
        """Aggregated quality bucket distribution for the window."""
        _require(viewer_permissions, P.FEEDBACK_VIEW_ANALYTICS)
        start_dt, end_dt = _window(start, end)

        window_filter = and_(
            ConversationFeedback.submitted_at >= start_dt,
            ConversationFeedback.submitted_at <= end_dt,
        )

        bucket_stmt = (
            select(
                ConversationFeedback.quality_bucket,
                func.count(ConversationFeedback.id).label("cnt"),
            )
            .where(window_filter)
            .group_by(ConversationFeedback.quality_bucket)
        )
        bucket_rows = (await self._db.execute(bucket_stmt)).all()
        bucket_map: dict[str, int] = {
            str(r.quality_bucket): int(r.cnt) for r in bucket_rows if r.quality_bucket
        }

        avg_rating_val = (
            await self._db.execute(
                select(func.avg(ConversationFeedback.rating)).where(window_filter)
            )
        ).scalar()

        total = sum(bucket_map.values())
        positive = bucket_map.get("positive", 0)

        return FeedbackSentimentReport(
            total_responses=total,
            positive=positive,
            neutral=bucket_map.get("neutral", 0),
            negative=bucket_map.get("negative", 0),
            avg_rating=round(float(avg_rating_val), 2) if avg_rating_val else None,
            positive_rate=round(positive / total, 4) if total else None,
            window_start=start_dt,
            window_end=end_dt,
        )


__all__ = ["PermissionDenied", "ScopedReportService"]
