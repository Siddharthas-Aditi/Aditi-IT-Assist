"""Real-DB integration tests for `HandoffService` (create_offer/accept/advance_once).

Like `test_ticket_reopen.py`, this runs against the real test Postgres — no DB
mocking. Each test opens its own `async_session_factory()` session, creates the
rows it needs directly via the ORM (unique ticket numbers / emails so runs
don't collide), exercises the service, and never commits — the session's
implicit rollback on close (pytest-asyncio function-scoped loop) undoes every
insert, so the shared dev DB is never left with test residue.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.database import async_session_factory, engine
from app.models.auth import User
from app.models.live_handoff import LiveHandoffOffer
from app.models.ticket import Ticket
from app.services.specialist_handoff_service import HandoffService
from app.services.specialist_presence_service import PresenceService

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    """Avoid cross-event-loop asyncpg errors (see test_specialist_report_api.py)."""
    yield
    await engine.dispose()


async def _make_user(db, tag: str) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"{tag}-{unique}@handoff-test.local",
        full_name=f"{tag}-{unique}",
        hashed_password="x",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_chat_ticket(db, requester: User) -> Ticket:
    ticket = Ticket(
        ticket_number=f"ITA-TEST-{uuid.uuid4().hex[:8]}",
        title="Live support request",
        description="Integration test ticket",
        requester_id=requester.id,
        source="chat",
        status="triaged",
        priority="medium",
        category="email/outlook",
    )
    db.add(ticket)
    await db.flush()
    return ticket


class TestCreateOffer:
    async def test_targets_available_specialist(self):
        async with async_session_factory() as db:
            spec = await _make_user(db, "spec")
            requester = await _make_user(db, "emp")
            await PresenceService(db).set_status(spec.id, "available")
            ticket = await _make_chat_ticket(db, requester)

            offer = await HandoffService(db).create_offer(ticket)

            assert offer is not None
            assert offer.offered_to == spec.id
            assert offer.state == "offered"
            # Never committed — session close rolls everything back.

    async def test_returns_none_when_no_one_available(self):
        async with async_session_factory() as db:
            requester = await _make_user(db, "emp")
            ticket = await _make_chat_ticket(db, requester)

            offer = await HandoffService(db).create_offer(ticket)

            assert offer is None


class TestAdvanceOnce:
    async def test_expired_offer_falls_back_when_none_available(self):
        async with async_session_factory() as db:
            requester = await _make_user(db, "emp")
            ticket = await _make_chat_ticket(db, requester)
            stale = datetime.now(UTC) - timedelta(seconds=300)
            db.add(
                LiveHandoffOffer(
                    ticket_id=ticket.id,
                    offered_to=None,
                    offered_at=stale,
                    expires_at=stale + timedelta(seconds=30),
                    round_index=1,
                    state="offered",
                )
            )
            await db.flush()

            counts = await HandoffService(db).advance_once()

            assert counts["fallback"] >= 1
            offer = await HandoffService(db).active_offer_for(ticket.id)
            assert offer is None  # moved to terminal 'fallback'

    async def test_expired_offer_reoffers_to_another_available_specialist(self):
        async with async_session_factory() as db:
            requester = await _make_user(db, "emp")
            first = await _make_user(db, "spec-first")
            second = await _make_user(db, "spec-second")
            await PresenceService(db).set_status(second.id, "available")
            ticket = await _make_chat_ticket(db, requester)
            expired = datetime.now(UTC) - timedelta(seconds=40)  # past 30s TTL
            offer = LiveHandoffOffer(
                ticket_id=ticket.id,
                offered_to=first.id,
                offered_at=expired,
                expires_at=expired + timedelta(seconds=30),
                round_index=0,
                state="offered",
            )
            db.add(offer)
            await db.flush()

            counts = await HandoffService(db).advance_once()

            assert counts["reoffered"] >= 1
            assert offer.offered_to == second.id
            assert offer.round_index == 1
            assert offer.state == "offered"


class TestAccept:
    async def test_accept_happy_path(self):
        async with async_session_factory() as db:
            spec = await _make_user(db, "spec")
            requester = await _make_user(db, "emp")
            await PresenceService(db).set_status(spec.id, "available")
            ticket = await _make_chat_ticket(db, requester)
            offer = await HandoffService(db).create_offer(ticket)
            assert offer is not None

            accepted = await HandoffService(db).accept(ticket.id, specialist=spec)

            assert accepted.state == "accepted"
            assert accepted.offered_to == spec.id

    async def test_accept_is_idempotent_for_same_specialist(self):
        async with async_session_factory() as db:
            spec = await _make_user(db, "spec")
            requester = await _make_user(db, "emp")
            await PresenceService(db).set_status(spec.id, "available")
            ticket = await _make_chat_ticket(db, requester)
            offer = await HandoffService(db).create_offer(ticket)
            assert offer is not None
            service = HandoffService(db)

            first = await service.accept(ticket.id, specialist=spec)
            second = await service.accept(ticket.id, specialist=spec)

            assert first.id == second.id
            assert second.state == "accepted"
            assert second.offered_to == spec.id

    async def test_accept_conflicts_when_different_specialist_already_accepted(self):
        async with async_session_factory() as db:
            spec_a = await _make_user(db, "spec-a")
            spec_b = await _make_user(db, "spec-b")
            requester = await _make_user(db, "emp")
            await PresenceService(db).set_status(spec_a.id, "available")
            ticket = await _make_chat_ticket(db, requester)
            offer = await HandoffService(db).create_offer(ticket)
            assert offer is not None
            service = HandoffService(db)
            await service.accept(ticket.id, specialist=spec_a)

            with pytest.raises(PermissionError):
                await service.accept(ticket.id, specialist=spec_b)
