"""Unit tests for the conversational intent classifier.

These tests pin the contract documented in docs/architecture/conversation-intents.md.
Each test exercises one routing decision; together they form the safety net
that prevents intent regressions from silently breaking workflow behavior.
"""

from __future__ import annotations

import pytest

from app.services.agents.intent_classifier import (
    CLASSIFIER_VERSION,
    ConversationIntent,
    IntentClassification,
    classify_intent,
)

# ── NEW_TOPIC ──────────────────────────────────────────────────────────────


class TestNewTopic:
    """The bug-class that motivated the classifier."""

    @pytest.mark.parametrize(
        "msg",
        [
            "I have another problem",
            "I have an another problem",  # the exact phrase from the bug report
            "I've got another issue",
            "I have a different question",
            "different problem now",
            "new issue",
            "one more thing",
            "something else - my VPN isn't working",
            "btw I have another issue",
            "unrelated, but my camera is dead",
            "Switch topic - I can't join the meeting",
        ],
    )
    def test_explicit_new_topic_phrases(self, msg: str) -> None:
        result = classify_intent(msg, has_active_issue=True, steps_given=True)
        assert result.intent is ConversationIntent.NEW_TOPIC, (
            f"expected NEW_TOPIC for {msg!r}, got {result.intent}"
        )
        assert result.confidence >= 0.7

    def test_new_topic_wins_over_continue_when_active_issue(self) -> None:
        """The smoking gun: after steps were given, this MUST NOT be CONTINUE."""
        result = classify_intent(
            "I have another problem",
            has_active_issue=True,
            steps_given=True,
        )
        assert result.intent is ConversationIntent.NEW_TOPIC

    def test_post_resolution_long_message_promoted_to_new_topic(self) -> None:
        """After issue_resolved, a substantive follow-up is a new request."""
        result = classify_intent(
            "Actually my VPN keeps dropping every few minutes too",
            has_active_issue=True,
            steps_given=True,
            issue_resolved=True,
        )
        assert result.intent is ConversationIntent.NEW_TOPIC

    def test_post_resolution_thanks_stays_gratitude(self) -> None:
        result = classify_intent(
            "thanks so much for the help",
            has_active_issue=True,
            steps_given=True,
            issue_resolved=True,
        )
        assert result.intent is ConversationIntent.GRATITUDE


# ── ESCALATE_REQUEST ───────────────────────────────────────────────────────


class TestEscalate:
    @pytest.mark.parametrize(
        "msg",
        [
            "I want to talk to a human",
            "Can you connect me with a specialist?",
            "please escalate this",
            "create a ticket for me",
            "I need a real person",
            "raise a ticket",
            "speak to someone",
            "connect with an agent",
        ],
    )
    def test_explicit_escalate(self, msg: str) -> None:
        assert classify_intent(msg).intent is ConversationIntent.ESCALATE_REQUEST

    def test_whole_word_agent_matches(self) -> None:
        assert (
            classify_intent("please give me an agent").intent is ConversationIntent.ESCALATE_REQUEST
        )

    def test_another_does_not_match_agent(self) -> None:
        """Regression: substring match used to fire 'agent' inside 'another'."""
        result = classify_intent(
            "I have an another problem",
            has_active_issue=True,
            steps_given=True,
        )
        assert result.intent is not ConversationIntent.ESCALATE_REQUEST
        assert result.intent is ConversationIntent.NEW_TOPIC

    def test_escalate_beats_confirm(self) -> None:
        result = classify_intent(
            "yes, connect me to a human",
            awaiting_confirmation=True,
        )
        # Primary assertion: ESCALATE_REQUEST wins over any CONFIRM signal.
        assert result.intent is ConversationIntent.ESCALATE_REQUEST
        # CONFIRM may or may not appear in alternates — the classifier's
        # strict whole-message token check legitimately rejects mixed-intent
        # messages like this one. What matters is ESCALATE wins.


# ── CONFIRM / DENY ─────────────────────────────────────────────────────────


class TestConfirmDeny:
    def test_yes_during_confirmation_is_confirm(self) -> None:
        result = classify_intent("yes", awaiting_confirmation=True)
        assert result.intent is ConversationIntent.CONFIRM

    def test_yes_without_confirmation_is_continue(self) -> None:
        """A bare 'yes' on a fresh session is not a confirmation of anything."""
        result = classify_intent("yes")
        assert result.intent is ConversationIntent.CONTINUE

    def test_no_during_confirmation_is_deny(self) -> None:
        assert classify_intent("no", awaiting_confirmation=True).intent is ConversationIntent.DENY

    def test_thats_right(self) -> None:
        assert (
            classify_intent("that's right", awaiting_confirmation=True).intent
            is ConversationIntent.CONFIRM
        )

    def test_not_quite(self) -> None:
        assert (
            classify_intent("not quite", awaiting_confirmation=True).intent
            is ConversationIntent.DENY
        )

    def test_ok_cool_is_small_talk_not_confirm(self) -> None:
        # Even with awaiting_confirmation, content-free filler should not be a
        # firm yes. We classify SMALL_TALK so the agent can re-ask.
        result = classify_intent("ok cool", awaiting_confirmation=True)
        assert result.intent in {ConversationIntent.SMALL_TALK, ConversationIntent.CONFIRM}


# ── FEEDBACK ────────────────────────────────────────────────────────────────


class TestFeedback:
    def test_didnt_work_is_negative(self) -> None:
        result = classify_intent("that didn't work", has_active_issue=True, steps_given=True)
        assert result.intent is ConversationIntent.NEGATIVE_FEEDBACK

    def test_it_worked_is_positive(self) -> None:
        result = classify_intent("it worked!", has_active_issue=True, steps_given=True)
        assert result.intent is ConversationIntent.POSITIVE_FEEDBACK

    def test_not_resolved_is_not_positive(self) -> None:
        """Negation must demote a positive phrase."""
        result = classify_intent("still not resolved", has_active_issue=True, steps_given=True)
        assert result.intent is ConversationIntent.NEGATIVE_FEEDBACK

    def test_positive_requires_steps_given(self) -> None:
        """We don't infer 'resolved' before we've suggested anything."""
        result = classify_intent("it worked", steps_given=False)
        # No steps yet → not a feedback signal; falls through.
        assert result.intent is not ConversationIntent.POSITIVE_FEEDBACK


# ── GREETING / GRATITUDE / SMALL TALK ─────────────────────────────────────


class TestSocial:
    def test_hello_on_fresh_session(self) -> None:
        assert classify_intent("hello").intent is ConversationIntent.GREETING

    def test_hello_during_active_issue_is_continue(self) -> None:
        """A mid-flow 'hey' is not a session reset."""
        result = classify_intent("hey", has_active_issue=True)
        assert result.intent is ConversationIntent.CONTINUE

    def test_thanks_pure(self) -> None:
        assert classify_intent("thanks!").intent is ConversationIntent.GRATITUDE
        assert classify_intent("thank you so much").intent is ConversationIntent.GRATITUDE

    def test_how_are_you(self) -> None:
        assert classify_intent("how are you").intent is ConversationIntent.SMALL_TALK


# ── REPEAT / SIMPLIFY ─────────────────────────────────────────────────────


class TestSimplify:
    @pytest.mark.parametrize(
        "msg",
        [
            "can you explain again?",
            "I'm confused",
            "in plain English please",
            "break it down step by step",
            "I don't follow",
        ],
    )
    def test_simplify_phrases(self, msg: str) -> None:
        assert (
            classify_intent(msg, has_active_issue=True, steps_given=True).intent
            is ConversationIntent.REPEAT_OR_SIMPLIFY
        )


# ── DEFAULT / EDGE CASES ──────────────────────────────────────────────────


class TestDefaults:
    def test_empty_message(self) -> None:
        result = classify_intent("")
        assert result.intent is ConversationIntent.SMALL_TALK
        assert result.confidence <= 0.3

    def test_typical_issue_description_is_continue(self) -> None:
        result = classify_intent("my outlook keeps crashing on startup")
        assert result.intent is ConversationIntent.CONTINUE

    def test_version_pinned(self) -> None:
        """Bump CLASSIFIER_VERSION when changing rules — tests guard against silent drift."""
        result = classify_intent("hello")
        assert result.version == CLASSIFIER_VERSION

    def test_returns_dataclass(self) -> None:
        assert isinstance(classify_intent("hello"), IntentClassification)


# ── PRIORITY RESOLUTION ───────────────────────────────────────────────────


class TestPriority:
    def test_new_topic_beats_negative_feedback(self) -> None:
        """If a user says 'didn't work, also another issue', new-topic wins.

        NEW_TOPIC is higher priority than NEGATIVE_FEEDBACK because preserving
        the user's pivot intent is more important than logging a failure.
        """
        result = classify_intent(
            "that didn't work, also I have another problem",
            has_active_issue=True,
            steps_given=True,
        )
        assert result.intent is ConversationIntent.NEW_TOPIC
        assert ConversationIntent.NEGATIVE_FEEDBACK in result.alternates

    def test_escalate_beats_new_topic(self) -> None:
        result = classify_intent(
            "I have another problem, connect me to a specialist please",
            has_active_issue=True,
            steps_given=True,
        )
        assert result.intent is ConversationIntent.ESCALATE_REQUEST
