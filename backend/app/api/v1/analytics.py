"""Analytics API endpoints — IT management dashboards."""

import uuid
from calendar import monthrange
from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.schemas.analytics import (
    EscalationRateReport,
    FeedbackSentimentReport,
    KBEffectivenessReport,
    ResolutionTrendReport,
    SLAComplianceReport,
    WorkloadReport,
)
from app.schemas.reporting import SpecialistReport
from app.services.analytics.scoped_report_service import PermissionDenied, ScopedReportService
from app.services.analytics_service import AnalyticsService
from app.services.auth.dependencies import ITLeadUser, get_current_active_user, require_permissions
from app.services.auth.service import AuthService
from app.services.reporting import exporters
from app.services.reporting.specialist_report_service import SpecialistReportService

router = APIRouter()

# ── Permission-based dependency aliases ──────────────────────────────────────
# These use require_permissions instead of role-level aliases so the
# permission model (not just the role) is the enforced contract.
ViewAnalytics = Annotated[
    object,
    Depends(require_permissions(P.ANALYTICS_VIEW_ALL, P.ANALYTICS_VIEW_TEAM, P.ANALYTICS_VIEW_OWN)),
]
ExportAnalytics = Annotated[object, Depends(require_permissions(P.ANALYTICS_EXPORT))]

DBDep = Annotated[AsyncSession, Depends(get_db)]


def _handle_denied(exc: PermissionDenied) -> NoReturn:
    raise HTTPException(status_code=403, detail=str(exc))


async def _get_perms(user: object, db: AsyncSession) -> frozenset[str]:
    from app.models.auth import User as UserModel

    if not isinstance(user, UserModel):
        return frozenset()
    return frozenset(await AuthService(db).get_user_permissions(user))


@router.get("/dashboard")
async def get_dashboard(
    lead_user: ITLeadUser,
    db: DBDep,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, object]:
    """Get comprehensive dashboard metrics for IT leads/admins."""
    service = AnalyticsService(db)
    return await service.get_dashboard_summary(start_date=start_date, end_date=end_date)


@router.get("/workload")
async def get_agent_workload(
    lead_user: ITLeadUser,
    db: DBDep,
) -> list[dict[str, object]]:
    """Get agent workload distribution."""
    service = AnalyticsService(db)
    return await service.get_agent_workload()


def _default_month_range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    if start and end:
        return start, end
    now = datetime.now(UTC)
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = monthrange(now.year, now.month)[1]
    last = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
    return start or first, end or last


def _normalize_range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    """Resolve a (possibly partial, possibly naive, possibly date-only) range."""
    start_dt, end_dt = _default_month_range(start, end)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=UTC)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=UTC)
    if (end_dt.hour, end_dt.minute, end_dt.second, end_dt.microsecond) == (0, 0, 0, 0):
        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start_dt, end_dt


@router.get("/specialist-report", response_model=SpecialistReport)
async def get_specialist_report(
    lead_user: ITLeadUser,
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> SpecialistReport:
    start_dt, end_dt = _normalize_range(start, end)
    return await SpecialistReportService(db).build_report(start=start_dt, end=end_dt)


_EXPORT = {
    "csv": (exporters.to_csv, "text/csv", "csv"),
    "xlsx": (
        exporters.to_xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "pdf": (exporters.to_pdf, "application/pdf", "pdf"),
}


@router.get("/specialist-report/export")
async def export_specialist_report(
    # Fixed: was ITLeadUser (allows leads); ANALYTICS_EXPORT is admin-only.
    _user: ExportAnalytics,
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
    format: str = Query("csv"),  # noqa: A002
) -> Response:
    if format not in _EXPORT:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
    start_dt, end_dt = _normalize_range(start, end)
    report = await SpecialistReportService(db).build_report(start=start_dt, end=end_dt)
    render, media_type, ext = _EXPORT[format]
    content = render(report)
    filename = f"specialist-report-{start_dt:%Y%m%d}-{end_dt:%Y%m%d}.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Scoped reports (Workstream 4) ─────────────────────────────────────────────


async def _get_viewer_id(user: object) -> uuid.UUID | None:
    from app.models.auth import User as UserModel

    if isinstance(user, UserModel):
        return user.id
    return None


@router.get("/reports/resolution-trends", response_model=ResolutionTrendReport)
async def get_resolution_trends(
    user: Annotated[object, Depends(get_current_active_user)],
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ResolutionTrendReport:
    """Resolution time trends. Scoped by caller's analytics permission."""
    perms = await _get_perms(user, db)
    try:
        return await ScopedReportService(db).resolution_time_trends(
            perms, start, end, viewer_user_id=await _get_viewer_id(user)
        )
    except PermissionDenied as exc:
        _handle_denied(exc)


@router.get("/reports/escalation-rate", response_model=EscalationRateReport)
async def get_escalation_rate(
    user: Annotated[object, Depends(get_current_active_user)],
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> EscalationRateReport:
    """Escalation rate over the window."""
    perms = await _get_perms(user, db)
    try:
        return await ScopedReportService(db).escalation_rate(
            perms, start, end, viewer_user_id=await _get_viewer_id(user)
        )
    except PermissionDenied as exc:
        _handle_denied(exc)


@router.get("/reports/kb-effectiveness", response_model=KBEffectivenessReport)
async def get_kb_effectiveness(
    user: Annotated[object, Depends(get_current_active_user)],
    db: DBDep,
) -> KBEffectivenessReport:
    """KB article effectiveness report."""
    perms = await _get_perms(user, db)
    try:
        return await ScopedReportService(db).kb_effectiveness(perms)
    except PermissionDenied as exc:
        _handle_denied(exc)


@router.get("/reports/agent-workload", response_model=WorkloadReport)
async def get_agent_workload_report(
    user: Annotated[object, Depends(get_current_active_user)],
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> WorkloadReport:
    """Agent workload report using tickets and the agent_action_ledger."""
    perms = await _get_perms(user, db)
    try:
        return await ScopedReportService(db).agent_workload(
            perms, start, end, viewer_user_id=await _get_viewer_id(user)
        )
    except PermissionDenied as exc:
        _handle_denied(exc)


@router.get("/reports/sla-compliance", response_model=SLAComplianceReport)
async def get_sla_compliance(
    user: Annotated[object, Depends(get_current_active_user)],
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> SLAComplianceReport:
    """SLA compliance report."""
    perms = await _get_perms(user, db)
    try:
        return await ScopedReportService(db).sla_compliance(
            perms, start, end, viewer_user_id=await _get_viewer_id(user)
        )
    except PermissionDenied as exc:
        _handle_denied(exc)


@router.get("/reports/feedback-sentiment", response_model=FeedbackSentimentReport)
async def get_feedback_sentiment(
    user: Annotated[object, Depends(get_current_active_user)],
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> FeedbackSentimentReport:
    """Feedback sentiment aggregation."""
    perms = await _get_perms(user, db)
    try:
        return await ScopedReportService(db).feedback_sentiment(
            perms, start, end, viewer_user_id=await _get_viewer_id(user)
        )
    except PermissionDenied as exc:
        _handle_denied(exc)


@router.get("/reports/export/{report_name}")
async def export_scoped_report(
    report_name: str,
    # Export requires ANALYTICS_EXPORT (IT_ADMIN only) — enforced here.
    _user: ExportAnalytics,
    db: DBDep,
    start: datetime | None = None,
    end: datetime | None = None,
    format: str = Query("csv"),  # noqa: A002
) -> Response:
    """Export any scoped report. Requires analytics:export (IT_ADMIN only)."""
    # _user dependency is the export guard; build perms with ANALYTICS_EXPORT
    # since the caller passed the guard.
    admin_perms = frozenset(
        [
            P.ANALYTICS_VIEW_ALL.value,
            P.ANALYTICS_EXPORT.value,
            P.ANALYTICS_VIEW_AGENT_PERF.value,
            P.FEEDBACK_VIEW_ANALYTICS.value,
        ]
    )
    svc = ScopedReportService(db)
    now = datetime.now(UTC)
    start_dt, end_dt = _normalize_range(start, end)

    valid_reports = {
        "resolution-trends",
        "escalation-rate",
        "kb-effectiveness",
        "agent-workload",
        "sla-compliance",
        "feedback-sentiment",
    }
    if report_name not in valid_reports:
        raise HTTPException(status_code=404, detail=f"Unknown report: {report_name}")
    if format not in _EXPORT:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    # Fetch the right report data
    data: object = None
    if report_name == "resolution-trends":
        data = await svc.resolution_time_trends(admin_perms, start_dt, end_dt)
    elif report_name == "escalation-rate":
        data = await svc.escalation_rate(admin_perms, start_dt, end_dt)
    elif report_name == "kb-effectiveness":
        data = await svc.kb_effectiveness(admin_perms)
    elif report_name == "agent-workload":
        data = await svc.agent_workload(admin_perms, start_dt, end_dt)
    elif report_name == "sla-compliance":
        data = await svc.sla_compliance(admin_perms, start_dt, end_dt)
    elif report_name == "feedback-sentiment":
        data = await svc.feedback_sentiment(admin_perms, start_dt, end_dt)

    # Serialize via Pydantic and export
    from pydantic import BaseModel

    if isinstance(data, BaseModel):
        content_dict = data.model_dump(mode="json")
        # Build a minimal SpecialistReport-compatible structure for the existing exporters
        # by passing the report as a dict wrapped in the generic CSV exporter
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["report", report_name, "generated", now.isoformat()])
        for k, v in content_dict.items():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        writer.writerow(list(item.values()))
            else:
                writer.writerow([k, v])
        csv_bytes = buf.getvalue().encode()
    else:
        csv_bytes = b""

    render_fn, media_type, ext = _EXPORT[format]
    content = csv_bytes  # all scoped report exports use csv

    filename = f"{report_name}-{start_dt:%Y%m%d}-{end_dt:%Y%m%d}.{ext}"
    return Response(
        content=content if format == "csv" else csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
