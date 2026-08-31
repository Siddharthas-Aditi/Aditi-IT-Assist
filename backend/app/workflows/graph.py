"""LangGraph workflow definition — the core agent orchestration graph."""

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.config import settings
from app.services.agents.escalation_triggers import evaluate_escalation
from app.services.agents.supervisor import NextAction
from app.workflows.nodes.escalation import escalation_node
from app.workflows.nodes.policy import policy_enforcement_node
from app.workflows.nodes.resolution import resolution_node
from app.workflows.nodes.retrieval import retrieval_node
from app.workflows.nodes.specialist_dispatch import specialist_dispatch_node
from app.workflows.nodes.supervisor_shadow import supervisor_shadow_node
from app.workflows.nodes.ticketing import ticket_node
from app.workflows.nodes.triage import triage_node
from app.workflows.state import WorkflowState

# Maximum dialogue turns before the bot auto-escalates to a human agent.
_MAX_TURNS = 10


def route_after_triage(state: WorkflowState) -> str:
    """Route after triage: clarify, retrieve, escalate, or end (resolved)."""
    # User confirmed the issue is fixed — close out cleanly. This is checked
    # BEFORE the max-turns guard: a user who says "it works, thanks" on a long
    # conversation must get a clean close, not a forced escalation to a ticket.
    if state.get("issue_resolved"):
        return str(END)

    if state.get("needs_clarification"):
        return str(END)  # Return clarification question to user

    decision = evaluate_escalation(
        state,
        stage="triage",
        minimum_confidence=settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE,
        miss_threshold=settings.RESOLUTION_MISS_ESCALATE_THRESHOLD,
        max_turns=_MAX_TURNS,
    )
    if decision.should_escalate:
        return "escalate"

    # Shadow and primary supervisor both live in the same node; routing out of
    # it differs based on whether FEATURE_SUPERVISOR_PRIMARY is on.
    return "supervisor_shadow"


def route_after_supervisor(state: WorkflowState) -> str:
    """Route after the supervisor node.

    Shadow mode (FEATURE_SUPERVISOR_PRIMARY=False): unconditionally forward to
    the policy node — no UX change, the supervisor's logged decision is for
    analytics only.

    Primary mode (FEATURE_SUPERVISOR_PRIMARY=True): honour the supervisor's
    ESCALATE and END decisions immediately. All other actions continue to the
    policy node so RBAC and consent enforcement always runs before retrieval or
    specialist dispatch.
    """
    if not settings.FEATURE_SUPERVISOR_PRIMARY:
        return "policy"

    supervisor_decision: dict[str, Any] = state.get("supervisor_decision") or {}
    action_str = supervisor_decision.get("action", "")
    try:
        action = NextAction(action_str)
    except ValueError:
        return "policy"

    if action is NextAction.ESCALATE:
        return "escalate"
    if action is NextAction.END:
        return str(END)
    # CLARIFY → triage already set needs_clarification; surface it via END
    if action is NextAction.CLARIFY:
        return str(END)
    # WEB_FALLBACK: the web-research node is not yet wired into the graph.
    # A cap-hit that produces WEB_FALLBACK means the specialist is exhausted;
    # escalating is safer than silently falling through to standard retrieval.
    if action is NextAction.WEB_FALLBACK:
        return "escalate"
    # DELEGATE, DELEGATE_SUB, RETRIEVE, RESPOND → continue through policy
    return "policy"


def route_after_policy(state: WorkflowState) -> str:
    """Route after policy enforcement: retrieve or escalate if policy blocked."""
    violations = state.get("policy_violations") or []
    if violations:
        return "escalate"
    if state.get("requires_consent") and not state.get("consent_granted"):
        return str(END)  # Wait for consent before proceeding
    return "retrieve"


def route_after_retrieval(state: WorkflowState) -> str:
    """Route after knowledge retrieval.

    When FEATURE_SUPERVISOR_PRIMARY is on and the supervisor decided DELEGATE
    or DELEGATE_SUB, route to specialist_dispatch instead of the legacy
    resolution node. The reliability floor is still checked first — a specialist
    without grounded articles is the same as the legacy path: escalate.
    """
    decision = evaluate_escalation(
        state,
        stage="retrieval",
        minimum_confidence=settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE,
        miss_threshold=settings.RESOLUTION_MISS_ESCALATE_THRESHOLD,
        max_turns=_MAX_TURNS,
    )
    if decision.should_escalate:
        return "escalate"

    if settings.FEATURE_SUPERVISOR_PRIMARY:
        supervisor_decision: dict[str, Any] = state.get("supervisor_decision") or {}
        action_str = supervisor_decision.get("action", "")
        try:
            action = NextAction(action_str)
        except ValueError:
            action = NextAction.RETRIEVE
        if action in (NextAction.DELEGATE, NextAction.DELEGATE_SUB):
            return "specialist_dispatch"

    return "resolve"


def route_after_resolution(state: WorkflowState) -> str:
    """Route after resolution attempt.

    The same reliability floor remains a defensive post-resolution guard. The
    retrieval route normally prevents weak context from reaching this point.
    """
    decision = evaluate_escalation(
        state,
        stage="resolution",
        minimum_confidence=settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE,
        miss_threshold=settings.RESOLUTION_MISS_ESCALATE_THRESHOLD,
        max_turns=_MAX_TURNS,
    )
    if decision.should_escalate:
        return "escalate"
    return str(END)


def route_after_specialist_dispatch(state: WorkflowState) -> str:
    """Route after specialist dispatch.

    A specialist that signals escalation (escalation_signal set) moves to the
    escalate node. Otherwise the session ends for this turn (the graph will be
    re-entered on the next user message).
    """
    if state.get("should_escalate"):
        return "escalate"
    return str(END)


def route_after_escalation(state: WorkflowState) -> str:
    """Route after escalation decision."""
    if state.get("should_escalate"):
        return "draft_ticket"
    return str(END)


def build_support_workflow() -> CompiledStateGraph[
    WorkflowState, None, WorkflowState, WorkflowState
]:
    """Build and compile the support workflow graph.

    Shadow mode topology (FEATURE_SUPERVISOR_PRIMARY=False, default):
        triage -> supervisor_shadow -> policy -> retrieve -> resolve ->
        escalate -> draft_ticket -> END

    Primary mode topology (FEATURE_SUPERVISOR_PRIMARY=True):
        triage -> supervisor_shadow -> [ESCALATE→escalate | END→END | *→policy]
        -> retrieve -> [DELEGATE→specialist_dispatch | *→resolve]
        specialist_dispatch -> [should_escalate→escalate | *→END]
        resolve -> escalate -> draft_ticket -> END

    The policy node runs between supervisor and retrieval on every productive
    turn. It enforces RBAC, consent requirements, and the max-turn safety limit.
    The specialist_dispatch node replaces the resolution node for delegated
    issues when the supervisor is primary.
    """
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("supervisor_shadow", supervisor_shadow_node)
    workflow.add_node("policy", policy_enforcement_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("resolve", resolution_node)
    workflow.add_node("specialist_dispatch", specialist_dispatch_node)
    workflow.add_node("escalate", escalation_node)
    workflow.add_node("draft_ticket", ticket_node)

    # Set entry point
    workflow.set_entry_point("triage")

    # Define edges with conditional routing
    workflow.add_conditional_edges("triage", route_after_triage)
    # Shadow mode: single edge forward. Primary mode: supervisor drives routing.
    workflow.add_conditional_edges("supervisor_shadow", route_after_supervisor)
    workflow.add_conditional_edges("policy", route_after_policy)
    workflow.add_conditional_edges("retrieve", route_after_retrieval)
    workflow.add_conditional_edges("specialist_dispatch", route_after_specialist_dispatch)
    workflow.add_conditional_edges("resolve", route_after_resolution)
    workflow.add_conditional_edges("escalate", route_after_escalation)
    workflow.add_edge("draft_ticket", END)

    return workflow.compile()


# Singleton compiled graph
support_graph = build_support_workflow()
