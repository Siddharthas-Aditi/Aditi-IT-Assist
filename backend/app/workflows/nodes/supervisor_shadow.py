"""Supervisor shadow node — runs the supervisor's routing logic in
*shadow mode* for analytics + dual-run validation.

When the legacy linear graph is still authoritative (Phase 1), this node
adds zero behavior change: it computes a :class:`SupervisorDecision` based
on the current workflow state, logs it, attaches it to the audit trail,
and returns. The legacy nodes still drive the actual routing edges.

When ``FEATURE_SUPERVISOR_PRIMARY`` flips to True (Phase 2), this node's
decision can be promoted to a primary routing signal — but that promotion
adds branching in :mod:`app.workflows.graph` and is gated by the
dual-run-eval thresholds documented in
``docs/development/rollout-plan-multi-agent.md``.

Why a shadow node now
---------------------
1. Catches integration mistakes early — wiring the supervisor in shadow
   means a deploy doesn't change UX, but every divergence between the
   supervisor's pick and the legacy graph's actual route shows up in
   logs and the audit trail.
2. Lets analytics start joining ``supervisor_decision`` events to ticket
   outcomes immediately, so the eval thresholds can be measured against
   real production traffic.
3. Adds zero risk to active sessions — the function returns an empty
   state delta (no edges, no mutations) when in shadow mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.agents.intent_classifier import (
    ConversationIntent,
    IntentClassification,
)
from app.services.agents.supervisor import SessionMetrics, decide

if TYPE_CHECKING:
    from app.workflows.state import WorkflowState

logger = get_logger(__name__)


def _infer_network_type(subtype: str | None) -> str | None:
    """Infer the network_type slot value from a known subtype slug."""
    if not subtype:
        return None
    sub = subtype.lower()
    if "vpn" in sub:
        return "vpn"
    if "wifi" in sub or "wi-fi" in sub:
        return "wifi"
    if "internet" in sub or "connectivity" in sub:
        return "internet"
    if "3cx" in sub or "voip" in sub:
        return "voip"
    return None


def _extra_slots_from_diag(diag: Any, issue_subtype: str | None) -> dict[str, str | None]:
    """Build the extra_slots dict the supervisor needs from DiagnosticContext.

    Values from the context take precedence; if a slot is still None we try to
    infer it deterministically from the issue subtype so the supervisor can
    satisfy specialist required-slot checks without an extra conversational turn.
    """
    network_type: str | None = diag.get("network_type") or _infer_network_type(issue_subtype)
    platform_os: str | None = diag.get("platform_os")
    device_type: str | None = diag.get("device_type")
    return {
        "network_type": network_type,
        "platform_os": platform_os,
        "device_type": device_type,
    }


async def supervisor_shadow_node(state: WorkflowState) -> dict[str, Any]:
    """Compute (but do not act on) the supervisor's routing decision.

    No-op when ``FEATURE_SUPERVISOR_SHADOW`` is off — the function returns
    immediately so the workflow graph cost is negligible.
    """
    if not settings.FEATURE_SUPERVISOR_SHADOW:
        return {}

    diag = state.get("diagnostic_context") or {}
    intent_value = diag.get("last_intent") or "continue"
    try:
        intent_enum = ConversationIntent(intent_value)
    except ValueError:
        intent_enum = ConversationIntent.CONTINUE
    intent = IntentClassification(
        intent=intent_enum,
        confidence=float(diag.get("last_intent_confidence") or 0.5),
        matched=str(diag.get("last_intent_matched") or "shadow"),
    )

    # Build session metrics from whatever we have on the state. Without a
    # supervisor-owned counter the shadow's per-agent caps are imprecise,
    # but they're good enough to measure routing intent.
    metrics = SessionMetrics(
        handoffs=int(state.get("audit_trail_handoffs") or 0),  # type: ignore[call-overload]
        turn_count=int(state.get("turn_count") or 0),
        loop_signals=int(diag.get("loop_counter") or 0),
    )

    decision = decide(
        intent=intent,
        issue_category=state.get("issue_category"),
        issue_subtype=state.get("issue_subtype"),
        normalized_system=diag.get("normalized_system"),
        knowledge_confidence=float(state.get("knowledge_confidence") or 0.0),
        has_knowledge_results=bool(state.get("knowledge_results")),
        needs_clarification=bool(state.get("needs_clarification")),
        issue_resolved=bool(state.get("issue_resolved")),
        resolution_attempts=int(diag.get("resolution_attempts") or 0),
        metrics=metrics,
        extra_slots=_extra_slots_from_diag(diag, state.get("issue_subtype")),
    )

    logger.info(
        "supervisor_shadow_decision",
        session_id=state.get("session_id"),
        action=decision.action.value,
        agent=decision.agent,
        sub_agent=decision.sub_agent,
        reason=decision.reason,
        confidence=decision.confidence,
        supervisor_version=decision.supervisor_version,
        registry_version=decision.registry_version,
        intent_version=decision.intent_version,
    )

    audit_entry = {
        "event": "supervisor.shadow_decision",
        "action": decision.action.value,
        "agent": decision.agent,
        "sub_agent": decision.sub_agent,
        "reason": decision.reason,
        "confidence": decision.confidence,
        "shadow_only": not settings.FEATURE_SUPERVISOR_PRIMARY,
    }

    return {
        "audit_trail": [audit_entry],
        # Snapshot the decision on the state so the resolution / response
        # nodes (Phase 2) can read it without re-computing.
        "supervisor_decision": {
            "action": decision.action.value,
            "agent": decision.agent,
            "sub_agent": decision.sub_agent,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "supervisor_version": decision.supervisor_version,
        },
    }


__all__ = ["supervisor_shadow_node"]
