"""Device-execution safety eval harness (Phase 9 gate).

Runs ``tests/data/device_execution_safety_eval.yaml`` against the real catalog,
policy engine, tool specs, and runtime. Deterministic (pure policy + fake
session). Enforces the two hard gates:

* **0 autonomous above threshold** — no HIGH-risk action (and no MEDIUM unless
  explicitly opted in) ever resolves to an autonomous decision or an executed
  tool result;
* **0 off-catalog executions** — anything not in the approved catalog is denied
  and never touches the (fake) server.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.services.agents.device_actions import catalog as cat
from app.services.agents.device_actions.catalog import CATALOG_VERSION, ActionKind
from app.services.agents.device_actions.policy import (
    AUTONOMY_POLICY_VERSION,
    ExecutionDecision,
    PolicyInputs,
    evaluate_device_action,
)
from app.services.agents.device_actions.tools import (
    GuardrailFacts,
    all_device_tool_specs,
    build_device_execution_tools,
)
from app.services.agents.mcp import profiles as mcp_profiles
from app.services.agents.tools.base import Approval, SideEffect, ToolContext, ToolInvocation
from app.services.agents.tools.runtime import AgentToolRuntime

_DATASET = Path(__file__).parent.parent / "data" / "device_execution_safety_eval.yaml"
with _DATASET.open() as fh:
    DATA = yaml.safe_load(fh)

POLICY_CASES = DATA["policy_cases"]
CONTRACT = DATA["contract"]
_EXEC_SERVER = "msgraph_intune_exec"

_KIND_MAP = {
    "install_app": ActionKind.INSTALL_APP,
    "remediation": ActionKind.REMEDIATION,
    "device_action": ActionKind.DEVICE_ACTION,
}


def _ids(items):
    return [c["name"] for c in items]


def _resolve(kind: str, ref: str):
    match _KIND_MAP[kind]:
        case ActionKind.INSTALL_APP:
            return cat.get_app(ref)
        case ActionKind.REMEDIATION:
            return cat.get_remediation(ref)
        case ActionKind.DEVICE_ACTION:
            return cat.get_device_action(ref)


def _inputs(case: dict) -> PolicyInputs:
    return PolicyInputs(
        entry=_resolve(case["kind"], case["ref"]),
        device_id=case.get("device_id", "DEV-1"),
        device_eligible=case.get("device_eligible", True),
        consent_present=case.get("consent_present", True),
        justification=case.get("justification", ""),
        autonomous_enabled=case.get("autonomous_enabled", True),
        autonomous_medium_allowed=case.get("autonomous_medium_allowed", False),
    )


# ── Versioning ────────────────────────────────────────────────────────────────


def test_dataset_versioned() -> None:
    assert DATA.get("version")
    assert DATA["catalog_version"] == CATALOG_VERSION
    assert DATA["policy_version"] == AUTONOMY_POLICY_VERSION
    assert POLICY_CASES


# ── Contract pins ─────────────────────────────────────────────────────────────


class TestContract:
    def test_specs_are_typed_write_and_permissioned(self) -> None:
        specs = {s.name: s for s in all_device_tool_specs()}
        assert set(specs) == set(CONTRACT["tools"])
        for spec in specs.values():
            assert spec.side_effect is SideEffect(CONTRACT["side_effect"])
            assert CONTRACT["permission"] in spec.required_permissions
            assert spec.mcp_server == CONTRACT["server"]
            # HUMAN-gated: the runtime never executes without a token. Autonomy is
            # granted only by DeviceExecutionService after the policy clears it.
            assert spec.approval is Approval.HUMAN

    def test_exec_server_allowlist(self) -> None:
        profile = mcp_profiles.get_profile(_EXEC_SERVER)
        assert profile is not None
        for name in CONTRACT["tools"]:
            assert name in profile.allowed_tools


# ── Policy decisions ──────────────────────────────────────────────────────────


class TestPolicyDecisions:
    @pytest.mark.parametrize("case", POLICY_CASES, ids=_ids(POLICY_CASES))
    def test_expected_decision(self, case) -> None:
        decision = evaluate_device_action(_inputs(case))
        assert decision.decision.value == case["expect"]

    def test_no_autonomous_above_threshold(self) -> None:
        """Hard gate: HIGH is never autonomous; MEDIUM only when opted in."""
        for case in POLICY_CASES:
            entry = _resolve(case["kind"], case["ref"])
            if entry is None:
                continue
            decision = evaluate_device_action(_inputs(case))
            if decision.decision is ExecutionDecision.AUTONOMOUS:
                assert entry.risk_tier.value in ("low", "medium")
                if entry.risk_tier.value == "medium":
                    assert case.get("autonomous_medium_allowed") is True

    def test_off_catalog_always_denied(self) -> None:
        for case in POLICY_CASES:
            if _resolve(case["kind"], case["ref"]) is None:
                assert evaluate_device_action(_inputs(case)).is_denied


# ── Runtime dispatch (fake session) ───────────────────────────────────────────


class TestRuntimeDispatch:
    def _runtime(self, *, autonomous: bool, medium: bool = False, eligible=True, consent=True):
        calls: list[str] = []

        class _Sess:
            async def call_tool(self, name, arguments):
                calls.append(name)
                return {"correlation_id": "intune-abc", "accepted": True}

            async def close(self):
                return None

        async def provider(profile):
            return _Sess()

        async def guardrails(kind, ref, device_id, ctx):
            return GuardrailFacts(device_eligible=eligible, consent_present=consent)

        tools = build_device_execution_tools(
            feature_on=True,
            autonomous_enabled=autonomous,
            autonomous_medium_allowed=medium,
            enabled_server_ids=[_EXEC_SERVER],
            session_provider=provider,
            guardrail_provider=guardrails,
        )
        return AgentToolRuntime(tools, audit_sink=lambda e: None), calls

    def _ctx(self, *perms: str, approvals=()):
        return ToolContext(
            user_id="agent-svc",
            permissions=frozenset(perms),
            approvals=frozenset(approvals),
        )

    def _install(self, app="python-3.12"):
        return ToolInvocation(
            "install_win32_app",
            {"app_id": app, "device_id": "DEV-1", "idempotency_key": "idem-1234"},
        )

    async def test_unauthorized_rejected(self) -> None:
        rt, calls = self._runtime(autonomous=True)
        out = await rt.dispatch(
            self._install(),
            self._ctx(approvals=("install_win32_app",)),  # token but NO permission
            allowed_tools=("install_win32_app",),
        )
        assert out.status.value == "rejected_forbidden"
        assert calls == []  # RBAC is checked before the approval gate; never runs

    async def test_no_token_held_by_runtime(self) -> None:
        # HUMAN-gated: with the permission but no approval token, the runtime holds
        # the call for approval and run() is never reached (nothing executes).
        rt, calls = self._runtime(autonomous=True)
        out = await rt.dispatch(
            self._install(),
            self._ctx("integration:device_execute"),
            allowed_tools=("install_win32_app",),
        )
        assert out.status.value == "needs_approval"
        assert calls == []

    async def test_token_low_risk_executes(self) -> None:
        # A scoped token (as the service mints for an autonomous decision) executes.
        rt, calls = self._runtime(autonomous=True)
        out = await rt.dispatch(
            self._install(),
            self._ctx("integration:device_execute", approvals=("install_win32_app",)),
            allowed_tools=("install_win32_app",),
        )
        assert out.executed and out.result.status == "executed"
        assert out.result.execution_mode == "autonomous"
        assert calls == ["install_win32_app"]

    async def test_off_catalog_denied_even_with_token(self) -> None:
        # Defense in depth: even an approved token can't run an off-catalog id.
        rt, calls = self._runtime(autonomous=True)
        out = await rt.dispatch(
            self._install(app="evil-payload"),
            self._ctx("integration:device_execute", approvals=("install_win32_app",)),
            allowed_tools=("install_win32_app",),
        )
        assert out.result.status == "denied"
        assert calls == []

    async def test_ineligible_denied_even_with_token(self) -> None:
        rt, calls = self._runtime(autonomous=True, eligible=False)
        out = await rt.dispatch(
            self._install(),
            self._ctx("integration:device_execute", approvals=("install_win32_app",)),
            allowed_tools=("install_win32_app",),
        )
        assert out.result.status == "denied"
        assert calls == []

    async def test_feature_off_builds_nothing(self) -> None:
        tools = build_device_execution_tools(feature_on=False, enabled_server_ids=[_EXEC_SERVER])
        assert tools == {}
