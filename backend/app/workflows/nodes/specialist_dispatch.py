"""Specialist dispatch node — routes triaged issues to the correct typed specialist.

This node is the Phase-2 promotion of the supervisor shadow: when
``FEATURE_SUPERVISOR_PRIMARY`` is ``True`` and the supervisor decided
``DELEGATE`` or ``DELEGATE_SUB``, this node runs in place of the legacy
``resolution_node`` and dispatches to the correct specialist from the
``SPECIALIST_REGISTRY``.

Design choices
--------------
* **Registry-first lookup**: the specialist is found by name from
  ``SPECIALIST_REGISTRY`` — no hardcoded references in the routing logic.
  Future specialists drop into the registry and get dispatched automatically.
* **Escalation triggers reused**: after the specialist runs, the same
  ``evaluate_escalation`` used at the retrieval stage is called at
  "progression" stage to decide whether to escalate. This avoids duplicating
  routing conditions outside of ``escalation_triggers.py``.
* **Ledger integration**: every dispatch is recorded to ``agent_action_ledger``
  before and after the specialist runs. A crash during execution is visible as
  an incomplete row (``completed_at`` is NULL). The ledger is written via the
  ``ActionLedgerService`` which requires a DB session; when no session is
  available (e.g., tests that pass a mock state) the ledger write is skipped
  with a warning.
* **Fallback**: if the supervisor decision is missing or the specialist is not
  found in the registry, the node returns an empty dict — the graph falls
  through to the legacy ``resolution_node``.

What this node does NOT do
--------------------------
* It does not own retrieval — knowledge_results come from the retrieval node.
* It does not create tickets — that is the escalation + chat service path.
* It does not enforce RBAC or approval gates for tool calls — those stay in
  ``AgentToolRuntime``. Specialist ``handle()`` calls the runtime internally
  if tool calls are needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.repositories.agent_action_ledger_repository import AgentActionLedgerRepository
from app.services.agents.action_ledger_service import ActionLedgerService
from app.services.agents.diagnostic_state import DiagnosticContext, DiagnosticPhase
from app.services.agents.escalation_triggers import evaluate_escalation
from app.services.agents.specialists import get_specialist
from app.services.agents.specialists.base import SpecialistInput, SpecialistOutput
from app.services.agents.supervisor import NextAction

if TYPE_CHECKING:
    from app.workflows.state import WorkflowState

logger = get_logger(__name__)


def _build_specialist_input(state: WorkflowState, sub_agent_name: str | None) -> SpecialistInput:
    """Assemble SpecialistInput from the current workflow state."""
    diag_ctx = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})

    raw_results = state.get("knowledge_results") or []
    raw_citations = state.get("knowledge_citations") or []
    messages = state.get("messages") or []
    user_message = ""
    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            user_message = str(getattr(msg, "content", ""))
            break

    from app.services.agents.registry import AGENT_REGISTRY, SubAgentSpec

    sub_agent_spec: SubAgentSpec | None = None
    if sub_agent_name:
        spec_raw = AGENT_REGISTRY.get(sub_agent_name)
        if isinstance(spec_raw, SubAgentSpec):
            sub_agent_spec = spec_raw

    return SpecialistInput(
        user_message=user_message,
        diag_ctx=diag_ctx,
        knowledge_results=tuple(raw_results),
        knowledge_confidence=float(state.get("knowledge_confidence") or 0.0),
        knowledge_citations=tuple(dict(c) for c in raw_citations),
        sub_agent=sub_agent_spec,
        session_id=state.get("session_id") or "",
        turn_count=int(state.get("turn_count") or 0),
        tool_context=None,  # tool_context is populated by chat service when tools are enabled
    )


def _output_to_state(output: SpecialistOutput, current_state: WorkflowState) -> dict[str, Any]:
    """Map a SpecialistOutput to workflow state update fields."""
    from app.workflows.state import ResolutionStep

    steps: list[ResolutionStep] = [
        {
            "step_number": s.step_number,
            "instruction": s.instruction,
            "details": s.details,
        }
        for s in output.steps
    ]

    diag_ctx = DiagnosticContext.from_dict(current_state.get("diagnostic_context") or {})
    for step_text in output.presented_steps:
        diag_ctx.record_suggested_steps([step_text])

    audit_entry: dict[str, Any] = {
        "event": "specialist_dispatch.complete",
        "confidence": output.confidence,
        **(output.audit or {}),
    }
    if output.escalation_signal:
        audit_entry["escalation_signal"] = output.escalation_signal

    return {
        "resolution_steps": steps,
        "resolution_confidence": output.confidence,
        "diagnostic_context": diag_ctx.to_dict(),
        "audit_trail": [audit_entry],
        # Signal for route_after_specialist to check escalation.
        "should_escalate": bool(output.escalation_signal),
        "escalation_reason": output.escalation_signal,
    }


async def specialist_dispatch_node(state: WorkflowState) -> dict[str, Any]:
    """Dispatch to the correct typed specialist based on the supervisor decision.

    Returns an empty dict when ``FEATURE_SUPERVISOR_PRIMARY`` is off or the
    decision is missing — the graph then routes to the legacy resolution node.
    """
    if not settings.FEATURE_SUPERVISOR_PRIMARY:
        return {}

    supervisor_decision: dict[str, Any] = state.get("supervisor_decision") or {}
    action_str = supervisor_decision.get("action", "")
    try:
        action = NextAction(action_str)
    except ValueError:
        return {}

    if action not in (NextAction.DELEGATE, NextAction.DELEGATE_SUB):
        return {}

    specialist_name: str | None = supervisor_decision.get("agent")
    sub_agent_name: str | None = supervisor_decision.get("sub_agent")

    if not specialist_name:
        logger.warning(
            "specialist_dispatch_no_agent",
            session_id=state.get("session_id"),
            supervisor_action=action_str,
        )
        return {}

    specialist = get_specialist(specialist_name)
    if specialist is None:
        logger.warning(
            "specialist_dispatch_unknown",
            specialist_name=specialist_name,
            session_id=state.get("session_id"),
        )
        return {}

    inp = _build_specialist_input(state, sub_agent_name)

    # ── Ledger: open row before running (so a crash leaves a trace) ──────
    ledger_entry = None
    try:
        inputs_snap: dict[str, Any] = {
            "category": state.get("issue_category"),
            "subtype": state.get("issue_subtype"),
            "system": (state.get("diagnostic_context") or {}).get("normalized_system"),
            "knowledge_confidence": state.get("knowledge_confidence"),
            "turn_count": state.get("turn_count"),
        }
        async with async_session_factory() as db:
            svc = ActionLedgerService(AgentActionLedgerRepository(db))
            ledger_entry = await svc.begin_dispatch(
                session_id=state.get("session_id") or "",
                triggered_by=state.get("user_id") or "system",
                specialist_name=specialist_name,
                sub_agent_name=sub_agent_name,
                inputs_snapshot=inputs_snap,
            )
            await db.commit()
    except Exception as exc:
        logger.warning("specialist_dispatch_ledger_open_failed", error=str(exc))

    # ── Run the specialist ────────────────────────────────────────────────
    logger.info(
        "specialist_dispatch",
        session_id=state.get("session_id"),
        specialist=specialist_name,
        sub_agent=sub_agent_name,
        knowledge_confidence=state.get("knowledge_confidence"),
    )

    output: SpecialistOutput = await specialist.handle(inp)

    # ── Ledger: record result ─────────────────────────────────────────────
    if ledger_entry is not None:
        try:
            result_snap: dict[str, Any] = {
                "steps_count": len(output.steps),
                "confidence": output.confidence,
                "escalation_signal": output.escalation_signal,
                "message_preview": output.message[:120] if output.message else "",
            }
            async with async_session_factory() as db:
                # Re-merge into this session since ledger_entry is from a closed session
                merged_entry = await db.merge(ledger_entry)
                svc = ActionLedgerService(AgentActionLedgerRepository(db))
                await svc.complete_dispatch(
                    merged_entry,
                    result_snapshot=result_snap,
                    confidence=output.confidence,
                    escalation_signal=output.escalation_signal,
                )
                await db.commit()
        except Exception as exc:
            logger.warning("specialist_dispatch_ledger_complete_failed", error=str(exc))

    # ── Check escalation triggers using the same function as the graph ────
    state_after = dict(state)
    state_after["resolution_steps"] = [
        {"step_number": s.step_number, "instruction": s.instruction, "details": s.details}
        for s in output.steps
    ]
    state_after["resolution_confidence"] = output.confidence
    diag_after = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})
    for step_text in output.presented_steps:
        diag_after.record_suggested_steps([step_text])
    if output.escalation_signal:
        diag_after.phase = DiagnosticPhase.ESCALATING
    state_after["diagnostic_context"] = diag_after.to_dict()

    escalation_decision = evaluate_escalation(
        state_after,
        stage="progression",
        minimum_confidence=settings.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE,
        miss_threshold=settings.RESOLUTION_MISS_ESCALATE_THRESHOLD,
        max_turns=10,
    )

    result = _output_to_state(output, state)
    if escalation_decision.should_escalate or output.escalation_signal:
        result["should_escalate"] = True
        result["escalation_reason"] = output.escalation_signal or escalation_decision.trigger
    else:
        result["should_escalate"] = False
        result["escalation_reason"] = None

    return result


__all__ = ["specialist_dispatch_node"]
