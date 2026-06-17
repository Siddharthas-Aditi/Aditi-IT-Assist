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
    issue_subtype: str | None = None          # Specific subtype, e.g. "mailbox-full"
    subtype_confidence: float = 0.0
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

    # ── Troubleshooting State & Memory ───────────────────────────
    # Normalized instruction text the agent has already PRESENTED to the user.
    suggested_steps: list[str] = field(default_factory=list)
    # Steps the user explicitly says they tried.
    attempted_steps: list[str] = field(default_factory=list)
    # Steps that were presented and then reported as not working.
    failed_steps: list[str] = field(default_factory=list)
    # Steps that resolved (partial wins).
    resolved_steps: list[str] = field(default_factory=list)
    # Article ids/titles already used as a source (avoid re-grounding on the same chunk).
    retrieval_sources_used: list[str] = field(default_factory=list)
    # "clarify" | "confirm" | "resolve" | "escalate" | "resolved"
    last_response_type: str | None = None
    # Increments when a round produces no NEW grounded step (stuck-state signal).
    loop_counter: int = 0
    # Set by triage when the user reports the last steps did not work.
    last_resolution_failed: bool = False
    # Set when the user confirms the issue is fixed.
    issue_resolved: bool = False
    escalation_reason: str | None = None

    # ── Understanding confirmation (human-like flow) ──────────────
    # The agent restates its understanding and waits for the user to confirm
    # BEFORE giving a solution. awaiting_confirmation = we asked, waiting for
    # yes/no; understanding_confirmed = the user agreed our understanding is right.
    awaiting_confirmation: bool = False
    understanding_confirmed: bool = False

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
            self.issue_subtype
            or self.symptom
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

    def reset_issue_context(self) -> None:
        """Clear everything specific to the *current* issue.

        Used on a topic shift (the user switches to a different system) so the
        new issue is diagnosed and confirmed from scratch instead of inheriting
        stale symptoms/subtypes/tried-steps from the previous problem — that
        leak was why "I have an issue with outlook" got answered with a stale
        Sixth-Sense login symptom and the wrong KB article.

        System identity (normalized_system/affected_system/issue_category) is
        intentionally NOT cleared here — the caller applies the new entity right
        after calling this.
        """
        self.issue_subcategory = None
        self.issue_subtype = None
        self.subtype_confidence = 0.0
        self.symptom = None
        self.exact_problem_statement = None
        self.error_message = None
        self.login_issue_flag = False
        self.blocked_account_flag = None
        self.otp_issue_flag = False
        self.unhandled_message_flag = False
        self.device_type = None
        self.platform_os = None
        self.duration = None
        self.steps_already_tried = []
        self.suggested_steps = []
        self.attempted_steps = []
        self.failed_steps = []
        self.resolved_steps = []
        self.retrieval_sources_used = []
        self.loop_counter = 0
        self.resolution_attempts = 0
        self.clarification_count = 0
        self.last_resolution_failed = False
        self.awaiting_confirmation = False
        self.understanding_confirmed = False
        self.issue_resolved = False
        self.escalation_reason = None
        self.last_response_type = None

    @staticmethod
    def _norm_step(text: str) -> str:
        """Normalize a step instruction for de-duplication / memory matching."""
        return " ".join((text or "").lower().split())

    def record_suggested_steps(self, instructions: list[str]) -> None:
        """Remember step instructions we have presented this turn."""
        for ins in instructions:
            key = self._norm_step(ins)
            if key and key not in (self._norm_step(s) for s in self.suggested_steps):
                self.suggested_steps.append(ins)

    def mark_last_batch_failed(self) -> None:
        """Move the most recently suggested-but-unconfirmed steps to failed."""
        for ins in self.suggested_steps:
            key = self._norm_step(ins)
            if key not in (self._norm_step(s) for s in self.failed_steps):
                self.failed_steps.append(ins)
                self.attempted_steps.append(ins)

    def is_step_exhausted_or_seen(self, instruction: str) -> bool:
        """Whether a step has already been suggested or marked failed."""
        key = self._norm_step(instruction)
        seen = {self._norm_step(s) for s in self.suggested_steps}
        seen |= {self._norm_step(s) for s in self.failed_steps}
        return key in seen

    def get_retrieval_query(self) -> str:
        """Build a focused retrieval query from accumulated context."""
        parts: list[str] = []
        if self.issue_category:
            parts.append(self.issue_category)
        if self.issue_subtype:
            parts.append(self.issue_subtype.replace("-", " "))
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
            "issue_category", "issue_subcategory", "issue_subtype", "symptom",
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
            "issue_subtype": self.issue_subtype,
            "subtype_confidence": self.subtype_confidence,
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
            "suggested_steps": self.suggested_steps,
            "attempted_steps": self.attempted_steps,
            "failed_steps": self.failed_steps,
            "resolved_steps": self.resolved_steps,
            "retrieval_sources_used": self.retrieval_sources_used,
            "last_response_type": self.last_response_type,
            "loop_counter": self.loop_counter,
            "last_resolution_failed": self.last_resolution_failed,
            "issue_resolved": self.issue_resolved,
            "escalation_reason": self.escalation_reason,
            "awaiting_confirmation": self.awaiting_confirmation,
            "understanding_confirmed": self.understanding_confirmed,
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
