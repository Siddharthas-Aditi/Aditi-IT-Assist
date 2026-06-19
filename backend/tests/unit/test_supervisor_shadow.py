"""Tests for the supervisor shadow node.

These pin the dual-run contract:

* When the feature flag is OFF, the node is a strict no-op.
* When ON, it logs and stamps a typed decision on the state without
  altering the workflow's routing.
* Intent short-circuits (NEW_TOPIC, ESCALATE_REQUEST) reach the supervisor
  even though the calling node only forwards the persisted last_intent.

These tests run without a DB or LLM — pure state-in / state-out.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.workflows.nodes.supervisor_shadow import supervisor_shadow_node


def _base_state(**overrides) -> dict:
    state = {
        "session_id": "test-shadow",
        "issue_category": "email/outlook",
        "issue_subtype": "mailbox-full",
        "knowledge_confidence": 0.8,
        "knowledge_results": [{"id": "x", "title": "Mailbox full"}],
        "needs_clarification": False,
        "issue_resolved": False,
        "turn_count": 2,
        "diagnostic_context": {
            "normalized_system": "outlook",
            "issue_subtype": "mailbox-full",
            "resolution_attempts": 0,
            "loop_counter": 0,
            "last_intent": "continue",
            "last_intent_confidence": 0.9,
            "last_intent_matched": "default",
        },
    }
    state.update(overrides)
    return state


class TestShadowFlag:
    @pytest.mark.asyncio
    async def test_off_returns_empty_delta(self) -> None:
        with patch(
            "app.workflows.nodes.supervisor_shadow.settings.FEATURE_SUPERVISOR_SHADOW",
            False,
        ):
            delta = await supervisor_shadow_node(_base_state())
        assert delta == {}, "shadow off must be a strict no-op"

    @pytest.mark.asyncio
    async def test_on_records_decision_and_audit(self) -> None:
        with patch(
            "app.workflows.nodes.supervisor_shadow.settings.FEATURE_SUPERVISOR_SHADOW",
            True,
        ):
            delta = await supervisor_shadow_node(_base_state())
        assert "supervisor_decision" in delta
        assert "audit_trail" in delta
        sd = delta["supervisor_decision"]
        # Version pin keeps the schema stable for analytics joins.
        assert "supervisor_version" in sd
        assert sd["action"] in {"delegate", "delegate_sub", "respond", "clarify"}


class TestIntentShortCircuits:
    @pytest.mark.asyncio
    async def test_new_topic_reaches_reset(self) -> None:
        with patch(
            "app.workflows.nodes.supervisor_shadow.settings.FEATURE_SUPERVISOR_SHADOW",
            True,
        ):
            state = _base_state()
            state["diagnostic_context"]["last_intent"] = "new_topic"
            delta = await supervisor_shadow_node(state)
        assert delta["supervisor_decision"]["action"] == "reset_topic"

    @pytest.mark.asyncio
    async def test_escalate_request_reaches_escalate(self) -> None:
        with patch(
            "app.workflows.nodes.supervisor_shadow.settings.FEATURE_SUPERVISOR_SHADOW",
            True,
        ):
            state = _base_state()
            state["diagnostic_context"]["last_intent"] = "escalate_request"
            delta = await supervisor_shadow_node(state)
        assert delta["supervisor_decision"]["action"] == "escalate"


class TestSubAgentDispatch:
    @pytest.mark.asyncio
    async def test_outlook_mailbox_full_dispatches_to_sub_agent(self) -> None:
        with patch(
            "app.workflows.nodes.supervisor_shadow.settings.FEATURE_SUPERVISOR_SHADOW",
            True,
        ):
            delta = await supervisor_shadow_node(_base_state())
        sd = delta["supervisor_decision"]
        assert sd["action"] == "delegate_sub"
        assert sd["agent"] == "outlook"
        assert sd["sub_agent"] == "outlook.mailbox_full"


class TestUnknownIntentTolerance:
    """A malformed intent on the state must NOT crash the shadow — it falls
    back to CONTINUE. This is what makes the shadow safe to deploy."""

    @pytest.mark.asyncio
    async def test_unknown_intent_falls_back_to_continue(self) -> None:
        with patch(
            "app.workflows.nodes.supervisor_shadow.settings.FEATURE_SUPERVISOR_SHADOW",
            True,
        ):
            state = _base_state()
            state["diagnostic_context"]["last_intent"] = "not_a_real_intent"
            delta = await supervisor_shadow_node(state)
        # No crash; some valid action emitted.
        assert delta["supervisor_decision"]["action"] in {
            "delegate", "delegate_sub", "respond", "clarify",
            "retrieve", "escalate", "end", "reset_topic", "web_fallback",
        }
