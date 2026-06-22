"""Tests for human-like conversation behaviour in the triage node.

Covers: greeting, confirm-understanding-before-solving, topic-shift reset, and
the denial → re-clarify path. LLM is patched unavailable so the deterministic
keyword path is exercised.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.services.agents.diagnostic_state import DiagnosticContext
from app.workflows.nodes.triage import triage_node


@contextmanager
def _no_llm():
    patches = [
        patch("app.workflows.nodes.triage.get_llm_service"),
        patch("app.services.agents.diagnostic_engine.get_llm_service"),
    ]
    mocks = [p.start() for p in patches]
    for m in mocks:
        inst = AsyncMock()
        inst.is_available = False
        m.return_value = inst
    try:
        yield
    finally:
        for p in patches:
            p.stop()


class TestGreeting:
    @pytest.mark.asyncio
    async def test_greeting_is_welcomed_not_triaged(self):
        with _no_llm():
            result = await triage_node({
                "messages": [HumanMessage(content="Hi")],
                "session_id": "g1",
                "diagnostic_context": None,
            })
        assert result["needs_clarification"] is True
        assert result["issue_category"] is None
        assert result["conversation_phase"] == "intake"
        # It should invite the issue, not ask "which system is affected?"
        assert "help" in result["clarification_question"].lower()

    @pytest.mark.asyncio
    async def test_greeting_variants(self):
        for greeting in ["hello", "hey there", "good morning"]:
            with _no_llm():
                result = await triage_node({
                    "messages": [HumanMessage(content=greeting)],
                    "session_id": "g",
                    "diagnostic_context": None,
                })
            assert result["issue_category"] is None, greeting


class TestConfirmUnderstanding:
    @pytest.mark.asyncio
    async def test_asks_to_confirm_before_solving(self):
        prior = DiagnosticContext(
            issue_category="email/outlook",
            normalized_system="outlook",
            entity_confidence=0.9,
            affected_system="Microsoft Outlook",
        )
        with _no_llm():
            result = await triage_node({
                "messages": [
                    HumanMessage(content="outlook issue"),
                    AIMessage(content="what's happening?"),
                    HumanMessage(content="my inbox is full"),
                ],
                "session_id": "c1",
                "issue_category": "email/outlook",
                "diagnostic_context": prior.to_dict(),
                "conversation_phase": "clarifying",
            })
        assert result["needs_clarification"] is True
        assert result["diagnostic_context"]["awaiting_confirmation"] is True
        # The confirmation message is now LLM-generated for natural variety.
        # We only assert structural invariants: it must be a question (contains
        # a question-like phrase or ends with "?") and reference the issue.
        q = result["clarification_question"].lower()
        is_question = (
            "?" in q
            or any(p in q for p in (
                "is that right", "have i got that", "does that match",
                "is that the gist", "have i understood", "got that right",
                "sound right", "sound correct", "is that correct", "confirm",
                "did i get that", "does that sound", "is that what",
                "am i on the right track", "do i have that right",
            ))
        )
        assert is_question, f"Expected a confirmation question, got: {q!r}"
        # Must reference the issue in some way (mailbox/full/inbox/email)
        assert any(
            word in q for word in ("mailbox", "full", "inbox", "email", "mail")
        ), f"Expected issue context in confirmation, got: {q!r}"

    @pytest.mark.asyncio
    async def test_affirmation_proceeds_to_solution(self):
        prior = DiagnosticContext(
            issue_category="email/outlook",
            issue_subtype="mailbox-full",
            symptom="mailbox-full",
            subtype_confidence=0.9,
            normalized_system="outlook",
            entity_confidence=0.9,
            awaiting_confirmation=True,
        )
        with _no_llm():
            result = await triage_node({
                "messages": [HumanMessage(content="yes that's right")],
                "session_id": "c2",
                "issue_category": "email/outlook",
                "diagnostic_context": prior.to_dict(),
                "conversation_phase": "clarifying",
            })
        # Proceeds (no clarification) — routing will send this to retrieval.
        assert result["needs_clarification"] is False
        assert result["diagnostic_context"]["understanding_confirmed"] is True

    @pytest.mark.asyncio
    async def test_denial_reclarifies(self):
        prior = DiagnosticContext(
            issue_category="email/outlook",
            issue_subtype="mailbox-full",
            symptom="mailbox-full",
            subtype_confidence=0.9,
            normalized_system="outlook",
            entity_confidence=0.9,
            awaiting_confirmation=True,
        )
        with _no_llm():
            result = await triage_node({
                "messages": [HumanMessage(content="no, that's not it")],
                "session_id": "c3",
                "issue_category": "email/outlook",
                "diagnostic_context": prior.to_dict(),
                "conversation_phase": "clarifying",
            })
        assert result["needs_clarification"] is True
        diag = result["diagnostic_context"]
        assert diag["awaiting_confirmation"] is False
        assert diag["understanding_confirmed"] is False
        # The wrong assumption was dropped.
        assert diag["issue_subtype"] is None


class TestTopicShift:
    @pytest.mark.asyncio
    async def test_switching_system_resets_stale_context(self):
        # Was diagnosing a locked Sixth Sense login; user now switches to Outlook.
        prior = DiagnosticContext(
            issue_category="access/sixth_sense",
            normalized_system="sixth_sense",
            entity_confidence=0.9,
            affected_system="Sixth Sense (Naukri)",
            symptom="login-failure",
            issue_subtype="login-failure",
            subtype_confidence=0.8,
            login_issue_flag=True,
            understanding_confirmed=True,
        )
        with _no_llm():
            result = await triage_node({
                "messages": [HumanMessage(content="I have an issue with outlook")],
                "session_id": "ts1",
                "issue_category": "access/sixth_sense",
                "diagnostic_context": prior.to_dict(),
            })
        diag = result["diagnostic_context"]
        # New system adopted, old login symptom/subtype cleared.
        assert diag["normalized_system"] == "outlook"
        assert diag["issue_category"] == "email/outlook"
        assert diag["symptom"] is None
        assert diag["issue_subtype"] is None
        assert diag["login_issue_flag"] is False
        assert diag["understanding_confirmed"] is False
        # Vague Outlook → should ask what's happening, not answer.
        assert result["needs_clarification"] is True
