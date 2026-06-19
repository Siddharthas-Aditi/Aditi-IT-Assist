"""Tests for the supervisor's routing decisions.

The supervisor is a pure function; every test constructs an
IntentClassification + a SessionMetrics, calls :func:`decide`, and pins the
returned :class:`SupervisorDecision`. These are the routing-contract tests:
break one, and you've changed behavior.
"""

from __future__ import annotations

from app.services.agents.intent_classifier import (
    ConversationIntent,
    IntentClassification,
)
from app.services.agents.supervisor import (
    NextAction,
    SessionMetrics,
    decide,
)


def _ic(intent: ConversationIntent, conf: float = 0.9) -> IntentClassification:
    return IntentClassification(intent=intent, confidence=conf, matched="test")


def _base_kwargs(**overrides):
    base = dict(
        issue_category=None,
        issue_subtype=None,
        normalized_system=None,
        knowledge_confidence=0.0,
        has_knowledge_results=False,
        needs_clarification=False,
        issue_resolved=False,
        resolution_attempts=0,
        metrics=SessionMetrics(),
    )
    base.update(overrides)
    return base


class TestIntentShortCircuits:
    def test_new_topic_returns_reset(self) -> None:
        d = decide(intent=_ic(ConversationIntent.NEW_TOPIC), **_base_kwargs())
        assert d.action is NextAction.RESET_TOPIC

    def test_escalate_request_returns_escalate(self) -> None:
        d = decide(intent=_ic(ConversationIntent.ESCALATE_REQUEST), **_base_kwargs())
        assert d.action is NextAction.ESCALATE

    def test_issue_resolved_ends_session(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.GRATITUDE),
            **_base_kwargs(issue_resolved=True),
        )
        assert d.action is NextAction.END


class TestGuardrails:
    def test_global_handoff_cap_forces_escalate(self) -> None:
        m = SessionMetrics(handoffs=10)
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(metrics=m, issue_category="email/outlook"),
        )
        assert d.action is NextAction.ESCALATE
        assert "handoff cap" in d.reason

    def test_loop_signals_force_escalate(self) -> None:
        m = SessionMetrics(loop_signals=2)
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(metrics=m, issue_category="email/outlook"),
        )
        assert d.action is NextAction.ESCALATE


class TestClarification:
    def test_needs_clarification_returns_clarify(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(needs_clarification=True),
        )
        assert d.action is NextAction.CLARIFY


class TestSpecialistRouting:
    def test_outlook_subtype_delegates_to_sub_agent(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(
                issue_category="email/outlook",
                issue_subtype="mailbox-full",
                normalized_system="outlook",
                knowledge_confidence=0.8,
                has_knowledge_results=True,
            ),
        )
        assert d.action is NextAction.DELEGATE_SUB
        assert d.agent == "outlook"
        assert d.sub_agent == "outlook.mailbox_full"

    def test_outlook_without_subtype_delegates_to_specialist(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(
                issue_category="email/outlook",
                normalized_system="outlook",
                knowledge_confidence=0.7,
                has_knowledge_results=True,
            ),
        )
        assert d.action is NextAction.DELEGATE
        assert d.agent == "outlook"

    def test_unknown_domain_falls_back_to_retrieval_then_escalate(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(issue_category="unknown/whatever"),
        )
        assert d.action is NextAction.RETRIEVE

        d2 = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(
                issue_category="unknown/whatever", resolution_attempts=2,
            ),
        )
        assert d2.action is NextAction.ESCALATE

    def test_per_specialist_cap_triggers_web_fallback_when_allowed(self) -> None:
        m = SessionMetrics(handoffs=4)
        m.delegations_per_agent["zoom_meetings"] = 3  # at cap
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(
                metrics=m,
                issue_category="video-conferencing/zoom",
                normalized_system="zoom",
                has_knowledge_results=True,
                knowledge_confidence=0.4,
            ),
        )
        # zoom_meetings has web_fallback_allowed=True
        assert d.action is NextAction.WEB_FALLBACK

    def test_per_specialist_cap_escalates_when_no_web_fallback(self) -> None:
        m = SessionMetrics(handoffs=4)
        m.delegations_per_agent["outlook"] = 3
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(
                metrics=m,
                issue_category="email/outlook",
                normalized_system="outlook",
                has_knowledge_results=True,
                knowledge_confidence=0.4,
            ),
        )
        # outlook has web_fallback_allowed=False → escalate
        assert d.action is NextAction.ESCALATE

    def test_low_confidence_with_attempts_escalates(self) -> None:
        d = decide(
            intent=_ic(ConversationIntent.CONTINUE),
            **_base_kwargs(
                issue_category="email/outlook",
                normalized_system="outlook",
                has_knowledge_results=True,
                knowledge_confidence=0.1,
                resolution_attempts=1,
            ),
        )
        assert d.action is NextAction.ESCALATE
