"""MCP-backed read-only diagnostic tools (Phase 7).

Four tools that let agents *diagnose against live systems* through MCP servers,
governed identically to local tools by the :class:`AgentToolRuntime`:

* ``entra_account_status``      — Entra ID account / lock / MFA state
* ``intune_device_compliance``  — Intune device compliance state
* ``mailbox_quota_status``      — real Exchange mailbox usage vs quota
* ``servicenow_incident_lookup``— ServiceNow incident summary

Each is a typed :class:`ToolSpec` (``mcp_server`` set, ``side_effect=read``,
``approval=none``, RBAC via ``integration:*`` permissions). The
:class:`McpBackedTool` validates inputs (the runtime does this against
``args_model`` before ``run``), calls the server tool over an injected
:class:`McpSession` with a hard timeout, and parses the structured result into
the typed ``result_model`` — degrading to a typed runtime ERROR (never a crash)
on timeout or server failure, so the agent falls back to KB-only guidance.

Tools are only built for servers that are both **enabled** (``FEATURE_MCP_TOOLS``
+ ``MCP_ENABLED_SERVERS``) and declare the tool in their profile ``allowed_tools``.
A binding whose side effect exceeds the server's ceiling is rejected at build
time.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.core.permissions import P
from app.services.agents.mcp import profiles as mcp_profiles
from app.services.agents.mcp.session import SessionProvider, default_session_provider
from app.services.agents.tools.base import Approval, SideEffect, ToolContext, ToolSpec

if TYPE_CHECKING:  # pragma: no cover
    from app.services.agents.mcp.profiles import McpServerProfile

logger = get_logger(__name__)


# ── Typed arg/result models ──────────────────────────────────────────────────


class EntraAccountStatusArgs(BaseModel):
    user_principal_name: str = Field(..., min_length=3, description="UPN / email of the user.")


class EntraAccountStatusResult(BaseModel):
    user_principal_name: str = ""
    account_enabled: bool = True
    locked: bool = False
    mfa_registered: bool = False
    last_sign_in: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class IntuneDeviceComplianceArgs(BaseModel):
    device_id: str | None = Field(None, description="Intune device id.")
    user_principal_name: str | None = Field(None, description="UPN to look up devices for.")


class IntuneDeviceComplianceResult(BaseModel):
    device_id: str | None = None
    compliance_state: str = "unknown"  # compliant | noncompliant | unknown
    os: str | None = None
    last_check_in: str | None = None
    noncompliant_reasons: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class MailboxQuotaStatusArgs(BaseModel):
    mailbox: str = Field(..., min_length=3, description="Mailbox / UPN to inspect.")


class MailboxQuotaStatusResult(BaseModel):
    mailbox: str = ""
    used_gb: float = 0.0
    quota_gb: float = 0.0
    percent_used: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict)


class ServiceNowIncidentLookupArgs(BaseModel):
    number: str = Field(..., min_length=2, description="Incident number, e.g. INC0012345.")


class ServiceNowIncidentLookupResult(BaseModel):
    number: str = ""
    state: str | None = None
    short_description: str | None = None
    assigned_to: str | None = None
    opened_at: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


# ── Write tools (Phase 8) — human-approved, idempotent where possible ────────


class EntraUnlockAccountArgs(BaseModel):
    user_principal_name: str = Field(..., min_length=3, description="UPN of the account to unlock.")
    # Idempotency key lets the server dedupe retries of the same intended action.
    idempotency_key: str = Field(..., min_length=8, description="Caller-generated dedupe key.")


class EntraUnlockAccountResult(BaseModel):
    user_principal_name: str = ""
    unlocked: bool = False
    already_unlocked: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class ResetMfaArgs(BaseModel):
    user_principal_name: str = Field(..., min_length=3, description="UPN whose MFA to reset.")
    idempotency_key: str = Field(..., min_length=8, description="Caller-generated dedupe key.")


class ResetMfaResult(BaseModel):
    user_principal_name: str = ""
    mfa_reset: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class ServiceNowCreateIncidentArgs(BaseModel):
    short_description: str = Field(..., min_length=5, description="Incident summary.")
    description: str = Field("", description="Detail / steps already tried.")
    urgency: str = Field("normal", description="low | normal | high")
    idempotency_key: str = Field(..., min_length=8, description="Caller-generated dedupe key.")


class ServiceNowCreateIncidentResult(BaseModel):
    number: str = ""
    created: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


# ── Binding: our tool ⇄ a server tool ────────────────────────────────────────


@dataclass(frozen=True)
class _Binding:
    spec: ToolSpec
    server_id: str
    mcp_tool_name: str               # the tool name on the server
    result_model: type[BaseModel]


def _spec(name: str, server_id: str, description: str, args_model, result_model,
          permission: str, *, side_effect: SideEffect = SideEffect.READ,
          approval: Approval = Approval.NONE) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        args_model=args_model,
        result_model=result_model,
        side_effect=side_effect,
        required_permissions=(permission,),
        approval=approval,
        mcp_server=server_id,
    )


_BINDINGS: tuple[_Binding, ...] = (
    _Binding(
        spec=_spec(
            "entra_account_status", "msgraph",
            "Look up an Entra ID account's enabled/locked/MFA state to diagnose sign-in issues.",
            EntraAccountStatusArgs, EntraAccountStatusResult, P.INTEGRATION_DIRECTORY_READ.value,
        ),
        server_id="msgraph", mcp_tool_name="get_user_account_status",
        result_model=EntraAccountStatusResult,
    ),
    _Binding(
        spec=_spec(
            "intune_device_compliance", "msgraph",
            "Check an Intune device's compliance state and reasons to diagnose access blocks.",
            IntuneDeviceComplianceArgs, IntuneDeviceComplianceResult,
            P.INTEGRATION_DIRECTORY_READ.value,
        ),
        server_id="msgraph", mcp_tool_name="get_device_compliance",
        result_model=IntuneDeviceComplianceResult,
    ),
    _Binding(
        spec=_spec(
            "mailbox_quota_status", "msgraph",
            "Read a mailbox's real usage vs quota from Exchange to confirm a full-mailbox issue.",
            MailboxQuotaStatusArgs, MailboxQuotaStatusResult, P.INTEGRATION_DIRECTORY_READ.value,
        ),
        server_id="msgraph", mcp_tool_name="get_mailbox_usage",
        result_model=MailboxQuotaStatusResult,
    ),
    _Binding(
        spec=_spec(
            "servicenow_incident_lookup", "servicenow",
            "Look up a ServiceNow incident's state and summary by number.",
            ServiceNowIncidentLookupArgs, ServiceNowIncidentLookupResult,
            P.INTEGRATION_TICKETING_READ.value,
        ),
        server_id="servicenow", mcp_tool_name="get_incident",
        result_model=ServiceNowIncidentLookupResult,
    ),
    # ── Write tools (Phase 8): WRITE side effect + HUMAN approval ──
    _Binding(
        spec=_spec(
            "entra_unlock_account", "msgraph",
            "Unlock a locked Entra ID account. Reversible; idempotent via idempotency_key.",
            EntraUnlockAccountArgs, EntraUnlockAccountResult,
            P.INTEGRATION_DIRECTORY_WRITE.value,
            side_effect=SideEffect.WRITE, approval=Approval.HUMAN,
        ),
        server_id="msgraph", mcp_tool_name="unlock_account",
        result_model=EntraUnlockAccountResult,
    ),
    _Binding(
        spec=_spec(
            "reset_mfa", "msgraph",
            "Reset a user's MFA registration so they can re-enrol. Idempotent via idempotency_key.",
            ResetMfaArgs, ResetMfaResult,
            P.INTEGRATION_DIRECTORY_WRITE.value,
            side_effect=SideEffect.WRITE, approval=Approval.HUMAN,
        ),
        server_id="msgraph", mcp_tool_name="reset_mfa",
        result_model=ResetMfaResult,
    ),
    _Binding(
        spec=_spec(
            "servicenow_create_incident", "servicenow",
            "Create a ServiceNow incident. Idempotent via idempotency_key.",
            ServiceNowCreateIncidentArgs, ServiceNowCreateIncidentResult,
            P.INTEGRATION_TICKETING_WRITE.value,
            side_effect=SideEffect.WRITE, approval=Approval.HUMAN,
        ),
        server_id="servicenow", mcp_tool_name="create_incident",
        result_model=ServiceNowCreateIncidentResult,
    ),
)


class McpBackedTool:
    """A :class:`Tool` whose execution is delegated to an MCP server."""

    def __init__(
        self,
        binding: _Binding,
        profile: McpServerProfile,
        session_provider: SessionProvider,
        *,
        timeout_seconds: float,
    ) -> None:
        self.spec = binding.spec
        self._binding = binding
        self._profile = profile
        self._session_provider = session_provider
        self._timeout = timeout_seconds

    async def run(self, args: BaseModel, context: ToolContext) -> BaseModel:
        request_args = args.model_dump(exclude_none=True)
        session = await self._session_provider(self._profile)
        try:
            raw = await asyncio.wait_for(
                session.call_tool(self._binding.mcp_tool_name, request_args),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                f"MCP call timed out after {self._timeout}s "
                f"({self._profile.server_id}/{self._binding.mcp_tool_name})"
            ) from exc
        finally:
            close = getattr(session, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("mcp_session_close_failed", error=str(exc))
        return self._parse(raw, request_args)

    def _parse(self, raw: dict[str, Any], request_args: dict[str, Any]) -> BaseModel:
        """Map a server's structured result into the typed result model.

        Unknown/extra fields are preserved under ``raw`` rather than dropped;
        identifier fields the server omits are backfilled from the request args
        so the result is always self-describing; and a shape we can't map still
        yields a valid (mostly-empty) typed result rather than raising.
        """
        model = self._binding.result_model
        data = dict(raw) if isinstance(raw, dict) else {"raw": {"value": raw}}
        known = set(model.model_fields)
        mapped = {k: v for k, v in data.items() if k in known}
        # Backfill identifier fields the server didn't echo (e.g. the UPN/number).
        for k, v in request_args.items():
            if k in known:
                mapped.setdefault(k, v)
        mapped.setdefault("raw", {k: v for k, v in data.items() if k not in known})
        try:
            return model.model_validate(mapped)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_result_parse_failed", tool=self.spec.name, error=str(exc))
            return model.model_validate({"raw": data}) if "raw" in known else model()


def build_mcp_tools(
    *,
    feature_on: bool | None = None,
    enabled_server_ids: list[str] | None = None,
    session_provider: SessionProvider | None = None,
    timeout_seconds: float | None = None,
    write_actions_on: bool | None = None,
) -> dict[str, McpBackedTool]:
    """Construct MCP-backed tools for currently-enabled servers.

    Returns ``{tool_name: McpBackedTool}``. Empty when the feature is off or no
    server is enabled. Enforces, at build time:
      * the tool is in its server's profile ``allowed_tools`` (allow-list);
      * the tool's side effect does not exceed the server's ceiling;
      * **write/destructive tools are only built when ``write_actions_on``**
        (``FEATURE_AGENT_WRITE_ACTIONS``) — so a Phase-7 deployment stays
        strictly read-only even though the servers' ceilings now permit writes.
        (Execution of any such tool is additionally human-approved by the
        runtime, regardless of this flag.)
    """
    feature_on = settings.FEATURE_MCP_TOOLS if feature_on is None else feature_on
    enabled_server_ids = (
        list(settings.MCP_ENABLED_SERVERS) if enabled_server_ids is None else enabled_server_ids
    )
    write_actions_on = (
        settings.FEATURE_AGENT_WRITE_ACTIONS if write_actions_on is None else write_actions_on
    )
    provider = session_provider or default_session_provider
    timeout = timeout_seconds if timeout_seconds is not None else settings.MCP_TOOL_TIMEOUT_SECONDS

    enabled = {p.server_id: p for p in mcp_profiles.enabled_profiles(
        feature_on=feature_on, enabled_server_ids=enabled_server_ids
    )}
    tools: dict[str, McpBackedTool] = {}
    for binding in _BINDINGS:
        profile = enabled.get(binding.server_id)
        if profile is None:
            continue
        if binding.spec.name not in profile.allowed_tools:
            # Declared tool not on this server's allow-list — never expose it.
            continue
        if binding.spec.side_effect is not SideEffect.READ and not write_actions_on:
            # Write/destructive tool, but write actions are disabled — don't build.
            continue
        _assert_within_ceiling(binding, profile)
        tools[binding.spec.name] = McpBackedTool(
            binding, profile, provider, timeout_seconds=timeout
        )
    return tools


_SIDE_EFFECT_ORDER = {SideEffect.READ: 0, SideEffect.WRITE: 1, SideEffect.DESTRUCTIVE: 2}


def _assert_within_ceiling(binding: _Binding, profile: McpServerProfile) -> None:
    tool_level = _SIDE_EFFECT_ORDER[binding.spec.side_effect]
    ceiling = _SIDE_EFFECT_ORDER[profile.side_effect_ceiling]
    if tool_level > ceiling:
        raise RuntimeError(
            f"MCP tool {binding.spec.name!r} side_effect {binding.spec.side_effect} "
            f"exceeds server {profile.server_id!r} ceiling {profile.side_effect_ceiling}"
        )


def all_binding_specs() -> list[ToolSpec]:
    """Every declared MCP tool spec (regardless of enablement) — for contract evals."""
    return [b.spec for b in _BINDINGS]


# Exposed for tests / evals that need binding metadata.
BindingSpec = Callable[[], list[ToolSpec]]

__all__ = [
    "EntraAccountStatusArgs",
    "EntraAccountStatusResult",
    "EntraUnlockAccountArgs",
    "EntraUnlockAccountResult",
    "IntuneDeviceComplianceArgs",
    "IntuneDeviceComplianceResult",
    "MailboxQuotaStatusArgs",
    "MailboxQuotaStatusResult",
    "McpBackedTool",
    "ResetMfaArgs",
    "ResetMfaResult",
    "ServiceNowCreateIncidentArgs",
    "ServiceNowCreateIncidentResult",
    "ServiceNowIncidentLookupArgs",
    "ServiceNowIncidentLookupResult",
    "all_binding_specs",
    "build_mcp_tools",
]
