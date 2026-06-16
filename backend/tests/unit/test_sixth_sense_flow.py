"""Tests for the Sixth Sense conversation flow — end-to-end triage validation.

These tests simulate the exact failure scenario and verify that the upgraded
triage node handles it correctly:

BEFORE (broken):
  user: "I am having issue with sixthsenses"
  bot: generic "what system?" question
  user: "I am unable to login to sixth senses"
  bot: immediately drafts support ticket as category "other"

AFTER (fixed):
  user: "I am having issue with sixthsenses"
  bot: recognizes Sixth Sense, asks what's specifically happening
  user: "I am unable to login to sixth senses"
  bot: recognizes login issue, retrieves Sixth Sense KB, provides troubleshooting
"""

import pytest
from langchain_core.messages import HumanMessage

from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.playbooks import get_playbook, get_playbook_for_entity
from app.workflows.nodes.triage import (
    _keyword_classify,
    triage_node,
)


class TestSixthSenseTriageFlow:
    """End-to-end triage tests for the Sixth Sense failure scenario."""

    @pytest.mark.asyncio
    async def test_sixthsenses_misspelled_is_recognized(self):
        """Turn 1: 'I am having issue with sixthsenses' should be classified."""
        state = {
            "messages": [HumanMessage(content="I am having issue with sixthsenses")],
            "session_id": "test-ss-001",
            "diagnostic_context": None,
        }
        result = await triage_node(state)

        # Must NOT fall through to "other"
        assert result.get("issue_category") != "other"
        # Should detect Sixth Sense entity
        diag = result.get("diagnostic_context", {})
        assert diag.get("normalized_system") == "sixth_sense"
        # Category should be access/sixth_sense or access/permissions
        assert "access" in result.get("issue_category", "")

    @pytest.mark.asyncio
    async def test_sixth_sense_login_classified_correctly(self):
        """Turn 2: 'I am unable to login to sixth senses' with existing context."""
        # Simulate turn 2 where diagnostic context already has entity info
        existing_ctx = DiagnosticContext(
            normalized_system="sixth_sense",
            issue_category="access/sixth_sense",
            entity_confidence=0.9,
            affected_system="Sixth Sense (Naukri)",
            raw_system_mention="sixthsenses",
        )
        state = {
            "messages": [
                HumanMessage(content="I am having issue with sixthsenses"),
                HumanMessage(content="I am unable to login to sixth senses"),
            ],
            "session_id": "test-ss-002",
            "diagnostic_context": existing_ctx.to_dict(),
            "issue_category": "access/sixth_sense",
        }
        result = await triage_node(state)

        diag = result.get("diagnostic_context", {})
        # Must detect login intent
        assert diag.get("login_issue_flag") is True
        # Must NOT immediately escalate (should clarify or proceed to retrieval)
        assert result.get("issue_category") != "other"

    @pytest.mark.asyncio
    async def test_triage_does_not_jump_to_escalation(self):
        """The bot should NOT jump to ticket creation after first symptom."""
        state = {
            "messages": [
                HumanMessage(content="I am unable to login to sixth senses"),
            ],
            "session_id": "test-ss-003",
            "diagnostic_context": None,
        }
        result = await triage_node(state)

        # Should either ask clarification OR proceed to retrieval — NOT escalate
        diag = result.get("diagnostic_context", {})
        assert diag.get("normalized_system") == "sixth_sense"
        assert diag.get("login_issue_flag") is True
        # The category must be access-related, not "other"
        assert "access" in result.get("issue_category", "")


class TestKeywordClassifyWithEntity:
    """Tests for keyword classification with entity normalization."""

    def test_sixthsenses_keyword_classify(self):
        """Keyword classifier must now detect Sixth Sense entity."""
        diag_ctx = DiagnosticContext()
        result = _keyword_classify("I am having issue with sixthsenses", diag_ctx)
        # Must NOT return "other"
        assert result["category"] != "other"
        assert "access" in result["category"]

    def test_sixth_sense_login_keyword_classify(self):
        """Login + Sixth Sense should classify as access issue."""
        diag_ctx = DiagnosticContext()
        result = _keyword_classify("I am unable to login to sixth senses", diag_ctx)
        assert "access" in result["category"]
        assert result["has_specific_symptom"] is True

    def test_outlook_still_works(self):
        """Existing Outlook classification should not break."""
        diag_ctx = DiagnosticContext()
        result = _keyword_classify("My Outlook is crashing", diag_ctx)
        assert result["category"] == "email/outlook"

    def test_unknown_system_falls_to_other(self):
        """Unknown systems should still fall to 'other'."""
        diag_ctx = DiagnosticContext()
        result = _keyword_classify("something is broken", diag_ctx)
        assert result["category"] == "other"


class TestPlaybookRouting:
    """Tests that entities route to the correct playbooks."""

    def test_sixth_sense_has_playbook(self):
        playbook = get_playbook_for_entity("sixth_sense")
        assert playbook is not None
        assert playbook.category == "access/sixth_sense"
        assert "login-failure" in playbook.subtypes
        assert "account-locked" in playbook.subtypes

    def test_outlook_has_playbook(self):
        playbook = get_playbook_for_entity("outlook")
        assert playbook is not None
        assert playbook.category == "email/outlook"

    def test_unknown_entity_has_no_playbook(self):
        playbook = get_playbook_for_entity("unknown_system")
        assert playbook is None

    def test_sixth_sense_playbook_has_login_questions(self):
        """Sixth Sense playbook must have login-specific diagnostic questions."""
        playbook = get_playbook("access/sixth_sense")
        assert playbook is not None
        symptoms = [opt.value for q in playbook.questions for opt in q.options]
        assert "login-failure" in symptoms
        assert "account-locked" in symptoms
        assert "otp-issue" in symptoms

    def test_sixth_sense_playbook_retrieval_terms(self):
        """Playbook must have Sixth Sense-specific retrieval boost terms."""
        playbook = get_playbook("access/sixth_sense")
        assert "sixth sense" in playbook.retrieval_boost_terms
        assert "naukri" in playbook.retrieval_boost_terms
        assert "locked" in playbook.retrieval_boost_terms


class TestConversationStatePersistence:
    """Tests that diagnostic context survives across turns."""

    def test_diagnostic_context_round_trip(self):
        """Context serialization/deserialization must preserve entity info."""
        ctx = DiagnosticContext(
            normalized_system="sixth_sense",
            raw_system_mention="sixthsenses",
            entity_confidence=0.85,
            issue_category="access/sixth_sense",
            login_issue_flag=True,
            blocked_account_flag="yes",
            otp_issue_flag=True,
        )
        data = ctx.to_dict()
        restored = DiagnosticContext.from_dict(data)

        assert restored.normalized_system == "sixth_sense"
        assert restored.raw_system_mention == "sixthsenses"
        assert restored.entity_confidence == 0.85
        assert restored.login_issue_flag is True
        assert restored.blocked_account_flag == "yes"
        assert restored.otp_issue_flag is True

    def test_has_enough_context_with_entity_login(self):
        """Entity + login flag should be enough context for retrieval."""
        ctx = DiagnosticContext(
            normalized_system="sixth_sense",
            issue_category="access/sixth_sense",
            login_issue_flag=True,
        )
        assert ctx.has_enough_context() is True

    def test_entity_only_is_not_enough(self):
        """Entity alone without intent flags is not enough."""
        ctx = DiagnosticContext(
            normalized_system="sixth_sense",
            issue_category="access/sixth_sense",
        )
        # No symptom, no login flag, no error — should NOT be enough
        assert ctx.has_enough_context() is False


class TestTopicShiftHandling:
    """Tests for topic shift detection."""

    @pytest.mark.asyncio
    async def test_context_preserved_between_turns(self):
        """Diagnostic context should persist when continuing the same issue."""
        # Turn 1: identify the system
        ctx = DiagnosticContext(
            normalized_system="sixth_sense",
            issue_category="access/sixth_sense",
            entity_confidence=0.9,
        )
        state = {
            "messages": [
                HumanMessage(content="I am unable to login to sixth sense"),
            ],
            "session_id": "test-topic-001",
            "diagnostic_context": ctx.to_dict(),
            "issue_category": "access/sixth_sense",
        }
        result = await triage_node(state)

        # Entity should still be recognized
        diag = result.get("diagnostic_context", {})
        assert diag.get("normalized_system") == "sixth_sense"
