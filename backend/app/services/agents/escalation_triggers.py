"""Deterministic escalation policy for the employee support workflow.

The policy is deliberately pure: graph routes and nodes ask it *why* a turn
must escalate, while ticket persistence remains confirmation-gated in
``ChatService``. Keeping the decision here prevents a weak retrieval, failed
step threshold, and turn-limit guard from drifting apart over time.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EscalationTrigger(StrEnum):
    """Stable, auditable reasons the AI flow may offer escalation."""

    USER_REQUEST = "user_request"
    MAX_TURNS = "max_turns"
    UNCLASSIFIABLE_ISSUE = "unclassifiable_issue"
    NO_GROUNDED_ARTICLES = "no_grounded_articles"
    LOW_RETRIEVAL_CONFIDENCE = "low_retrieval_confidence"
    FAILED_STEP_THRESHOLD = "failed_step_threshold"
    GROUNDED_STEPS_EXHAUSTED = "grounded_steps_exhausted"
    LOW_RESOLUTION_CONFIDENCE = "low_resolution_confidence"


@dataclass(frozen=True)
class EscalationDecision:
    """Result of evaluating a workflow state at a named routing stage."""

    trigger: EscalationTrigger | None = None

    @property
    def should_escalate(self) -> bool:
        return self.trigger is not None


def evaluate_escalation(
    state: Mapping[str, Any],
    *,
    stage: str,
    minimum_confidence: float,
    miss_threshold: int,
    max_turns: int,
) -> EscalationDecision:
    """Return the first applicable deterministic escalation trigger.

    ``stage`` keeps guards intentionally scoped: a confidence value reset at
    the start of a new turn cannot be mistaken for a post-resolution result.
    The priority ordering makes the reason reproducible and suitable for audit
    and the immutable escalation context.
    """
    diagnostic = state.get("diagnostic_context") or {}
    if not isinstance(diagnostic, Mapping):
        diagnostic = {}

    if diagnostic.get("live_agent_requested"):
        return EscalationDecision(EscalationTrigger.USER_REQUEST)

    if stage == "triage":
        if int(state.get("turn_count") or 0) >= max_turns:
            return EscalationDecision(EscalationTrigger.MAX_TURNS)
        if not state.get("issue_category"):
            return EscalationDecision(EscalationTrigger.UNCLASSIFIABLE_ISSUE)

    if stage == "retrieval":
        articles = state.get("knowledge_results") or []
        if not articles:
            return EscalationDecision(EscalationTrigger.NO_GROUNDED_ARTICLES)
        if float(state.get("knowledge_confidence") or 0.0) < minimum_confidence:
            return EscalationDecision(EscalationTrigger.LOW_RETRIEVAL_CONFIDENCE)

    if stage in {"resolution", "progression"}:
        failed_steps = diagnostic.get("failed_steps") or []
        if len(failed_steps) >= max(1, miss_threshold):
            return EscalationDecision(EscalationTrigger.FAILED_STEP_THRESHOLD)
        if diagnostic.get("phase") == "escalating":
            return EscalationDecision(EscalationTrigger.GROUNDED_STEPS_EXHAUSTED)
    if stage == "resolution":
        if not state.get("resolution_steps"):
            return EscalationDecision(EscalationTrigger.GROUNDED_STEPS_EXHAUSTED)
        if float(state.get("resolution_confidence") or 0.0) < minimum_confidence:
            return EscalationDecision(EscalationTrigger.LOW_RESOLUTION_CONFIDENCE)

    return EscalationDecision()


def escalation_reason(trigger: EscalationTrigger | None) -> str | None:
    """Employee-safe explanation for a deterministic escalation trigger."""
    reasons = {
        EscalationTrigger.USER_REQUEST: "User requested human assistance",
        EscalationTrigger.MAX_TURNS: "Troubleshooting needs further IT review",
        EscalationTrigger.UNCLASSIFIABLE_ISSUE: "The issue needs IT review to classify safely",
        EscalationTrigger.NO_GROUNDED_ARTICLES: "No relevant approved knowledge article was found",
        EscalationTrigger.LOW_RETRIEVAL_CONFIDENCE: (
            "I don't have enough reliable, approved guidance to recommend a fix safely"
        ),
        EscalationTrigger.FAILED_STEP_THRESHOLD: (
            "Multiple troubleshooting steps did not resolve the issue"
        ),
        EscalationTrigger.GROUNDED_STEPS_EXHAUSTED: (
            "All relevant troubleshooting steps were exhausted"
        ),
        EscalationTrigger.LOW_RESOLUTION_CONFIDENCE: (
            "I don't have enough reliable, approved guidance to recommend a fix safely"
        ),
    }
    return reasons.get(trigger) if trigger else None
