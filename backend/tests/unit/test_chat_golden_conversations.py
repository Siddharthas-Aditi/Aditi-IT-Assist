"""Golden conversations — end-to-end behavioral tests for the chat workflow.

Each test simulates a realistic multi-turn exchange and asserts the workflow
takes the right *navigational* decisions: when to ticket, when to reset, when
to escalate, when to close warmly. They complement the unit tests for
individual nodes (which test the parts) by exercising the whole graph (the
whole).

The most important test here is :class:`TestMailboxFullThenAnotherProblem`,
which pins the original bug: typing "I have another problem" after a resolved
mailbox-full flow MUST NOT create a ticket.

These tests use the in-memory ChatService — no DB, no LLM. The workflow falls
back to keyword classification, which is enough for routing assertions.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from app.services.agents.chat_service import ChatService
from app.services.agents.intent_classifier import (
    ConversationIntent,
    classify_intent,
)
from app.services.agents.session_store import (
    ChatSession,
    InMemorySessionStore,
    set_session_store,
)

# ── Test helpers ────────────────────────────────────────────────────────────


def _fake_ticket(number: str = "INC-TEST-001") -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.ticket_number = number
    t.status = "triaged"
    t.priority = "high"
    return t


def _mock_ticket_service() -> MagicMock:
    svc = MagicMock()
    svc.create_ticket = AsyncMock(return_value=_fake_ticket())
    svc.request_live_agent = AsyncMock()
    svc.db = MagicMock()
    svc.db.commit = AsyncMock()
    return svc


def _requester() -> MagicMock:
    return MagicMock(id=uuid.uuid4(), full_name="Test Employee", email="emp@aditi.com")


def _clear_state() -> None:
    set_session_store(InMemorySessionStore())


# ── Intent-classifier-level guards (cheap & fast) ──────────────────────────


class TestIntentGuardsTheBug:
    """Reproducer-level tests — these pin the original failure mode.

    They run the classifier directly with the exact transcript phrase that
    triggered ITA-000007 ("I have an another problem") and prove the
    classifier now reports NEW_TOPIC, not anything that would create a ticket.
    """

    def test_another_problem_is_new_topic_not_confirm(self) -> None:
        result = classify_intent(
            "I have an another problem",
            has_active_issue=True,
            awaiting_confirmation=True,  # the worst-case context
            steps_given=True,
        )
        assert result.intent is ConversationIntent.NEW_TOPIC

    def test_another_problem_is_not_an_escalate_request(self) -> None:
        result = classify_intent(
            "I have an another problem",
            has_active_issue=True,
            awaiting_confirmation=True,
            steps_given=True,
        )
        assert result.intent is not ConversationIntent.ESCALATE_REQUEST

    def test_help_word_inside_unrelated_sentence_is_not_escalate(self) -> None:
        """The pre-fix bug: any message containing 'help' as a substring was
        considered escalation. With whole-word matching, only explicit help
        requests should trigger escalation."""
        result = classify_intent("I helped myself by checking the spam folder")
        assert result.intent is not ConversationIntent.ESCALATE_REQUEST


# ── Service-level: the ticket guard is the last line of defense ───────────


class TestServiceTicketGuard:
    """Even when workflow flags say 'confirmed', the service-layer intent guard
    must refuse a ticket if the user's actual message wasn't an escalation.

    This is the belt-and-suspenders guarantee that ITA-000007-style bugs
    cannot recur even if a future workflow change accidentally flips
    ``escalation_confirmed`` for the wrong reason.
    """

    @pytest.mark.asyncio
    async def test_ticket_blocked_when_user_message_is_new_topic(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        # Simulate the failure mode: upstream wrongly set escalation_confirmed
        # but the user's last message was "I have another problem".
        result = {
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": {
                "title": "IT Issue",
                "description": "...",
                "category": "email/outlook",
                "priority": "medium",
            },
            "session_id": "sess-bug",
            "messages": [HumanMessage(content="I have an another problem")],
        }
        session = ChatSession(user_id=None, state={"session_id": "sess-bug"})
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is None, "intent guard must refuse the ticket for NEW_TOPIC messages"
        svc.create_ticket.assert_not_called()

    @pytest.mark.asyncio
    async def test_ticket_allowed_when_user_explicitly_asks_for_human(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        result = {
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": {
                "title": "IT Issue",
                "description": "...",
                "category": "email/outlook",
                "priority": "medium",
            },
            "session_id": "sess-ok",
            "messages": [HumanMessage(content="please connect me with a specialist")],
        }
        session = ChatSession(user_id=None, state={"session_id": "sess-ok"})
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is not None
        svc.create_ticket.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ticket_allowed_for_yes_after_offer(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        result = {
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": {
                "title": "IT Issue",
                "description": "...",
                "category": "email/outlook",
                "priority": "medium",
            },
            "session_id": "sess-yes",
            "messages": [HumanMessage(content="yes please")],
        }
        session = ChatSession(user_id=None, state={"session_id": "sess-yes"})
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is not None
        svc.create_ticket.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ticket_blocked_for_gratitude_message(self) -> None:
        """A pure 'thanks' must never spawn a ticket."""
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        result = {
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": {
                "title": "x",
                "description": "...",
                "category": "other",
                "priority": "low",
            },
            "session_id": "sess-thx",
            "messages": [HumanMessage(content="thanks so much, that worked")],
        }
        session = ChatSession(user_id=None, state={"session_id": "sess-thx"})
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is None
        svc.create_ticket.assert_not_called()


# ── End-to-end workflow: the full transcript from the bug report ──────────


class TestMailboxFullThenAnotherProblem:
    """The exact failing transcript from the user's bug report.

    Flow:
      1. User: "Hi, mailbox is full"
      2. Bot:  "...is that right?"  (awaiting confirmation)
      3. User: "yes"
      4. Bot:  troubleshooting steps
      5. User: "I have an another problem"   ← the bug
      6. Bot:  MUST NOT create a ticket. MUST ask what the new issue is.
    """

    @pytest.mark.asyncio
    async def test_new_topic_after_resolution_does_not_ticket(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)
        requester = _requester()
        session_id = "golden-bug"

        # Turn 1 — user states the problem.
        await chat.process_message(
            session_id=session_id,
            user_message="Hi, mailbox is full",
            user_id="u-1",
            user_name=requester.full_name,
            user_email=requester.email,
            requester=requester,
        )

        # Turn 2 — user confirms understanding.
        await chat.process_message(
            session_id=session_id,
            user_message="yes",
            user_id="u-1",
            user_name=requester.full_name,
            user_email=requester.email,
            requester=requester,
        )

        # Turn 3 — user switches topics ← the bug-trigger.
        response = await chat.process_message(
            session_id=session_id,
            user_message="I have an another problem",
            user_id="u-1",
            user_name=requester.full_name,
            user_email=requester.email,
            requester=requester,
        )

        # The headline assertion: NO TICKET WAS CREATED.
        assert response.ticket is None, (
            "Switching topics must not create a ticket — "
            "this is the regression guard for ITA-000007."
        )
        # The TicketService must not have been called at all.
        svc.create_ticket.assert_not_called()

        # The bot should ask what the new problem is, not say "I've created a ticket".
        assert "ticket" not in response.content.lower() or "created" not in response.content.lower()


# ── End-to-end workflow: explicit human request DOES ticket ───────────────


class TestExplicitEscalationCreatesTicket:
    """Companion to the bug test — when the user actually asks for a human,
    we MUST create a ticket (otherwise we've over-corrected the fix)."""

    @pytest.mark.asyncio
    async def test_connect_me_with_specialist_creates_ticket(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)
        requester = _requester()
        session_id = "golden-escalate"

        # Establish a context the user can escalate from.
        await chat.process_message(
            session_id=session_id,
            user_message="My VPN keeps disconnecting",
            user_id="u-1",
            user_name=requester.full_name,
            user_email=requester.email,
            requester=requester,
        )

        response = await chat.process_message(
            session_id=session_id,
            user_message="please connect me with a specialist",
            user_id="u-1",
            user_name=requester.full_name,
            user_email=requester.email,
            requester=requester,
        )

        assert response.ticket is not None, "Explicit escalation request must produce a ticket."
        svc.create_ticket.assert_awaited()


# ── End-to-end workflow: gratitude closes warmly without ticket ───────────


class TestConfirmUnderstandingDoesNotEscalate:
    """The ITA-000006 regression.

    "yes correct" answers a confirm-understanding question; it must NOT be
    treated as escalation consent. A ticket may only be created when an
    escalation OFFER was already made in a prior turn.
    """

    @pytest.mark.asyncio
    async def test_yes_correct_without_prior_offer_blocks_ticket(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        # Simulate the failure mode: workflow flipped escalation_confirmed=True
        # for the wrong reason (e.g. KB empty → escalate → CONFIRM misread).
        # The diagnostic context shows escalation was NEVER offered before.
        result = {
            "session_id": "sess-A",
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": False,  # nothing was offered yet
            "ticket_draft": {
                "title": "Network issue",
                "description": "...",
                "category": "network/connectivity",
                "priority": "high",
            },
            "messages": [HumanMessage(content="yes correct")],
            "diagnostic_context": {
                # critical: no prior offer in this session
                "escalation_offered_in_session": False,
                "live_agent_requested": False,
                "issue_category": "network/connectivity",
            },
        }
        session = ChatSession(user_id=None, state={"session_id": "sess-A"})
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is None, "CONFIRM without a prior offer must NOT create a ticket"
        svc.create_ticket.assert_not_called()

    @pytest.mark.asyncio
    async def test_yes_after_explicit_offer_creates_ticket(self) -> None:
        """Once we've offered, a 'yes' from the user IS consent."""
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        result = {
            "session_id": "sess-B",
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "ticket_draft": {
                "title": "Network issue",
                "description": "...",
                "category": "network/connectivity",
                "priority": "high",
            },
            "messages": [HumanMessage(content="yes please")],
            "diagnostic_context": {
                "escalation_offered_in_session": True,
                "issue_category": "network/connectivity",
            },
        }
        session = ChatSession(user_id=None, state={"session_id": "sess-B"})
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is not None
        svc.create_ticket.assert_awaited_once()


class TestTicketBannerDoesNotHijackSubsequentTurns:
    """The second ITA-000006 regression.

    Once a ticket exists for a session, subsequent turns must NOT have their
    replies overwritten by the "ticket created" banner. The cache is for
    idempotency on re-clicks, not a permanent overlay.
    """

    @pytest.mark.asyncio
    async def test_subsequent_turn_returns_no_ticket_overlay(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        # Pre-populate the session as if a ticket was created earlier this session.
        session = ChatSession(
            user_id=None,
            state={"session_id": "sess-existing"},
            ticket={
                "ticket_id": str(uuid.uuid4()),
                "ticket_number": "ITA-000099",
                "status": "triaged",
                "priority": "high",
                "live_agent_requested": True,
            },
        )

        # The user now asks a NEW question. The workflow is NOT escalating.
        result = {
            "session_id": "sess-existing",
            "should_escalate": False,
            "escalation_confirmed": False,
            "ticket_offered": False,
            "messages": [HumanMessage(content="My mailbox is full")],
            "diagnostic_context": {"live_agent_requested": False},
        }
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is None, "Without escalation this turn, the cached ticket must not re-surface"

    @pytest.mark.asyncio
    async def test_reclick_connect_with_specialist_returns_same_ticket(self) -> None:
        """Idempotency: explicit re-escalation returns the SAME ticket."""
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)

        ticket_id = str(uuid.uuid4())
        session = ChatSession(
            user_id=None,
            state={"session_id": "sess-reclick"},
            ticket={
                "ticket_id": ticket_id,
                "ticket_number": "ITA-000100",
                "status": "triaged",
                "priority": "high",
                "live_agent_requested": True,
            },
        )

        result = {
            "session_id": "sess-reclick",
            "should_escalate": True,
            "escalation_confirmed": True,
            "ticket_offered": True,
            "messages": [HumanMessage(content="connect me with a specialist")],
            "diagnostic_context": {
                "live_agent_requested": True,
                "escalation_offered_in_session": True,
            },
        }
        ref = await chat._handle_ticketing(session, result, _requester())
        assert ref is not None
        assert ref.ticket_number == "ITA-000100"
        svc.create_ticket.assert_not_called()  # no duplicate created


class TestLLMNewTopicGuard:
    """Regression: an LLM that returns NEW_TOPIC on a fresh session must be
    overruled. NEW_TOPIC is only valid when has_active_issue=True.

    This is the structural validity guard in :func:`classify_intent_with_llm`.
    The user-visible bug was: the very first turn — "I need help with outlook,
    my mailbox is full and I am unable to get new mail" — was being treated
    as a topic switch because the LLM pattern-matched on the word "mailbox is
    full" in our own prompt examples.
    """

    @pytest.mark.asyncio
    async def test_first_turn_problem_description_is_not_new_topic(self) -> None:
        from unittest.mock import patch

        from app.services.agents.llm_intent import classify_intent_with_llm

        # Stub the LLM service to return NEW_TOPIC with high confidence — the
        # worst case we're guarding against. The wrapper must demote it.
        class _StubLLM:
            is_available = True

            async def complete_json(self, *_args, **_kwargs):
                return {
                    "intent": "new_topic",
                    "confidence": 0.95,
                    "rationale": "pattern matched on 'mailbox is full'",
                    "slot_hints": {},
                }

        with patch(
            "app.services.agents.llm_intent.get_llm_service",
            return_value=_StubLLM(),
        ):
            result = await classify_intent_with_llm(
                "I need help with outlook, my mailbox is full and I am unable to get new mail",
                has_active_issue=False,  # fresh session — the guard's trigger
                awaiting_confirmation=False,
                steps_given=False,
                issue_resolved=False,
                llm=_StubLLM(),
            )

        assert result.intent is ConversationIntent.CONTINUE, (
            "LLM NEW_TOPIC on a fresh session must be structurally rejected"
        )
        assert "llm-invalid-newtopic-without-active-issue" in result.matched


class TestGratitudeClosesWithoutTicket:
    @pytest.mark.asyncio
    async def test_thanks_after_steps_does_not_ticket(self) -> None:
        _clear_state()
        svc = _mock_ticket_service()
        chat = ChatService(svc)
        requester = _requester()
        session_id = "golden-thanks"

        await chat.process_message(
            session_id=session_id,
            user_message="My Outlook is slow",
            user_id="u-1",
            user_name=requester.full_name,
            user_email=requester.email,
            requester=requester,
        )

        response = await chat.process_message(
            session_id=session_id,
            user_message="thanks so much, that worked",
            user_id="u-1",
            user_name=requester.full_name,
            user_email=requester.email,
            requester=requester,
        )

        assert response.ticket is None
        svc.create_ticket.assert_not_called()
