"""Action-safety evaluation harness (Phase 8 gate).

Runs ``tests/data/action_safety_eval.yaml`` against the real write-tool bindings
and runtime with a fake MCP session that records whether the underlying action
actually ran. Asserts the central Phase-8 safety contract:

* every write tool is ``write`` + ``human``-approval;
* dispatch without approval is held (``needs_approval``) and **does not run** —
  the 0-unapproved-execution gate;
* dispatch with approval + permission executes verbatim.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.services.agents.mcp import profiles as mcp_profiles
from app.services.agents.mcp.tools import all_binding_specs, build_mcp_tools
from app.services.agents.tools.base import Approval, SideEffect, ToolContext, ToolInvocation
from app.services.agents.tools.runtime import AgentToolRuntime, ProposedAction

_DATASET = Path(__file__).parent.parent / "data" / "action_safety_eval.yaml"
with _DATASET.open() as fh:
    DATA = yaml.safe_load(fh)

WRITE_TOOLS = DATA["write_tools"]
_SPECS = {s.name: s for s in all_binding_specs()}


def _ids(items):
    return [t["name"] for t in items]


class _RecordingSession:
    """Fake MCP session that records every actual call (proves no execution)."""

    calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, arguments):
        type(self).calls.append((name, arguments))
        return {}

    async def close(self):
        return None


def _runtime():
    _RecordingSession.calls = []

    async def provider(profile):
        return _RecordingSession()

    tools = build_mcp_tools(
        feature_on=True,
        enabled_server_ids=[p.server_id for p in mcp_profiles.list_profiles()],
        write_actions_on=True,  # write tools built
        session_provider=provider,
    )
    return AgentToolRuntime(tools, audit_sink=lambda e: None), tools


def test_dataset_versioned() -> None:
    assert DATA.get("version")
    assert WRITE_TOOLS


class TestWriteToolContract:
    @pytest.mark.parametrize("case", WRITE_TOOLS, ids=_ids(WRITE_TOOLS))
    def test_write_and_human_gated(self, case) -> None:
        spec = _SPECS[case["name"]]
        assert spec.side_effect is SideEffect.WRITE  # never destructive in Phase 8
        assert spec.approval is Approval.HUMAN
        assert case["permission"] in spec.required_permissions


class TestZeroUnapprovedExecution:
    @pytest.mark.parametrize("case", WRITE_TOOLS, ids=_ids(WRITE_TOOLS))
    async def test_not_executed_without_approval(self, case) -> None:
        rt, _ = _runtime()
        ctx = ToolContext(user_id="lead-1", permissions=frozenset({case["permission"]}))
        out = await rt.dispatch(
            ToolInvocation(case["name"], case["valid_args"]),
            ctx,  # holds permission, but NO approval token
            allowed_tools=(case["name"],),
        )
        assert out.status.value == "needs_approval"
        # The crux: the MCP server was never called.
        assert _RecordingSession.calls == []

    @pytest.mark.parametrize("case", WRITE_TOOLS, ids=_ids(WRITE_TOOLS))
    async def test_executes_after_approval(self, case) -> None:
        rt, _ = _runtime()
        ctx = ToolContext(user_id="lead-1", permissions=frozenset({case["permission"]}))
        # Simulate the propose → approve → execute flow.
        proposed = ProposedAction(
            invocation=ToolInvocation(case["name"], case["valid_args"]),
            tool_name=case["name"],
            side_effect="write",
            mcp_server=case["server"],
            description="",
            args_hash="x",
        )
        out = await rt.execute_approved(
            proposed, ctx, allowed_tools=(case["name"],), approver_id="lead-1"
        )
        assert out.executed
        assert len(_RecordingSession.calls) == 1  # exactly one underlying call

    @pytest.mark.parametrize("case", WRITE_TOOLS, ids=_ids(WRITE_TOOLS))
    async def test_approval_does_not_bypass_rbac(self, case) -> None:
        """An approver lacking the write permission still cannot execute."""
        rt, _ = _runtime()
        ctx = ToolContext(user_id="agent-1", permissions=frozenset())  # no write perm
        proposed = ProposedAction(
            invocation=ToolInvocation(case["name"], case["valid_args"]),
            tool_name=case["name"],
            side_effect="write",
            mcp_server=case["server"],
            description="",
            args_hash="x",
        )
        out = await rt.execute_approved(
            proposed, ctx, allowed_tools=(case["name"],), approver_id="agent-1"
        )
        assert out.status.value == "rejected_forbidden"
        assert _RecordingSession.calls == []


class TestBuildGating:
    def test_write_tools_absent_when_flag_off(self) -> None:
        tools = build_mcp_tools(
            feature_on=True,
            enabled_server_ids=[p.server_id for p in mcp_profiles.list_profiles()],
            write_actions_on=False,
            session_provider=None,
        )
        assert "entra_unlock_account" not in tools
        assert "reset_mfa" not in tools
        assert "servicenow_create_incident" not in tools
        # Read tools remain available.
        assert "entra_account_status" in tools
