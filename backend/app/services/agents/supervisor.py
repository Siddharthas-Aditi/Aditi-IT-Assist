"""Supervisor agent — the routing brain of the multi-agent system.

The supervisor is a pure function over (conversation state, registry, intent
classification) that returns a :class:`SupervisorDecision`. It does NOT call
LLMs and does NOT mutate state — that's the workflow node's job. This makes
the supervisor cheap, deterministic, and trivially unit-testable.

Why a supervisor (and not just LangGraph edges)
-----------------------------------------------
LangGraph's conditional edges encode routing as code paths. That works for a
linear flow (triage → retrieval → resolve → escalate) but breaks down when
you have a dozen specialists, sub-agents, web fallback, and a queue. The
supervisor unifies all that routing into one declarative function so we can:

* Reason about every possible routing decision by reading one module.
* Cap handoffs, detect loops, enforce timeouts in one place.
* Replay supervisor decisions deterministically for golden tests.
* Swap individual specialists without touching the graph.

Decision space
--------------
The supervisor emits one of these next actions (in :class:`NextAction`):

* ``CLARIFY``       — ask the user a clarifying question (slots missing).
* ``RETRIEVE``      — go to the retrieval agent.
* ``DELEGATE``      — hand off to a specialist (decision.agent set).
* ``DELEGATE_SUB``  — hand off to a sub-agent (decision.agent + decision.sub_agent).
* ``RESPOND``       — generate the final user-facing response.
* ``WEB_FALLBACK``  — try controlled web research.
* ``ESCALATE``      — hand off to a human IT specialist.
* ``RESET_TOPIC``   — user switched topics; reset and re-triage.
* ``END``           — issue resolved or session naturally over.

Each decision carries a ``reason`` string (for the audit trail) and an
optional ``confidence``.

Guardrails enforced here
------------------------
* **Max handoffs per session** — supervisor caps the total number of agent
  handoffs at ``ConfidenceThresholds`` config (default 6). Beyond that, the
  supervisor escalates rather than ping-ponging.
* **Loop detection** — if the same specialist has been delegated to N times
  with no progress (no new slots filled, no new steps tried), escalate.
* **Confidence floor** — if knowledge confidence is below
  ``thresholds.escalate_below`` AND no specialist owns this issue,
  escalate immediately rather than guessing.
* **New-topic short-circuit** — if intent is NEW_TOPIC, return RESET_TOPIC
  before any other check (the user is no longer talking about the active
  issue).
* **Explicit escalate short-circuit** — if intent is ESCALATE_REQUEST, return
  ESCALATE before any other check.

This module is independent of LangGraph; it can be called from anywhere.
The current workflow wires it in as an advisory layer behind a feature flag
(see :mod:`app.workflows.graph` after the Phase-1 wiring lands).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.services.agents.intent_classifier import (
    CLASSIFIER_VERSION as _INTENT_VERSION,
)
from app.services.agents.intent_classifier import (
    ConversationIntent,
    IntentClassification,
)
from app.services.agents.registry import (
    REGISTRY_VERSION,
    SpecialistAgentSpec,
    SubAgentSpec,
    find_specialist_for,
    find_sub_agent_for,
)

SUPERVISOR_VERSION = "1.0.0"


class NextAction(StrEnum):
    """The supervisor's next-step decision."""

    CLARIFY = "clarify"
    RETRIEVE = "retrieve"
    DELEGATE = "delegate"
    DELEGATE_SUB = "delegate_sub"
    RESPOND = "respond"
    WEB_FALLBACK = "web_fallback"
    ESCALATE = "escalate"
    RESET_TOPIC = "reset_topic"
    END = "end"


@dataclass(frozen=True)
class SupervisorDecision:
    """One supervisor routing decision with full provenance.

    The workflow node persists this in the audit trail and uses ``action`` to
    pick the next graph edge. The other fields are diagnostics for the debug
    panel and analytics.
    """

    action: NextAction
    reason: str
    # The specialist (if any) the supervisor wants to hand off to.
    agent: str | None = None
    # The sub-agent within that specialist (if applicable).
    sub_agent: str | None = None
    # Supervisor's own confidence in this decision (0..1).
    confidence: float = 0.0
    # Pass-through for analytics: snapshot of every input that drove the call.
    inputs_snapshot: dict[str, Any] = field(default_factory=dict)
    # Version pins for reproducibility in dashboards / golden tests.
    supervisor_version: str = SUPERVISOR_VERSION
    registry_version: str = REGISTRY_VERSION
    intent_version: str = _INTENT_VERSION


@dataclass
class SessionMetrics:
    """Counters the supervisor watches to enforce guardrails.

    Lives on the workflow state; the supervisor reads but does not mutate it
    (the calling node updates after the decision is acted on).
    """

    handoffs: int = 0                  # total agent-to-agent handoffs this session
    delegations_per_agent: dict[str, int] = field(default_factory=dict)
    turn_count: int = 0
    loop_signals: int = 0              # consecutive turns with no progress
    last_progress_turn: int = 0        # turn # we last filled a slot / tried a step

    def record_delegation(self, agent_name: str) -> None:
        self.handoffs += 1
        self.delegations_per_agent[agent_name] = (
            self.delegations_per_agent.get(agent_name, 0) + 1
        )

    def per_agent(self, agent_name: str) -> int:
        return self.delegations_per_agent.get(agent_name, 0)


# Per-specialist soft cap on consecutive delegations before we escalate.
_PER_SPECIALIST_CAP = 3

# Hard ceiling on total handoffs in a session (defense in depth on top of the
# supervisor's own AgentSpec.max_handoffs limit).
_GLOBAL_HANDOFF_CAP = 8


def decide(
    *,
    intent: IntentClassification,
    issue_category: str | None,
    issue_subtype: str | None,
    normalized_system: str | None,
    knowledge_confidence: float,
    has_knowledge_results: bool,
    needs_clarification: bool,
    issue_resolved: bool,
    resolution_attempts: int,
    metrics: SessionMetrics,
) -> SupervisorDecision:
    """Pure-function routing decision.

    Every input is what the supervisor needs and nothing more. The caller
    (the workflow node) is responsible for assembling these from the workflow
    state, then acting on the returned decision.

    The function is small enough to fit on a page intentionally — the registry
    holds the per-agent rules, the intent classifier holds the conversational
    rules, and this function is the routing logic. Three layers, one purpose
    each.
    """
    snapshot = {
        "intent": intent.intent.value,
        "intent_confidence": intent.confidence,
        "category": issue_category,
        "subtype": issue_subtype,
        "system": normalized_system,
        "knowledge_confidence": knowledge_confidence,
        "needs_clarification": needs_clarification,
        "resolution_attempts": resolution_attempts,
        "handoffs": metrics.handoffs,
    }

    # ── 1. Short-circuits driven by conversational intent ───────────────
    # These happen BEFORE the registry / confidence checks because the user's
    # explicit conversational moves dominate routing.

    if intent.intent is ConversationIntent.NEW_TOPIC:
        return SupervisorDecision(
            action=NextAction.RESET_TOPIC,
            reason="user switched topics — reset and re-triage",
            confidence=intent.confidence,
            inputs_snapshot=snapshot,
        )

    if intent.intent is ConversationIntent.ESCALATE_REQUEST:
        return SupervisorDecision(
            action=NextAction.ESCALATE,
            reason="user explicitly requested a human / ticket",
            confidence=intent.confidence,
            inputs_snapshot=snapshot,
        )

    if issue_resolved:
        return SupervisorDecision(
            action=NextAction.END,
            reason="user confirmed the issue is resolved",
            confidence=1.0,
            inputs_snapshot=snapshot,
        )

    # ── 2. Guardrails — caps and loop detection ────────────────────────

    if metrics.handoffs >= _GLOBAL_HANDOFF_CAP:
        return SupervisorDecision(
            action=NextAction.ESCALATE,
            reason=f"global handoff cap reached ({metrics.handoffs})",
            confidence=0.95,
            inputs_snapshot=snapshot,
        )

    if metrics.loop_signals >= 2:
        return SupervisorDecision(
            action=NextAction.ESCALATE,
            reason="loop detected — no progress over consecutive turns",
            confidence=0.9,
            inputs_snapshot=snapshot,
        )

    # ── 3. Clarification before action ─────────────────────────────────

    if needs_clarification:
        return SupervisorDecision(
            action=NextAction.CLARIFY,
            reason="diagnostic context lacks required slots",
            confidence=0.7,
            inputs_snapshot=snapshot,
        )

    # ── 4. Find a specialist for this (system, category, subtype) ──────

    specialist = find_specialist_for(
        system=normalized_system,
        category=issue_category,
        subtype=issue_subtype,
    )

    # No specialist owns this domain ─ rely on general retrieval. If the KB has
    # nothing useful AND we've already tried, escalate. Otherwise keep going.
    if specialist is None:
        if not has_knowledge_results and resolution_attempts >= 1:
            return SupervisorDecision(
                action=NextAction.ESCALATE,
                reason="no specialist owns this issue and KB returned nothing",
                confidence=0.85,
                inputs_snapshot=snapshot,
            )
        if not has_knowledge_results:
            return SupervisorDecision(
                action=NextAction.RETRIEVE,
                reason="no specialist match — try general retrieval",
                confidence=0.5,
                inputs_snapshot=snapshot,
            )
        return SupervisorDecision(
            action=NextAction.RESPOND,
            reason="general retrieval succeeded — respond directly",
            confidence=knowledge_confidence,
            inputs_snapshot=snapshot,
        )

    # ── 5. Per-specialist guardrails ────────────────────────────────────

    if metrics.per_agent(specialist.name) >= _PER_SPECIALIST_CAP:
        # Try web fallback if this specialist allows it; otherwise escalate.
        if (
            specialist.web_fallback_allowed
            and metrics.per_agent("web_research") == 0
        ):
            return SupervisorDecision(
                action=NextAction.WEB_FALLBACK,
                reason=(
                    f"specialist {specialist.name} retried "
                    f"{metrics.per_agent(specialist.name)}x — try web fallback"
                ),
                agent="web_research",
                confidence=0.55,
                inputs_snapshot=snapshot,
            )
        return SupervisorDecision(
            action=NextAction.ESCALATE,
            reason=(
                f"specialist {specialist.name} exhausted after "
                f"{metrics.per_agent(specialist.name)} attempts"
            ),
            agent=specialist.name,
            confidence=0.9,
            inputs_snapshot=snapshot,
        )

    # ── 6. Required slots check (specialist-defined) ───────────────────

    # The caller is expected to have populated DiagnosticContext slot status;
    # we ask "do we have what THIS specialist needs?" before delegating.
    missing = _missing_required_slots(specialist, snapshot)
    if missing:
        return SupervisorDecision(
            action=NextAction.CLARIFY,
            reason=(
                f"specialist {specialist.name} requires {sorted(missing)} "
                f"before it can act"
            ),
            agent=specialist.name,
            confidence=0.6,
            inputs_snapshot=snapshot,
        )

    # ── 7. Confidence floor — escalate without guessing ────────────────

    if (
        has_knowledge_results
        and knowledge_confidence < specialist.thresholds.escalate_below
        and resolution_attempts >= 1
    ):
        return SupervisorDecision(
            action=NextAction.ESCALATE,
            reason=(
                f"knowledge_confidence {knowledge_confidence:.2f} below "
                f"specialist floor {specialist.thresholds.escalate_below:.2f} "
                f"after {resolution_attempts} attempts"
            ),
            agent=specialist.name,
            confidence=0.85,
            inputs_snapshot=snapshot,
        )

    # ── 8. Delegate to sub-agent if one owns this subtype ──────────────

    sub_agent = find_sub_agent_for(specialist, issue_subtype)
    if sub_agent is not None:
        return SupervisorDecision(
            action=NextAction.DELEGATE_SUB,
            reason=(
                f"sub-agent {sub_agent.name} owns subtype {issue_subtype!r} "
                f"inside specialist {specialist.name}"
            ),
            agent=specialist.name,
            sub_agent=sub_agent.name,
            confidence=knowledge_confidence or 0.6,
            inputs_snapshot=snapshot,
        )

    # ── 9. Default — delegate to the specialist itself ─────────────────

    return SupervisorDecision(
        action=NextAction.DELEGATE,
        reason=(
            f"delegating to specialist {specialist.name} for category "
            f"{specialist.categories!r}"
        ),
        agent=specialist.name,
        confidence=knowledge_confidence or 0.6,
        inputs_snapshot=snapshot,
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _missing_required_slots(
    specialist: SpecialistAgentSpec | SubAgentSpec,
    snapshot: dict[str, Any],
) -> set[str]:
    """Return the set of required slots that are not yet populated.

    The supervisor only checks the high-level slots reachable from its own
    input snapshot (system, category, subtype). For finer-grained slot
    inspection, the calling node can pass an extended snapshot — we look up
    by key.
    """
    missing: set[str] = set()
    snapshot_keys = {k for k, v in snapshot.items() if v}
    for required in specialist.required_slots:
        # Map between slot names the registry uses and snapshot keys.
        alias_map = {
            "normalized_system": "system",
            "affected_system": "system",
        }
        snapshot_key = alias_map.get(required, required)
        if snapshot_key not in snapshot_keys:
            missing.add(required)
    return missing


__all__ = [
    "SUPERVISOR_VERSION",
    "NextAction",
    "SessionMetrics",
    "SupervisorDecision",
    "decide",
]
