"""Tests for the multi-turn diagnostic conversation architecture.

These tests validate that the upgraded chat experience:
1. Detects vague queries and asks follow-up questions
2. Correctly fills diagnostic slots from user responses
3. Narrows retrieval after clarification
4. Escalates appropriately
5. Preserves context across turns
"""

import pytest

from app.services.agents.diagnostic_state import DiagnosticContext, DiagnosticPhase
from app.services.agents.diagnostic_engine import (
    evaluate_clarify_or_answer,
    update_context_from_extraction,
    _pattern_extract_slots,
)
from app.services.agents.playbooks import (
    get_playbook,
    OUTLOOK_PLAYBOOK,
    ZOOM_PLAYBOOK,
    INTUNE_PLAYBOOK,
)


# ══════════════════════════════════════════════════════════════════════
#  DIAGNOSTIC STATE TESTS
# ══════════════════════════════════════════════════════════════════════


class TestDiagnosticContext:
    """Tests for DiagnosticContext slot management."""

    def test_empty_context_has_no_enough_context(self):
        ctx = DiagnosticContext()
        assert not ctx.has_enough_context()

    def test_category_only_is_not_enough(self):
        ctx = DiagnosticContext(issue_category="email/outlook")
        assert not ctx.has_enough_context()

    def test_category_plus_symptom_is_enough(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            symptom="not-receiving-emails",
        )
        assert ctx.has_enough_context()

    def test_category_plus_problem_statement_is_enough(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            exact_problem_statement="My Outlook stopped syncing emails since yesterday",
        )
        assert ctx.has_enough_context()

    def test_should_clarify_when_not_enough_context(self):
        ctx = DiagnosticContext(issue_category="email/outlook")
        assert ctx.should_clarify()

    def test_should_not_clarify_when_enough_context(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            symptom="not-receiving-emails",
        )
        assert not ctx.should_clarify()

    def test_should_not_clarify_after_max_clarifications(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            clarification_count=3,
            max_clarifications=3,
        )
        assert not ctx.should_clarify()

    def test_should_escalate_when_live_agent_requested(self):
        ctx = DiagnosticContext(live_agent_requested=True)
        assert ctx.should_escalate()

    def test_should_escalate_after_failed_resolution(self):
        ctx = DiagnosticContext(
            resolution_attempts=2,
            resolution_confidence=0.3,
        )
        assert ctx.should_escalate()

    def test_should_not_escalate_with_good_resolution(self):
        ctx = DiagnosticContext(
            resolution_attempts=1,
            resolution_confidence=0.8,
        )
        assert not ctx.should_escalate()

    def test_retrieval_query_builds_from_context(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            symptom="not-receiving-emails",
            error_message="mailbox unavailable",
        )
        query = ctx.get_retrieval_query()
        assert "email/outlook" in query
        assert "not-receiving-emails" in query
        assert "mailbox unavailable" in query

    def test_serialization_roundtrip(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            symptom="not-receiving-emails",
            phase=DiagnosticPhase.CLARIFYING,
            clarification_count=2,
        )
        data = ctx.to_dict()
        restored = DiagnosticContext.from_dict(data)
        assert restored.issue_category == "email/outlook"
        assert restored.symptom == "not-receiving-emails"
        assert restored.phase == DiagnosticPhase.CLARIFYING
        assert restored.clarification_count == 2


# ══════════════════════════════════════════════════════════════════════
#  CLARIFY-OR-ANSWER POLICY TESTS
# ══════════════════════════════════════════════════════════════════════


class TestClarifyOrAnswerPolicy:
    """Tests for the clarify-or-answer decision engine."""

    def test_vague_outlook_triggers_clarification(self):
        """'I have an Outlook issue' should ask follow-up, not dump KB."""
        ctx = DiagnosticContext(issue_category="email/outlook")
        decision = evaluate_clarify_or_answer(ctx)
        assert decision.should_clarify
        assert decision.question is not None
        assert len(decision.options) > 0

    def test_specific_outlook_issue_proceeds_to_answer(self):
        """'Outlook is not receiving emails' should NOT ask follow-up."""
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            symptom="not-receiving-emails",
        )
        decision = evaluate_clarify_or_answer(ctx)
        assert not decision.should_clarify

    def test_vague_zoom_triggers_clarification(self):
        ctx = DiagnosticContext(issue_category="video-conferencing/zoom")
        decision = evaluate_clarify_or_answer(ctx)
        assert decision.should_clarify
        # Should offer options like audio, video, can't join
        labels = [o.label for o in decision.options]
        assert any("audio" in l.lower() or "hear" in l.lower() for l in labels)

    def test_live_agent_request_skips_clarification(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            live_agent_requested=True,
        )
        decision = evaluate_clarify_or_answer(ctx)
        assert not decision.should_clarify
        assert decision.reason == "user_requested_agent"

    def test_max_clarifications_proceeds_anyway(self):
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            clarification_count=3,
            max_clarifications=3,
        )
        decision = evaluate_clarify_or_answer(ctx)
        assert not decision.should_clarify
        assert decision.reason == "max_clarifications_reached"


# ══════════════════════════════════════════════════════════════════════
#  SLOT EXTRACTION TESTS
# ══════════════════════════════════════════════════════════════════════


class TestSlotExtraction:
    """Tests for pattern-based slot extraction."""

    def test_detects_live_agent_request(self):
        result = _pattern_extract_slots("I want to talk to a human please", "email/outlook")
        assert result.get("live_agent_requested") is True

    def test_detects_platform_windows(self):
        result = _pattern_extract_slots("I'm on Windows 11", "email/outlook")
        assert result.get("platform_os") == "Windows"

    def test_detects_platform_mac(self):
        result = _pattern_extract_slots("Using my MacBook Pro", "email/outlook")
        assert result.get("platform_os") == "Mac"

    def test_detects_device_type(self):
        result = _pattern_extract_slots("It's happening on my laptop", "email/outlook")
        assert result.get("device_type") == "laptop"

    def test_extracts_symptom_from_keywords(self):
        result = _pattern_extract_slots("I'm not receiving any emails since morning", "email/outlook")
        assert result.get("symptom") == "not-receiving-emails"

    def test_extracts_option_selection(self):
        """When user clicks a quick-reply chip, it should map to the correct slot."""
        result = _pattern_extract_slots("Not receiving emails", "email/outlook")
        assert result.get("symptom") == "not-receiving-emails"

    def test_extracts_zoom_audio_symptom(self):
        result = _pattern_extract_slots("I can't hear anything in Zoom", "video-conferencing/zoom")
        assert result.get("symptom") == "no-audio"


# ══════════════════════════════════════════════════════════════════════
#  PLAYBOOK TESTS
# ══════════════════════════════════════════════════════════════════════


class TestPlaybooks:
    """Tests for issue-specific playbook behavior."""

    def test_outlook_playbook_requires_symptom(self):
        assert "symptom" in OUTLOOK_PLAYBOOK.required_slots

    def test_outlook_playbook_first_question_asks_symptom(self):
        question = OUTLOOK_PLAYBOOK.get_next_question({}, 0)
        assert question is not None
        assert question.slot == "symptom"
        assert len(question.options) > 0

    def test_outlook_playbook_skips_when_symptom_filled(self):
        filled = {"symptom": "not-receiving-emails"}
        assert OUTLOOK_PLAYBOOK.has_enough_context(filled)

    def test_zoom_playbook_has_audio_video_options(self):
        question = ZOOM_PLAYBOOK.get_next_question({}, 0)
        assert question is not None
        values = [o.value for o in question.options]
        assert "no-audio" in values
        assert "no-video" in values

    def test_intune_playbook_has_compliance_options(self):
        question = INTUNE_PLAYBOOK.get_next_question({}, 0)
        assert question is not None
        values = [o.value for o in question.options]
        assert "non-compliant" in values

    def test_get_playbook_returns_correct_one(self):
        pb = get_playbook("email/outlook")
        assert pb.category == "email/outlook"

    def test_get_playbook_falls_back_to_other(self):
        pb = get_playbook("unknown/category")
        assert pb.category == "other"


# ══════════════════════════════════════════════════════════════════════
#  CONTEXT UPDATE TESTS
# ══════════════════════════════════════════════════════════════════════


class TestContextUpdate:
    """Tests for updating diagnostic context from extraction results."""

    def test_updates_symptom(self):
        ctx = DiagnosticContext(issue_category="email/outlook")
        ctx = update_context_from_extraction(ctx, {"symptom": "not-receiving-emails"})
        assert ctx.symptom == "not-receiving-emails"
        assert ctx.issue_subcategory == "not-receiving-emails"

    def test_appends_steps_tried(self):
        ctx = DiagnosticContext(steps_already_tried=["restart outlook"])
        ctx = update_context_from_extraction(
            ctx, {"steps_already_tried": ["cleared cache", "reset profile"]}
        )
        assert len(ctx.steps_already_tried) == 3
        assert "cleared cache" in ctx.steps_already_tried

    def test_sets_live_agent_flag(self):
        ctx = DiagnosticContext()
        ctx = update_context_from_extraction(ctx, {"live_agent_requested": True})
        assert ctx.live_agent_requested is True


# ══════════════════════════════════════════════════════════════════════
#  CONVERSATION FLOW INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════


class TestConversationFlows:
    """End-to-end flow tests for common scenarios."""

    def test_vague_outlook_then_specific_answer(self):
        """Simulates: 'I have an Outlook issue' → clarification → 'not receiving emails' → proceed."""
        # Turn 1: Vague message
        ctx = DiagnosticContext(issue_category="email/outlook")
        decision = evaluate_clarify_or_answer(ctx)
        assert decision.should_clarify

        # Turn 2: User provides specifics
        ctx.clarification_count += 1
        ctx = update_context_from_extraction(ctx, {"symptom": "not-receiving-emails"})
        decision = evaluate_clarify_or_answer(ctx)
        assert not decision.should_clarify
        assert ctx.has_enough_context()

    def test_zoom_clarification_to_resolution(self):
        """Simulates: 'Zoom not working' → clarification → 'no audio' → proceed."""
        ctx = DiagnosticContext(issue_category="video-conferencing/zoom")
        decision = evaluate_clarify_or_answer(ctx)
        assert decision.should_clarify

        ctx.clarification_count += 1
        ctx = update_context_from_extraction(ctx, {"symptom": "no-audio"})
        decision = evaluate_clarify_or_answer(ctx)
        assert not decision.should_clarify

    def test_escalation_after_max_attempts(self):
        """Issue not resolved after multiple attempts should trigger escalation."""
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            symptom="not-receiving-emails",
            resolution_attempts=2,
            resolution_confidence=0.3,
        )
        assert ctx.should_escalate()

    def test_immediate_agent_request(self):
        """User immediately asking for live agent should escalate."""
        ctx = DiagnosticContext(issue_category="email/outlook")
        ctx = update_context_from_extraction(ctx, {"live_agent_requested": True})
        decision = evaluate_clarify_or_answer(ctx)
        assert not decision.should_clarify
        assert ctx.should_escalate()

    def test_specific_message_skips_clarification(self):
        """'My Outlook is not syncing emails' should skip clarification entirely."""
        ctx = DiagnosticContext(
            issue_category="email/outlook",
            symptom="Outlook is not syncing emails",
            exact_problem_statement="My Outlook is not syncing emails",
        )
        decision = evaluate_clarify_or_answer(ctx)
        assert not decision.should_clarify
        assert ctx.has_enough_context()
