"""Scheduled-report bookkeeping (C2) — replica-safe once-per-month claim.

``ScheduledReportRun`` is the idempotency record a background job writes
before it starts sending the monthly IT-leadership report. The ``period``
column is unique so that, even with multiple app replicas racing the same
scheduled tick, only one process can successfully claim a given month
(``INSERT`` fails with a unique-violation for every loser).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScheduledReportRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per attempted monthly scheduled-report send.

    ``period`` is the ``"YYYY-MM"`` string identifying the report month and
    is unique — the replica-safe once-per-month claim. ``status`` tracks the
    send lifecycle (``sending`` -> ``sent`` | ``failed``).
    """

    __tablename__ = "scheduled_report_runs"

    period: Mapped[str] = mapped_column(String(7), unique=True, index=True)  # "YYYY-MM"
    status: Mapped[str] = mapped_column(String(20), default="sending")  # sending|sent|failed
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["ScheduledReportRun"]
