"""Unit tests for Task 9: escalation -> handoff-offer wiring + `handoff_state`.

Covers:
- `WaitingStatusResponse` gains `handoff_state` and round-trips (schema test).
- `ChatService._derive_handoff_state` maps the offer/live-session lookups to
  the right typed state ("connected" / "busy" / "fallback" / "connecting").
- `request_live_agent` best-effort-creates a handoff offer without raising
  when the offer/ticket-lookup machinery is unavailable (mocked services).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.chat import WaitingStatusResponse
from app.services.agents.chat_service import ChatService

# ── Helpers ────────────────────────────────────────────────────────────


def _requester() -> MagicMock:
    return MagicMock(id=uuid.uuid4(), full_name="Test Employee", email="emp@aditi.com")


def _ticket_cache() -> dict:
    return {
        "ticket_id": str(uuid.uuid4()),
        "ticket_number": "INC-000123",
        "status": "triaged",
        "priority": "high",
        "live_agent_requested": True,
    }


def _ticket_service() -> MagicMock:
    svc = MagicMock()
    svc.db = MagicMock()
    svc.db.commit = AsyncMock()
    svc._get_ticket = AsyncMock(return_value=None)
    return svc


# ── Schema round-trip ──────────────────────────────────────────────────


def test_waiting_status_has_handoff_state() -> None:
    r = WaitingStatusResponse(
        session_id="sess-1",
        waiting=True,
        waited_seconds=5,
        specialist_available=True,
        handoff_state="connecting",
    )
    assert r.handoff_state == "connecting"


def test_waiting_status_handoff_state_defaults_to_connecting() -> None:
    r = WaitingStatusResponse(session_id="sess-2", waiting=False)
    assert r.handoff_state == "connecting"


# ── request_live_agent: best-effort offer creation ─────────────────────


class TestHandoffOfferCreationIsBestEffort:
    @pytest.mark.asyncio
    async def test_ticket_lookup_failure_does_not_raise(self) -> None:
        """If _get_ticket raises, the offer-creation helper swallows it."""
        svc = _ticket_service()
        svc._get_ticket = AsyncMock(side_effect=RuntimeError("db down"))
        chat = ChatService(svc)

        # Must not raise.
        await chat._create_handoff_offer(str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_no_ticket_found_skips_offer_creation(self) -> None:
        """When the ticket can't be resolved, no offer is attempted."""
        svc = _ticket_service()
        svc._get_ticket = AsyncMock(return_value=None)
        chat = ChatService(svc)

        await chat._create_handoff_offer(str(uuid.uuid4()))
        svc.db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_offer_created_and_committed_when_ticket_resolves(self) -> None:
        """A resolvable ticket routes through HandoffService.create_offer + commit."""
        svc = _ticket_service()
        ticket_obj = MagicMock(id=uuid.uuid4())
        svc._get_ticket = AsyncMock(return_value=ticket_obj)
        chat = ChatService(svc)

        created_offer = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            handoff_cls = MagicMock()
            handoff_instance = MagicMock()
            handoff_instance.create_offer = AsyncMock(return_value=created_offer)
            handoff_cls.return_value = handoff_instance
            mp.setattr(
                "app.services.specialist_handoff_service.HandoffService",
                handoff_cls,
            )

            await chat._create_handoff_offer(str(ticket_obj.id))

        handoff_instance.create_offer.assert_awaited_once_with(ticket_obj)
        svc.db.commit.assert_awaited_once()


# ── get_waiting_status: handoff_state derivation ───────────────────────


class TestDeriveHandoffState:
    @pytest.mark.asyncio
    async def test_no_ticket_service_defaults_to_connecting(self) -> None:
        chat = ChatService(ticket_service=None)
        state = await chat._derive_handoff_state(_ticket_cache(), _requester(), True)
        assert state == "connecting"

    @pytest.mark.asyncio
    async def test_malformed_ticket_id_defaults_to_connecting(self) -> None:
        svc = _ticket_service()
        chat = ChatService(svc)
        state = await chat._derive_handoff_state({"ticket_id": "not-a-uuid"}, _requester(), True)
        assert state == "connecting"

    @pytest.mark.asyncio
    async def test_live_specialist_session_is_connected(self) -> None:
        svc = _ticket_service()
        chat = ChatService(svc)

        live_session = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            specialist_cls = MagicMock()
            specialist_instance = MagicMock()
            specialist_instance.get_active_for_participant = AsyncMock(return_value=live_session)
            specialist_cls.return_value = specialist_instance
            mp.setattr(
                "app.services.specialist_chat_service.SpecialistChatService",
                specialist_cls,
            )

            state = await chat._derive_handoff_state(_ticket_cache(), _requester(), True)

        assert state == "connected"

    @pytest.mark.asyncio
    async def test_no_offer_and_specialist_unavailable_is_fallback(self) -> None:
        svc = _ticket_service()
        chat = ChatService(svc)

        with pytest.MonkeyPatch.context() as mp:
            specialist_cls = MagicMock()
            specialist_instance = MagicMock()
            specialist_instance.get_active_for_participant = AsyncMock(return_value=None)
            specialist_cls.return_value = specialist_instance
            mp.setattr(
                "app.services.specialist_chat_service.SpecialistChatService",
                specialist_cls,
            )

            handoff_cls = MagicMock()
            handoff_instance = MagicMock()
            handoff_instance.active_offer_for = AsyncMock(return_value=None)
            handoff_cls.return_value = handoff_instance
            mp.setattr(
                "app.services.specialist_handoff_service.HandoffService",
                handoff_cls,
            )

            state = await chat._derive_handoff_state(
                _ticket_cache(), _requester(), specialist_available=False
            )

        assert state == "fallback"

    @pytest.mark.asyncio
    async def test_no_offer_and_specialist_available_is_busy(self) -> None:
        svc = _ticket_service()
        chat = ChatService(svc)

        with pytest.MonkeyPatch.context() as mp:
            specialist_cls = MagicMock()
            specialist_instance = MagicMock()
            specialist_instance.get_active_for_participant = AsyncMock(return_value=None)
            specialist_cls.return_value = specialist_instance
            mp.setattr(
                "app.services.specialist_chat_service.SpecialistChatService",
                specialist_cls,
            )

            handoff_cls = MagicMock()
            handoff_instance = MagicMock()
            handoff_instance.active_offer_for = AsyncMock(return_value=None)
            handoff_cls.return_value = handoff_instance
            mp.setattr(
                "app.services.specialist_handoff_service.HandoffService",
                handoff_cls,
            )

            state = await chat._derive_handoff_state(
                _ticket_cache(), _requester(), specialist_available=True
            )

        assert state == "busy"

    @pytest.mark.asyncio
    async def test_broadened_offer_is_busy(self) -> None:
        svc = _ticket_service()
        chat = ChatService(svc)

        offer = MagicMock(state="broadened")
        with pytest.MonkeyPatch.context() as mp:
            specialist_cls = MagicMock()
            specialist_instance = MagicMock()
            specialist_instance.get_active_for_participant = AsyncMock(return_value=None)
            specialist_cls.return_value = specialist_instance
            mp.setattr(
                "app.services.specialist_chat_service.SpecialistChatService",
                specialist_cls,
            )

            handoff_cls = MagicMock()
            handoff_instance = MagicMock()
            handoff_instance.active_offer_for = AsyncMock(return_value=offer)
            handoff_cls.return_value = handoff_instance
            mp.setattr(
                "app.services.specialist_handoff_service.HandoffService",
                handoff_cls,
            )

            state = await chat._derive_handoff_state(_ticket_cache(), _requester(), True)

        assert state == "busy"

    @pytest.mark.asyncio
    async def test_active_targeted_offer_is_connecting(self) -> None:
        svc = _ticket_service()
        chat = ChatService(svc)

        offer = MagicMock(state="offered")
        with pytest.MonkeyPatch.context() as mp:
            specialist_cls = MagicMock()
            specialist_instance = MagicMock()
            specialist_instance.get_active_for_participant = AsyncMock(return_value=None)
            specialist_cls.return_value = specialist_instance
            mp.setattr(
                "app.services.specialist_chat_service.SpecialistChatService",
                specialist_cls,
            )

            handoff_cls = MagicMock()
            handoff_instance = MagicMock()
            handoff_instance.active_offer_for = AsyncMock(return_value=offer)
            handoff_cls.return_value = handoff_instance
            mp.setattr(
                "app.services.specialist_handoff_service.HandoffService",
                handoff_cls,
            )

            state = await chat._derive_handoff_state(_ticket_cache(), _requester(), True)

        assert state == "connecting"

    @pytest.mark.asyncio
    async def test_lookup_error_degrades_to_connecting(self) -> None:
        svc = _ticket_service()
        chat = ChatService(svc)

        with pytest.MonkeyPatch.context() as mp:
            specialist_cls = MagicMock()
            specialist_instance = MagicMock()
            specialist_instance.get_active_for_participant = AsyncMock(
                side_effect=RuntimeError("db down")
            )
            specialist_cls.return_value = specialist_instance
            mp.setattr(
                "app.services.specialist_chat_service.SpecialistChatService",
                specialist_cls,
            )

            state = await chat._derive_handoff_state(_ticket_cache(), _requester(), True)

        assert state == "connecting"
