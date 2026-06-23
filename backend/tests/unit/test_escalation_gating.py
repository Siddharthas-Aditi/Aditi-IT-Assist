"""No-direct-connect policy + typing-indicator unit tests.

Pins the enterprise rule that a live-agent handoff (and the anchoring ticket)
must never happen until we have a minimally-useful problem statement:

* the pure policy (:func:`handoff_context_sufficient`),
* the triage gate (early "connect me to a human" → asks for details, no ticket),
* the service-layer gate (`request_live_agent` on a contextless session).

Plus the ephemeral typing-indicator registry.

All in-memory — no DB, no LLM (keyword fallback drives routing).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agents import chat_service as cs_mod
from app.services.agents.chat_service import ChatService
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.escalation_policy import (
    GATHER_PROBLEM_PROMPT,
    handoff_context_sufficient,
)
from app.services.specialist_chat_service import (
    clear_typing,
    set_typing,
    typing_roles,
)


def _ticket_service() -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.ticket_number = "INC-GATE-001"
    t.status = "triaged"
    t.priority = "high"
    svc = MagicMock()
    svc.create_ticket = AsyncMock(return_value=t)
    svc.request_live_agent = AsyncMock()
    svc.db = MagicMock()
    svc.db.commit = AsyncMock()
    return svc


def _requester() -> MagicMock:
    return MagicMock(id=uuid.uuid4(), full_name="Test Employee", email="emp@aditi.com")


def _clear() -> None:
    cs_mod._sessions.clear()
    cs_mod._session_tickets.clear()


# ── Pure policy ────────────────────────────────────────────────────────────


class TestHandoffPolicy:
    def test_empty_context_is_insufficient(self) -> None:
        assert handoff_context_sufficient(DiagnosticContext()) is False

    def test_category_plus_symptom_is_sufficient(self) -> None:
        diag = DiagnosticContext()
        diag.issue_category = "email/outlook"
        diag.symptom = "cannot send email"
        assert handoff_context_sufficient(diag) is True

    def test_already_attempted_steps_short_circuit(self) -> None:
        """If the AI already tried steps, context plainly exists — the
        post-troubleshooting 'Connect' button must keep working."""
        diag = DiagnosticContext()
        diag.suggested_steps = ["Restart Outlook in safe mode"]
        assert handoff_context_sufficient(diag) is True


# ── Triage gate (end-to-end, in-memory) ─────────────────────────────────────


class TestNoDirectConnectAtChatStart:
    @pytest.mark.asyncio
    async def test_cold_human_request_asks_for_details_no_ticket(self) -> None:
        _clear()
        svc = _ticket_service()
        chat = ChatService(svc)

        resp = await chat.process_message(
            session_id="sess-cold",
            user_message="connect me to a live specialist",
            requester=_requester(),
        )

        # No ticket created, and the assistant asks for a problem description.
        assert resp.ticket is None
        svc.create_ticket.assert_not_called()
        assert GATHER_PROBLEM_PROMPT[:40] in resp.content

    @pytest.mark.asyncio
    async def test_vague_help_does_not_escalate(self) -> None:
        _clear()
        svc = _ticket_service()
        chat = ChatService(svc)
        resp = await chat.process_message(
            session_id="sess-vague",
            user_message="help",
            requester=_requester(),
        )
        assert resp.ticket is None
        svc.create_ticket.assert_not_called()


# ── Service-layer gate ───────────────────────────────────────────────────────


class TestRequestLiveAgentGate:
    @pytest.mark.asyncio
    async def test_contextless_session_is_gated(self) -> None:
        """A known session with no draft, no offer, no problem statement must
        NOT create a ticket — it asks for details first."""
        _clear()
        svc = _ticket_service()
        chat = ChatService(svc)
        cs_mod._sessions["sess-empty"] = {"diagnostic_context": {}}

        message, ref = await chat.request_live_agent("sess-empty", _requester())

        assert ref is None
        svc.create_ticket.assert_not_called()
        assert GATHER_PROBLEM_PROMPT[:40] in message

    @pytest.mark.asyncio
    async def test_session_with_offer_is_allowed(self) -> None:
        _clear()
        svc = _ticket_service()
        chat = ChatService(svc)
        cs_mod._sessions["sess-offered"] = {
            "diagnostic_context": {"escalation_offered_in_session": True},
        }

        message, ref = await chat.request_live_agent("sess-offered", _requester())

        assert ref is not None
        assert ref.ticket_number == "INC-GATE-001"
        svc.create_ticket.assert_called_once()
        assert "INC-GATE-001" in message

    @pytest.mark.asyncio
    async def test_unknown_session_still_allowed(self) -> None:
        """No session state at all (direct API / minimal-draft path) is not
        gated — we can't inspect what isn't there, and the UI only reaches
        here post-offer anyway."""
        _clear()
        svc = _ticket_service()
        chat = ChatService(svc)
        _message, ref = await chat.request_live_agent("sess-unknown", _requester())
        assert ref is not None
        svc.create_ticket.assert_called_once()


# ── Typing indicators ────────────────────────────────────────────────────────


class TestTypingRegistry:
    def test_set_and_read_excludes_caller(self) -> None:
        sid = uuid.uuid4()
        clear_typing(sid)
        set_typing(sid, "specialist", is_typing=True)
        # The user polling sees the specialist typing…
        assert typing_roles(sid, exclude_role="user") == ["specialist"]
        # …but the specialist does not see itself.
        assert typing_roles(sid, exclude_role="specialist") == []

    def test_clear_removes_state(self) -> None:
        sid = uuid.uuid4()
        set_typing(sid, "user", is_typing=True)
        set_typing(sid, "user", is_typing=False)
        assert typing_roles(sid) == []

    def test_clear_typing_drops_session(self) -> None:
        sid = uuid.uuid4()
        set_typing(sid, "user", is_typing=True)
        clear_typing(sid)
        assert typing_roles(sid) == []
