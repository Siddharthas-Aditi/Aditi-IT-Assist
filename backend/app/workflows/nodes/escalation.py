"""Escalation Agent Node — decides whether to escalate and prepares handoff."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.workflows.state import WorkflowState

logger = get_logger(__name__)


async def escalation_node(state: WorkflowState) -> dict:
    """Decide on escalation and prepare handoff summary.

    This node:
    1. Evaluates whether escalation is necessary
    2. Prepares structured handoff summary for human agent
    3. Checks if human agents are available (future)
    """
    logger.info(
        "escalation_node_start",
        session_id=state.get("session_id"),
        confidence=state.get("resolution_confidence", 0),
    )

    # Determine escalation reason
    reason = _determine_escalation_reason(state)

    # Build handoff summary
    handoff_summary = _build_handoff_summary(state, reason)

    # Generate user-facing message
    message = (
        "I understand this issue needs more specialized attention. "
        "I'm preparing a handoff to our IT support team with all the context "
        "from our conversation. They'll be able to help you further.\n\n"
        "Would you like me to create a support ticket?"
    )

    audit_entry = {
        "event": "escalation.triggered",
        "reason": reason,
        "category": state.get("issue_category"),
    }

    return {
        "current_node": "escalate",
        "should_escalate": True,
        "escalation_reason": reason,
        "handoff_summary": handoff_summary,
        "messages": [AIMessage(content=message)],
        "audit_trail": [audit_entry],
    }


def _determine_escalation_reason(state: WorkflowState) -> str:
    """Determine why escalation is necessary."""
    confidence = state.get("resolution_confidence", 0)
    knowledge_results = state.get("knowledge_results", [])

    if not knowledge_results:
        return "No knowledge base articles found for this issue type"
    if confidence < 0.3:
        return "Very low confidence in available resolution steps"
    if confidence < 0.5:
        return "Low confidence in resolution — human expertise needed"
    return "User requested human assistance"


def _build_handoff_summary(state: WorkflowState, reason: str) -> dict:
    """Build structured handoff summary for human IT agent."""
    # Extract conversation summary from messages
    messages = state.get("messages", [])
    conversation_points = []
    for msg in messages:
        if hasattr(msg, "content") and msg.content:
            role = getattr(msg, "type", "unknown")
            conversation_points.append(f"[{role}] {msg.content[:200]}")

    return {
        "employee_name": "Employee",  # TODO(team): Get from user profile
        "issue_category": state.get("issue_category", "unknown"),
        "issue_description": conversation_points[0] if conversation_points else "No description",
        "steps_attempted": state.get("steps_attempted", []),
        "ai_confidence": state.get("resolution_confidence", 0),
        "recommended_actions": ["Review conversation history", "Check system-specific logs"],
        "severity": state.get("severity", "medium"),
        "urgency": state.get("urgency", "medium"),
        "conversation_history": conversation_points[-10:],  # Last 10 messages
    }
