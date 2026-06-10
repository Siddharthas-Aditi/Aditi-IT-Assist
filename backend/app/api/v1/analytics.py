"""Analytics API endpoints — IT management dashboards."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.analytics_service import AnalyticsService
from app.services.auth.dependencies import ITLeadUser

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
