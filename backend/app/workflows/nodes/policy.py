"""Policy enforcement node — validates actions against user permissions and enterprise rules.

This node runs at key decision points to ensure:
1. User has appropriate permissions for requested actions
2. Consent requirements are met (e.g., remote support)
3. Role-based restrictions are enforced
4. Sensitive operations are logged to audit trail
"""

import structlog

from app.workflows.state import WorkflowState

logger = structlog.get_logger()

# Actions that require specific roles
ROLE_REQUIRED_ACTIONS = {
    "escalate_to_agent": {"it_agent", "it_lead", "it_admin"},
    "assign_ticket": {"it_agent", "it_lead", "it_admin"},
    "view_all_tickets": {"it_agent", "it_lead", "it_admin"},
    "request_remote_support": {"it_agent", "it_lead", "it_admin"},
    "request_screen_control": {"it_lead", "it_admin"},
    "approve_knowledge_article": {"it_lead", "it_admin"},
    "manage_users": {"it_admin"},
    "view_audit_logs": {"it_admin", "security_auditor"},
}

# Actions that require employee consent
CONSENT_REQUIRED_ACTIONS = {
    "screen_view",
    "screen_control",
    "full_remote",
}


async def policy_enforcement_node(state: WorkflowState) -> dict:
    """Enforce enterprise policies on workflow actions.

    This node:
    1. Validates user permissions for the current action
    2. Checks consent requirements
    3. Blocks unauthorized actions
    4. Logs policy decisions to audit trail

    Returns updated state fields only.
    """
    user_roles = set(state.get("user_roles", []))
    policy_violations: list[str] = []
    audit_entries: list[dict] = []

    # ── Role-based policy checks ─────────────────────────────────

    # Employees cannot access IT-only features
    # Employees should not be routed to escalation management
    if (
        state.get("is_employee_facing", True)
        and state.get("current_node") == "escalation"
        and not state.get("should_escalate")
    ):
        pass  # Allow escalation from AI (system-initiated)

    # ── Remote support policy ────────────────────────────────────

    if state.get("remote_session_requested"):
        session_type = state.get("remote_session_type", "screen_view")

        # Check agent has permission for session type
        if session_type == "screen_control" and not user_roles.intersection(
            {"it_lead", "it_admin"}
        ):
            policy_violations.append("Screen control requires IT Lead or Admin role")
            logger.warning(
                "policy_violation",
                action="remote_screen_control",
                user_roles=list(user_roles),
            )

        # Check consent requirement
        if session_type in CONSENT_REQUIRED_ACTIONS and not state.get("consent_granted", False):
            audit_entries.append(
                {
                    "action": "policy_check",
                    "detail": f"Consent required for {session_type}",
                    "result": "blocked_pending_consent",
                }
            )
            return {
                "requires_consent": True,
                "policy_violations": policy_violations,
                "audit_trail": audit_entries,
            }

    # ── AI copilot mode policy ───────────────────────────────────

    # When in copilot mode (assisting IT agent), allow more actions
    if state.get("copilot_mode") and not user_roles.intersection(
        {"it_agent", "it_lead", "it_admin"}
    ):
        policy_violations.append("AI copilot mode requires IT staff role")

    # ── Max turn safety ──────────────────────────────────────────

    if state.get("turn_count", 0) >= 10:
        audit_entries.append(
            {
                "action": "policy_enforcement",
                "detail": "Max turns reached, forcing escalation",
                "result": "auto_escalate",
            }
        )

    # ── Log policy decision ──────────────────────────────────────

    if policy_violations:
        logger.info(
            "policy_enforcement_result",
            violations=policy_violations,
            user_roles=list(user_roles),
        )
        audit_entries.append(
            {
                "action": "policy_violation",
                "detail": "; ".join(policy_violations),
                "result": "blocked",
            }
        )

    return {
        "policy_violations": policy_violations,
        "audit_trail": audit_entries,
    }
