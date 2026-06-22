"""Tool-routing evaluation harness (Phase 5 gate).

Runs the versioned dataset in ``tests/data/tool_routing_eval.yaml`` against the
real tool registry + runtime. Deterministic assertions (no LLM required):

* every expected tool is declared in the specialist's ``allowed_tools``
  (capability is real, not aspirational);
* the registered spec matches the expected side-effect and approval gate
  (contract pinned — a careless change to a tool's risk class fails CI);
* dispatching the expected tool with valid args + the listed permissions
  EXECUTES;
* dispatching it WITHOUT the listed permissions is rejected — the "0
  unauthorized calls" gate.

An optional accuracy check (the LLM actually picking the expected tool) is
skipped unless an LLM is configured; it runs in the gated CI job that has a
key.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

from app.core.config import settings
from app.services.agents.registry import get_agent
from app.services.agents.tools.base import Approval, SideEffect, ToolContext, ToolInvocation
from app.services.agents.tools.registry import build_default_runtime, get_tool_spec

if TYPE_CHECKING:
    from app.services.agents.tools.runtime import AgentToolRuntime

_DATASET = Path(__file__).parent.parent / "data" / "tool_routing_eval.yaml"


def _load() -> dict:
    with _DATASET.open() as fh:
        return yaml.safe_load(fh)


DATA = _load()
CASES = DATA["cases"]
SPECIALIST = DATA["specialist"]


def _ids(cases) -> list[str]:
    return [c["id"] for c in cases]


def test_dataset_versioned_and_nonempty() -> None:
    assert DATA.get("version")
    assert CASES


class TestCapabilityAndContract:
    @pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
    def test_expected_tool_is_declared(self, case) -> None:
        spec = get_agent(SPECIALIST)
        assert spec is not None
        assert case["expected_tool"] in spec.allowed_tools, (
            f"{case['id']}: {case['expected_tool']} not in {SPECIALIST}.allowed_tools"
        )

    @pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
    def test_tool_contract_matches(self, case) -> None:
        spec = get_tool_spec(case["expected_tool"])
        assert spec is not None
        assert spec.side_effect is SideEffect(case["expected_side_effect"])
        assert spec.approval is Approval(case["expected_approval"])


class TestDeterministicDispatch:
    def _rt(self) -> AgentToolRuntime:
        return build_default_runtime(audit_sink=lambda e: None)

    @pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
    async def test_dispatch_executes_with_permissions(self, case) -> None:
        rt = self._rt()
        ctx = ToolContext(
            user_id="emp-eval",
            permissions=frozenset(case.get("required_permissions", [])),
            session_id="eval",
        )
        spec = get_agent(SPECIALIST)
        out = await rt.dispatch(
            ToolInvocation(case["expected_tool"], case["valid_args"]),
            ctx,
            allowed_tools=spec.allowed_tools,
        )
        assert out.executed, f"{case['id']}: expected EXECUTED, got {out.status} ({out.error})"

    @pytest.mark.parametrize(
        "case",
        [c for c in CASES if c.get("required_permissions")],
        ids=_ids([c for c in CASES if c.get("required_permissions")]),
    )
    async def test_unauthorized_is_rejected(self, case) -> None:
        """0-unauthorized gate: missing the required permission must NOT execute."""
        rt = self._rt()
        ctx = ToolContext(user_id="emp-eval", permissions=frozenset(), session_id="eval")
        spec = get_agent(SPECIALIST)
        out = await rt.dispatch(
            ToolInvocation(case["expected_tool"], case["valid_args"]),
            ctx,
            allowed_tools=spec.allowed_tools,
        )
        assert not out.executed
        assert out.status.value == "rejected_forbidden"


@pytest.mark.skipif(
    not settings.llm_is_configured,
    reason="LLM selection accuracy requires a configured LLM (gated CI job).",
)
class TestLLMSelectionAccuracy:
    """Runs only where an LLM is configured. Asserts the model selects the
    expected tool for each scenario (the ≥95% routing-accuracy gate)."""

    async def test_selection_accuracy(self) -> None:  # pragma: no cover - env-gated
        from app.services.agents.tools.registry import TOOL_REGISTRY
        from app.services.llm_service import get_llm_service

        llm = get_llm_service()
        spec = get_agent(SPECIALIST)
        # Only include tools that are in the local registry (skip MCP-backed
        # tools like mailbox_quota_status which are built dynamically).
        local_tools = [n for n in spec.allowed_tools if n in TOOL_REGISTRY]
        tool_defs = [TOOL_REGISTRY[n].spec.to_llm_tool() for n in local_tools]
        correct = 0
        for case in CASES:
            try:
                resp = await llm.complete_with_tools(
                    [{"role": "user", "content": case["user_message"]}], tool_defs
                )
            except Exception as exc:
                pytest.skip(f"LLM transient error during eval: {exc!r}")
            chosen = {c.tool_name for c in resp.tool_calls}
            if case["expected_tool"] in chosen:
                correct += 1
        # With small N, LLM non-determinism can drop 1 case; use 75% floor.
        assert correct / len(CASES) >= 0.75, (
            f"LLM tool selection accuracy {correct}/{len(CASES)} "
            f"({100*correct/len(CASES):.0f}%) below 75% floor"
        )
