"""Integration test: a reopened ticket increments the C1 specialist report.

Like `test_ticket_reopen.py` and `test_specialist_report_api.py`, this runs
against the real test Postgres (no DB mocking) — a ticket is created,
assigned, resolved, and reopened via the real `TicketService`, then
`SpecialistReportService.build_report` is run over a window covering the
reopen event to prove the `reopened` count on the assigned agent's row
actually reflects the write, end to end (not just the FakeSession-derivation
unit tests in `test_specialist_report_service.py`).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.models.auth import Role, User, UserRoleAssignment
from app.services.reporting.specialist_report_service import SpecialistReportService
from app.services.ticket_service import TicketService


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    """Avoid cross-event-loop asyncpg errors (see test_specialist_report_api.py)."""
    yield
    await engine.dispose()


async def _real_user(role_name: str) -> User:
    """Fetch a real, DB-persisted seeded user with the given role."""
    async with async_session_factory() as session:
        stmt = (
            select(User)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(Role.name == role_name)
            .limit(1)
        )
        user = (await session.execute(stmt)).scalars().first()
        assert user is not None, f"expected a seeded {role_name} user in the test DB"
        _ = user.primary_role
        return user


@pytest.mark.asyncio
async def test_reopen_increments_specialist_report_reopened_count():
    requester = await _real_user("employee")
    try:
        agent = await _real_user("it_agent")
    except AssertionError:
        agent = await _real_user("it_lead")

    async with async_session_factory() as session:
        service = TicketService(session)
        ticket = await service.create_ticket(
            requester=requester,
            title="Reopen -> report integration test ticket",
            description="Seeded to prove reopen increments the C1 report",
            priority="medium",
        )
        await session.flush()
        await service.assign_ticket(ticket.id, agent.id, agent)
        await service.update_status(ticket.id, "resolved", agent)
        await session.commit()
        ticket_id = ticket.id

    async with async_session_factory() as session:
        service = TicketService(session)
        await service.reopen_ticket(ticket_id, agent)
        await session.commit()

    start = datetime.now(UTC) - timedelta(minutes=5)
    end = datetime.now(UTC) + timedelta(minutes=5)
    async with async_session_factory() as session:
        report = await SpecialistReportService(session).build_report(start=start, end=end)

    agent_row = next((r for r in report.rows if r.agent_id == str(agent.id)), None)
    assert agent_row is not None, "expected the assigned agent's row in the report"
    assert agent_row.reopened >= 1
