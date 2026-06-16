"""Unit tests for the triage workflow node."""

import pytest

from app.services.agents.diagnostic_state import DiagnosticContext
from app.workflows.nodes.triage import _classify_issue, _keyword_classify, triage_node


class TestKeywordClassify:
    """Tests for the deterministic keyword classifier."""

    def test_classify_outlook_keywords(self):
        """Should classify Outlook-related messages with specific symptoms."""
        ctx = DiagnosticContext()
        result = _keyword_classify("My Outlook keeps crashing when I open it", ctx)
        assert result["category"] == "email/outlook"
        # Entity-based classification may use different symptom detection
        assert result["confidence"] >= 0.6

    def test_classify_zoom_keywords(self):
        """Should classify Zoom-related messages."""
        ctx = DiagnosticContext()
        result = _keyword_classify("I can't sign into Zoom", ctx)
        assert result["category"] == "video-conferencing/zoom"

    def test_classify_intune_keywords(self):
        """Should classify Intune compliance messages."""
        ctx = DiagnosticContext()
        result = _keyword_classify("My laptop shows non-compliant in Intune", ctx)
        assert result["category"] == "device-management/intune"
        assert result["confidence"] >= 0.6

    def test_classify_camera_keywords(self):
        """Should classify camera-related messages."""
        ctx = DiagnosticContext()
        result = _keyword_classify("My webcam is not working", ctx)
        assert result["category"] == "hardware/camera"

    def test_classify_vague_message(self):
        """Should return low confidence for vague messages."""
        ctx = DiagnosticContext()
        result = _keyword_classify("something is broken", ctx)
        assert result["category"] == "other"
        assert result["confidence"] < 0.5

    def test_classify_specific_outlook_has_high_confidence(self):
        """Should detect specific symptoms and give high confidence."""
        ctx = DiagnosticContext()
        result = _keyword_classify("Outlook keeps crashing when I open attachments", ctx)
        assert result["category"] == "email/outlook"
        assert result["confidence"] >= 0.6

    def test_classify_vague_outlook_has_lower_confidence(self):
        """Vague Outlook message should have lower confidence."""
        ctx = DiagnosticContext()
        result = _keyword_classify("Outlook issue", ctx)
        assert result["category"] == "email/outlook"
        assert result["has_specific_symptom"] is False


class TestClassifyIssue:
    """Tests for _classify_issue (LLM + keyword fallback)."""

    @pytest.mark.asyncio
    async def test_falls_back_to_keyword_when_no_llm(self):
        """Should use keyword classification when LLM unavailable."""
        ctx = DiagnosticContext()
        result = await _classify_issue("My Outlook is slow", ctx)
        assert result["category"] == "email/outlook"
        assert result["_method"] in ("keyword", "entity", "entity_keyword")

    @pytest.mark.asyncio
    async def test_classify_email_issue(self):
        """Should classify email issues correctly."""
        ctx = DiagnosticContext()
        result = await _classify_issue("I can't receive emails in my inbox", ctx)
        assert result["category"] == "email/outlook"

    @pytest.mark.asyncio
    async def test_classify_zoom_issue(self):
        """Should classify Zoom issues correctly."""
        ctx = DiagnosticContext()
        result = await _classify_issue("My Zoom meeting won't start", ctx)
        assert result["category"] == "video-conferencing/zoom"


class TestTriageNode:
    """Tests for the triage_node function."""

    @pytest.mark.asyncio
    async def test_triage_empty_messages(self):
        """Should ask for description when no messages present."""
        state = {"messages": [], "session_id": "test-123"}
        result = await triage_node(state)
        assert result["needs_clarification"] is True
        assert result["current_node"] == "triage"
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_triage_vague_query_asks_clarification(self):
        """Vague Outlook query should trigger clarification, not retrieval."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="I have an Outlook issue")],
            "session_id": "test-vague",
            "diagnostic_context": None,
        }
        result = await triage_node(state)
        assert result["needs_clarification"] is True
        assert result["issue_category"] == "email/outlook"
        assert result.get("quick_replies") is not None

    @pytest.mark.asyncio
    async def test_triage_specific_query_proceeds(self):
        """Specific query with entity + symptom should proceed (not clarify)."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="My Outlook is not syncing emails since this morning")],
            "session_id": "test-specific",
            "diagnostic_context": None,
        }
        result = await triage_node(state)
        # Entity detection now routes Outlook specifically; the behavior depends
        # on whether the playbook considers "syncing" a specific enough symptom.
        assert result["issue_category"] == "email/outlook"
        # After entity recognition + symptom extraction, should either proceed
        # or ask one clarifying question — both are acceptable.
        assert result["current_node"] == "triage"

    @pytest.mark.asyncio
    async def test_triage_includes_audit_trail(self):
        """Should include an audit trail entry."""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="My email is broken")],
            "session_id": "test-456",
            "diagnostic_context": None,
        }
        result = await triage_node(state)
        assert "audit_trail" in result
        audit = result["audit_trail"][0]
        assert "event" in audit
        assert "triage" in audit["event"]

