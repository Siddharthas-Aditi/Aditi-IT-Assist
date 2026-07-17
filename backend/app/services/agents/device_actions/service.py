"""DeviceExecutionService — the end-to-end orchestrator for device actions.

This is the one place that decides, for a requested catalog action, whether to
**execute autonomously**, **park for human approval**, or **deny** — and then
carries that decision out. It is the only component allowed to mint an
*autonomous* approval token, and it does so only after the pure autonomy policy
clears the action.

Flow (`request_action`):

1. Validate the tool is a device tool and the args are well-formed.
2. Gather guardrail facts (Intune eligibility + consent) via
   :class:`~app.services.agents.device_actions.guardrails.DeviceGuardrails`.
3. Run the pure policy (:func:`evaluate_device_action`).
4. Route:
   - **deny** → return a denied outcome; nothing is dispatched or queued.
   - **autonomous** → dispatch through the runtime under a scoped autonomous
     token (RBAC still enforced against the requester); return the executed
     result.
   - **human_approval** → ``propose`` into the shared approval queue so an
     it_lead actions it in the existing ``/agent-ops/approvals`` surface.

`approve` re-verifies eligibility + consent for the parked action's target
before delegating to the queue's ``execute_approved`` (so a consent revoked
between request and approval still blocks execution).

Every outcome is audited via the injected :class:`AuditService`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.services.agents.approvals import (
    ApprovalQueue,
    ApprovalStatus,
    PendingApproval,
    get_approval_queue,
)
from app.services.agents.device_actions import catalog as cat
from app.services.agents.device_actions.guardrails import DeviceGuardrails
from app.services.agents.device_actions.policy import (
    AUTONOMY_POLICY_VERSION,
    ExecutionDecision,
    PolicyInputs,
    evaluate_device_action,
)
from app.services.agents.device_actions.tools import (
    action_kind_for,
    action_ref_for,
    build_device_execution_tools,
    is_device_tool,
)
from app.services.agents.mcp.session import SessionProvider, default_session_provider
from app.services.agents.tools.base import ToolContext, ToolInvocation, ToolOutcomeStatus
from app.services.agents.tools.runtime import AgentToolRuntime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class DeviceExecOutcomeStatus(StrEnum):
    EXECUTED = "executed"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"
    REJECTED = "rejected"  # RBAC / validation failure
    ERROR = "error"


@dataclass
class DeviceExecOutcome:
    status: DeviceExecOutcomeStatus
    decision: str  # autonomous | human_approval | deny
    tool_name: str
    action_ref: str
    device_id: str
    reason: str = ""
    risk_tier: str | None = None
    approval_id: str | None = None
    result: dict[str, Any] | None = None
    policy_signals: list[str] = field(default_factory=list)
    policy_version: str = AUTONOMY_POLICY_VERSION


class DeviceExecutionService:
    """Route + carry out device actions with catalog + policy + consent gates."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        mcp_session_provider: SessionProvider | None = None,
        guardrails: DeviceGuardrails | None = None,
        approval_queue: ApprovalQueue | None = None,
        runtime: AgentToolRuntime | None = None,
        audit_service: Any | None = None,
        autonomous_enabled: bool | None = None,
        autonomous_medium_allowed: bool | None = None,
    ) -> None:
        from app.core.config import settings

        self._db = db
        self._provider = mcp_session_provider or default_session_provider
        self._guardrails = guardrails or DeviceGuardrails(session_provider=self._provider)
        self._queue = approval_queue or get_approval_queue()
        # Honour the autonomy kill-switch: when off, the policy degrades every
        # action to human approval (nothing auto-executes).
        self._autonomous_enabled = (
            settings.DEVICE_EXECUTION_AUTONOMOUS
            if autonomous_enabled is None
            else autonomous_enabled
        )
        self._autonomous_medium = (
            settings.DEVICE_EXECUTION_AUTONOMOUS_MEDIUM
            if autonomous_medium_allowed is None
            else autonomous_medium_allowed
        )
        # A runtime carrying only the device tools, used for the autonomous
        # dispatch path. Built with the same autonomy flags so the tool's
        # defense-in-depth policy re-check agrees with our routing decision.
        self._runtime = runtime or AgentToolRuntime(
            build_device_execution_tools(
                # Honour the build gate here too (defense-in-depth). Previously
                # hardcoded True, so any caller of this service built device
                # tools even with FEATURE_DEVICE_EXECUTION off — the flag was
                # only enforced at the API edge. When off, no device tools are
                # constructed and dispatch degrades safely.
                feature_on=settings.FEATURE_DEVICE_EXECUTION,
                autonomous_enabled=self._autonomous_enabled,
                autonomous_medium_allowed=self._autonomous_medium,
                session_provider=self._provider,
            )
        )
        self._audit = audit_service

    # ── Request → route → carry out ──────────────────────────────────────

    async def request_action(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        requester: ToolContext,
        employee_id: str,
        reason: str = "",
    ) -> DeviceExecOutcome:
        if not is_device_tool(tool_name):
            return DeviceExecOutcome(
                status=DeviceExecOutcomeStatus.REJECTED,
                decision="deny",
                tool_name=tool_name,
                action_ref="",
                device_id="",
                reason=f"{tool_name!r} is not a device-execution tool",
            )

        spec = self._runtime.get_spec(tool_name)
        if spec is None:
            return DeviceExecOutcome(
                status=DeviceExecOutcomeStatus.REJECTED,
                decision="deny",
                tool_name=tool_name,
                action_ref="",
                device_id="",
                reason="device execution is not enabled in this runtime",
            )
        # Validate args early so routing works off trusted values.
        try:
            spec.args_model.model_validate(args)
        except Exception as exc:  # noqa: BLE001
            return DeviceExecOutcome(
                status=DeviceExecOutcomeStatus.REJECTED,
                decision="deny",
                tool_name=tool_name,
                action_ref="",
                device_id="",
                reason=f"invalid arguments: {exc}",
            )

        action_ref = action_ref_for(tool_name, args) or ""
        device_id = args.get("device_id", "")
        kind = action_kind_for(tool_name)
        entry = cat.resolve(kind, action_ref) if kind else None

        facts = await self._guardrails.facts(device_id=device_id, employee_id=employee_id)
        decision = evaluate_device_action(
            PolicyInputs(
                entry=entry,
                device_id=device_id,
                device_eligible=facts.device_eligible,
                consent_present=facts.consent_present,
                justification=args.get("justification", ""),
                autonomous_enabled=self._autonomous_enabled,
                autonomous_medium_allowed=self._autonomous_medium,
            )
        )
        base = dict(
            tool_name=tool_name,
            action_ref=action_ref,
            device_id=device_id,
            reason=decision.reason,
            risk_tier=decision.risk_tier,
            policy_signals=list(decision.signals),
        )

        if decision.decision is ExecutionDecision.DENY:
            await self._audit_action("device_action_denied", requester, base)
            return DeviceExecOutcome(status=DeviceExecOutcomeStatus.DENIED, decision="deny", **base)

        if decision.decision is ExecutionDecision.HUMAN_APPROVAL:
            return await self._enqueue(tool_name, args, requester, reason or decision.reason, base)

        # AUTONOMOUS — mint a scoped token and dispatch. RBAC still enforced.
        ctx = ToolContext(
            user_id=requester.user_id,
            permissions=requester.permissions,
            roles=requester.roles,
            session_id=requester.session_id,
            approvals=frozenset({*requester.approvals, tool_name}),
        )
        outcome = await self._runtime.dispatch(
            ToolInvocation(tool_name, args), ctx, allowed_tools=(tool_name,)
        )
        if outcome.executed and outcome.result is not None:
            result = outcome.result.model_dump(mode="json")
            await self._audit_action("device_action_autonomous", requester, {**base, **result})
            return DeviceExecOutcome(
                status=DeviceExecOutcomeStatus.EXECUTED,
                decision="autonomous",
                result=result,
                **base,
            )
        # Requester isn't authorized to execute directly — gracefully fall back
        # to the human-approval queue (an authorized lead can carry it out) rather
        # than dropping the request. 0-unauthorized-execution is preserved.
        if outcome.status is ToolOutcomeStatus.REJECTED_FORBIDDEN:
            return await self._enqueue(
                tool_name,
                args,
                requester,
                reason or "autonomous eligible; requester unauthorized to execute",
                base,
            )
        await self._audit_action("device_action_error", requester, {**base, "error": outcome.error})
        return DeviceExecOutcome(
            status=DeviceExecOutcomeStatus.ERROR,
            decision="autonomous",
            reason=outcome.error or outcome.status.value,
            **{k: v for k, v in base.items() if k != "reason"},
        )

    async def _enqueue(
        self,
        tool_name: str,
        args: dict[str, Any],
        requester: ToolContext,
        reason: str,
        base: dict[str, Any],
    ) -> DeviceExecOutcome:
        """Park an action in the shared approval queue; honour the record status."""
        record = await self._queue.propose(
            tool_name=tool_name,
            raw_args=args,
            proposer_id=requester.user_id,
            reason=reason,
        )
        if record.status is not ApprovalStatus.PENDING:
            # The queue rejected the proposal (e.g. device execution not enabled in
            # its runtime, or bad args) — surface it rather than a false "pending".
            await self._audit_action(
                "device_action_error", requester, {**base, "error": record.error}
            )
            return DeviceExecOutcome(
                status=DeviceExecOutcomeStatus.ERROR,
                decision="human_approval",
                approval_id=record.id,
                **{k: v for k, v in base.items() if k != "reason"},
                reason=record.error or "approval proposal was not accepted",
            )
        await self._audit_action(
            "device_action_queued", requester, {**base, "approval_id": record.id}
        )
        return DeviceExecOutcome(
            status=DeviceExecOutcomeStatus.PENDING_APPROVAL,
            decision="human_approval",
            approval_id=record.id,
            **base,
        )

    # ── Approve a parked device action ───────────────────────────────────

    async def approve(
        self, approval_id: str, *, approver: ToolContext, employee_id: str
    ) -> PendingApproval:
        """Re-verify consent + eligibility, then execute the approved action."""
        record = self._queue.get(approval_id)
        if record is None:
            raise KeyError(approval_id)
        device_id = record.raw_args.get("device_id", "")
        facts = await self._guardrails.facts(device_id=device_id, employee_id=employee_id)
        if not facts.consent_present or not facts.device_eligible:
            # Do not execute; reject with a clear reason (audited by the queue read).
            rejected = self._queue.reject(approval_id, approver.user_id)
            logger.info(
                "device_action_approval_blocked",
                approval_id=approval_id,
                consent=facts.consent_present,
                eligible=facts.device_eligible,
            )
            return rejected
        return await self._queue.approve(approval_id, approver)

    def reject(self, approval_id: str, approver_id: str) -> PendingApproval:
        return self._queue.reject(approval_id, approver_id)

    # ── Audit helper ─────────────────────────────────────────────────────

    async def _audit_action(
        self, action: str, requester: ToolContext, payload: dict[str, Any]
    ) -> None:
        if self._audit is None:
            logger.info("device_exec", action=action, actor=requester.user_id, **_safe(payload))
            return
        try:
            await self._audit.log(
                action=action,
                resource_type="device_action",
                resource_id=str(payload.get("device_id") or ""),
                description=str(payload.get("reason") or action),
                new_value={**_safe(payload), "actor_id": requester.user_id},
            )
        except Exception as exc:  # noqa: BLE001 — never let auditing break the flow
            logger.warning("device_exec_audit_failed", action=action, error=str(exc))


def _safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep audit payloads JSON-friendly and compact."""
    return {k: v for k, v in payload.items() if isinstance(v, (str, int, float, bool, list, dict))}


__all__ = ["DeviceExecOutcome", "DeviceExecOutcomeStatus", "DeviceExecutionService"]
