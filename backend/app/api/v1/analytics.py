"""Analytics API endpoints — IT management dashboards."""

from calendar import monthrange
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.reporting import SpecialistReport
from app.services.analytics_service import AnalyticsService
from app.services.auth.dependencies import ITLeadUser
from app.services.reporting import exporters
from app.services.reporting.specialist_report_service import SpecialistReportService

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    lead_user: ITLeadUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """Get comprehensive dashboard metrics for IT leads/admins."""
    service = AnalyticsService(db)
    return await service.get_dashboard_summary(start_date=start_date, end_date=end_date)


@router.get("/workload")
async def get_agent_workload(
    lead_user: ITLeadUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
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
    """Resolve a (possibly partial, possibly naive, possibly date-only) range.

    The frontend sends bare `YYYY-MM-DD` query params for both `start` and
    `end` (see SpecialistReportPage) — FastAPI parses those as naive midnight
    datetimes. `_default_month_range` only fills in end-of-day when BOTH
    bounds are None, so an explicit bare-date `end` was left at naive
    midnight, excluding the entire last day (`<= end` boundary) and risking
    naive-vs-tz-aware comparisons against tz-aware DB columns. This
    normalizes both endpoints after the defaulting step: attaches UTC to any
    naive datetime, and — since a date-only value always parses to exact
    midnight — treats a midnight `end` as "through the end of that day".
    """
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
    db: Annotated[AsyncSession, Depends(get_db)],
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
    lead_user: ITLeadUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: datetime | None = None,
    end: datetime | None = None,
    format: str = Query("csv"),  # noqa: A002 - matches the public query param name
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
