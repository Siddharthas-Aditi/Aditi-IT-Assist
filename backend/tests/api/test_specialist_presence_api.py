"""API tests for specialist presence + offer endpoints.

RBAC: specialist_queue:view (presence + offers list) / :claim (accept-offer)
are it_agent and above; a plain employee gets a categorical 403.

Presence writes an FK-backed row keyed on ``users.id``. The shared
``lead_client``/``agent_client`` fixtures authenticate as a ``MagicMock``
user with a random id that has no row in ``users`` — fine for the 403 gate
(rejected before any DB write) but not for a real write. So the success
paths build a real, DB-persisted specialist user (mirroring
``test_ticket_reopen.py``'s ``_real_user`` helper) and override auth to it
directly on the unauthenticated ``client`` fixture.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import async_session_factory, engine
from app.main import app
from app.models.auth import Role, User, UserRoleAssignment
from app.models.live_handoff import SpecialistAvailability
from app.models.support import SupportSession
from app.models.ticket import Ticket
from app.services.auth.dependencies import get_current_active_user
from app.services.specialist_handoff_service import HandoffService
from app.services.specialist_presence_service import PresenceService

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    # Avoid cross-event-loop asyncpg errors (see test_specialist_report_api.py /
    # test_ticket_reopen.py — each test gets its own event loop under
    # pytest-asyncio's function-scoped loop).
    yield
    await engine.dispose()


async def _real_specialist() -> User:
    """Fetch a real, DB-persisted seeded specialist (it_agent, else it_lead)."""
    async with async_session_factory() as session:
        for role_name in ("it_agent", "it_lead"):
            stmt = (
                select(User)
                .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
                .join(Role, Role.id == UserRoleAssignment.role_id)
                .where(Role.name == role_name)
                .limit(1)
            )
            user = (await session.execute(stmt)).scalars().first()
            if user is not None:
                _ = user.primary_role  # materialize before session closes
                return user
        raise AssertionError("expected a seeded it_agent or it_lead user in the test DB")


async def _real_employee() -> User:
    """Fetch a real, DB-persisted seeded employee to act as ticket requester."""
    async with async_session_factory() as session:
        stmt = (
            select(User)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(Role.name == "employee")
            .limit(1)
        )
        user = (await session.execute(stmt)).scalars().first()
        assert user is not None, "expected a seeded employee user in the test DB"
        _ = user.primary_role
        return user


@pytest.fixture
async def real_specialist_client():
    """Unauthenticated ``client``-style fixture, overridden to a real user.

    Cleans up the auth override AND any ``specialist_availability`` row this
    test created, so presence state doesn't leak across tests.
    """
    user = await _real_specialist()
    app.dependency_overrides[get_current_active_user] = lambda: user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, user
    app.dependency_overrides.pop(get_current_active_user, None)
    async with async_session_factory() as session:
        await session.execute(
            delete(SpecialistAvailability).where(SpecialistAvailability.user_id == user.id)
        )
        await session.commit()


class TestAvailabilityGating:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.put(
            "/api/v1/specialist-queue/availability", json={"status": "available"}
        )
        assert resp.status_code == 401

    async def test_availability_requires_specialist(self, employee_client: AsyncClient):
        # Rejected by RBAC before any DB write — safe with the mock (non-persisted) user.
        resp = await employee_client.put(
            "/api/v1/specialist-queue/availability", json={"status": "available"}
        )
        assert resp.status_code == 403

    async def test_heartbeat_requires_specialist(self, employee_client: AsyncClient):
        resp = await employee_client.post("/api/v1/specialist-queue/availability/heartbeat")
        assert resp.status_code == 403

    async def test_get_availability_requires_specialist(self, employee_client: AsyncClient):
        resp = await employee_client.get("/api/v1/specialist-queue/availability")
        assert resp.status_code == 403


class TestAvailabilitySuccess:
    async def test_set_and_get_availability(self, real_specialist_client):
        ac, user = real_specialist_client
        r = await ac.put("/api/v1/specialist-queue/availability", json={"status": "available"})
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == str(user.id)
        assert body["status"] == "available"
        assert body["is_available"] is True

        r2 = await ac.get("/api/v1/specialist-queue/availability")
        assert r2.status_code == 200
        assert r2.json()["status"] == "available"
        assert r2.json()["is_available"] is True

    async def test_get_availability_defaults_to_away_when_no_row(self, real_specialist_client):
        ac, user = real_specialist_client
        r = await ac.get("/api/v1/specialist-queue/availability")
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == str(user.id)
        assert body["status"] == "away"
        assert body["is_available"] is False
        assert body["last_heartbeat_at"] is None

    async def test_heartbeat_keeps_available(self, real_specialist_client):
        ac, _user = real_specialist_client
        await ac.put("/api/v1/specialist-queue/availability", json={"status": "available"})
        r = await ac.post("/api/v1/specialist-queue/availability/heartbeat")
        assert r.status_code == 200
        assert r.json()["is_available"] is True

    async def test_set_availability_invalid_status_is_422(self, real_specialist_client):
        ac, _user = real_specialist_client
        r = await ac.put("/api/v1/specialist-queue/availability", json={"status": "bogus"})
        assert r.status_code == 422


class TestOffersMine:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/specialist-queue/offers/mine")
        assert resp.status_code == 401

    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get("/api/v1/specialist-queue/offers/mine")
        assert resp.status_code == 403

    async def test_no_offers_returns_empty_list(self, real_specialist_client):
        ac, _user = real_specialist_client
        r = await ac.get("/api/v1/specialist-queue/offers/mine")
        assert r.status_code == 200
        assert r.json() == []


class TestAcceptOfferGating:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(f"/api/v1/specialist-queue/offers/{uuid.uuid4()}/accept")
        assert resp.status_code == 401

    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.post(f"/api/v1/specialist-queue/offers/{uuid.uuid4()}/accept")
        assert resp.status_code == 403

    async def test_missing_ticket_is_404(self, real_specialist_client):
        ac, _user = real_specialist_client
        resp = await ac.post(f"/api/v1/specialist-queue/offers/{uuid.uuid4()}/accept")
        assert resp.status_code == 404


class TestAcceptOfferHappyPath:
    """Regression coverage for the dead ``chat_service._sessions`` lookup.

    ``_claim_response`` used to do
    ``cs_mod._sessions.get(str(ticket.session_id))`` — but ``_sessions`` was
    removed by the SessionStore refactor, so ANY claimable chat ticket with a
    non-null ``session_id`` (i.e. every real chat escalation) 500'd with
    ``AttributeError: module 'app.services.agents.chat_service' has no
    attribute '_sessions'``. This drives the real accept-offer endpoint
    end-to-end against a real, DB-persisted chat ticket that has a non-null
    ``session_id`` — the exact shape that used to blow up — and asserts a
    clean 200 + a well-formed ``ClaimResponse``.
    """

    async def test_accept_offer_builds_handoff_package_for_real_chat_ticket(
        self, real_specialist_client
    ):
        ac, specialist = real_specialist_client
        requester = await _real_employee()

        async with async_session_factory() as session:
            # `Ticket.session_id` FKs to `support_sessions.id` — a real chat
            # escalation always has a backing session row, so the regression
            # test must too (an arbitrary UUID trips the FK constraint).
            support_session = SupportSession(user_id=requester.id, session_type="ai_chat")
            session.add(support_session)
            await session.flush()

            ticket = Ticket(
                ticket_number=f"ITA-TEST-{uuid.uuid4().hex[:8]}",
                title="Live chat escalation",
                description="Regression ticket for accept-offer handoff package build",
                requester_id=requester.id,
                source="chat",
                status="triaged",
                priority="medium",
                category="email/outlook",
                session_id=support_session.id,
            )
            session.add(ticket)
            await session.flush()
            await PresenceService(session).set_status(specialist.id, "available")
            offer = await HandoffService(session).create_offer(ticket)
            assert offer is not None
            assert offer.offered_to == specialist.id
            await session.commit()
            ticket_id = ticket.id

        resp = await ac.post(f"/api/v1/specialist-queue/offers/{ticket_id}/accept")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ticket_id"] == str(ticket_id)
        assert body["claimed_by_user_id"] == str(specialist.id)
        assert body["handoff_package"]["session_id"] != ""

        async with async_session_factory() as session:
            refreshed = await session.get(Ticket, ticket_id)
            assert refreshed is not None
            assert refreshed.assigned_to == specialist.id
            assert refreshed.status == "in_progress"
