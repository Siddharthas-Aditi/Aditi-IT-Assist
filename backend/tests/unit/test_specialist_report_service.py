"""Unit tests for SpecialistReportService (per-specialist performance report, C1).

Exercises the report aggregation logic with a lightweight fake async session
(no Postgres required) — mirrors the FakeSession pattern used by
tests/unit/test_escalation_artifacts.py. Ticket/TicketEvent/User rows are
constructed directly (unpersisted ORM instances) and handed back by the fake
session based on which entity the query selects. FeedbackAnalyticsService is
patched at the seam (its own correctness is covered by
tests/unit/test_feedback_analytics.py) so this test focuses on: ticket
grouping by assignee, SLA-violation detection, reopen counting, average
resolution time, and wiring feedback numbers into the report rows/totals.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.auth import User
from app.models.ticket import Ticket, TicketEvent
from app.schemas.feedback import AgentFeedbackSummary
from app.services.reporting.specialist_report_service import SpecialistReportService

# ── Fake async session ──────────────────────────────────────────────────────


class _ScalarResult:
    """Mimics the `.scalars().all()` chain for a select(SomeModel) query."""

    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> list:
        return self._rows


class FakeSession:
    """Routes execute() to canned rows based on the query's primary entity.

    Only the entities this service actually queries are supported: Ticket,
    the TicketEvent/Ticket join, and User. Anything else is a test bug.
    """

    def __init__(
        self,
        tickets: list[Ticket],
        events_with_assignee: list[tuple[TicketEvent, uuid.UUID]],
        users: list[User],
    ) -> None:
        self.tickets = tickets
        self.events_with_assignee = events_with_assignee
        self.users = users

    async def execute(self, stmt):
        entity_names = [d["name"] for d in stmt.column_descriptions]
        if entity_names == ["Ticket"]:
            return _ScalarResult(self.tickets)
        if entity_names == ["TicketEvent", "assigned_to"]:
            return _ScalarResult(self.events_with_assignee)
        if entity_names == ["User"]:
            return _ScalarResult(self.users)
        raise AssertionError(f"FakeSession: unexpected query shape {entity_names}")


# ── Seed fixture ─────────────────────────────────────────────────────────────


def _user(full_name: str, email: str) -> User:
    u = User(email=email, full_name=full_name)
    u.id = uuid.uuid4()
    return u


def _ticket(
    *,
    assigned_to: uuid.UUID,
    created_at: datetime,
    resolved_at: datetime,
    sla_resolution_target: datetime,
    status: str = "resolved",
) -> Ticket:
    t = Ticket(
        ticket_number=f"ITA-{uuid.uuid4().hex[:6]}",
        title="t",
        description="d",
        requester_id=uuid.uuid4(),
    )
    t.id = uuid.uuid4()
    t.assigned_to = assigned_to
    t.created_at = created_at
    t.resolved_at = resolved_at
    t.sla_resolution_target = sla_resolution_target
    t.status = status
    return t


def _reopen_event(ticket_id: uuid.UUID, created_at: datetime) -> TicketEvent:
    ev = TicketEvent(
        ticket_id=ticket_id,
        event_type="status_changed",
        description="reopened",
        old_value="resolved",
        new_value="in_progress",
    )
    ev.created_at = created_at
    return ev


@dataclass
class _Seed:
    agent_a: User
    agent_b: User
    month_start: datetime
    month_end: datetime
    expected_avg_hours_a: float
    tickets: list[Ticket] = field(default_factory=list)
    events_with_assignee: list[tuple[TicketEvent, uuid.UUID]] = field(default_factory=list)


@pytest.fixture
def seed() -> _Seed:
    month_start = datetime(2026, 7, 1, tzinfo=UTC)
    month_end = datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC)

    agent_a = _user("Agent A", "agent-a@aditi.com")
    agent_b = _user("Agent B", "agent-b@aditi.com")

    # Agent A: 2 resolved tickets — one within SLA, one violating it.
    a1_created = datetime(2026, 7, 2, 9, 0, tzinfo=UTC)
    a1 = _ticket(
        assigned_to=agent_a.id,
        created_at=a1_created,
        resolved_at=a1_created + timedelta(hours=5),
        sla_resolution_target=a1_created + timedelta(hours=24),
    )
    a2_created = datetime(2026, 7, 5, 9, 0, tzinfo=UTC)
    a2 = _ticket(
        assigned_to=agent_a.id,
        created_at=a2_created,
        resolved_at=a2_created + timedelta(hours=50),
        sla_resolution_target=a2_created + timedelta(hours=24),
    )
    expected_avg_hours_a = (5 + 50) / 2

    # Agent B: 1 resolved ticket, within SLA, never reopened.
    b1_created = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)
    b1 = _ticket(
        assigned_to=agent_b.id,
        created_at=b1_created,
        resolved_at=b1_created + timedelta(hours=3),
        sla_resolution_target=b1_created + timedelta(hours=24),
    )

    # A reopen event for one of agent A's tickets (resolved -> in_progress).
    reopen = _reopen_event(a1.id, a1.resolved_at + timedelta(hours=1))

    seed = _Seed(
        agent_a=agent_a,
        agent_b=agent_b,
        month_start=month_start,
        month_end=month_end,
        expected_avg_hours_a=expected_avg_hours_a,
    )
    seed.tickets = [a1, a2, b1]
    seed.events_with_assignee = [(reopen, agent_a.id)]
    return seed


def _fake_feedback_summary(agent_id: uuid.UUID, *, from_dt, to_dt, seed: _Seed):
    if agent_id == seed.agent_a.id:
        return AgentFeedbackSummary(
            agent_user_id=agent_id,
            total_sessions=2,
            sessions_with_feedback=2,
            helpful_rate=1.0,
            resolved_rate=0.5,
            csat_avg=4.5,
            positive_count=1,
            negative_count=1,
            period_start=from_dt,
            period_end=to_dt,
        )
    return AgentFeedbackSummary(
        agent_user_id=agent_id,
        total_sessions=0,
        sessions_with_feedback=0,
        helpful_rate=None,
        resolved_rate=None,
        csat_avg=None,
        positive_count=0,
        negative_count=0,
        period_start=from_dt,
        period_end=to_dt,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestBuildReport:
    async def test_build_report_aggregates_per_agent(self, seed: _Seed) -> None:
        session = FakeSession(
            tickets=seed.tickets,
            events_with_assignee=seed.events_with_assignee,
            users=[seed.agent_a, seed.agent_b],
        )
        svc = SpecialistReportService(session)
        svc.feedback.get_agent_summary = AsyncMock(
            side_effect=lambda agent_id, **kw: _fake_feedback_summary(agent_id, seed=seed, **kw)
        )

        report = await svc.build_report(start=seed.month_start, end=seed.month_end)
        rows = {r.agent_id: r for r in report.rows}

        a = rows[str(seed.agent_a.id)]
        assert a.total_tickets == 2
        assert a.sla_violations == 1
        assert a.reopened == 1
        assert a.avg_resolution_hours == pytest.approx(seed.expected_avg_hours_a, rel=0.01)
        assert a.csat_avg == pytest.approx(4.5, rel=0.01)
        assert a.dsat == 1

        b = rows[str(seed.agent_b.id)]
        assert b.total_tickets == 1
        assert b.sla_violations == 0
        assert b.reopened == 0
        # Agent with no feedback -> csat_avg None ("No data").
        assert b.csat_avg is None

        assert report.totals.total_tickets == a.total_tickets + b.total_tickets
        assert report.totals.sla_violations == a.sla_violations + b.sla_violations
        assert report.totals.reopened == a.reopened + b.reopened
        assert report.totals.agent_id is None

    async def test_empty_window_returns_no_rows_and_no_data_totals(self) -> None:
        session = FakeSession(tickets=[], events_with_assignee=[], users=[])
        svc = SpecialistReportService(session)
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 31, tzinfo=UTC)

        report = await svc.build_report(start=start, end=end)

        assert report.rows == []
        assert report.totals.total_tickets == 0
        assert report.totals.avg_resolution_hours is None
        assert report.totals.csat_avg is None

    async def test_agent_name_falls_back_to_email_when_no_full_name(self) -> None:
        agent = User(email="noname@aditi.com", full_name="")
        agent.id = uuid.uuid4()
        created = datetime(2026, 7, 1, tzinfo=UTC)
        ticket = _ticket(
            assigned_to=agent.id,
            created_at=created,
            resolved_at=created + timedelta(hours=2),
            sla_resolution_target=created + timedelta(hours=24),
        )
        session = FakeSession(tickets=[ticket], events_with_assignee=[], users=[agent])
        svc = SpecialistReportService(session)
        svc.feedback.get_agent_summary = AsyncMock(
            return_value=AgentFeedbackSummary(
                agent_user_id=agent.id,
                total_sessions=0,
                sessions_with_feedback=0,
                helpful_rate=None,
                resolved_rate=None,
                csat_avg=None,
                positive_count=0,
                negative_count=0,
                period_start=created,
                period_end=created,
            )
        )

        report = await svc.build_report(
            start=datetime(2026, 7, 1, tzinfo=UTC), end=datetime(2026, 7, 31, tzinfo=UTC)
        )

        assert report.rows[0].agent_name == "noname@aditi.com"
