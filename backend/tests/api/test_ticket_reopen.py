"""API tests for the ticket reopen action (POST /tickets/{id}/reopen).

Like `test_specialist_report_api.py`, this runs against the real test
Postgres — no DB mocking. A ticket is seeded via `TicketService.create_ticket`
directly against a real session, then reopened through the real endpoint (or
the service directly for the event-logging assertion). This exercises the
actual `reopen_ticket` SQL + event-logging, not a mock.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.main import app
from app.models.auth import Role, User, UserRoleAssignment
from app.models.ticket import TicketEvent
from app.services.auth.dependencies import get_current_active_user
from app.services.ticket_service import TicketService

BASE = "/api/v1/tickets"


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    """Avoid cross-event-loop asyncpg errors (see test_specialist_report_api.py)."""
    yield
    await engine.dispose()


async def _real_user(role_name: str) -> User:
    """Fetch a real, DB-persisted seeded user with the given role.

    Unlike `agent_client` (a `MagicMock` with a random `id`), this user
    actually exists in `users`, so it can be the `actor_id` on a written
    `TicketEvent` without tripping the FK constraint.
    """
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
        # Force role_assignments/role to materialize before the session closes.
        _ = user.primary_role
        return user


@pytest.fixture
async def real_agent_client():
    """A client authenticated as a real (DB-persisted) it_agent user.

    Needed for reopen tests that actually write a `TicketEvent` — the shared
    `agent_client` fixture's mock user has no row in `users`, which is fine
    for read-only/gating assertions but violates the `actor_id` FK once the
    endpoint under test performs a write.
    """
    user = await _real_user("it_agent")
    app.dependency_overrides[get_current_active_user] = lambda: user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_active_user, None)


async def _seed_ticket(status: str = "resolved") -> uuid.UUID:
    """Create a real ticket row (with a creation event) against the test DB."""
    async with async_session_factory() as session:
        requester = (await session.execute(select(User).limit(1))).scalars().first()
        assert requester is not None, "expected at least one seeded user in the test DB"
        service = TicketService(session)
        ticket = await service.create_ticket(
            requester=requester,
            title="Reopen test ticket",
            description="Seeded for reopen API test",
            priority="medium",
        )
        await session.flush()
        if status != "new":
            await service.update_status(ticket.id, status, requester)
        await session.commit()
        return ticket.id


class TestReopenGating:
    async def test_requires_auth(self, client: AsyncClient):
        ticket_id = await _seed_ticket("resolved")
        resp = await client.post(f"{BASE}/{ticket_id}/reopen")
        assert resp.status_code == 401

    async def test_auditor_forbidden_no_reopen_permission(self, auditor_client: AsyncClient):
        # security_auditor is not an IT-staff role (it_agent/it_lead/it_admin).
        ticket_id = await _seed_ticket("resolved")
        resp = await auditor_client.post(f"{BASE}/{ticket_id}/reopen")
        assert resp.status_code == 403

    async def test_employee_forbidden_idor_regression(self, employee_client: AsyncClient):
        # IDOR regression guard: an employee (even a non-owner) must never be
        # able to reopen a ticket via role-gated ticket:reopen scope-bypass.
        # Reopen is IT-staff-only; employees get a categorical 403.
        ticket_id = await _seed_ticket("resolved")
        resp = await employee_client.post(f"{BASE}/{ticket_id}/reopen")
        assert resp.status_code == 403

    async def test_reopen_nonexistent_ticket_returns_404(self, agent_client: AsyncClient):
        missing_id = uuid.uuid4()
        resp = await agent_client.post(f"{BASE}/{missing_id}/reopen")
        assert resp.status_code == 404


class TestReopenAction:
    async def test_reopen_resolved_ticket_returns_200_and_active_status(
        self, real_agent_client: AsyncClient
    ):
        ticket_id = await _seed_ticket("resolved")
        resp = await real_agent_client.post(f"{BASE}/{ticket_id}/reopen")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "in_progress"

    async def test_reopen_closed_ticket_returns_200(self, real_agent_client: AsyncClient):
        ticket_id = await _seed_ticket("closed")
        resp = await real_agent_client.post(f"{BASE}/{ticket_id}/reopen")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    async def test_reopen_non_terminal_ticket_conflicts(self, agent_client: AsyncClient):
        # No event is written on the reject path, so the mock (non-persisted)
        # agent user's id never reaches the `actor_id` FK.
        ticket_id = await _seed_ticket("in_progress")
        resp = await agent_client.post(f"{BASE}/{ticket_id}/reopen")
        assert resp.status_code == 409

    async def test_reopen_with_comment_adds_comment_event(self, real_agent_client: AsyncClient):
        ticket_id = await _seed_ticket("resolved")
        resp = await real_agent_client.post(
            f"{BASE}/{ticket_id}/reopen", json={"comment": "Back again"}
        )
        assert resp.status_code == 200

        async with async_session_factory() as session:
            stmt = select(TicketEvent).where(TicketEvent.ticket_id == ticket_id)
            events = (await session.execute(stmt)).scalars().all()
        # reopen_ticket adds the comment as an internal note.
        assert any(e.event_type == "internal_note_added" for e in events)


class TestReopenServiceDirect:
    """Direct service-level assertions on event logging + timestamp clearing."""

    async def test_reopen_writes_status_changed_event_with_old_value_resolved(self):
        ticket_id = await _seed_ticket("resolved")

        async with async_session_factory() as session:
            requester = (await session.execute(select(User).limit(1))).scalars().first()
            service = TicketService(session)
            ticket = await service.reopen_ticket(ticket_id, requester)
            assert ticket.status == "in_progress"
            assert ticket.resolved_at is None
            await session.commit()

        async with async_session_factory() as session:
            stmt = select(TicketEvent).where(TicketEvent.ticket_id == ticket_id)
            events = (await session.execute(stmt)).scalars().all()
        reopen_events = [
            e for e in events if e.event_type == "status_changed" and e.old_value == "resolved"
        ]
        assert len(reopen_events) == 1
        assert reopen_events[0].new_value == "in_progress"

    async def test_reopen_clears_resolved_at_and_closed_at(self):
        ticket_id = await _seed_ticket("closed")

        async with async_session_factory() as session:
            requester = (await session.execute(select(User).limit(1))).scalars().first()
            service = TicketService(session)
            ticket = await service.reopen_ticket(ticket_id, requester)
            assert ticket.closed_at is None
            assert ticket.resolved_at is None
            await session.commit()

    async def test_reopen_rejects_non_terminal_status(self):
        ticket_id = await _seed_ticket("triaged")

        async with async_session_factory() as session:
            requester = (await session.execute(select(User).limit(1))).scalars().first()
            service = TicketService(session)
            with pytest.raises(ValueError):
                await service.reopen_ticket(ticket_id, requester)
