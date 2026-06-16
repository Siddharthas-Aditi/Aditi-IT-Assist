"""Diagnostic conversation state — structured slot-filling for multi-turn IT support.

This module manages the structured issue context that accumulates across turns.
The agent progressively fills slots to build enough context for targeted retrieval
and grounded resolution — avoiding the "dump everything" anti-pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiagnosticPhase(str, Enum):
    """Current phase of the diagnostic conversation."""

    INTAKE = "intake"  # Initial message, broad category identified
    CLARIFYING = "clarifying"  # Asking follow-up questions
    DIAGNOSING = "diagnosing"  # Enough context, searching knowledge
    RESOLVING = "resolving"  # Providing step-by-step resolution
    CONFIRMING = "confirming"  # Checking if resolution worked
    ESCALATING = "escalating"  # Handing off to human


class ConfidenceLevel(str, Enum):
    """Confidence bands for retrieval/resolution quality."""

    HIGH = "high"  # >= 0.8 — answer directly
    MEDIUM = "medium"  # 0.5–0.8 — answer with disclaimer
    LOW = "low"  # 0.3–0.5 — ask more or escalate
    VERY_LOW = "very_low"  # < 0.3 — escalate


@dataclass
class DiagnosticSlot:
    """A single piece of diagnostic context."""

    name: str
    value: str | None = None
    required: bool = False
    asked: bool = False  # Whether we've already asked for this
    source: str = ""  # "user" | "inferred" | "system"


@dataclass
class DiagnosticContext:
    """Structured diagnostic state accumulated across conversation turns.

    This is the 'memory' of what the agent knows about the current issue,
    separate from the raw chat history. It enables targeted retrieval and
    intelligent follow-up decisions.
    """

    # ── Core Classification ──────────────────────────────────────
    issue_category: str | None = None
    issue_subcategory: str | None = None
    symptom: str | None = None
    exact_problem_statement: str | None = None

    # ── Entity Normalization ─────────────────────────────────────
    normalized_system: str | None = None     # Canonical system name from entity registry
    raw_system_mention: str | None = None    # Original text the user typed
    entity_confidence: float = 0.0           # Entity recognition confidence

    # ── Environment Context ──────────────────────────────────────
    affected_system: str | None = None
    device_type: str | None = None
    platform_os: str | None = None
    error_message: str | None = None

    # ── Issue-Specific Flags ─────────────────────────────────────
    login_issue_flag: bool = False
    blocked_account_flag: str | None = None   # "yes" | "no" | "unsure"
    otp_issue_flag: bool = False
    unhandled_message_flag: bool = False

    # ── Temporal & Impact ────────────────────────────────────────
    duration: str | None = None
    urgency: str | None = None
    business_impact: str | None = None
    others_affected: bool | None = None

    # ── Network / Environment ────────────────────────────────────
    vpn_status: str | None = None
    network_type: str | None = None

    # ── Resolution Context ───────────────────────────────────────
    steps_already_tried: list[str] = field(default_factory=list)
    live_agent_requested: bool = False

    # ── Conversation Meta ────────────────────────────────────────
    phase: DiagnosticPhase = DiagnosticPhase.INTAKE
    clarification_count: int = 0
    max_clarifications: int = 3
    resolution_attempts: int = 0
    topic_shifts: int = 0

    # ── Confidence Tracking ──────────────────────────────────────
    classification_confidence: float = 0.0
    retrieval_confidence: float = 0.0
    resolution_confidence: float = 0.0

    def has_enough_context(self) -> bool:
        """Determine if we have enough context to attempt retrieval.

        The minimum requirement is:
        - A specific category (not just broad product match)
        - AND at least one of: symptom, exact problem, error message
        - OR: a recognized entity + login flag (enough for playbook-guided flow)
        """
        has_category = bool(self.issue_category)
        has_specificity = bool(
            self.symptom
            or self.exact_problem_statement
            or self.error_message
            or self.issue_subcategory
        )
        # Entity-aware: if we know the system AND have a login/issue flag, proceed
        has_entity_context = bool(
            self.normalized_system
            and (self.login_issue_flag or self.otp_issue_flag or self.unhandled_message_flag)
        )
        return (has_category and has_specificity) or has_entity_context

    def should_clarify(self) -> bool:
        """Determine if the agent should ask a follow-up question."""
        if self.live_agent_requested:
            return False
        if self.clarification_count >= self.max_clarifications:
            return False
        if self.phase == DiagnosticPhase.ESCALATING:
            return False
        return not self.has_enough_context()

    def should_escalate(self) -> bool:
        """Determine if the issue should be escalated to a human."""
        if self.live_agent_requested:
            return True
        if self.resolution_attempts >= 2 and self.resolution_confidence < 0.5:
            return True
        if self.clarification_count >= self.max_clarifications and not self.has_enough_context():
            return True
        return False

    def get_retrieval_query(self) -> str:
        """Build a focused retrieval query from accumulated context."""
        parts: list[str] = []
        if self.issue_category:
            parts.append(self.issue_category)
        if self.issue_subcategory:
            parts.append(self.issue_subcategory)
        if self.symptom:
            parts.append(self.symptom)
        if self.exact_problem_statement:
            parts.append(self.exact_problem_statement)
        if self.error_message:
            parts.append(f"error: {self.error_message}")
        return " ".join(parts) if parts else ""

    def get_retrieval_filters(self) -> dict[str, Any]:
        """Build metadata filters for narrowing retrieval results."""
        filters: dict[str, Any] = {}
        if self.issue_category:
            filters["category"] = self.issue_category
        if self.platform_os:
            filters["platform"] = self.platform_os
        return filters

    def get_filled_slots(self) -> dict[str, str]:
        """Return all slots that have values."""
        result: dict[str, str] = {}
        for slot_name in [
            "issue_category", "issue_subcategory", "symptom",
            "exact_problem_statement", "affected_system", "device_type",
            "platform_os", "error_message", "duration", "urgency",
            "business_impact", "vpn_status", "network_type",
            "normalized_system", "raw_system_mention",
            "blocked_account_flag",
        ]:
            val = getattr(self, slot_name, None)
            if val:
                result[slot_name] = str(val)
        if self.login_issue_flag:
            result["login_issue_flag"] = "true"
        if self.otp_issue_flag:
            result["otp_issue_flag"] = "true"
        if self.unhandled_message_flag:
            result["unhandled_message_flag"] = "true"
        if self.steps_already_tried:
            result["steps_already_tried"] = ", ".join(self.steps_already_tried)
        return result

    def get_missing_critical_slots(self) -> list[str]:
        """Return the names of critical slots that are still empty."""
        missing: list[str] = []
        if not self.symptom and not self.exact_problem_statement:
            missing.append("symptom")
        if not self.issue_subcategory and not self.symptom:
            missing.append("issue_subcategory")
        return missing

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for workflow state storage."""
        return {
            "issue_category": self.issue_category,
            "issue_subcategory": self.issue_subcategory,
            "symptom": self.symptom,
            "exact_problem_statement": self.exact_problem_statement,
            "normalized_system": self.normalized_system,
            "raw_system_mention": self.raw_system_mention,
            "entity_confidence": self.entity_confidence,
            "affected_system": self.affected_system,
            "device_type": self.device_type,
            "platform_os": self.platform_os,
            "error_message": self.error_message,
            "login_issue_flag": self.login_issue_flag,
            "blocked_account_flag": self.blocked_account_flag,
            "otp_issue_flag": self.otp_issue_flag,
            "unhandled_message_flag": self.unhandled_message_flag,
            "duration": self.duration,
            "urgency": self.urgency,
            "business_impact": self.business_impact,
            "others_affected": self.others_affected,
            "vpn_status": self.vpn_status,
            "network_type": self.network_type,
            "steps_already_tried": self.steps_already_tried,
            "live_agent_requested": self.live_agent_requested,
            "phase": self.phase.value,
            "clarification_count": self.clarification_count,
            "resolution_attempts": self.resolution_attempts,
            "topic_shifts": self.topic_shifts,
            "classification_confidence": self.classification_confidence,
            "retrieval_confidence": self.retrieval_confidence,
            "resolution_confidence": self.resolution_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiagnosticContext:
        """Restore from serialized dict."""
        if not data:
            return cls()
        ctx = cls()
        for key, val in data.items():
            if key == "phase" and isinstance(val, str):
                ctx.phase = DiagnosticPhase(val)
            elif hasattr(ctx, key):
                setattr(ctx, key, val)
        return ctx
