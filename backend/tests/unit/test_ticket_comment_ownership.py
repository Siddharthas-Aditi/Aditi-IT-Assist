"""Unit tests for TicketService.add_comment ownership / internal-note rules."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ticket_service import TicketService


def _user(*, role: str, user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.full_name = f"Test {role}"
    user.role_names = [role]
    return user


@pytest.mark.asyncio
async def test_employee_cannot_comment_on_others_ticket():
    db = AsyncMock()
    service = TicketService(db)
    owner_id = uuid.uuid4()
    ticket = MagicMock()
    ticket.id = uuid.uuid4()
    ticket.requester_id = owner_id
    service._get_ticket = AsyncMock(return_value=ticket)
    service._add_event = AsyncMock()

    employee = _user(role="employee")
    with pytest.raises(PermissionError, match="own tickets"):
        await service.add_comment(ticket.id, employee, "hello")


@pytest.mark.asyncio
async def test_employee_internal_flag_forced_false():
    db = AsyncMock()
    service = TicketService(db)
    owner_id = uuid.uuid4()
    ticket = MagicMock()
    ticket.id = uuid.uuid4()
    ticket.requester_id = owner_id
    service._get_ticket = AsyncMock(return_value=ticket)
    service._add_event = AsyncMock()

    employee = _user(role="employee", user_id=owner_id)
    comment = await service.add_comment(
        ticket.id, employee, "public update", is_internal=True
    )
    assert comment.is_internal is False
    db.add.assert_called()


@pytest.mark.asyncio
async def test_staff_can_add_internal_note():
    db = AsyncMock()
    service = TicketService(db)
    ticket = MagicMock()
    ticket.id = uuid.uuid4()
    ticket.requester_id = uuid.uuid4()
    service._get_ticket = AsyncMock(return_value=ticket)
    service._add_event = AsyncMock()

    agent = _user(role="it_lead")
    comment = await service.add_comment(
        ticket.id, agent, "internal triage note", is_internal=True
    )
    assert comment.is_internal is True
