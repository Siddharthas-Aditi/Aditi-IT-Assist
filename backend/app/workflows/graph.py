"""LangGraph workflow definition — the core agent orchestration graph."""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.config import settings
from app.services.agents.escalation_triggers import evaluate_escalation
from app.workflows.nodes.escalation import escalation_node
from app.workflows.nodes.policy import policy_enforcement_node
from app.workflows.nodes.resolution import resolution_node
from app.workflows.nodes.retrieval import retrieval_node
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

    # Shadow-mode supervisor runs between triage and policy. It logs +
    # records its decision but never alters routing in Phase 1. See
    # docs/development/rollout-plan-multi-agent.md for the promotion plan.
    return "supervisor_shadow"


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

    A response may only reach the resolver when its grounded retrieval passes
    the configured reliability floor. This prevents the LLM from using weak
    context as permission to answer from parametric knowledge.
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


def route_after_escalation(state: WorkflowState) -> str:
    """Route after escalation decision."""
    if state.get("should_escalate"):
        return "draft_ticket"
    return str(END)


def build_support_workflow() -> CompiledStateGraph[
    WorkflowState, None, WorkflowState, WorkflowState
]:
    """Build and compile the support workflow graph.

    Graph topology:
        triage -> policy -> retrieve -> resolve -> escalate -> draft_ticket -> END

    The policy node runs between triage and retrieval on every productive turn.
    It enforces RBAC, consent requirements, and the max-turn safety limit.
    """
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("supervisor_shadow", supervisor_shadow_node)
    workflow.add_node("policy", policy_enforcement_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("resolve", resolution_node)
    workflow.add_node("escalate", escalation_node)
    workflow.add_node("draft_ticket", ticket_node)

    # Set entry point
    workflow.set_entry_point("triage")

    # Define edges with conditional routing
    workflow.add_conditional_edges("triage", route_after_triage)
    # supervisor_shadow is a pass-through: it logs the supervisor's decision
    # then hands off to the policy node so the legacy linear path continues.
    # Promoting it to a primary routing node (Phase 2) replaces this single
    # edge with a conditional that branches on supervisor_decision.action.
    workflow.add_edge("supervisor_shadow", "policy")
    workflow.add_conditional_edges("policy", route_after_policy)
    workflow.add_conditional_edges("retrieve", route_after_retrieval)
    workflow.add_conditional_edges("resolve", route_after_resolution)
    workflow.add_conditional_edges("escalate", route_after_escalation)
    workflow.add_edge("draft_ticket", END)

    return workflow.compile()


# Singleton compiled graph
support_graph = build_support_workflow()
