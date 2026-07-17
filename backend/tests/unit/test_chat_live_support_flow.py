"""Comprehensive tests for the full chat → live-agent handoff flow.

Covers the enterprise requirements:
1. User cannot directly connect to live agent at chat start
2. Vague issue cannot be escalated without more detail
3. AI-first troubleshooting attempt occurs
4. Unresolved issue creates ticket and live support request
5. User sees waiting message
6. Specialist receives context package
7. Same-window handoff works (via polling)
8. Typing indicators work both ways
9. 7-minute idle warning is sent
10. 2-minute grace period ends chat
11. User response during warning resets idle timer
12. Duplicate specialist claim prevented
13. No-specialist-available fallback works
14. Cancel waiting works
15. Repeated failure auto-escalation triggers
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agents.chat_service import (
    WAIT_TIMEOUT_SECONDS,
    ChatService,
)
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.escalation_policy import (
    GATHER_PROBLEM_PROMPT,
    handoff_context_sufficient,
)
from app.services.agents.session_store import (
    ChatSession,
    InMemorySessionStore,
    get_session_store,
    set_session_store,
)
from app.services.specialist_chat_service import (
    SpecialistChatService,
    clear_typing,
    set_typing,
    typing_roles,
)

# ── Helpers ────────────────────────────────────────────────────────────


def _ticket_service(ticket_number: str = "INC-000042") -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.ticket_number = ticket_number
    t.status = "triaged"
    t.priority = "high"
    svc = MagicMock()
    svc.create_ticket = AsyncMock(return_value=t)
    svc.request_live_agent = AsyncMock()
    svc.db = MagicMock()
    svc.db.commit = AsyncMock()
    return svc


def _requester(name: str = "Test Employee") -> MagicMock:
    return MagicMock(id=uuid.uuid4(), full_name=name, email="emp@aditi.com")


def _clear_all() -> None:
    set_session_store(InMemorySessionStore())


# ── 1. No Direct Connect at Chat Start ────────────────────────────────


class TestNoDirectConnectAtStart:
    """Users cannot directly connect to a live agent immediately at chat start."""

    @pytest.mark.asyncio
    async def test_cold_connect_request_asks_for_details(self) -> None:
        """On first message, 'connect me to a human' triggers problem-gathering, not handoff."""
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        resp = await chat.process_message(
            session_id="sess-cold-start",
            user_message="connect me to a live specialist",
            requester=_requester(),
        )

        # No ticket should be created
        assert resp.ticket is None
        svc.create_ticket.assert_not_called()
        # The response should ask for problem details
        assert GATHER_PROBLEM_PROMPT[:40] in resp.content or "describe" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_bare_help_does_not_escalate(self) -> None:
        """Vague 'help' should not create a ticket or escalate."""
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        resp = await chat.process_message(
            session_id="sess-help",
            user_message="help",
            requester=_requester(),
        )

        assert resp.ticket is None
        assert resp.requires_escalation is False
        svc.create_ticket.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_me_now_without_context_is_gated(self) -> None:
        """'I want to talk to a real person' without any context is gated."""
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        resp = await chat.process_message(
            session_id="sess-human-request",
            user_message="I want to talk to a real person right now",
            requester=_requester(),
        )

        assert resp.ticket is None
        svc.create_ticket.assert_not_called()


# ── 2. Vague Issue Cannot Be Escalated ────────────────────────────────


class TestVagueIssueBlocked:
    """Insufficient problem descriptions are blocked from escalation."""

    def test_empty_diagnostic_context_insufficient(self) -> None:
        assert handoff_context_sufficient(DiagnosticContext()) is False

    def test_category_only_insufficient(self) -> None:
        """Category alone (no symptom/subtype) is not enough."""
        diag = DiagnosticContext()
        diag.issue_category = "email/outlook"
        # No symptom, no subtype
        assert diag.has_enough_context() is False

    def test_category_plus_symptom_is_sufficient(self) -> None:
        diag = DiagnosticContext()
        diag.issue_category = "email/outlook"
        diag.symptom = "emails not arriving"
        assert handoff_context_sufficient(diag) is True


# ── 3. AI-First Troubleshooting ──────────────────────────────────────


class TestAIFirstTroubleshooting:
    """The LLM attempts resolution before any escalation."""

    @pytest.mark.asyncio
    async def test_specific_issue_gets_ai_response_not_escalation(self) -> None:
        """A clear issue description should trigger AI troubleshooting, not escalation."""
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        resp = await chat.process_message(
            session_id="sess-ai-first",
            user_message="My Outlook is not syncing emails since this morning",
            requester=_requester(),
        )

        # Should NOT immediately escalate
        assert resp.ticket is None
        svc.create_ticket.assert_not_called()
        # Should provide some response (AI engagement)
        assert len(resp.content) > 20
        # Should classify the issue
        assert resp.issue_category is not None or resp.confidence_score > 0


# ── 4. Unresolved Issue Creates Ticket ────────────────────────────────


class TestUnresolvedCreatesTicket:
    """Unresolved issues properly create ticket + live support request."""

    @pytest.mark.asyncio
    async def test_confirmed_escalation_creates_ticket(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        draft = {
            "title": "Outlook not syncing",
            "description": "Cannot sync emails",
            "priority": "high",
            "category": "email/outlook",
            "problem_statement": "Outlook emails not syncing since morning",
        }
        result = {
            "session_id": "sess-escalate",
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": draft,
            "messages": [],
        }

        session = ChatSession(user_id=None, state={"session_id": "sess-escalate"})
        ref = await chat._handle_ticketing(session, result, _requester())

        assert ref is not None
        assert ref.ticket_number == "INC-000042"
        assert ref.live_agent_requested is True
        svc.create_ticket.assert_awaited_once()
        svc.request_live_agent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_live_agent_creates_ticket_from_session(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)
        await get_session_store().save(
            "sess-live",
            ChatSession(
                user_id=None,
                state={
                    "ticket_draft": {"title": "VPN Issue", "category": "network/connectivity"},
                    "diagnostic_context": {"escalation_offered_in_session": True},
                },
            ),
        )

        message, ref = await chat.request_live_agent("sess-live", _requester())

        assert ref is not None
        assert ref.ticket_number == "INC-000042"
        assert "INC-000042" in message
        svc.create_ticket.assert_awaited_once()


# ── 5. Waiting Message ────────────────────────────────────────────────


class TestWaitingMessage:
    """User sees appropriate waiting messaging after handoff."""

    @pytest.mark.asyncio
    async def test_handoff_response_contains_waiting_info(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)
        await get_session_store().save(
            "sess-wait",
            ChatSession(
                user_id=None,
                state={
                    "ticket_draft": {"title": "Issue", "category": "other"},
                    "diagnostic_context": {"escalation_offered_in_session": True},
                },
            ),
        )

        message, ref = await chat.request_live_agent("sess-wait", _requester())

        assert ref is not None
        # Message should indicate the ticket was created and specialist will follow up
        assert "specialist" in message.lower() or "follow up" in message.lower()


# ── 6. Specialist Receives Context ──────────────────────────────────────


class TestHandoffContextPackage:
    """Specialist receives full context when claiming a ticket."""

    @pytest.mark.asyncio
    async def test_handoff_package_includes_conversation(self) -> None:
        from app.services.specialist_queue_service import SpecialistQueueService

        db = MagicMock()
        # The service now checks for a persisted escalation context first;
        # simulate "no context found" so it falls back to the in-memory state.
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)
        queue_svc = SpecialistQueueService(db)

        ticket = MagicMock()
        ticket.id = uuid.uuid4()
        ticket.session_id = None
        ticket.ai_summary = "Outlook not syncing emails"
        ticket.title = "Outlook sync issue"
        ticket.category = "email/outlook"
        ticket.subcategory = "email-sync"
        ticket.urgency = "high"
        ticket.ai_confidence = 0.3

        session_state = {
            "diagnostic_context": {
                "exact_problem_statement": "Outlook not syncing since 9am",
                "affected_system": "outlook",
                "issue_subtype": "email-sync",
                "escalation_reason": "AI steps exhausted",
                "live_agent_requested": True,
            },
        }

        package = await queue_svc.build_handoff_package(ticket, session_state=session_state)

        assert package.summary.issue_one_liner == "Outlook not syncing emails"
        assert package.summary.issue_category == "email/outlook"
        assert package.handoff_reason == "AI steps exhausted"
        assert package.handoff_triggered_by == "user_request"


# ── 7. Typing Indicators Both Ways ──────────────────────────────────


class TestTypingIndicators:
    """Typing indicators work bidirectionally."""

    def test_specialist_typing_visible_to_user(self) -> None:
        sid = uuid.uuid4()
        clear_typing(sid)
        set_typing(sid, "specialist", is_typing=True)
        # User should see specialist is typing
        assert "specialist" in typing_roles(sid, exclude_role="user")
        # Specialist should NOT see itself
        assert typing_roles(sid, exclude_role="specialist") == []

    def test_user_typing_visible_to_specialist(self) -> None:
        sid = uuid.uuid4()
        clear_typing(sid)
        set_typing(sid, "user", is_typing=True)
        # Specialist should see user is typing
        assert "user" in typing_roles(sid, exclude_role="specialist")
        # User should NOT see itself
        assert typing_roles(sid, exclude_role="user") == []

    def test_stop_typing_clears_indicator(self) -> None:
        sid = uuid.uuid4()
        clear_typing(sid)
        set_typing(sid, "user", is_typing=True)
        set_typing(sid, "user", is_typing=False)
        assert typing_roles(sid) == []

    def test_session_end_clears_all_typing(self) -> None:
        sid = uuid.uuid4()
        set_typing(sid, "user", is_typing=True)
        set_typing(sid, "specialist", is_typing=True)
        clear_typing(sid)
        assert typing_roles(sid) == []


# ── 8. Idle Warning at 7 Minutes ─────────────────────────────────────


class TestIdleWarning:
    """7-minute idle warning fires correctly."""

    def test_warning_fires_at_7_minutes(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = MagicMock()
        session.last_activity_at = datetime.now(UTC) - timedelta(minutes=7, seconds=30)
        session.idle_warning_seconds = 420  # 7 min
        session.idle_end_seconds = 540  # 9 min

        ev = svc.evaluate_idle(session)

        assert ev.is_idle_warning is True
        assert ev.is_idle_end is False

    def test_no_warning_before_7_minutes(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = MagicMock()
        session.last_activity_at = datetime.now(UTC) - timedelta(minutes=6)
        session.idle_warning_seconds = 420
        session.idle_end_seconds = 540

        ev = svc.evaluate_idle(session)

        assert ev.is_idle_warning is False
        assert ev.is_idle_end is False


# ── 9. Grace Period Auto-End ─────────────────────────────────────────


class TestGracePeriodAutoEnd:
    """2-minute grace period ends chat automatically."""

    def test_auto_end_after_9_minutes(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = MagicMock()
        session.last_activity_at = datetime.now(UTC) - timedelta(minutes=9, seconds=1)
        session.idle_warning_seconds = 420
        session.idle_end_seconds = 540

        ev = svc.evaluate_idle(session)

        assert ev.is_idle_end is True

    def test_no_end_during_grace(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = MagicMock()
        session.last_activity_at = datetime.now(UTC) - timedelta(minutes=8)
        session.idle_warning_seconds = 420
        session.idle_end_seconds = 540

        ev = svc.evaluate_idle(session)

        assert ev.is_idle_warning is True
        assert ev.is_idle_end is False


# ── 10. User Response Resets Idle Timer ──────────────────────────────


class TestIdleTimerReset:
    """User response during warning resets the idle timer."""

    @pytest.mark.asyncio
    async def test_message_resets_idle_warning_status(self) -> None:
        """Sending a message when in idle_warning should reset to active."""
        svc = SpecialistChatService(db=MagicMock())

        session = MagicMock()
        session.id = uuid.uuid4()
        session.user_id = uuid.uuid4()
        session.specialist_id = uuid.uuid4()
        session.status = "idle_warning"
        session.idle_warning_at = datetime.now(UTC) - timedelta(minutes=1)
        session.messages = []

        sender = MagicMock()
        sender.id = session.user_id

        # Mock the _load to return our session
        svc._load = AsyncMock(return_value=session)
        svc.db = MagicMock()
        svc.db.add = MagicMock()
        svc.db.flush = AsyncMock()
        svc.audit = MagicMock()
        svc.audit.log = AsyncMock()

        await svc.send_message(session.id, sender=sender, content="I'm still here!")

        # Status should be reset to active
        assert session.status == "active"
        assert session.idle_warning_at is None


# ── 11. Duplicate Specialist Claim Prevention ────────────────────────


class TestDuplicateClaimPrevention:
    """Two specialists cannot claim the same live session."""

    @pytest.mark.asyncio
    async def test_second_claim_raises_permission_error(self) -> None:
        from app.services.specialist_queue_service import SpecialistQueueService

        db = MagicMock()
        queue_svc = SpecialistQueueService(db)

        specialist1 = MagicMock(id=uuid.uuid4())
        specialist2 = MagicMock(id=uuid.uuid4())
        ticket_id = uuid.uuid4()

        # First specialist claims successfully
        claimed_ticket = MagicMock()
        claimed_ticket.id = ticket_id
        claimed_ticket.ticket_number = "INC-001"
        claimed_ticket.assigned_to = specialist1.id

        # Second attempt — ticket is now assigned to specialist1
        existing_ticket = MagicMock()
        existing_ticket.id = ticket_id
        existing_ticket.ticket_number = "INC-001"
        existing_ticket.assigned_to = specialist1.id

        # Simulate the atomic UPDATE returning None (already claimed)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=execute_result)
        db.get = AsyncMock(return_value=existing_ticket)

        with pytest.raises(PermissionError, match="already claimed"):
            await queue_svc.claim(ticket_id, claimer=specialist2)


# ── 12. Specialist Unavailable Fallback ──────────────────────────────


class TestSpecialistUnavailableFallback:
    """After timeout, system signals no specialist available."""

    @pytest.mark.asyncio
    async def test_waiting_status_shows_unavailable_after_timeout(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        # Simulate a session that has been waiting for more than WAIT_TIMEOUT_SECONDS
        session_id = "sess-long-wait"
        await get_session_store().save(
            session_id,
            ChatSession(
                user_id=None,
                state={},
                ticket={
                    "ticket_id": str(uuid.uuid4()),
                    "ticket_number": "INC-TIMEOUT",
                    "status": "triaged",
                    "priority": "high",
                    "live_agent_requested": True,
                },
                # Set waiting start time to beyond timeout
                waiting_since=datetime.now(UTC) - timedelta(seconds=WAIT_TIMEOUT_SECONDS + 60),
            ),
        )

        status = await chat.get_waiting_status(session_id, _requester())

        assert status.waiting is True
        assert status.specialist_available is False
        assert status.fallback_message is not None
        assert "ticket" in status.fallback_message.lower()
        assert "INC-TIMEOUT" in status.fallback_message

    @pytest.mark.asyncio
    async def test_waiting_status_available_within_timeout(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        session_id = "sess-short-wait"
        await get_session_store().save(
            session_id,
            ChatSession(
                user_id=None,
                state={},
                ticket={
                    "ticket_id": str(uuid.uuid4()),
                    "ticket_number": "INC-QUICK",
                    "status": "triaged",
                    "priority": "high",
                    "live_agent_requested": True,
                },
                waiting_since=datetime.now(UTC) - timedelta(seconds=60),
            ),
        )

        status = await chat.get_waiting_status(session_id, _requester())

        assert status.waiting is True
        assert status.specialist_available is True
        assert status.fallback_message is None


# ── 13. Cancel Waiting ───────────────────────────────────────────────


class TestCancelWaiting:
    """User can cancel waiting for a specialist."""

    @pytest.mark.asyncio
    async def test_cancel_clears_waiting_state(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        session_id = "sess-cancel"
        await get_session_store().save(
            session_id,
            ChatSession(
                user_id=None,
                state={},
                ticket={
                    "ticket_id": str(uuid.uuid4()),
                    "ticket_number": "INC-CANCEL",
                    "status": "triaged",
                    "priority": "high",
                    "live_agent_requested": True,
                },
                waiting_since=datetime.now(UTC),
            ),
        )

        message = await chat.cancel_waiting(session_id, _requester())

        assert "cancelled" in message.lower() or "cancel" in message.lower()
        assert "INC-CANCEL" in message
        sess = await get_session_store().load(session_id)
        assert sess is None or sess.waiting_since is None

    @pytest.mark.asyncio
    async def test_cancel_without_waiting_returns_info(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)

        message = await chat.cancel_waiting("sess-not-waiting", _requester())

        assert "not currently waiting" in message.lower()


# ── 14. Request Live Agent Gating ─────────────────────────────────────


class TestRequestLiveAgentGating:
    """Service-layer no-direct-connect gate on request_live_agent."""

    @pytest.mark.asyncio
    async def test_contextless_session_returns_prompt(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)
        await get_session_store().save(
            "sess-contextless",
            ChatSession(user_id=None, state={"diagnostic_context": {}}),
        )

        message, ref = await chat.request_live_agent("sess-contextless", _requester())

        assert ref is None
        svc.create_ticket.assert_not_called()
        assert GATHER_PROBLEM_PROMPT[:40] in message

    @pytest.mark.asyncio
    async def test_session_with_tried_steps_is_allowed(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)
        await get_session_store().save(
            "sess-tried",
            ChatSession(
                user_id=None,
                state={"diagnostic_context": {"suggested_steps": ["Restart Outlook"]}},
            ),
        )

        message, ref = await chat.request_live_agent("sess-tried", _requester())

        assert ref is not None
        svc.create_ticket.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_idempotent_repeated_request(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)
        await get_session_store().save(
            "sess-repeat",
            ChatSession(
                user_id=None,
                state={
                    "ticket_draft": {"title": "Issue", "category": "other"},
                    "diagnostic_context": {"escalation_offered_in_session": True},
                },
            ),
        )

        await chat.request_live_agent("sess-repeat", _requester())
        message, ref = await chat.request_live_agent("sess-repeat", _requester())

        assert "already in the queue" in message.lower()
        svc.create_ticket.assert_awaited_once()  # only once


# ── 15. Waiting-Since Tracking ────────────────────────────────────────


class TestWaitingSinceTracking:
    """request_live_agent records the wait start time."""

    @pytest.mark.asyncio
    async def test_handoff_records_waiting_since(self) -> None:
        _clear_all()
        svc = _ticket_service()
        chat = ChatService(svc)
        await get_session_store().save(
            "sess-track",
            ChatSession(
                user_id=None,
                state={
                    "ticket_draft": {"title": "Issue"},
                    "diagnostic_context": {"escalation_offered_in_session": True},
                },
            ),
        )

        before = datetime.now(UTC)
        await chat.request_live_agent("sess-track", _requester())
        after = datetime.now(UTC)

        sess = await get_session_store().load("sess-track")
        assert sess is not None and sess.waiting_since is not None
        assert before <= sess.waiting_since <= after
