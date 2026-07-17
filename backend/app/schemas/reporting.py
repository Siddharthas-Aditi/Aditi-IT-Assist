"""Schemas for the per-specialist performance report (C1).

The report aggregates ticket-lifecycle and feedback signals per assigned
agent for a given time window. Values that cannot be computed (e.g. no
resolved tickets, no feedback submitted) are ``None`` rather than a
fabricated number — the frontend renders that as "No data".
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - pydantic evaluates annotations at runtime

from pydantic import BaseModel


class SpecialistReportRow(BaseModel):
    """One row of the per-specialist report: a single agent or the team totals."""

    agent_id: str | None  # None for the team-totals row
    agent_name: str
    agent_email: str | None = None
    total_tickets: int = 0
    reopened: int = 0
    avg_resolution_hours: float | None = None  # None => "No data"
    sla_violations: int = 0
    csat_avg: float | None = None  # None => "No data"
    dsat: int = 0
    feedback_responses: int = 0


class SpecialistReport(BaseModel):
    """Per-specialist performance report for a time window."""

    period_start: datetime
    period_end: datetime
    rows: list[SpecialistReportRow]
    totals: SpecialistReportRow
