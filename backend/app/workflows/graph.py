"""LangGraph workflow definition — the core agent orchestration graph."""

from langgraph.graph import END, StateGraph

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
        return END

    # Safety: if the conversation has gone too long without resolution, escalate.
    if (state.get("turn_count") or 0) >= _MAX_TURNS:
        return "escalate"

    if state.get("needs_clarification"):
        return END  # Return clarification question to user
    if state.get("issue_category") is None:
        return "escalate"  # Cannot classify after attempts

    # Check if diagnostic context indicates live agent request
    diag = state.get("diagnostic_context") or {}
    if diag.get("live_agent_requested"):
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
        return END  # Wait for consent before proceeding
    return "retrieve"


def route_after_retrieval(state: WorkflowState) -> str:
    """Route after knowledge retrieval.

    Policy: if the knowledge base has ANY relevant (grounded) article, we
    troubleshoot from it — we do NOT ticket just because confidence is moderate.
    We only escalate (→ ticket) when grounding found nothing usable, i.e. there
    is genuinely no solution in the KB for this issue.
    """
    if not state.get("knowledge_results"):
        return "escalate"
    return "resolve"


def route_after_resolution(state: WorkflowState) -> str:
    """Route after resolution attempt.

    Escalate when:
    - the resolver exhausted all grounded steps / detected a loop (confidence 0),
    - or grounding is too weak to stand behind an answer (< 0.35).

    Otherwise return the grounded next-step guidance to the user. A grounded but
    only moderately-confident answer (0.35-0.5) is still worth showing — it is
    on-domain and on-subtype — and the resolution node frames it with a
    "did this help?" so the user can drive escalation if it doesn't.
    """
    diag = state.get("diagnostic_context") or {}
    # The resolver sets phase=escalating only when it has exhausted every
    # grounded step for the issue. That — not a moderate confidence score — is
    # what warrants a ticket. A grounded answer is shown to the user regardless
    # of confidence (it's framed with "did this help?" so the user can escalate).
    if diag.get("phase") == "escalating":
        return "escalate"
    if not state.get("resolution_steps"):
        return "escalate"
    return END


def route_after_escalation(state: WorkflowState) -> str:
    """Route after escalation decision."""
    if state.get("should_escalate"):
        return "draft_ticket"
    return END


def build_support_workflow() -> StateGraph:
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
