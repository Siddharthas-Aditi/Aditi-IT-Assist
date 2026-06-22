"""Unit tests for the MCP client layer (Phase 7).

No live MCP server, no SDK: a fake :class:`McpSession` drives the
:class:`McpBackedTool` and the :class:`AgentToolRuntime`. Covers:
- profile registry shape + allow-list / side-effect-ceiling enforcement;
- build_mcp_tools enablement gating;
- McpBackedTool success (typed result), timeout, and server-error → typed
  runtime ERROR (graceful degradation, never a crash);
- RBAC + allow-list rejection through the runtime;
- args/result hashes present in the audit trail.
"""

from __future__ import annotations

import asyncio

from app.core.permissions import P
from app.services.agents.mcp import profiles as mcp_profiles
from app.services.agents.mcp.tools import (
    EntraAccountStatusResult,
    all_binding_specs,
    build_mcp_tools,
)
from app.services.agents.tools.base import (
    SideEffect,
    ToolContext,
    ToolInvocation,
    ToolOutcomeStatus,
)
from app.services.agents.tools.runtime import AgentToolRuntime

DIR = P.INTEGRATION_DIRECTORY_READ.value


class FakeSession:
    """Fake MCP session returning canned results or raising/hanging."""

    def __init__(self, *, result=None, raise_exc=None, hang=False) -> None:
        self._result = result if result is not None else {}
        self._raise = raise_exc
        self._hang = hang
        self.closed = False
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self):
        return []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self._hang:
            await asyncio.sleep(10)
        if self._raise:
            raise self._raise
        return self._result

    async def close(self):
        self.closed = True


def _provider(session):
    async def provider(profile):
        return session
    return provider


def _ctx(*perms: str) -> ToolContext:
    return ToolContext(user_id="agent-1", permissions=frozenset(perms), session_id="s1")


# ── Profiles ─────────────────────────────────────────────────────────────────


class TestProfiles:
    def test_registry_versioned_and_nonempty(self) -> None:
        assert mcp_profiles.MCP_PROFILE_VERSION
        assert mcp_profiles.MCP_SERVER_REGISTRY

    def test_no_destructive_servers(self) -> None:
        # Phase 8 raised ceilings to WRITE for human-approved actions; nothing
        # is allowed to declare DESTRUCTIVE tools.
        for p in mcp_profiles.list_profiles():
            assert p.side_effect_ceiling in (SideEffect.READ, SideEffect.WRITE)

    def test_enabled_requires_flag_and_listing(self) -> None:
        assert mcp_profiles.enabled_profiles(feature_on=False, enabled_server_ids=["msgraph"]) == []
        enabled = mcp_profiles.enabled_profiles(feature_on=True, enabled_server_ids=["msgraph"])
        assert [p.server_id for p in enabled] == ["msgraph"]


# ── Binding contracts ────────────────────────────────────────────────────────


class TestBindings:
    def test_every_binding_is_typed_and_mcp_tagged(self) -> None:
        specs = all_binding_specs()
        assert len(specs) == 7  # 4 read (Phase 7) + 3 write (Phase 8)
        for spec in specs:
            assert spec.mcp_server  # tagged as MCP-backed
            assert spec.side_effect in (SideEffect.READ, SideEffect.WRITE)
            assert spec.required_permissions  # RBAC declared

    def test_bindings_within_server_allowlist(self) -> None:
        for spec in all_binding_specs():
            profile = mcp_profiles.get_profile(spec.mcp_server)
            assert profile is not None
            assert spec.name in profile.allowed_tools


# ── build_mcp_tools enablement ───────────────────────────────────────────────


class TestBuild:
    def test_off_yields_nothing(self) -> None:
        assert build_mcp_tools(feature_on=False, enabled_server_ids=[]) == {}

    def test_enabled_server_exposes_its_tools(self) -> None:
        tools = build_mcp_tools(
            feature_on=True,
            enabled_server_ids=["msgraph"],
            session_provider=_provider(FakeSession()),
        )
        expected = {"entra_account_status", "intune_device_compliance",
                    "mailbox_quota_status"}
        assert expected.issubset(set(tools))

    def test_servicenow_isolated(self) -> None:
        tools = build_mcp_tools(
            feature_on=True, enabled_server_ids=["servicenow"],
            session_provider=_provider(FakeSession()),
        )
        assert "servicenow_incident_lookup" in set(tools)


# ── McpBackedTool execution via the runtime ──────────────────────────────────


class TestExecution:
    def _runtime(self, session):
        self.events: list[dict] = []
        tools = build_mcp_tools(
            feature_on=True, enabled_server_ids=["msgraph"],
            session_provider=_provider(session), timeout_seconds=0.2,
        )
        return AgentToolRuntime(tools, audit_sink=self.events.append)

    async def test_success_returns_typed_result(self) -> None:
        session = FakeSession(result={
            "user_principal_name": "alice@aditi.com",
            "account_enabled": True, "locked": True, "mfa_registered": True,
        })
        rt = self._runtime(session)
        out = await rt.dispatch(
            ToolInvocation("entra_account_status", {"user_principal_name": "alice@aditi.com"}),
            _ctx(DIR),
            allowed_tools=("entra_account_status",),
        )
        assert out.status is ToolOutcomeStatus.EXECUTED
        assert isinstance(out.result, EntraAccountStatusResult)
        assert out.result.locked is True
        assert session.closed is True  # session released

    async def test_unknown_fields_preserved_in_raw(self) -> None:
        session = FakeSession(result={"user_principal_name": "a@b.com", "weird_field": 7})
        rt = self._runtime(session)
        out = await rt.dispatch(
            ToolInvocation("entra_account_status", {"user_principal_name": "a@b.com"}),
            _ctx(DIR), allowed_tools=("entra_account_status",),
        )
        assert out.result.raw.get("weird_field") == 7

    async def test_timeout_degrades_to_error(self) -> None:
        # A hung server must become a typed ERROR (graceful degradation), never a
        # crash. The exact message ("timed out") is only produced on Python 3.11+
        # where asyncio.TimeoutError aliases the builtin TimeoutError this code
        # catches (the repo targets 3.12); the version-independent contract is
        # simply that the turn does not crash and the outcome is ERROR.
        rt = self._runtime(FakeSession(hang=True))
        out = await rt.dispatch(
            ToolInvocation("entra_account_status", {"user_principal_name": "a@b.com"}),
            _ctx(DIR), allowed_tools=("entra_account_status",),
        )
        assert out.status is ToolOutcomeStatus.ERROR

    async def test_server_error_degrades_to_error(self) -> None:
        rt = self._runtime(FakeSession(raise_exc=RuntimeError("graph 500")))
        out = await rt.dispatch(
            ToolInvocation("entra_account_status", {"user_principal_name": "a@b.com"}),
            _ctx(DIR), allowed_tools=("entra_account_status",),
        )
        assert out.status is ToolOutcomeStatus.ERROR

    async def test_rbac_denied_without_permission(self) -> None:
        rt = self._runtime(FakeSession(result={"user_principal_name": "a@b.com"}))
        out = await rt.dispatch(
            ToolInvocation("entra_account_status", {"user_principal_name": "a@b.com"}),
            _ctx(),  # missing integration:directory_read
            allowed_tools=("entra_account_status",),
        )
        assert out.status is ToolOutcomeStatus.REJECTED_FORBIDDEN

    async def test_not_in_agent_allowlist_rejected(self) -> None:
        rt = self._runtime(FakeSession(result={"user_principal_name": "a@b.com"}))
        out = await rt.dispatch(
            ToolInvocation("entra_account_status", {"user_principal_name": "a@b.com"}),
            _ctx(DIR),
            allowed_tools=("kb_search",),  # this agent can't call entra
        )
        assert out.status is ToolOutcomeStatus.REJECTED_NOT_ALLOWED

    async def test_audit_has_arg_and_result_hashes(self) -> None:
        session = FakeSession(result={"user_principal_name": "a@b.com", "locked": False})
        rt = self._runtime(session)
        await rt.dispatch(
            ToolInvocation("entra_account_status", {"user_principal_name": "a@b.com"}),
            _ctx(DIR), allowed_tools=("entra_account_status",),
        )
        event = self.events[-1]
        assert event["args_hash"]
        assert event["result_hash"]
