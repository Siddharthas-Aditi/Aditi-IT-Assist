"""LangGraph workflow definition — the core agent orchestration graph."""

from langgraph.graph import END, StateGraph

from app.workflows.nodes.escalation import escalation_node
from app.workflows.nodes.resolution import resolution_node
from app.workflows.nodes.retrieval import retrieval_node
from app.workflows.nodes.ticketing import ticket_node
from app.workflows.nodes.triage import triage_node
from app.workflows.state import WorkflowState


def route_after_triage(state: WorkflowState) -> str:
    """Route after triage: clarify, retrieve, or escalate."""
    if state.get("needs_clarification"):
        return END  # Return clarification question to user
    if state.get("issue_category") is None:
        return "escalate"  # Cannot classify after attempts

    # Check if diagnostic context indicates live agent request
    diag = state.get("diagnostic_context") or {}
    if diag.get("live_agent_requested"):
        return "escalate"

    return "retrieve"


def route_after_retrieval(state: WorkflowState) -> str:
    """Route after knowledge retrieval."""
    if not state.get("knowledge_results"):
        return "escalate"
    if state.get("knowledge_confidence", 0) < 0.3:
        return "escalate"
    return "resolve"


def route_after_resolution(state: WorkflowState) -> str:
    """Route after resolution attempt.

    Higher threshold (0.5) to return resolution.
    The resolution node itself adds "Did this help?" framing.
    """
    confidence = state.get("resolution_confidence", 0)
    if confidence >= 0.5:
        return END  # Provide resolution (with disclaimer if < 0.8)
    return "escalate"


def route_after_escalation(state: WorkflowState) -> str:
    """Route after escalation decision."""
    if state.get("should_escalate"):
        return "draft_ticket"
    return END


def build_support_workflow() -> StateGraph:
    """Build and compile the support workflow graph.

    Returns:
        Compiled LangGraph StateGraph ready for invocation.
    """
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("resolve", resolution_node)
    workflow.add_node("escalate", escalation_node)
    workflow.add_node("draft_ticket", ticket_node)

    # Set entry point
    workflow.set_entry_point("triage")

    # Define edges with conditional routing
    workflow.add_conditional_edges("triage", route_after_triage)
    workflow.add_conditional_edges("retrieve", route_after_retrieval)
    workflow.add_conditional_edges("resolve", route_after_resolution)
    workflow.add_conditional_edges("escalate", route_after_escalation)
    workflow.add_edge("draft_ticket", END)

    return workflow.compile()


# Singleton compiled graph
support_graph = build_support_workflow()
