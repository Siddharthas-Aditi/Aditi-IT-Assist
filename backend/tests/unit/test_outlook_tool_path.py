"""Outlook specialist: tool-augmented path vs deterministic path (Phase 5).

Verifies three things:
* with ``FEATURE_AGENT_TOOLS`` off (default), Outlook uses the unchanged
  deterministic step path;
* with the flag on + a configured LLM + an authorized tool_context, Outlook
  runs the bounded tool loop and returns the loop's message;
* the tool path is wrapped so any failure falls back to deterministic — the
  flag can never regress behaviour below today.

All fakes — no network, no DB.
"""

from __future__ import annotations

from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.specialists.base import SpecialistInput
from app.services.agents.specialists.outlook import OutlookSpecialist
from app.services.agents.tools.base import LLMToolResponse, ToolContext, ToolInvocation
from app.services.agents.tools.registry import build_default_runtime
from app.services.knowledge_service import RetrievalResult


class _FakeLLM:
    def __init__(self, script: list[LLMToolResponse]) -> None:
        self._script = list(script)

    @property
    def is_available(self) -> bool:
        return True

    async def complete_with_tools(self, messages, tools):  # noqa: ANN001
        return self._script.pop(0) if self._script else LLMToolResponse(text="done")


def _diag() -> DiagnosticContext:
    ctx = DiagnosticContext()
    ctx.issue_category = "email/outlook"
    ctx.normalized_system = "outlook"
    ctx.issue_subtype = "mailbox-full"
    return ctx


_MAILBOX_ARTICLE = {
    "title": "Free up Outlook mailbox space",
    "subcategory": "mailbox-full",
    "steps": [
        {"instruction": "Empty the Deleted Items folder"},
        {"instruction": "Archive mail older than 12 months"},
    ],
}


def _input(*, tool_context: ToolContext | None) -> SpecialistInput:
    return SpecialistInput(
        user_message="My Outlook mailbox is full",
        diag_ctx=_diag(),
        knowledge_results=(_MAILBOX_ARTICLE,),
        knowledge_confidence=0.7,
        knowledge_citations=(),
        session_id="sess-1",
        tool_context=tool_context,
    )


class TestDeterministicByDefault:
    async def test_flag_off_uses_step_path(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_AGENT_TOOLS", False)
        out = await OutlookSpecialist().handle(_input(tool_context=None))
        # Deterministic path returns structured steps from the KB article.
        assert out.steps
        assert "Deleted Items" in out.steps[0].instruction


class TestToolPathOptIn:
    async def test_runs_tool_loop_when_enabled(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_AGENT_TOOLS", True)

        async def fake_search(query, *, category=None, limit=5):
            return RetrievalResult(articles=[_MAILBOX_ARTICLE], confidence=0.8)

        from app.services.agents.tools.local_tools import KbSearchTool
        from app.services.agents.tools.runtime import AgentToolRuntime

        runtime = AgentToolRuntime(
            {
                "kb_search": KbSearchTool(search_fn=fake_search),
                **{
                    n: build_default_runtime()._tools[n]  # reuse canonical instances
                    for n in ("mailbox_quota_estimate", "ticket_draft")
                },
            },
            audit_sink=lambda e: None,
        )
        llm = _FakeLLM([
            LLMToolResponse(
                tool_calls=(ToolInvocation("kb_search", {"query": "mailbox full"}, "c1"),)
            ),
            LLMToolResponse(text="Your mailbox is full — clear Deleted Items to free space."),
        ])
        ctx = ToolContext(
            user_id="emp-1",
            permissions=frozenset({"knowledge:read"}),
            session_id="sess-1",
        )
        specialist = OutlookSpecialist(llm=llm, tool_runtime=runtime)
        out = await specialist.handle(_input(tool_context=ctx))

        assert "Deleted Items" in out.message
        assert out.audit["event"] == "specialist.outlook.tool_handled"
        assert "kb_search" in out.audit["tools_executed"]
        assert out.confidence == 0.6  # grounded via kb_search

    async def test_no_tool_context_stays_deterministic(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_AGENT_TOOLS", True)
        # Flag on but no tool_context → tool path must NOT run.
        out = await OutlookSpecialist(llm=_FakeLLM([])).handle(_input(tool_context=None))
        assert out.steps  # deterministic path

    async def test_falls_back_on_tool_path_error(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_AGENT_TOOLS", True)

        class _BoomLLM:
            is_available = True

            async def complete_with_tools(self, messages, tools):  # noqa: ANN001
                raise RuntimeError("provider down")

        ctx = ToolContext(user_id="emp-1", permissions=frozenset({"knowledge:read"}))
        out = await OutlookSpecialist(llm=_BoomLLM()).handle(_input(tool_context=ctx))
        # Fell back to deterministic steps rather than raising.
        assert out.steps
