"""Analytics snapshot model for dashboard metrics."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AnalyticsSnapshot(UUIDPrimaryKeyMixin, Base):
    """Periodic analytics snapshot for dashboard performance."""

    __tablename__ = "analytics_snapshots"

    # Period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_type: Mapped[str] = mapped_column(String(20), index=True)  # hourly, daily, weekly

    # Ticket metrics
    tickets_created: Mapped[int] = mapped_column(Integer, default=0)
    tickets_resolved: Mapped[int] = mapped_column(Integer, default=0)
    tickets_escalated: Mapped[int] = mapped_column(Integer, default=0)
    tickets_breached_sla: Mapped[int] = mapped_column(Integer, default=0)

    # AI metrics
    ai_resolutions: Mapped[int] = mapped_column(Integer, default=0)
    ai_avg_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    live_handoffs: Mapped[int] = mapped_column(Integer, default=0)

    # Performance
    avg_response_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_resolution_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Remote support
    remote_sessions_initiated: Mapped[int] = mapped_column(Integer, default=0)
    remote_sessions_completed: Mapped[int] = mapped_column(Integer, default=0)

    # Breakdown data
    category_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    priority_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agent_workload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
