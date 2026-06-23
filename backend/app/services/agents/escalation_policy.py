"""Escalation gating policy — the "no direct live-agent at chat start" rule.

A live-agent handoff (and the ticket that anchors it) must never happen until
the assistant has captured a minimally-useful problem statement. This module is
the single source of truth for "do we have enough context to route this to a
human yet?" so both enforcement points agree:

* the workflow's triage node (the natural-language ESCALATE_REQUEST path), and
* the service layer (`ChatService.request_live_agent`, behind the explicit
  "Connect with a specialist" action).

Keeping it pure (no DB, no LLM) makes it trivially unit-testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agents.diagnostic_state import DiagnosticContext

# A short, friendly request for the details a specialist needs to pick the case
# up cold. Shared so the gate reads identically wherever it fires.
GATHER_PROBLEM_PROMPT = (
    "I can connect you with a live IT specialist. First — so I route you to the "
    "right person and they have full context — could you briefly describe the "
    "issue? For example: which app or system is affected (Outlook, VPN, your "
    "laptop…), what's happening, and any error message you're seeing."
)


def handoff_context_sufficient(diag: DiagnosticContext) -> bool:
    """Return True when we know enough about the issue to hand off to a human.

    The bar is intentionally the same as the bar for attempting grounded
    retrieval (:meth:`DiagnosticContext.has_enough_context`): a known issue
    category plus a concrete symptom/problem/error/subtype, or a recognized
    system plus a specific issue flag.

    As a short-circuit, if the AI has already presented or the user has already
    tried any troubleshooting steps, context plainly exists — allow the handoff.
    This is what keeps the *post-troubleshooting* "Connect with a specialist"
    button working while still blocking a cold "connect me to a human" on turn 1.
    """
    if diag.steps_already_tried or diag.failed_steps or diag.suggested_steps:
        return True
    return diag.has_enough_context()


__all__ = ["GATHER_PROBLEM_PROMPT", "handoff_context_sufficient"]
