"""End-to-end style tests for the Outlook 'mailbox full' failure scenario.

This is the regression suite for the original bug:

    user: "I have an issue with outlook"   -> bot asks a clarifying question
    user: "my inbox is full"               -> classified as mailbox-full,
                                              answered with storage cleanup steps
                                              (Deleted/Junk), NOT password reset,
                                              NOT Windows Update.
    user: "it did not work"                -> advances to NEW steps (no repeat)
    ...repeat until exhausted              -> escalates cleanly.

The retrieval *node* hits the DB, so here we exercise the grounding + resolution
core directly against the real YAML knowledge base (the dev fallback source),
which is exactly where the contamination/repeat bugs lived.
"""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.knowledge_base.loader import get_articles_by_category
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.grounding import ground_results
from app.workflows.nodes.resolution import resolution_node
from app.workflows.nodes.triage import triage_node

PASSWORD_TERMS = ("password", "reset your password")
WINDOWS_TERMS = ("windows update",)
WAIT_TERMS = ("wait 15", "wait 1 hour", "auto-unlock")


def _no_llm(monkeypatch_targets):
    """Helper: patch get_llm_service in given modules to report unavailable."""
    patches = []
    for target in monkeypatch_targets:
        p = patch(target)
        mock_get = p.start()
        mock_llm = AsyncMock()
        mock_llm.is_available = False
        mock_get.return_value = mock_llm
        patches.append(p)
    return patches


def _grounded_mailbox_state():
    """Build resolution-node input grounded on the real mailbox-full article."""
    diag = DiagnosticContext(
        issue_category="email/outlook",
        issue_subtype="mailbox-full",
        symptom="mailbox-full",
        subtype_confidence=0.9,
        exact_problem_statement="my inbox is full",
        normalized_system="outlook",
        entity_confidence=0.9,
    )
    candidates = get_articles_by_category("email/outlook")
    grounded = ground_results(candidates, diag)
    kept = grounded.kept_articles()[:3]
    citations = [{"title": a["title"]} for a in kept]
    state = {
        "session_id": "mbx-1",
        "issue_category": "email/outlook",
        "issue_subtype": "mailbox-full",
        "messages": [HumanMessage(content="my inbox is full")],
        "knowledge_results": kept,
        "knowledge_confidence": 0.9,
        "knowledge_citations": citations,
        "retrieval_trace": grounded.trace(),
        "diagnostic_context": diag.to_dict(),
    }
    return state, diag, grounded


class TestGroundingAgainstRealKB:
    def test_mailbox_article_exists_and_ranks_first(self):
        _, _, grounded = _grounded_mailbox_state()
        kept = [a["id"] for a in grounded.kept_articles()]
        assert kept, "no outlook articles loaded from YAML"
        assert kept[0] == "outlook-mailbox-full"
        assert grounded.has_subtype_match is True


class TestMailboxFullResolution:
    @pytest.mark.asyncio
    async def test_first_response_is_storage_cleanup_not_password(self):
        state, _, _ = _grounded_mailbox_state()
        patches = _no_llm(["app.workflows.nodes.resolution.get_llm_service"])
        try:
            result = await resolution_node(state)
        finally:
            for p in patches:
                p.stop()

        text = _message_text(result).lower()
        steps_text = " ".join(s["instruction"].lower() for s in result["resolution_steps"])
        blob = text + " " + steps_text

        # Must be storage cleanup oriented
        assert "deleted items" in blob or "junk" in blob or "mailbox" in blob
        # Must NOT contain cross-domain advice
        for bad in PASSWORD_TERMS + WINDOWS_TERMS + WAIT_TERMS:
            assert bad not in blob, f"cross-domain advice leaked: {bad}"
        assert result["resolution_confidence"] >= 0.6

    @pytest.mark.asyncio
    async def test_advances_after_failure_no_repeat(self):
        state, diag, _ = _grounded_mailbox_state()
        patches = _no_llm(["app.workflows.nodes.resolution.get_llm_service"])
        try:
            first = await resolution_node(state)
            first_steps = {s["instruction"] for s in first["resolution_steps"]}

            # Simulate triage marking the batch as failed and re-running retrieval.
            diag2 = DiagnosticContext.from_dict(first["diagnostic_context"])
            diag2.mark_last_batch_failed()
            state2 = dict(state)
            state2["diagnostic_context"] = diag2.to_dict()
            second = await resolution_node(state2)
            second_steps = {s["instruction"] for s in second["resolution_steps"]}
        finally:
            for p in patches:
                p.stop()

        assert second_steps, "should still have steps to advance to"
        # The second batch must NOT repeat the first batch.
        assert first_steps.isdisjoint(second_steps), (first_steps, second_steps)

    @pytest.mark.asyncio
    async def test_eventually_escalates_when_exhausted(self):
        state, diag, _ = _grounded_mailbox_state()
        patches = _no_llm(["app.workflows.nodes.resolution.get_llm_service"])
        try:
            cur = dict(state)
            ctx = diag
            escalated = False
            for _ in range(8):  # bounded loop — should exhaust well before this
                res = await resolution_node(cur)
                if not res["resolution_steps"] and res["resolution_confidence"] == 0.0:
                    escalated = True
                    break
                ctx = DiagnosticContext.from_dict(res["diagnostic_context"])
                ctx.mark_last_batch_failed()
                cur = dict(cur)
                cur["diagnostic_context"] = ctx.to_dict()
        finally:
            for p in patches:
                p.stop()

        assert escalated, "resolver should exhaust grounded steps and escalate"


class TestTriageClarifyThenClassify:
    @pytest.mark.asyncio
    async def test_vague_outlook_asks_clarification(self):
        patches = _no_llm(
            [
                "app.workflows.nodes.triage.get_llm_service",
                "app.services.agents.diagnostic_engine.get_llm_service",
            ]
        )
        try:
            result = await triage_node(
                {
                    "messages": [HumanMessage(content="I have an issue with outlook")],
                    "session_id": "t1",
                    "diagnostic_context": None,
                }
            )
        finally:
            for p in patches:
                p.stop()

        assert result["needs_clarification"] is True
        assert result["issue_category"] == "email/outlook"
        assert result.get("issue_subtype") in (None, "")

    @pytest.mark.asyncio
    async def test_inbox_full_classified_as_mailbox_subtype(self):
        patches = _no_llm(
            [
                "app.workflows.nodes.triage.get_llm_service",
                "app.services.agents.diagnostic_engine.get_llm_service",
            ]
        )
        try:
            # Turn 2 with prior Outlook context already established.
            prior = DiagnosticContext(
                issue_category="email/outlook",
                normalized_system="outlook",
                entity_confidence=0.9,
                affected_system="Microsoft Outlook",
            )
            result = await triage_node(
                {
                    "messages": [
                        HumanMessage(content="I have an issue with outlook"),
                        AIMessage(content="What's happening with Outlook?"),
                        HumanMessage(content="my inbox is full"),
                    ],
                    "session_id": "t2",
                    "issue_category": "email/outlook",
                    "diagnostic_context": prior.to_dict(),
                    "conversation_phase": "clarifying",
                }
            )
        finally:
            for p in patches:
                p.stop()

        assert result["issue_subtype"] == "mailbox-full"
        # With a confident subtype the agent now CONFIRMS its understanding before
        # solving (human-like flow): it asks the user to confirm, and the next
        # affirmative turn proceeds to the grounded solution.
        assert result["needs_clarification"] is True
        assert result["diagnostic_context"]["awaiting_confirmation"] is True
        # Confirmation messages are now LLM-generated for natural variety.
        # We check structural invariants: it must be a question and reference
        # the issue (mailbox/inbox/full/email).
        q = result["clarification_question"].lower()
        is_question = "?" in q or any(
            p in q
            for p in (
                "is that right",
                "have i got that",
                "does that match",
                "is that the gist",
                "have i understood",
                "got that right",
                "sound right",
                "sound correct",
                "is that correct",
                "confirm",
                "did i get that",
                "does that sound",
                "is that what",
                "am i on the right track",
                "do i have that right",
            )
        )
        assert is_question, f"Expected a confirmation question, got: {q!r}"
        assert any(word in q for word in ("mailbox", "full", "inbox", "email", "mail")), (
            f"Expected issue context in confirmation, got: {q!r}"
        )

    @pytest.mark.asyncio
    async def test_negative_feedback_marks_failure_and_does_not_reclarify(self):
        patches = _no_llm(
            [
                "app.workflows.nodes.triage.get_llm_service",
                "app.services.agents.diagnostic_engine.get_llm_service",
            ]
        )
        try:
            prior = DiagnosticContext(
                issue_category="email/outlook",
                issue_subtype="mailbox-full",
                symptom="mailbox-full",
                subtype_confidence=0.9,
                normalized_system="outlook",
                entity_confidence=0.9,
                suggested_steps=["Empty the Deleted Items folder"],
            )
            result = await triage_node(
                {
                    "messages": [HumanMessage(content="that didn't work")],
                    "session_id": "t3",
                    "issue_category": "email/outlook",
                    "diagnostic_context": prior.to_dict(),
                    "conversation_phase": "confirming",
                }
            )
        finally:
            for p in patches:
                p.stop()

        diag = result["diagnostic_context"]
        assert diag["last_resolution_failed"] is True
        assert "Empty the Deleted Items folder" in diag["failed_steps"]
        assert result["needs_clarification"] is False


def _message_text(result: dict) -> str:
    for msg in result.get("messages", []):
        if isinstance(msg, AIMessage):
            return msg.content
    return ""
