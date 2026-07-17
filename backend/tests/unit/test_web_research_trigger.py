"""B2: governed research runs at KB-insufficient escalation; never shows web to employee."""

import inspect

import pytest

from app.services.agents.chat_service import ChatService
from app.services.agents.web_research import WebResearchOutcome, WebResearchPolicyDecision
from app.services.web_search_service import DomainTrust, WebSearchResult
from app.workflows.nodes import resolution


def test_resolution_node_has_no_employee_web_path():
    # The ungoverned raw web path must be gone: no _format_web_results_for_user,
    # no direct WebSearchService use in the resolution node.
    src = inspect.getsource(resolution)
    assert "_format_web_results_for_user" not in src
    assert "WebSearchService(" not in src


class _FakeTicketService:
    """Minimal stand-in: only `.db` is read by build_default_web_research_agent."""

    def __init__(self):
        self.db = object()


class _FakeWebResearchAgent:
    """Fake governed agent: records calls, always returns a canned outcome."""

    def __init__(self, outcome: WebResearchOutcome):
        self._outcome = outcome
        self.calls: list[dict] = []

    async def research(self, **kwargs):
        self.calls.append(kwargs)
        return self._outcome


def _make_outcome() -> WebResearchOutcome:
    result = WebSearchResult(
        "Fix Outlook Crashes",
        "https://support.microsoft.com/outlook-crash",
        "Try repairing your Office installation.",
        "support.microsoft.com",
        DomainTrust.OFFICIAL,
    )
    policy = WebResearchPolicyDecision(
        allowed=True,
        reason="ok",
        allowed_tiers=(DomainTrust.OFFICIAL,),
        specialist_name="outlook",
    )
    return WebResearchOutcome(results=(result,), policy=policy)


@pytest.mark.asyncio
async def test_kb_insufficient_escalation_triggers_governed_research(monkeypatch):
    """A real KB attempt (steps tried) that still escalates should run research."""
    fake_agent = _FakeWebResearchAgent(_make_outcome())
    monkeypatch.setattr(
        "app.services.agents.web_research.build_default_web_research_agent",
        lambda db: fake_agent,
    )

    chat = ChatService(_FakeTicketService())
    state = {
        "issue_category": "outlook",
        "knowledge_results": [{"title": "Some Outlook Article"}],
        "supervisor_decision": {"specialist": "outlook"},
        "diagnostic_context": {
            "exact_problem_statement": "Outlook keeps crashing on launch",
            "issue_subtype": "outlook-crash",
            "issue_category": "outlook",
            "normalized_system": "outlook",
            "failed_steps": ["Restart Outlook"],
            "suggested_steps": ["Restart Outlook"],
        },
    }

    await chat._maybe_run_web_research("sess-kb-insufficient", state)

    assert fake_agent.calls, "governed research agent should have been invoked"
    assert state["web_research_findings"] == [
        {
            "title": "Fix Outlook Crashes",
            "url": "https://support.microsoft.com/outlook-crash",
            "snippet": "Try repairing your Office installation.",
            "trust_tier": "official",
            "provider": "google",
        }
    ]


@pytest.mark.asyncio
async def test_bare_live_agent_request_does_not_trigger_research(monkeypatch):
    """A bare 'I want a human' with no KB attempt must NOT trigger research."""
    fake_agent = _FakeWebResearchAgent(_make_outcome())
    monkeypatch.setattr(
        "app.services.agents.web_research.build_default_web_research_agent",
        lambda db: fake_agent,
    )

    chat = ChatService(_FakeTicketService())
    state = {
        "diagnostic_context": {
            "live_agent_requested": True,
            "exact_problem_statement": "I want to talk to a human",
        },
    }

    await chat._maybe_run_web_research("sess-bare-human", state)

    assert not fake_agent.calls, "research must not run for a bare human handoff request"
    assert "web_research_findings" not in state


@pytest.mark.asyncio
async def test_web_research_failure_never_raises(monkeypatch):
    """Best-effort: any exception from the research agent must be swallowed."""

    class _BoomAgent:
        async def research(self, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "app.services.agents.web_research.build_default_web_research_agent",
        lambda db: _BoomAgent(),
    )

    chat = ChatService(_FakeTicketService())
    state = {
        "knowledge_results": [{"title": "Some Article"}],
        "diagnostic_context": {
            "exact_problem_statement": "Outlook keeps crashing",
            "failed_steps": ["Restart Outlook"],
        },
    }

    # Must not raise.
    await chat._maybe_run_web_research("sess-boom", state)
    assert "web_research_findings" not in state
