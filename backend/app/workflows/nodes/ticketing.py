"""Ticket/Email Drafting Agent Node — creates support ticket drafts."""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.agents.diagnostic_state import DiagnosticContext
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
    diag = state.get("diagnostic_context") or {}
    steps_tried = (
        state.get("steps_attempted")
        or diag.get("failed_steps")
        or diag.get("attempted_steps")
        or []
    )

    # Build ticket draft
    ticket_draft = {
        "title": _generate_ticket_title(state),
        "description": _generate_ticket_description(state, handoff),
        "category": state.get("issue_category", "other"),
        "priority": _map_severity_to_priority(state.get("severity", "medium")),
        "requested_by": {
            "name": state.get("user_name"),
            "email": state.get("user_email"),
            "user_id": state.get("user_id"),
        },
        "problem_statement": (
            diag.get("exact_problem_statement") or handoff.get("issue_description", "")
        ),
        "steps_attempted": steps_tried,
        "conversation_summary": handoff.get("issue_description", ""),
    }

    # IMPORTANT: this node prepares a draft and OFFERS to escalate — it does NOT
    # persist a ticket. Real ticket creation happens in the service layer only
    # after the user explicitly confirms (clicks "Connect with a specialist" or
    # replies yes), which is also where the live-agent queueing happens. This
    # keeps workflow nodes side-effect free and avoids promising a ticket that
    # was never created (the previous bug).
    confirmed = bool(state.get("escalation_confirmed"))

    if confirmed:
        # User already confirmed → the service will create + queue the ticket and
        # replace this content with the real ticket number. Interim text only.
        message = (
            "Thanks — I'm creating your support ticket and connecting you with "
            "an IT specialist now."
        )
    else:
        message = (
            f"I wasn't able to fully resolve this one on my own, so the best next "
            f"step is our IT team.\n\n"
            f"I can raise a **{ticket_draft['priority']}**-priority support ticket "
            f"(**{ticket_draft['category']}**) with everything we've covered — your "
            f"problem details and the steps we tried — and connect you with a "
            f"specialist.\n\n"
            f"Click **Connect with a specialist** below (or reply *yes*) and I'll set it up."
        )

    audit_entry = {
        "event": "ticket.offered",
        "title": ticket_draft["title"],
        "priority": ticket_draft["priority"],
        "confirmed": confirmed,
    }

    # Mark the session as having been offered escalation, so a future bare
    # "yes" can be unambiguously interpreted as "yes please escalate" rather
    # than the prior bug where any confirmation became ticket consent.
    diag_ctx = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})
    diag_ctx.escalation_offered_in_session = True

    return {
        "current_node": "draft_ticket",
        "ticket_draft": ticket_draft,
        "ticket_offered": True,
        "ticket_created": False,
        "diagnostic_context": diag_ctx.to_dict(),
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
    """Generate detailed ticket description including user, problem, and steps tried."""
    diag = state.get("diagnostic_context") or {}
    problem = (
        diag.get("exact_problem_statement")
        or handoff.get("issue_description")
        or "No description available"
    )

    lines = [
        "## Requested By",
        f"Name: {state.get('user_name') or 'Unknown'}",
        f"Email: {state.get('user_email') or 'Unknown'}",
        f"User ID: {state.get('user_id', 'Unknown')}",
        "",
        "## Issue Summary",
        f"Category: {state.get('issue_category', 'Unknown')}",
        f"Subtype: {state.get('issue_subtype') or diag.get('issue_subtype') or 'Unknown'}",
        f"Affected system: {diag.get('affected_system') or 'Unknown'}",
        f"Severity: {state.get('severity', 'medium')}",
        f"Urgency: {state.get('urgency', 'medium')}",
        "",
        "## Problem Statement",
        problem,
        "",
        "## Troubleshooting Already Tried",
    ]

    # Prefer the actual steps the agent walked the user through.
    steps = (
        state.get("steps_attempted")
        or diag.get("failed_steps")
        or diag.get("attempted_steps")
        or []
    )
    if steps:
        for step in steps:
            lines.append(f"- {step}")
    else:
        lines.append("- AI troubleshooting was attempted but did not resolve the issue")

    lines.extend(
        [
            "",
            "## Escalation Reason",
            state.get("escalation_reason", "Automated escalation due to low confidence"),
        ]
    )

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
