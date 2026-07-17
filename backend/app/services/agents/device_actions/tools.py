"""Device-execution tools — typed, catalog-bound, policy-gated write tools.

These are the *only* way an agent can act on an endpoint. Each is a
:class:`~app.services.agents.tools.base.ToolSpec` write tool governed by the
:class:`~app.services.agents.tools.runtime.AgentToolRuntime` exactly like every
other tool (allow-list → arg validation → RBAC → audit). On top of that shared
gate, each tool's ``run`` enforces the two device-specific guardrails before it
will ever touch Intune:

1. **Catalog membership** — the ``*_id`` arg must resolve to a
   :mod:`~app.services.agents.device_actions.catalog` entry. The tool then uses
   the *catalog's* published Intune id as the execution payload; the LLM's args
   never carry an installer, script, or command. Off-catalog ⇒ typed ``denied``
   result, no execution.
2. **Autonomy policy** — :func:`~app.services.agents.device_actions.policy.
   evaluate_device_action` decides autonomous vs human-approval vs deny from the
   entry's risk tier, guardrail facts (device eligibility, consent), an
   injection scan of the free-text justification, and config. Anything that
   isn't cleared for autonomy returns a typed ``needs_approval`` result and does
   **not** execute — so a high-risk or suspicious request can never auto-run.

The ``ToolSpec.approval`` is ``human``: the ``AgentToolRuntime`` never executes a
device tool without an approval token in the context. Autonomy is granted by the
:class:`~app.services.agents.device_actions.service.DeviceExecutionService`,
which — and only which — mints that token *after* the pure policy returns
``autonomous`` for an approved, low-risk, consented action. Anything the policy
holds is parked in the shared human-approval queue instead; anything it denies is
never dispatched. ``run`` re-evaluates the policy as defense in depth, so an
off-catalog id is refused even if a token is somehow present.

Every dispatch is audited with arg/result hashes by the runtime, and the business
outcome (executed / needs_approval / denied) is explicit in the typed result.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.core.permissions import P
from app.services.agents.device_actions import catalog as cat
from app.services.agents.device_actions.catalog import CATALOG_VERSION, ActionKind
from app.services.agents.device_actions.guardrails import DeviceGuardrails, GuardrailFacts
from app.services.agents.device_actions.policy import (
    AUTONOMY_POLICY_VERSION,
    ExecutionDecision,
    PolicyInputs,
    evaluate_device_action,
)
from app.services.agents.mcp.session import SessionProvider, default_session_provider
from app.services.agents.tools.base import Approval, SideEffect, ToolContext, ToolSpec

logger = get_logger(__name__)


# ── Typed arg models ──────────────────────────────────────────────────────────
# Note what is NOT here: no installer URL, no script body, no shell command. The
# only levers are a catalog id, a device id, an idempotency key, and free-text
# justification (scanned, never executed).


class InstallAppArgs(BaseModel):
    app_id: str = Field(..., min_length=2, description="Catalog app id, e.g. 'python-3.12'.")
    device_id: str = Field(..., min_length=2, description="Target Intune managed device id.")
    idempotency_key: str = Field(..., min_length=8, description="Caller-generated dedupe key.")
    justification: str = Field("", description="Why this install is needed (scanned, not run).")


class RunRemediationArgs(BaseModel):
    remediation_id: str = Field(..., min_length=2, description="Catalog remediation id.")
    device_id: str = Field(..., min_length=2, description="Target Intune managed device id.")
    idempotency_key: str = Field(..., min_length=8, description="Caller-generated dedupe key.")
    justification: str = Field("", description="Why this remediation is needed (scanned).")


class DeviceActionArgs(BaseModel):
    action_id: str = Field(..., min_length=2, description="Catalog device action id, e.g. 'sync'.")
    device_id: str = Field(..., min_length=2, description="Target Intune managed device id.")
    idempotency_key: str = Field(..., min_length=8, description="Caller-generated dedupe key.")
    justification: str = Field("", description="Why this action is needed (scanned).")


class DeviceExecutionResult(BaseModel):
    """Uniform, self-describing outcome for every device-execution tool."""

    status: str = "denied"  # executed | needs_approval | denied | error
    execution_mode: str = "blocked"  # autonomous | human_approval | blocked
    action_kind: str = ""
    action_ref: str = ""
    device_id: str = ""
    risk_tier: str | None = None
    reason: str = ""
    policy_signals: list[str] = Field(default_factory=list)
    provider_correlation_id: str | None = None
    catalog_version: str = CATALOG_VERSION
    policy_version: str = AUTONOMY_POLICY_VERSION
    raw: dict = Field(default_factory=dict)


# ── Guardrail facts (the injection seam for eligibility + consent) ────────────


GuardrailProvider = Callable[[str, str, str | None, ToolContext], Awaitable[GuardrailFacts]]


# ── The tool ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _DeviceBinding:
    kind: ActionKind
    server_tool_name: str  # the tool name on the exec MCP server
    id_field: str  # which arg holds the catalog id


class DeviceExecutionTool:
    """A catalog-bound, policy-gated Intune execution tool."""

    def __init__(
        self,
        spec: ToolSpec,
        binding: _DeviceBinding,
        profile,
        session_provider: SessionProvider,
        *,
        timeout_seconds: float,
        autonomous_enabled: bool,
        autonomous_medium_allowed: bool,
        guardrail_provider: GuardrailProvider,
    ) -> None:
        self.spec = spec
        self._binding = binding
        self._profile = profile
        self._session_provider = session_provider
        self._timeout = timeout_seconds
        self._autonomous_enabled = autonomous_enabled
        self._autonomous_medium_allowed = autonomous_medium_allowed
        self._guardrail_provider = guardrail_provider

    def _resolve(self, action_ref: str):
        return cat.resolve(self._binding.kind, action_ref)

    @staticmethod
    def _intune_ref(entry) -> str:
        """The published Intune object id / action this catalog entry maps to."""
        for attr in ("intune_app_id", "intune_script_id", "graph_action"):
            val = getattr(entry, attr, None)
            if val:
                return val
        return ""

    async def run(self, args: BaseModel, context: ToolContext) -> DeviceExecutionResult:
        data = args.model_dump()
        action_ref = data[self._binding.id_field]
        device_id = data.get("device_id", "")
        justification = data.get("justification", "")
        kind = self._binding.kind.value

        entry = self._resolve(action_ref)

        facts = await self._guardrail_provider(kind, action_ref, device_id, context)
        decision = evaluate_device_action(
            PolicyInputs(
                entry=entry,
                device_id=device_id,
                device_eligible=facts.device_eligible,
                consent_present=facts.consent_present,
                justification=justification,
                autonomous_enabled=self._autonomous_enabled,
                autonomous_medium_allowed=self._autonomous_medium_allowed,
            )
        )

        base = dict(
            action_kind=kind,
            action_ref=action_ref,
            device_id=device_id,
            risk_tier=decision.risk_tier,
            reason=decision.reason,
            policy_signals=list(decision.signals),
        )

        # DENY — never touch Intune.
        if decision.decision is ExecutionDecision.DENY:
            return DeviceExecutionResult(status="denied", execution_mode="blocked", **base)

        # HUMAN_APPROVAL — hold unless a scoped approval token is present.
        if decision.decision is ExecutionDecision.HUMAN_APPROVAL and (
            self.spec.name not in context.approvals
        ):
            return DeviceExecutionResult(
                status="needs_approval", execution_mode="human_approval", **base
            )

        # AUTONOMOUS, or an approved human-gated action — execute via the server.
        execution_mode = (
            "autonomous" if decision.decision is ExecutionDecision.AUTONOMOUS else "human_approval"
        )
        payload = {
            "intune_ref": self._intune_ref(entry),
            "device_id": device_id,
            "idempotency_key": data["idempotency_key"],
            "action_ref": action_ref,
        }
        session = await self._session_provider(self._profile)
        try:
            raw = await asyncio.wait_for(
                session.call_tool(self._binding.server_tool_name, payload),
                timeout=self._timeout,
            )
        except TimeoutError:
            return DeviceExecutionResult(
                status="error",
                execution_mode=execution_mode,
                reason=f"execution timed out after {self._timeout}s",
                **{k: v for k, v in base.items() if k != "reason"},
            )
        except Exception as exc:  # noqa: BLE001 — surface as typed result, never crash
            logger.warning("device_exec_error", tool=self.spec.name, error=str(exc))
            return DeviceExecutionResult(
                status="error",
                execution_mode=execution_mode,
                reason=str(exc),
                **{k: v for k, v in base.items() if k != "reason"},
            )
        finally:
            close = getattr(session, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("device_exec_session_close_failed", error=str(exc))

        correlation = (raw or {}).get("correlation_id") or f"intune-{uuid.uuid4().hex[:16]}"
        return DeviceExecutionResult(
            status="executed",
            execution_mode=execution_mode,
            provider_correlation_id=correlation,
            raw=raw if isinstance(raw, dict) else {"value": raw},
            **base,
        )


# ── Specs + bindings ──────────────────────────────────────────────────────────

_PERMISSION = P.INTEGRATION_DEVICE_EXECUTE.value
_EXEC_SERVER = "msgraph_intune_exec"


def _spec(name: str, description: str, args_model) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        args_model=args_model,
        result_model=DeviceExecutionResult,
        side_effect=SideEffect.WRITE,
        required_permissions=(_PERMISSION,),
        # HUMAN-gated at the runtime: nothing executes without a token. The
        # DeviceExecutionService mints an autonomous token only after the policy
        # clears the action; otherwise it parks it for human approval.
        approval=Approval.HUMAN,
        mcp_server=_EXEC_SERVER,
    )


@dataclass(frozen=True)
class _ToolDef:
    spec: ToolSpec
    binding: _DeviceBinding


_TOOL_DEFS: tuple[_ToolDef, ...] = (
    _ToolDef(
        spec=_spec(
            "install_win32_app",
            "Install an approved application (by catalog id) on a managed device via Intune. "
            f"Allowed app ids: {', '.join(cat.app_ids())}.",
            InstallAppArgs,
        ),
        binding=_DeviceBinding(ActionKind.INSTALL_APP, "install_win32_app", "app_id"),
    ),
    _ToolDef(
        spec=_spec(
            "run_remediation_script",
            "Run an approved remediation (by catalog id) on a managed device via Intune. "
            f"Allowed remediation ids: {', '.join(cat.remediation_ids())}.",
            RunRemediationArgs,
        ),
        binding=_DeviceBinding(ActionKind.REMEDIATION, "run_remediation_script", "remediation_id"),
    ),
    _ToolDef(
        spec=_spec(
            "device_action",
            "Take an approved built-in device action (by catalog id) via Intune. "
            f"Allowed action ids: {', '.join(cat.device_action_ids())}.",
            DeviceActionArgs,
        ),
        binding=_DeviceBinding(ActionKind.DEVICE_ACTION, "device_action", "action_id"),
    ),
)


# Public map {tool_name: _DeviceBinding} so the service can resolve a tool's
# action kind + id field without re-declaring them.
DEVICE_TOOL_BINDINGS = {d.spec.name: d.binding for d in _TOOL_DEFS}
DEVICE_TOOL_SPECS = {d.spec.name: d.spec for d in _TOOL_DEFS}


def all_device_tool_specs() -> list[ToolSpec]:
    """Every declared device-execution spec (regardless of enablement) — for evals."""
    return [d.spec for d in _TOOL_DEFS]


def is_device_tool(tool_name: str) -> bool:
    return tool_name in DEVICE_TOOL_BINDINGS


def action_ref_for(tool_name: str, args: dict) -> str | None:
    """Extract the catalog id an invocation targets, given the tool + raw args."""
    binding = DEVICE_TOOL_BINDINGS.get(tool_name)
    return None if binding is None else args.get(binding.id_field)


def action_kind_for(tool_name: str) -> ActionKind | None:
    binding = DEVICE_TOOL_BINDINGS.get(tool_name)
    return None if binding is None else binding.kind


def build_device_execution_tools(
    *,
    feature_on: bool | None = None,
    autonomous_enabled: bool | None = None,
    autonomous_medium_allowed: bool | None = None,
    enabled_server_ids: list[str] | None = None,
    session_provider: SessionProvider | None = None,
    timeout_seconds: float | None = None,
    guardrail_provider: GuardrailProvider | None = None,
) -> dict[str, DeviceExecutionTool]:
    """Construct device-execution tools when the capability is enabled.

    Empty unless ``FEATURE_DEVICE_EXECUTION`` is on and the tool is on the exec
    server's ``allowed_tools``. ``enabled_server_ids`` is an *optional* extra
    filter: when ``None`` (the default) the feature flag alone gates, so the tools
    are available to the DeviceExecutionService / approval-queue runtime; when a
    list is passed, the exec server must be in it. ``autonomous_enabled`` is the
    kill-switch threaded into the policy.
    """
    from app.core.config import settings
    from app.services.agents.mcp import profiles as mcp_profiles

    feature_on = settings.FEATURE_DEVICE_EXECUTION if feature_on is None else feature_on
    if not feature_on:
        return {}

    autonomous_enabled = (
        settings.DEVICE_EXECUTION_AUTONOMOUS if autonomous_enabled is None else autonomous_enabled
    )
    autonomous_medium_allowed = (
        settings.DEVICE_EXECUTION_AUTONOMOUS_MEDIUM
        if autonomous_medium_allowed is None
        else autonomous_medium_allowed
    )
    provider = session_provider or default_session_provider
    timeout = timeout_seconds if timeout_seconds is not None else settings.MCP_TOOL_TIMEOUT_SECONDS
    # Default guardrails resolve real Intune eligibility + device-owner consent
    # (permissive only under MCP_USE_MOCK), so consent is enforced in the tool on
    # every execution path — not just at request time.
    guardrails = (
        guardrail_provider or DeviceGuardrails(session_provider=provider).as_tool_provider()
    )

    profile = mcp_profiles.get_profile(_EXEC_SERVER)
    if profile is None:
        return {}
    if enabled_server_ids is not None and _EXEC_SERVER not in set(enabled_server_ids):
        return {}

    tools: dict[str, DeviceExecutionTool] = {}
    for d in _TOOL_DEFS:
        if d.spec.name not in profile.allowed_tools:
            continue
        tools[d.spec.name] = DeviceExecutionTool(
            d.spec,
            d.binding,
            profile,
            provider,
            timeout_seconds=timeout,
            autonomous_enabled=autonomous_enabled,
            autonomous_medium_allowed=autonomous_medium_allowed,
            guardrail_provider=guardrails,
        )
    return tools


__all__ = [
    "DEVICE_TOOL_BINDINGS",
    "DEVICE_TOOL_SPECS",
    "DeviceActionArgs",
    "DeviceExecutionResult",
    "DeviceExecutionTool",
    "GuardrailFacts",
    "GuardrailProvider",
    "InstallAppArgs",
    "RunRemediationArgs",
    "action_kind_for",
    "action_ref_for",
    "all_device_tool_specs",
    "build_device_execution_tools",
    "is_device_tool",
]
