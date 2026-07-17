"""Unit tests for the agent tool-calling layer (Phase 5).

Covers the contracts that gate every agent action:
- tool registry shape + versioning;
- each local tool's behaviour (pure where applicable);
- the runtime guardrails: allow-list, existence, arg validation, RBAC,
  approval gate (the "0 unauthorized writes" guarantee), and audit emission;
- the bounded LLM tool-use loop driven by a scripted fake LLM.

No network, no DB — the LLM and KB search are injected fakes.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.core.permissions import P
from app.services.agents.tools.base import (
    Approval,
    LLMToolResponse,
    SideEffect,
    ToolContext,
    ToolInvocation,
    ToolOutcomeStatus,
    ToolSpec,
)
from app.services.agents.tools.local_tools import (
    KbSearchTool,
    MailboxQuotaArgs,
    MailboxQuotaEstimateTool,
    TicketDraftArgs,
    TicketDraftTool,
)
from app.services.agents.tools.registry import (
    TOOL_REGISTRY,
    TOOL_REGISTRY_VERSION,
    build_default_runtime,
    list_tool_specs,
)
from app.services.agents.tools.runtime import AgentToolRuntime

ALL_TOOLS = ("kb_search", "mailbox_quota_estimate", "ticket_draft")


def _ctx(*perms: str, approvals: tuple[str, ...] = ()) -> ToolContext:
    return ToolContext(
        user_id="emp-1",
        permissions=frozenset(perms),
        session_id="sess-1",
        approvals=frozenset(approvals),
    )


# ── Registry ─────────────────────────────────────────────────────────────────


class TestToolRegistry:
    def test_three_tools_registered(self) -> None:
        assert set(TOOL_REGISTRY) == set(ALL_TOOLS)

    def test_version_pinned(self) -> None:
        assert TOOL_REGISTRY_VERSION

    def test_specs_sorted_and_typed(self) -> None:
        specs = list_tool_specs()
        assert [s.name for s in specs] == sorted(ALL_TOOLS)
        for s in specs:
            assert issubclass(s.args_model, BaseModel)
            assert issubclass(s.result_model, BaseModel)

    def test_all_phase5_tools_are_read_only(self) -> None:
        for s in list_tool_specs():
            assert s.side_effect is SideEffect.READ
            assert s.approval is Approval.NONE

    def test_to_llm_tool_shape(self) -> None:
        spec = TOOL_REGISTRY["kb_search"].spec
        defn = spec.to_llm_tool()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "kb_search"
        assert "properties" in defn["function"]["parameters"]


# ── Local tools ────────────────────────────────────────────────────────────


class TestMailboxQuotaTool:
    @pytest.mark.parametrize(
        ("used", "quota", "status", "over"),
        [(10, 50, "ok", False), (47, 50, "near_full", False), (50, 50, "over_quota", True)],
    )
    async def test_status_classification(self, used, quota, status, over) -> None:
        tool = MailboxQuotaEstimateTool()
        res = await tool.run(MailboxQuotaArgs(used_gb=used, quota_gb=quota), _ctx())
        assert res.status == status
        assert res.over_quota is over

    async def test_percent_and_headroom(self) -> None:
        tool = MailboxQuotaEstimateTool()
        res = await tool.run(MailboxQuotaArgs(used_gb=25, quota_gb=50), _ctx())
        assert res.percent_used == 50.0
        assert res.headroom_gb == 25.0


class TestTicketDraftTool:
    async def test_never_persists(self) -> None:
        tool = TicketDraftTool()
        res = await tool.run(
            TicketDraftArgs(subject="VPN down", summary="cannot connect", urgency="HIGH"),
            _ctx(),
        )
        assert res.persisted is False
        assert res.urgency == "high"  # normalized
        assert "cannot connect" in res.body

    async def test_invalid_urgency_defaults_normal(self) -> None:
        tool = TicketDraftTool()
        res = await tool.run(TicketDraftArgs(subject="abc", summary="def", urgency="bogus"), _ctx())
        assert res.urgency == "normal"


class TestKbSearchTool:
    async def test_uses_injected_search(self) -> None:
        from app.services.knowledge_service import RetrievalResult

        async def fake_search(query, *, category=None, limit=5):
            return RetrievalResult(
                articles=[{"title": "Free up mailbox space", "summary": "Delete old items"}],
                confidence=0.8,
                source="keyword",
            )

        tool = KbSearchTool(search_fn=fake_search)
        from app.services.agents.tools.local_tools import KbSearchArgs

        res = await tool.run(KbSearchArgs(query="mailbox full"), _ctx(P.KNOWLEDGE_READ.value))
        assert len(res.hits) == 1
        assert res.hits[0].title == "Free up mailbox space"
        assert res.confidence == 0.8


# ── Runtime guardrails ───────────────────────────────────────────────────────


class TestRuntimeGuardrails:
    def _runtime(self) -> AgentToolRuntime:
        # Capture audit events so we can assert every path is audited.
        self.events: list[dict] = []
        return build_default_runtime(audit_sink=self.events.append)

    async def test_executes_allowed_read_tool(self) -> None:
        rt = self._runtime()
        out = await rt.dispatch(
            ToolInvocation("mailbox_quota_estimate", {"used_gb": 10, "quota_gb": 50}),
            _ctx(),
            allowed_tools=ALL_TOOLS,
        )
        assert out.status is ToolOutcomeStatus.EXECUTED
        assert out.result is not None
        assert self.events  # audited

    async def test_rejects_tool_not_in_allowlist(self) -> None:
        rt = self._runtime()
        out = await rt.dispatch(
            ToolInvocation("mailbox_quota_estimate", {"used_gb": 1}),
            _ctx(),
            allowed_tools=("kb_search",),  # not allowed here
        )
        assert out.status is ToolOutcomeStatus.REJECTED_NOT_ALLOWED

    async def test_rejects_unknown_tool(self) -> None:
        rt = self._runtime()
        out = await rt.dispatch(
            ToolInvocation("delete_everything", {}),
            _ctx(),
            allowed_tools=("delete_everything",),  # allow-listed but not registered
        )
        assert out.status is ToolOutcomeStatus.REJECTED_UNKNOWN

    async def test_invalid_args_rejected(self) -> None:
        rt = self._runtime()
        out = await rt.dispatch(
            ToolInvocation("mailbox_quota_estimate", {"used_gb": -5}),  # ge=0 violated
            _ctx(),
            allowed_tools=ALL_TOOLS,
        )
        assert out.status is ToolOutcomeStatus.INVALID_ARGS

    async def test_rbac_denies_without_permission(self) -> None:
        rt = self._runtime()
        out = await rt.dispatch(
            ToolInvocation("kb_search", {"query": "vpn"}),
            _ctx(),  # no knowledge:read
            allowed_tools=ALL_TOOLS,
        )
        assert out.status is ToolOutcomeStatus.REJECTED_FORBIDDEN

    async def test_rbac_allows_with_permission(self) -> None:
        rt = self._runtime()

        async def fake_search(query, *, category=None, limit=5):
            from app.services.knowledge_service import RetrievalResult

            return RetrievalResult(articles=[], confidence=0.0)

        rt = AgentToolRuntime(
            {"kb_search": KbSearchTool(search_fn=fake_search)},
            audit_sink=self.events.append,
        )
        out = await rt.dispatch(
            ToolInvocation("kb_search", {"query": "vpn"}),
            _ctx(P.KNOWLEDGE_READ.value),
            allowed_tools=("kb_search",),
        )
        assert out.status is ToolOutcomeStatus.EXECUTED

    async def test_tool_error_becomes_typed_outcome(self) -> None:
        self.events = []

        class Boom:
            spec = ToolSpec(
                name="boom",
                args_model=MailboxQuotaArgs,
                result_model=MailboxQuotaArgs,
                side_effect=SideEffect.READ,
            )

            async def run(self, args, context):
                raise ValueError("kaboom")

        rt = AgentToolRuntime({"boom": Boom()}, audit_sink=self.events.append)
        out = await rt.dispatch(
            ToolInvocation("boom", {"used_gb": 1}), _ctx(), allowed_tools=("boom",)
        )
        assert out.status is ToolOutcomeStatus.ERROR
        assert "kaboom" in (out.error or "")


# ── Approval gate: the "0 unauthorized writes" guarantee ─────────────────────


class _WriteProbe:
    """A synthetic write tool that records whether it actually executed."""

    executed = False

    class Args(BaseModel):
        target: str

    class Result(BaseModel):
        ok: bool

    spec = ToolSpec(
        name="reset_mfa",
        description="Reset a user's MFA (synthetic write tool for tests).",
        args_model=Args,
        result_model=Result,
        side_effect=SideEffect.WRITE,
        required_permissions=(),
        approval=Approval.HUMAN,
    )

    async def run(self, args, context):  # pragma: no cover - only if gate fails
        type(self).executed = True
        return self.Result(ok=True)


class TestApprovalGate:
    def setup_method(self) -> None:
        _WriteProbe.executed = False
        self.events: list[dict] = []
        self.rt = AgentToolRuntime({"reset_mfa": _WriteProbe()}, audit_sink=self.events.append)

    async def test_human_gated_tool_is_held_not_executed(self) -> None:
        out = await self.rt.dispatch(
            ToolInvocation("reset_mfa", {"target": "emp-9"}),
            _ctx(),  # no approval token
            allowed_tools=("reset_mfa",),
        )
        assert out.status is ToolOutcomeStatus.NEEDS_APPROVAL
        assert _WriteProbe.executed is False  # the critical safety assertion

    async def test_executes_once_approved(self) -> None:
        out = await self.rt.dispatch(
            ToolInvocation("reset_mfa", {"target": "emp-9"}),
            _ctx(approvals=("reset_mfa",)),
            allowed_tools=("reset_mfa",),
        )
        assert out.status is ToolOutcomeStatus.EXECUTED
        assert _WriteProbe.executed is True


# ── Bounded tool-use loop ────────────────────────────────────────────────────


class _ScriptedLLM:
    """Fake LLM returning a pre-baked sequence of tool responses."""

    def __init__(self, script: list[LLMToolResponse]) -> None:
        self._script = list(script)
        self.calls = 0

    async def complete_with_tools(self, messages, tools):  # noqa: ANN001
        self.calls += 1
        if self._script:
            return self._script.pop(0)
        return LLMToolResponse(text="(no more script)")


class TestRunLoop:
    async def test_tool_then_final_text(self) -> None:
        rt = build_default_runtime(audit_sink=lambda e: None)
        llm = _ScriptedLLM(
            [
                LLMToolResponse(
                    tool_calls=(
                        ToolInvocation(
                            "mailbox_quota_estimate", {"used_gb": 49, "quota_gb": 50}, "c1"
                        ),
                    ),
                ),
                LLMToolResponse(text="Your mailbox is nearly full — let's clear space."),
            ]
        )
        res = await rt.run_loop(
            messages=[{"role": "user", "content": "quota?"}],
            allowed_tools=ALL_TOOLS,
            llm=llm,
            context=_ctx(),
            max_iters=4,
        )
        assert res.stopped_reason == "completed"
        assert "nearly full" in res.message
        assert any(o.executed for o in res.outcomes)
        assert res.iterations == 2

    async def test_max_iters_cap(self) -> None:
        rt = build_default_runtime(audit_sink=lambda e: None)
        # LLM that always asks for another tool call → must hit the cap.
        always_call = LLMToolResponse(
            tool_calls=(ToolInvocation("mailbox_quota_estimate", {"used_gb": 1}, "c"),)
        )
        llm = _ScriptedLLM([always_call] * 10)
        res = await rt.run_loop(
            messages=[{"role": "user", "content": "loop"}],
            allowed_tools=ALL_TOOLS,
            llm=llm,
            context=_ctx(),
            max_iters=3,
        )
        assert res.stopped_reason == "max_iters"
        assert res.iterations == 3

    async def test_loop_stops_on_needs_approval(self) -> None:
        rt = AgentToolRuntime({"reset_mfa": _WriteProbe()}, audit_sink=lambda e: None)
        _WriteProbe.executed = False
        llm = _ScriptedLLM(
            [
                LLMToolResponse(tool_calls=(ToolInvocation("reset_mfa", {"target": "x"}, "c1"),)),
                LLMToolResponse(text="should not be reached"),
            ]
        )
        res = await rt.run_loop(
            messages=[{"role": "user", "content": "reset my mfa"}],
            allowed_tools=("reset_mfa",),
            llm=llm,
            context=_ctx(),
            max_iters=4,
        )
        assert res.stopped_reason == "needs_approval"
        assert res.pending_approvals
        assert _WriteProbe.executed is False
