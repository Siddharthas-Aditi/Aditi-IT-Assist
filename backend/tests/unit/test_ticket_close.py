"""Unit tests for IT-only close + status bypass."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ticket_service import TicketService


def _user(role: str = "it_agent") -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.full_name = "Agent"
    u.email = f"{role}@test.com"
    u.role_names = [role]
    return u


def _ticket(**kwargs) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.status = kwargs.get("status", "in_progress")
    t.resolution_notes = None
    t.category = None
    t.subcategory = None
    t.item = None
    t.closed_at = None
    t.closed_by = None
    t.close_notes = None
    return t


@pytest.mark.asyncio
async def test_update_status_rejects_closed():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(ValueError, match="close"):
            await svc.update_status(ticket.id, "closed", _user())


@pytest.mark.asyncio
async def test_close_requires_resolution_notes():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(ValueError, match="resolution"):
            await svc.close_ticket(
                ticket.id,
                _user(),
                resolution_notes="  ",
                category="Incident",
                subcategory="Network Connectivity",
                item="VPN",
            )


@pytest.mark.asyncio
async def test_close_employee_forbidden():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(PermissionError):
            await svc.close_ticket(
                ticket.id,
                _user("employee"),
                resolution_notes="Fixed VPN",
                category="Incident",
                subcategory="Network Connectivity",
                item="VPN",
            )


@pytest.mark.asyncio
async def test_update_properties_rejects_closed_status():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(ValueError, match="Use POST"):
            await svc.update_ticket_properties(ticket.id, _user(), status="closed")


@pytest.mark.asyncio
async def test_update_properties_employee_forbidden():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(PermissionError):
            await svc.update_ticket_properties(
                ticket.id, _user("employee"), priority="high"
            )


@pytest.mark.asyncio
async def test_close_already_closed_raises():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket(status="closed")
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(ValueError, match="already closed"):
            await svc.close_ticket(
                ticket.id,
                _user(),
                resolution_notes="Notes",
                category="Incident",
                subcategory="Network",
                item="VPN",
            )


@pytest.mark.asyncio
async def test_close_happy_path_sets_fields():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    actor = _user()
    with (
        patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)),
        patch.object(svc, "_add_event", AsyncMock()),
        patch(
            "app.services.ticket_service.validate_category_cascade",
            AsyncMock(),
        ),
    ):
        result = await svc.close_ticket(
            ticket.id,
            actor,
            resolution_notes="Reset MFA and confirmed login.",
            category="Incident",
            subcategory="System Login Issue",
            item="Account Locked",
        )
    assert result.status == "closed"
    assert result.closed_by == actor.id
    assert result.category == "Incident"
    assert result.subcategory == "System Login Issue"
    assert result.item == "Account Locked"
    assert result.resolution_notes == "Reset MFA and confirmed login."
