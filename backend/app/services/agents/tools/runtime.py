"""AgentToolRuntime — the single enforcement point for agent tool calls.

Every tool invocation an agent makes goes through :meth:`AgentToolRuntime.dispatch`.
The runtime is the *only* place that:

1. checks the tool is in the agent's declared allow-list (``allowed_tools``);
2. checks the tool exists in the registry;
3. validates the raw args against the tool's ``args_model`` (Pydantic);
4. enforces RBAC (``required_permissions`` ⊆ caller permissions);
5. enforces the approval gate (human-gated tools do **not** execute without an
   explicit approval token in the context);
6. executes the tool and records an audit entry — for *every* path, including
   rejections.

Keeping all of this in one place is what lets the rest of the system stay
honest: a specialist cannot reach a tool it didn't declare, a caller cannot run
a tool it isn't authorized for, and no write action can fire without approval.
The same runtime serves the synchronous chat loop today and (Phase 8) the
background task runner.

The runtime takes no hard dependency on the LLM provider or the DB: the LLM is
passed in per loop, and audit is an injectable sink (defaults to structlog).
This makes the guardrails fully unit-testable without network or database.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.logging import get_logger
from app.services.agents.tools.base import (
    Approval,
    LLMToolResponse,
    Tool,
    ToolContext,
    ToolInvocation,
    ToolOutcome,
    ToolOutcomeStatus,
    ToolSpec,
)

logger = get_logger(__name__)

# Audit sink signature: receives a flat dict of event fields. Defaults to a
# structlog emit. Phase 8 swaps in a sink that writes AuditEvent rows.
AuditSink = Callable[[dict[str, Any]], None]


def _default_audit_sink(event: dict[str, Any]) -> None:
    logger.info("agent_tool_call", **event)


# Hard safety cap on tool calls per loop, independent of any caller-supplied
# value — defense against a misbehaving model spinning the loop.
_ABSOLUTE_MAX_ITERS = 8


@dataclass(frozen=True)
class ProposedAction:
    """A human-gated tool call captured for approval (Phase 8).

    Carries everything the queue UI / API needs to render an approve/reject
    decision, and everything the runtime needs to execute it verbatim once
    approved — so what a human approves is exactly what runs.
    """

    invocation: ToolInvocation
    tool_name: str
    side_effect: str
    mcp_server: str | None
    description: str
    args_hash: str


@dataclass
class ToolLoopResult:
    """Outcome of a bounded tool-use loop."""

    message: str
    outcomes: list[ToolOutcome] = field(default_factory=list)
    # Tool calls that were gated and need human approval before they run.
    pending_approvals: list[ToolOutcome] = field(default_factory=list)
    # Richer, executable proposals for the approval UI (parallel to the above).
    proposed_actions: list[ProposedAction] = field(default_factory=list)
    iterations: int = 0
    stopped_reason: str = "completed"  # completed | max_iters | needs_approval


class AgentToolRuntime:
    """Validates, authorizes, audits, and dispatches agent tool calls."""

    def __init__(
        self,
        tools: dict[str, Tool],
        *,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._tools = dict(tools)
        self._audit = audit_sink or _default_audit_sink

    # ── Introspection ────────────────────────────────────────────────────

    def get_spec(self, name: str) -> ToolSpec | None:
        tool = self._tools.get(name)
        return tool.spec if tool else None

    def llm_tool_defs(self, allowed_tools: tuple[str, ...]) -> list[dict[str, Any]]:
        """LiteLLM/OpenAI tool definitions for the agent's allowed tools only.

        Unknown names in ``allowed_tools`` are silently skipped here — the
        authoritative rejection happens in :meth:`dispatch`, so a stale
        allow-list entry can never widen what actually runs.
        """
        defs: list[dict[str, Any]] = []
        for name in allowed_tools:
            tool = self._tools.get(name)
            if tool is not None:
                defs.append(tool.spec.to_llm_tool())
        return defs

    # ── Single dispatch (the guardrail) ──────────────────────────────────

    async def dispatch(
        self,
        invocation: ToolInvocation,
        context: ToolContext,
        *,
        allowed_tools: tuple[str, ...],
    ) -> ToolOutcome:
        """Run one tool invocation through every gate. Never raises for control
        flow — failures become typed :class:`ToolOutcome` rejections so the
        caller (and the LLM loop) can react deterministically."""
        name = invocation.tool_name

        def _emit(status: ToolOutcomeStatus, **extra: Any) -> ToolOutcome:
            result_obj = extra.get("result")
            audit = {
                "tool": name,
                "status": status.value,
                "user_id": context.user_id,
                "session_id": context.session_id,
                "call_id": invocation.call_id,
                # Hash (not raw) args/results so the audit trail is complete and
                # tamper-evident without persisting potentially sensitive payloads.
                "args_hash": _hash_obj(invocation.raw_args),
                "result_hash": _hash_model(result_obj),
                **{k: v for k, v in extra.items() if k != "result"},
            }
            self._audit(audit)
            return ToolOutcome(
                tool_name=name,
                status=status,
                call_id=invocation.call_id,
                error=extra.get("error"),
                result=result_obj,
                audit=audit,
            )

        # 1. Allow-list — the agent may only call tools it declared.
        if name not in allowed_tools:
            return _emit(
                ToolOutcomeStatus.REJECTED_NOT_ALLOWED,
                error=f"tool {name!r} not in agent allow-list",
            )

        # 2. Existence — the tool must be registered.
        tool = self._tools.get(name)
        if tool is None:
            return _emit(
                ToolOutcomeStatus.REJECTED_UNKNOWN, error=f"tool {name!r} not found in registry"
            )

        spec = tool.spec

        # 3. Arg validation — typed boundary; the LLM never reaches tool logic
        #    with malformed args.
        try:
            args = spec.args_model.model_validate(invocation.raw_args)
        except ValidationError as exc:
            return _emit(
                ToolOutcomeStatus.INVALID_ARGS,
                error=f"argument validation failed: {exc.error_count()} error(s)",
            )

        # 4. RBAC — caller must hold every required permission.
        missing = [p for p in spec.required_permissions if p not in context.permissions]
        if missing:
            return _emit(
                ToolOutcomeStatus.REJECTED_FORBIDDEN,
                error=f"missing permission(s): {', '.join(missing)}",
                side_effect=spec.side_effect.value,
            )

        # 5. Approval gate — human-gated tools require an explicit approval token.
        #    AUTO_ALLOWLISTED executes; HUMAN without approval is held, never run.
        if spec.approval is Approval.HUMAN and name not in context.approvals:
            return _emit(
                ToolOutcomeStatus.NEEDS_APPROVAL,
                side_effect=spec.side_effect.value,
                approval=spec.approval.value,
            )

        # 6. Execute.
        try:
            result = await tool.run(args, context)
        except Exception as exc:  # noqa: BLE001 — surface as typed outcome, never crash the turn
            logger.warning("agent_tool_error", tool=name, error=str(exc))
            return _emit(
                ToolOutcomeStatus.ERROR, error=str(exc), side_effect=spec.side_effect.value
            )

        return _emit(ToolOutcomeStatus.EXECUTED, result=result, side_effect=spec.side_effect.value)

    # ── Human approval flow (Phase 8) ────────────────────────────────────

    def _propose(self, invocation: ToolInvocation, outcome: ToolOutcome) -> ProposedAction:
        spec = self.get_spec(invocation.tool_name)
        return ProposedAction(
            invocation=invocation,
            tool_name=invocation.tool_name,
            side_effect=spec.side_effect.value if spec else "unknown",
            mcp_server=spec.mcp_server if spec else None,
            description=spec.description if spec else "",
            args_hash=outcome.audit.get("args_hash", ""),
        )

    @staticmethod
    def approved_context(context: ToolContext, tool_name: str, *, approver_id: str) -> ToolContext:
        """Return a context that authorizes ONE tool's execution.

        The approver becomes the acting principal (audited as ``user_id``) and
        must themselves hold the tool's ``required_permissions`` — approval does
        not bypass RBAC. The approval token is scoped to ``tool_name`` only.
        """
        return ToolContext(
            user_id=approver_id,
            permissions=context.permissions,
            roles=context.roles,
            session_id=context.session_id,
            approvals=frozenset({*context.approvals, tool_name}),
        )

    async def execute_approved(
        self,
        proposed: ProposedAction,
        approver_context: ToolContext,
        *,
        allowed_tools: tuple[str, ...],
        approver_id: str,
    ) -> ToolOutcome:
        """Execute a previously-proposed, human-approved action — verbatim.

        Runs the exact captured invocation through the full gate again under an
        approval-bearing context, so RBAC, allow-list, validation, audit (with
        args/result hashes) and idempotency all still apply. The only thing the
        approval changes is clearing the human-approval gate for this one tool.
        """
        ctx = self.approved_context(approver_context, proposed.tool_name, approver_id=approver_id)
        return await self.dispatch(proposed.invocation, ctx, allowed_tools=allowed_tools)

    # ── Bounded tool-use loop ────────────────────────────────────────────

    async def run_loop(
        self,
        *,
        messages: list[dict[str, Any]],
        allowed_tools: tuple[str, ...],
        llm: Any,
        context: ToolContext,
        max_iters: int = 4,
    ) -> ToolLoopResult:
        """Drive an LLM tool-use loop, bounded and audited.

        ``llm`` must expose
        ``async complete_with_tools(messages, tools) -> LLMToolResponse``.
        The loop appends each tool result back into ``messages`` and re-prompts
        until the model returns final text, a human-gated tool is hit, or the
        iteration cap is reached. The cap is the lower of ``max_iters`` and the
        absolute safety ceiling.
        """
        cap = max(1, min(max_iters, _ABSOLUTE_MAX_ITERS))
        tool_defs = self.llm_tool_defs(allowed_tools)
        convo = list(messages)
        result = ToolLoopResult(message="")

        for i in range(cap):
            result.iterations = i + 1
            response: LLMToolResponse = await llm.complete_with_tools(convo, tools=tool_defs)

            if not response.tool_calls:
                result.message = response.text or ""
                result.stopped_reason = "completed"
                return result

            # Record the assistant's tool-call turn so the conversation stays
            # coherent for the follow-up completion.
            convo.append(
                {
                    "role": "assistant",
                    "content": response.text or "",
                    "tool_calls": [
                        {"id": c.call_id, "name": c.tool_name, "arguments": c.raw_args}
                        for c in response.tool_calls
                    ],
                }
            )

            hit_approval = False
            for call in response.tool_calls:
                outcome = await self.dispatch(call, context, allowed_tools=allowed_tools)
                result.outcomes.append(outcome)
                if outcome.status is ToolOutcomeStatus.NEEDS_APPROVAL:
                    result.pending_approvals.append(outcome)
                    result.proposed_actions.append(self._propose(call, outcome))
                    hit_approval = True
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "name": call.tool_name,
                        "content": _outcome_to_tool_message(outcome),
                    }
                )

            if hit_approval:
                # Do not keep looping past a gated action — surface it for
                # approval and let the caller resume after a human decides.
                result.stopped_reason = "needs_approval"
                return result

        result.stopped_reason = "max_iters"
        return result


def _hash_obj(obj: Any) -> str:
    """Stable short SHA-256 of a JSON-serializable object (for audit trails)."""
    import hashlib
    import json

    try:
        payload = json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        payload = repr(obj)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _hash_model(result: Any) -> str | None:
    """SHA-256 of a Pydantic result model's JSON, or None when there's no result."""
    if result is None:
        return None
    if isinstance(result, BaseModel):
        return _hash_obj(result.model_dump(mode="json"))
    return _hash_obj(result)


def _outcome_to_tool_message(outcome: ToolOutcome) -> str:
    """Serialize a tool outcome into the content the LLM sees next turn."""
    if outcome.executed and isinstance(outcome.result, BaseModel):
        return outcome.result.model_dump_json()
    if outcome.status is ToolOutcomeStatus.NEEDS_APPROVAL:
        return '{"status": "needs_approval", "note": "awaiting human approval"}'
    return f'{{"status": "{outcome.status.value}", "error": {outcome.error!r}}}'


# Coroutine type alias kept for callers that want to type an injected runtime.
RunLoop = Callable[..., Awaitable[ToolLoopResult]]

__all__ = ["AgentToolRuntime", "AuditSink", "ProposedAction", "ToolLoopResult"]
