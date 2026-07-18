"""Unit tests for status_changed event logging in the specialist queue.

`release()`/`resolve()` now write a `status_changed` `TicketEvent` (captured
BEFORE the ticket's status is mutated) so the specialist report (C1) can
derive a "reopened" signal from the ticket timeline the same way the ticket
router's `update_status`/`reopen_ticket` already do. Internal side-effect
collaborators (`SpecialistChatService`, `EscalationService`) are patched out
— this test is scoped to the event-logging behavior added here, not those
collaborators' own logic.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.specialist_queue_service import SpecialistQueueService


def _mock_db(ticket: MagicMock) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=ticket)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _ticket(status: str, assigned_to: uuid.UUID) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.ticket_number = "INC-000123"
    t.status = status
    t.assigned_to = assigned_to
    t.title = "VPN issue"
    t.category = "network/vpn"
    t.subcategory = "vpn-connect"
    return t


def _user() -> MagicMock:
    return MagicMock(id=uuid.uuid4(), full_name="Charlie Martinez")


def _status_changed_events(db: MagicMock) -> list:
    added = [call.args[0] for call in db.add.call_args_list]
    return [e for e in added if getattr(e, "event_type", None) == "status_changed"]


class TestReleaseLogsStatusChanged:
    async def test_release_writes_status_changed_event_from_old_status(self):
        user = _user()
        ticket = _ticket("in_progress", assigned_to=user.id)
        db = _mock_db(ticket)
        queue_svc = SpecialistQueueService(db)

        with patch("app.services.specialist_chat_service.SpecialistChatService") as chat_cls:
            chat_cls.return_value.end_active_for_ticket = AsyncMock()
            result = await queue_svc.release(ticket.id, by_user=user)

        assert result.status == "triaged"
        status_events = _status_changed_events(db)
        assert len(status_events) == 1
        assert status_events[0].old_value == "in_progress"
        assert status_events[0].new_value == "triaged"

    async def test_release_from_waiting_for_user_records_correct_old_value(self):
        user = _user()
        ticket = _ticket("waiting_for_user", assigned_to=user.id)
        db = _mock_db(ticket)
        queue_svc = SpecialistQueueService(db)

        with patch("app.services.specialist_chat_service.SpecialistChatService") as chat_cls:
            chat_cls.return_value.end_active_for_ticket = AsyncMock()
            await queue_svc.release(ticket.id, by_user=user)

        status_events = _status_changed_events(db)
        assert len(status_events) == 1
        assert status_events[0].old_value == "waiting_for_user"
        assert status_events[0].new_value == "triaged"


class TestResolveLogsStatusChanged:
    async def test_resolve_writes_status_changed_event_from_old_status(self):
        user = _user()
        ticket = _ticket("in_progress", assigned_to=user.id)
        db = _mock_db(ticket)
        queue_svc = SpecialistQueueService(db)

        with (
            patch("app.services.specialist_chat_service.SpecialistChatService") as chat_cls,
            patch("app.services.escalation_service.EscalationService") as esc_cls,
        ):
            chat_cls.return_value.end_active_for_ticket = AsyncMock()
            esc_cls.return_value.record_resolution_comparison = AsyncMock()
            ticket_out, candidate_id = await queue_svc.resolve(
                ticket.id,
                by_user=user,
                resolution_notes="Reset VPN profile",
                propose_knowledge_candidate=False,
            )

        assert ticket_out.status == "resolved"
        assert candidate_id is None
        status_events = _status_changed_events(db)
        assert len(status_events) == 1
        assert status_events[0].old_value == "in_progress"
        assert status_events[0].new_value == "resolved"

    async def test_resolve_from_escalated_records_correct_old_value(self):
        user = _user()
        ticket = _ticket("escalated", assigned_to=user.id)
        db = _mock_db(ticket)
        queue_svc = SpecialistQueueService(db)

        with (
            patch("app.services.specialist_chat_service.SpecialistChatService") as chat_cls,
            patch("app.services.escalation_service.EscalationService") as esc_cls,
        ):
            chat_cls.return_value.end_active_for_ticket = AsyncMock()
            esc_cls.return_value.record_resolution_comparison = AsyncMock()
            await queue_svc.resolve(
                ticket.id,
                by_user=user,
                resolution_notes="Escalated fix applied",
                propose_knowledge_candidate=False,
            )

        status_events = _status_changed_events(db)
        assert len(status_events) == 1
        assert status_events[0].old_value == "escalated"
        assert status_events[0].new_value == "resolved"
