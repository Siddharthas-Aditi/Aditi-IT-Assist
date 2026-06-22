"""MCP tool contract evaluation harness (Phase 7 gate).

Runs ``tests/data/mcp_contract_eval.yaml`` against the real binding specs,
profile registry, and runtime. Deterministic (fake session): pins each MCP
tool's typed contract, allow-list membership, side-effect ceiling, RBAC, and
the 0-unauthorized gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.services.agents.mcp import profiles as mcp_profiles
from app.services.agents.mcp.tools import all_binding_specs, build_mcp_tools
from app.services.agents.tools.base import Approval, SideEffect, ToolContext, ToolInvocation
from app.services.agents.tools.runtime import AgentToolRuntime

_DATASET = Path(__file__).parent.parent / "data" / "mcp_contract_eval.yaml"

with _DATASET.open() as fh:
    DATA = yaml.safe_load(fh)

TOOLS = DATA["tools"]
_SE_ORDER = {SideEffect.READ: 0, SideEffect.WRITE: 1, SideEffect.DESTRUCTIVE: 2}
_SPECS = {s.name: s for s in all_binding_specs()}


def _ids(items):
    return [t["name"] for t in items]


def test_dataset_versioned() -> None:
    assert DATA.get("version")
    assert DATA.get("profile_version") == mcp_profiles.MCP_PROFILE_VERSION
    assert TOOLS


class TestContract:
    @pytest.mark.parametrize("case", TOOLS, ids=_ids(TOOLS))
    def test_typed_spec_exists_and_mcp_tagged(self, case) -> None:
        spec = _SPECS.get(case["name"])
        assert spec is not None
        assert spec.mcp_server == case["server"]
        assert spec.side_effect is SideEffect(case["side_effect"])
        assert spec.approval is Approval(case["approval"])
        assert case["permission"] in spec.required_permissions

    @pytest.mark.parametrize("case", TOOLS, ids=_ids(TOOLS))
    def test_within_allowlist_and_ceiling(self, case) -> None:
        profile = mcp_profiles.get_profile(case["server"])
        assert profile is not None
        assert case["name"] in profile.allowed_tools
        spec = _SPECS[case["name"]]
        assert _SE_ORDER[spec.side_effect] <= _SE_ORDER[profile.side_effect_ceiling]


class TestDispatchGate:
    def _runtime(self):
        class _Sess:
            async def call_tool(self, name, arguments):
                return {}

            async def close(self):
                return None

        async def provider(profile):
            return _Sess()

        tools = build_mcp_tools(
            feature_on=True,
            enabled_server_ids=[p.server_id for p in mcp_profiles.list_profiles()],
            session_provider=provider,
        )
        return AgentToolRuntime(tools, audit_sink=lambda e: None)

    @pytest.mark.parametrize("case", TOOLS, ids=_ids(TOOLS))
    async def test_unauthorized_rejected(self, case) -> None:
        rt = self._runtime()
        out = await rt.dispatch(
            ToolInvocation(case["name"], case["valid_args"]),
            ToolContext(user_id="x", permissions=frozenset()),  # no permission
            allowed_tools=(case["name"],),
        )
        assert out.status.value == "rejected_forbidden"

    @pytest.mark.parametrize("case", TOOLS, ids=_ids(TOOLS))
    async def test_authorized_executes(self, case) -> None:
        rt = self._runtime()
        out = await rt.dispatch(
            ToolInvocation(case["name"], case["valid_args"]),
            ToolContext(user_id="x", permissions=frozenset({case["permission"]})),
            allowed_tools=(case["name"],),
        )
        assert out.executed
