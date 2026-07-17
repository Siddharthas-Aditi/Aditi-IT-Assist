"""Escalation Agent Node — smart escalation with diagnostic context.

Upgraded to:
1. Only escalate after a meaningful diagnostic attempt
2. Use diagnostic context for richer handoff summaries
3. Include entity, intent, and playbook context in escalation
4. Provide clear, actionable escalation reasons
"""

from langchain_core.messages import AIMessage

from app.core.logging import get_logger
from app.services.agents.conversation_messages import (
    generate_escalation_confirmed,
    generate_escalation_offer,
)
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.intent_classifier import ConversationIntent
from app.services.agents.llm_intent import classify_intent_with_llm
from app.workflows.state import WorkflowState

logger = get_logger(__name__)


async def escalation_node(state: WorkflowState) -> dict:
    """Decide on escalation and prepare handoff summary.

    This node:
    1. Evaluates whether escalation is truly warranted
    2. Prepares a rich handoff summary with diagnostic context
    3. Generates an empathetic, context-aware escalation message
    4. NEW: Detects if user is confirming prior escalation offer (avoid duplicate)
    """
    logger.info(
        "escalation_node_start",
        session_id=state.get("session_id"),
        confidence=state.get("resolution_confidence", 0),
    )

    diag_ctx = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})

    # NEW: Check if user is confirming escalation (to avoid duplicate message).
    # Crucially, a bare CONFIRM only counts as escalation-consent when an
    # offer was already made in a prior turn — otherwise "yes correct" to a
    # confirm-understanding question would silently spawn a ticket.
    messages = state.get("messages", [])
    latest_message = messages[-1].content if messages else ""
    was_offered = bool(diag_ctx.escalation_offered_in_session)
    is_confirming_escalation = await _is_user_confirming_escalation(
        latest_message, was_offered=was_offered
    )

    if is_confirming_escalation and diag_ctx.resolution_attempts > 0:
        # User already said yes to escalation → skip asking again, proceed to handoff
        logger.info(
            "escalation_confirmed",
            session_id=state.get("session_id"),
            is_confirmation=True,
        )
        reason = _determine_escalation_reason(state, diag_ctx)
        handoff_summary = _build_handoff_summary(state, reason, diag_ctx)
        message = await generate_escalation_confirmed(diag_ctx)
    else:
        # New escalation request → offer with explanation
        reason = _determine_escalation_reason(state, diag_ctx)
        handoff_summary = _build_handoff_summary(state, reason, diag_ctx)
        if diag_ctx.live_agent_requested:
            message = _build_escalation_message(diag_ctx, reason)
        else:
            message = await generate_escalation_offer(diag_ctx, reason)

    audit_entry = {
        "event": "escalation.triggered",
        "reason": reason,
        "category": state.get("issue_category"),
        "entity": diag_ctx.normalized_system,
        "resolution_attempts": diag_ctx.resolution_attempts,
        "clarification_rounds": diag_ctx.clarification_count,
        "is_confirmation": is_confirming_escalation,
    }

    return {
        "current_node": "escalate",
        "should_escalate": True,
        # Explicit confirmation (typed "yes"/"connect me") or a prior live-agent
        # request → the service layer may now create + queue the real ticket.
        "escalation_confirmed": bool(is_confirming_escalation or diag_ctx.live_agent_requested),
        "escalation_reason": reason,
        "handoff_summary": handoff_summary,
        "messages": [AIMessage(content=message)],
        "audit_trail": [audit_entry],
    }


def _determine_escalation_reason(state: WorkflowState, diag_ctx: DiagnosticContext) -> str:
    """Determine why escalation is necessary, with diagnostic context."""
    confidence = state.get("resolution_confidence", 0)
    knowledge_results = state.get("knowledge_results", [])

    if diag_ctx.live_agent_requested:
        return "User requested human assistance"

    # Prefer the precise reason the resolver recorded (e.g. all grounded steps
    # for the subtype were exhausted), if any.
    if diag_ctx.escalation_reason:
        return diag_ctx.escalation_reason

    if not knowledge_results:
        system = diag_ctx.affected_system or diag_ctx.normalized_system or "this issue type"
        return f"No knowledge base articles found for {system}"

    if confidence < 0.3:
        return "Very low confidence in available resolution steps"

    if confidence < 0.5:
        if diag_ctx.resolution_attempts > 0:
            return (
                f"Resolution attempted ({diag_ctx.resolution_attempts} "
                f"attempt(s)) but confidence remains low — human expertise needed"
            )
        return "Low confidence in resolution — human expertise needed"

    if diag_ctx.resolution_attempts >= 2:
        return (
            f"Multiple resolution attempts ({diag_ctx.resolution_attempts}) "
            f"did not resolve the issue"
        )

    return "Automated troubleshooting exhausted — requires IT specialist"


def _build_escalation_message(diag_ctx: DiagnosticContext, reason: str) -> str:
    """Build a natural, context-aware escalation message."""
    system_name = diag_ctx.affected_system or "your system"

    if diag_ctx.live_agent_requested:
        return (
            "Absolutely — I'll connect you with our IT team right away. "
            "I've prepared a summary of everything we've discussed so they "
            "can pick up where we left off."
        )

    # NEW: Check if user asked for simpler explanation but it didn't help
    if diag_ctx.last_response_type == "resolve_simplified" and diag_ctx.resolution_attempts >= 2:
        return (
            "I understand these steps are complicated. "
            "Let me connect you with our IT team — they can walk you through "
            "this step-by-step and answer any questions you have."
        )

    if diag_ctx.resolution_attempts >= 2:
        return (
            f"I've tried multiple approaches to help with your {system_name} issue, "
            f"but I think our IT team is best suited to help you from here. "
            f"They'll have access to your system details and can troubleshoot more directly."
        )

    if diag_ctx.resolution_attempts > 0:
        return (
            f"I've tried to help troubleshoot the {system_name} issue, "
            f"but it looks like this needs a closer look from our IT team. "
            f"I'll include all the details from our conversation so they "
            f"can help you quickly."
        )

    return (
        f"I wasn't able to find a strong match in our knowledge base for "
        f"this {system_name} issue. Our IT team will be able to help you better. "
        f"Let me connect you with them."
    )


def _build_handoff_summary(state: WorkflowState, reason: str, diag_ctx: DiagnosticContext) -> dict:
    """Build structured handoff summary with rich diagnostic context."""
    messages = state.get("messages", [])
    conversation_points = []
    for msg in messages:
        if hasattr(msg, "content") and msg.content:
            role = getattr(msg, "type", "unknown")
            conversation_points.append(f"[{role}] {msg.content[:200]}")

    # Build detailed issue description
    issue_parts = []
    if diag_ctx.affected_system:
        issue_parts.append(f"System: {diag_ctx.affected_system}")
    if diag_ctx.symptom:
        issue_parts.append(f"Symptom: {diag_ctx.symptom}")
    if diag_ctx.exact_problem_statement:
        issue_parts.append(f"Problem: {diag_ctx.exact_problem_statement}")
    if diag_ctx.error_message:
        issue_parts.append(f"Error: {diag_ctx.error_message}")
    if diag_ctx.login_issue_flag:
        issue_parts.append("Type: Login/authentication issue")
    if diag_ctx.blocked_account_flag == "yes":
        issue_parts.append("Account appears locked/blocked")

    issue_description = (
        "; ".join(issue_parts)
        if issue_parts
        else (conversation_points[0] if conversation_points else "No description")
    )

    return {
        "employee_name": "Employee",
        "issue_category": state.get("issue_category", "unknown"),
        "issue_description": issue_description,
        "steps_attempted": (
            state.get("steps_attempted") or diag_ctx.failed_steps or diag_ctx.attempted_steps
        ),
        "ai_confidence": state.get("resolution_confidence", 0),
        "recommended_actions": _suggest_actions(diag_ctx),
        "severity": state.get("severity", "medium"),
        "urgency": state.get("urgency", "medium"),
        "conversation_history": conversation_points[-10:],
        "normalized_system": diag_ctx.normalized_system,
        "diagnostic_summary": {
            "entity": diag_ctx.normalized_system,
            "category": diag_ctx.issue_category,
            "subcategory": diag_ctx.issue_subcategory,
            "login_issue": diag_ctx.login_issue_flag,
            "account_locked": diag_ctx.blocked_account_flag,
            "otp_issue": diag_ctx.otp_issue_flag,
            "resolution_attempts": diag_ctx.resolution_attempts,
            "clarification_rounds": diag_ctx.clarification_count,
        },
    }


def _suggest_actions(diag_ctx: DiagnosticContext) -> list[str]:
    """Generate recommended actions for the human agent."""
    actions = ["Review conversation history"]

    if diag_ctx.normalized_system == "sixth_sense":
        actions.extend(
            [
                "Check Naukri account lock status",
                "Verify user's registered email/phone for OTP delivery",
            ]
        )
    elif diag_ctx.login_issue_flag:
        actions.extend(
            [
                "Check user's AD account status",
                "Verify MFA configuration",
            ]
        )
    elif diag_ctx.normalized_system == "outlook":
        actions.append("Check Exchange/M365 service status")
    else:
        actions.append("Check system-specific logs")

    return actions


async def _is_user_confirming_escalation(
    message: str,
    *,
    was_offered: bool = False,
) -> bool:
    """Check whether the user is confirming an escalation offer.

    Uses the hybrid LLM+keyword classifier so natural phrasings like
    "yeah go ahead and route it to IT" are understood without code changes.

    The disambiguation contract is unchanged:

    * ESCALATE_REQUEST always counts — the user explicitly asked for a human.
    * CONFIRM only counts when ``was_offered`` is True (a prior turn already
      offered escalation). Without that prior offer, a bare "yes" can mean
      "yes I have this issue" (confirm-understanding) — must NOT spawn a
      ticket.

    Everything else (NEW_TOPIC, REPEAT_OR_SIMPLIFY, GRATITUDE, CONTINUE, ...)
    blocks ticket creation regardless of LLM confidence.
    """
    if not message or not message.strip():
        return False
    result = await classify_intent_with_llm(
        message,
        awaiting_confirmation=True,
        has_active_issue=True,
    )
    if result.intent is ConversationIntent.ESCALATE_REQUEST:
        return True
    return result.intent is ConversationIntent.CONFIRM and was_offered
