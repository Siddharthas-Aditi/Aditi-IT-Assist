"""Unit tests for workflow nodes — escalation and ticketing.

Tests:
- Escalation node: detects various triggers correctly
- Ticketing node: generates draft ticket from escalation context
- Workflow routing logic
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, AIMessage

from app.workflows.nodes.escalation import escalation_node
from app.workflows.nodes.ticketing import ticket_node
from app.workflows.graph import (
    route_after_triage,
    route_after_retrieval,
    route_after_resolution,
    route_after_escalation,
)
from langgraph.graph import END


# ─────────────────────────────────────────────────────────────────────
# Orchestrator routing tests
# ─────────────────────────────────────────────────────────────────────


class TestOrchestrator:
    """Tests for LangGraph routing functions (Orchestrator Agent)."""

    def test_route_after_triage_returns_end_on_clarification(self):
        state = {"needs_clarification": True}
        assert route_after_triage(state) == END

    def test_route_after_triage_escalates_with_no_category(self):
        state = {"needs_clarification": False, "issue_category": None}
        assert route_after_triage(state) == "escalate"

    def test_route_after_triage_retrieves_with_category(self):
        state = {"needs_clarification": False, "issue_category": "email/outlook"}
        assert route_after_triage(state) == "retrieve"

    def test_route_after_retrieval_escalates_with_no_results(self):
        state = {"knowledge_results": [], "knowledge_confidence": 0.0}
        assert route_after_retrieval(state) == "escalate"

    def test_route_after_retrieval_escalates_with_low_confidence(self):
        state = {"knowledge_results": [{"id": "1"}], "knowledge_confidence": 0.2}
        assert route_after_retrieval(state) == "escalate"

    def test_route_after_retrieval_resolves_with_good_results(self):
        state = {"knowledge_results": [{"id": "1"}], "knowledge_confidence": 0.7}
        assert route_after_retrieval(state) == "resolve"

    def test_route_after_resolution_ends_with_high_confidence(self):
        state = {"resolution_confidence": 0.9}
        assert route_after_resolution(state) == END

    def test_route_after_resolution_ends_with_medium_confidence(self):
        """Medium confidence (>= 0.5) still resolves — with disclaimer in message."""
        state = {"resolution_confidence": 0.6}
        assert route_after_resolution(state) == END

    def test_route_after_resolution_escalates_with_low_confidence(self):
        state = {"resolution_confidence": 0.3}
        assert route_after_resolution(state) == "escalate"

    def test_route_after_escalation_drafts_ticket_when_escalated(self):
        state = {"should_escalate": True}
        assert route_after_escalation(state) == "draft_ticket"

    def test_route_after_escalation_ends_when_not_escalated(self):
        state = {"should_escalate": False}
        assert route_after_escalation(state) == END


# ─────────────────────────────────────────────────────────────────────
# Escalation node tests
# ─────────────────────────────────────────────────────────────────────


class TestEscalationNode:
    """Tests for the escalation agent node."""

    async def test_escalates_when_resolution_confidence_low(self):
        """Should escalate when resolution confidence is very low."""
        state = {
            "session_id": "test-session",
            "user_id": "user-1",
            "messages": [HumanMessage(content="My Outlook is broken")],
            "issue_category": "email/outlook",
            "issue_subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "impact": "individual",
            "resolution_confidence": 0.2,  # Very low
            "knowledge_results": [],
            "knowledge_confidence": 0.0,
            "resolution_steps": [],
            "steps_attempted": [],
            "should_escalate": False,
            "escalation_reason": None,
            "handoff_summary": None,
            "turn_count": 3,
            "needs_clarification": False,
            "clarification_question": None,
            "audit_trail": [],
            "ticket_draft": None,
            "ticket_created": False,
        }

        result = await escalation_node(state)

        assert result["should_escalate"] is True
        assert result["escalation_reason"] is not None
        assert "handoff_summary" in result
        assert result["handoff_summary"] is not None

    async def test_escalates_when_max_turns_exceeded(self):
        """Should escalate when conversation has too many turns."""
        state = {
            "session_id": "test-session",
            "user_id": "user-1",
            "messages": [HumanMessage(content="I still have the issue")],
            "issue_category": "other",
            "issue_subcategory": None,
            "severity": "medium",
            "urgency": "medium",
            "impact": "individual",
            "resolution_confidence": 0.0,
            "knowledge_results": [],
            "knowledge_confidence": 0.0,
            "resolution_steps": [],
            "steps_attempted": [],
            "should_escalate": False,
            "escalation_reason": None,
            "handoff_summary": None,
            "turn_count": 11,  # Max turns exceeded
            "needs_clarification": False,
            "clarification_question": None,
            "audit_trail": [],
            "ticket_draft": None,
            "ticket_created": False,
        }

        result = await escalation_node(state)
        assert result["should_escalate"] is True

    async def test_escalation_audit_trail_included(self):
        """Escalation should add entry to audit trail."""
        state = {
            "session_id": "test-session",
            "user_id": "user-1",
            "messages": [HumanMessage(content="Still broken")],
            "issue_category": "email/outlook",
            "issue_subcategory": None,
            "severity": "low",
            "urgency": "low",
            "impact": "individual",
            "resolution_confidence": 0.1,
            "knowledge_results": [],
            "knowledge_confidence": 0.0,
            "resolution_steps": [],
            "steps_attempted": [],
            "should_escalate": False,
            "escalation_reason": None,
            "handoff_summary": None,
            "turn_count": 2,
            "needs_clarification": False,
            "clarification_question": None,
            "audit_trail": [],
            "ticket_draft": None,
            "ticket_created": False,
        }

        result = await escalation_node(state)

        assert "audit_trail" in result
        assert len(result["audit_trail"]) > 0
        audit = result["audit_trail"][0]
        assert "event" in audit


# ─────────────────────────────────────────────────────────────────────
# Ticketing node tests
# ─────────────────────────────────────────────────────────────────────


class TestTicketingNode:
    """Tests for the ticketing agent node."""

    async def test_generates_ticket_draft(self):
        """Should generate a ticket draft from escalation context."""
        state = {
            "session_id": "test-session",
            "user_id": "user-1",
            "messages": [
                HumanMessage(content="My camera is broken"),
                AIMessage(content="I tried these steps but they didn't work"),
            ],
            "issue_category": "hardware/camera",
            "issue_subcategory": "camera-access",
            "severity": "medium",
            "urgency": "medium",
            "impact": "individual",
            "resolution_confidence": 0.2,
            "knowledge_results": [],
            "knowledge_confidence": 0.0,
            "resolution_steps": [],
            "steps_attempted": ["Checked camera settings", "Reinstalled driver"],
            "should_escalate": True,
            "escalation_reason": "Low confidence resolution",
            "handoff_summary": {
                "employee_name": "Test Employee",
                "issue_category": "hardware/camera",
                "issue_description": "Camera not working",
                "steps_attempted": ["Checked camera settings"],
                "ai_confidence": 0.2,
                "recommended_actions": ["Escalate to IT"],
                "severity": "medium",
                "urgency": "medium",
            },
            "turn_count": 3,
            "needs_clarification": False,
            "clarification_question": None,
            "audit_trail": [],
            "ticket_draft": None,
            "ticket_created": False,
        }

        result = await ticket_node(state)

        assert "ticket_draft" in result
        draft = result["ticket_draft"]
        assert draft is not None
        assert "title" in draft
        assert "description" in draft
        assert "priority" in draft

    async def test_ticket_priority_derived_from_severity(self):
        """Ticket priority should be based on issue severity."""
        state = {
            "session_id": "test-session",
            "user_id": "user-1",
            "messages": [HumanMessage(content="CRITICAL: All systems down")],
            "issue_category": "network/connectivity",
            "issue_subcategory": None,
            "severity": "critical",
            "urgency": "high",
            "impact": "organization",
            "resolution_confidence": 0.0,
            "knowledge_results": [],
            "knowledge_confidence": 0.0,
            "resolution_steps": [],
            "steps_attempted": [],
            "should_escalate": True,
            "escalation_reason": "Critical severity",
            "handoff_summary": {
                "employee_name": "Test Employee",
                "issue_category": "network/connectivity",
                "issue_description": "All systems down",
                "steps_attempted": [],
                "ai_confidence": 0.0,
                "recommended_actions": ["Immediate escalation"],
                "severity": "critical",
                "urgency": "high",
            },
            "turn_count": 1,
            "needs_clarification": False,
            "clarification_question": None,
            "audit_trail": [],
            "ticket_draft": None,
            "ticket_created": False,
        }

        result = await ticket_node(state)

        assert result["ticket_draft"] is not None
        # Critical severity maps to critical/high priority
        assert result["ticket_draft"]["priority"] in ("critical", "high")
