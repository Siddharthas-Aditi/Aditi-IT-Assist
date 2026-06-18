"""Unit tests for chat → ticket → live-agent handoff.

Covers the invariant the feature is built around: a real support ticket is
created (and queued for a human) only on EXPLICIT confirmation, and always
BEFORE the live-agent handoff. Ticket creation is idempotent per session.

These tests exercise the service layer directly with a mocked TicketService —
no DB, no LLM, no workflow graph.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from app.services.agents import chat_service as cs_mod
from app.services.agents.chat_service import ChatService

DRAFT = {
    "title": "IT Support Request - access/sixth_sense (login-failure)",
    "description": "## Problem\nUnable to log in to Sixth Sense.",
    "priority": "high",
    "category": "access/sixth_sense",
    "problem_statement": "Unable to log in to Sixth Sense.",
}


def _fake_ticket(number="INC-000042", status="triaged", priority="high"):
    ticket = MagicMock()
    ticket.id = uuid.uuid4()
    ticket.ticket_number = number
    ticket.status = status
    ticket.priority = priority
    return ticket


def _mock_ticket_service(ticket=None):
    svc = MagicMock()
    svc.create_ticket = AsyncMock(return_value=ticket or _fake_ticket())
    svc.request_live_agent = AsyncMock()
    svc.db = MagicMock()
    svc.db.commit = AsyncMock()
    return svc


def _requester():
    return MagicMock(id=uuid.uuid4(), full_name="Test Employee", email="emp@aditi.com")


def _clear_state():
    cs_mod._sessions.clear()
    cs_mod._session_tickets.clear()


class TestTicketOnConfirm:
    """`_handle_ticketing` only persists on explicit confirmation."""

    async def test_offer_without_confirmation_creates_no_ticket(self):
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        result = {
            "should_escalate": True,
            "escalation_confirmed": False,  # only offered, not confirmed
            "ticket_offered": True,
            "ticket_draft": DRAFT,
        }
        ref = await chat._handle_ticketing("sess-1", result, _requester())

        assert ref is None
        svc.create_ticket.assert_not_called()

    async def test_confirmation_creates_then_queues_ticket(self):
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        result = {
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": DRAFT,
        }
        ref = await chat._handle_ticketing("sess-1", result, _requester())

        assert ref is not None
        assert ref.ticket_number == "INC-000042"
        assert ref.live_agent_requested is True
        # Ticket created BEFORE the live-agent queue call.
        svc.create_ticket.assert_awaited_once()
        svc.request_live_agent.assert_awaited_once()
        svc.db.commit.assert_awaited_once()

    async def test_ticket_creation_is_idempotent_per_session(self):
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)
        result = {
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": DRAFT,
        }

        first = await chat._handle_ticketing("sess-1", result, _requester())
        second = await chat._handle_ticketing("sess-1", result, _requester())

        assert first.ticket_number == second.ticket_number
        svc.create_ticket.assert_awaited_once()  # not created twice

    async def test_no_ticket_service_degrades_to_offer(self):
        _clear_state()
        chat = ChatService(ticket_service=None)
        result = {
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": DRAFT,
        }
        ref = await chat._handle_ticketing("sess-1", result, _requester())
        assert ref is None


class TestRequestLiveAgent:
    """The explicit 'Connect with a specialist' action."""

    async def test_creates_ticket_from_session_draft(self):
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)
        cs_mod._sessions["sess-2"] = {"ticket_draft": DRAFT, "issue_category": "access/sixth_sense"}

        message, ref = await chat.request_live_agent("sess-2", _requester())

        assert "INC-000042" in message
        assert ref.ticket_number == "INC-000042"
        svc.create_ticket.assert_awaited_once()
        svc.request_live_agent.assert_awaited_once()

    async def test_uses_minimal_draft_when_no_session_context(self):
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        _, ref = await chat.request_live_agent("sess-3", _requester())

        assert ref is not None
        kwargs = svc.create_ticket.call_args.kwargs
        assert "Live support request" in kwargs["title"]

    async def test_idempotent_repeated_connect(self):
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)
        cs_mod._sessions["sess-2"] = {"ticket_draft": DRAFT}

        await chat.request_live_agent("sess-2", _requester())
        message, _ = await chat.request_live_agent("sess-2", _requester())

        assert "already in the queue" in message.lower()
        svc.create_ticket.assert_awaited_once()


class TestFormatResponse:
    """Response shaping: offer vs. created ticket."""

    def test_offer_sets_escalation_flags_no_ticket(self):
        chat = ChatService()
        result = {
            "messages": [AIMessage(content="...I can raise a ticket...")],
            "should_escalate": True,
            "ticket_offered": True,
        }
        resp = chat._format_response("s", result, ticket_ref=None)

        assert resp.requires_escalation is True
        assert resp.escalation_offered is True
        assert resp.ticket is None

    def test_created_ticket_overrides_content_and_hides_offer(self):
        _clear_state()
        chat = ChatService()
        ref = cs_mod.TicketRef(
            ticket_id=str(uuid.uuid4()),
            ticket_number="INC-000042",
            status="triaged",
            priority="high",
            live_agent_requested=True,
        )
        result = {
            "messages": [AIMessage(content="interim")],
            "should_escalate": True,
            "ticket_offered": True,
        }
        resp = chat._format_response("s", result, ticket_ref=ref)

        assert "INC-000042" in resp.content
        assert resp.ticket is not None
        assert resp.requires_escalation is False  # ticket exists → no re-offer
        assert resp.escalation_offered is False
