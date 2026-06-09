"""Ticket/Email Drafting Agent Node — creates support ticket drafts."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.workflows.state import WorkflowState

logger = get_logger(__name__)


async def ticket_node(state: WorkflowState) -> dict:
    """Create a support ticket draft from escalation context.

    This node:
    1. Takes the handoff summary from escalation
    2. Formats it into a structured ticket template
    3. Returns the draft for user approval
    """
    logger.info("ticket_node_start", session_id=state.get("session_id"))

    handoff = state.get("handoff_summary") or {}

    # Build ticket draft
    ticket_draft = {
        "title": _generate_ticket_title(state),
        "description": _generate_ticket_description(state, handoff),
        "category": state.get("issue_category", "other"),
        "priority": _map_severity_to_priority(state.get("severity", "medium")),
        "steps_attempted": state.get("steps_attempted", []),
        "conversation_summary": handoff.get("issue_description", ""),
    }

    # Generate user-facing message
    message = (
        f"I've drafted a support ticket for you:\n\n"
        f"**Title**: {ticket_draft['title']}\n"
        f"**Priority**: {ticket_draft['priority']}\n"
        f"**Category**: {ticket_draft['category']}\n\n"
        f"The ticket includes your conversation history and the steps we've "
        f"already tried. Our IT team will follow up with you shortly.\n\n"
        f"Is there anything else I can help you with?"
    )

    audit_entry = {
        "event": "ticket.drafted",
        "title": ticket_draft["title"],
        "priority": ticket_draft["priority"],
    }

    return {
        "current_node": "draft_ticket",
        "ticket_draft": ticket_draft,
        "ticket_created": True,
        "messages": [AIMessage(content=message)],
        "audit_trail": [audit_entry],
    }


def _generate_ticket_title(state: WorkflowState) -> str:
    """Generate a concise ticket title from issue context."""
    category = state.get("issue_category", "IT Issue")
    subcategory = state.get("issue_subcategory", "")

    category_titles = {
        "email/outlook": "Outlook Email Issue",
        "video-conferencing/zoom": "Zoom Application Issue",
        "device-management/intune": "Intune Compliance Issue",
        "hardware/camera": "Laptop Camera Issue",
        "network/connectivity": "Network Connectivity Issue",
        "access/permissions": "Access/Permissions Issue",
    }

    title = category_titles.get(category, f"IT Support Request - {category}")
    if subcategory:
        title += f" ({subcategory})"
    return title


def _generate_ticket_description(state: WorkflowState, handoff: dict) -> str:
    """Generate detailed ticket description."""
    lines = [
        "## Issue Summary",
        f"Category: {state.get('issue_category', 'Unknown')}",
        f"Severity: {state.get('severity', 'medium')}",
        f"Urgency: {state.get('urgency', 'medium')}",
        f"AI Confidence: {state.get('resolution_confidence', 0):.0%}",
        "",
        "## Description",
        handoff.get("issue_description", "No description available"),
        "",
        "## Steps Already Attempted",
    ]

    steps = state.get("steps_attempted", [])
    if steps:
        for step in steps:
            lines.append(f"- {step}")
    else:
        lines.append("- AI troubleshooting was attempted but did not resolve the issue")

    lines.extend([
        "",
        "## Escalation Reason",
        state.get("escalation_reason", "Automated escalation due to low confidence"),
    ])

    return "\n".join(lines)


def _map_severity_to_priority(severity: str | None) -> str:
    """Map severity to ticket priority."""
    mapping = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    return mapping.get(severity or "medium", "medium")
