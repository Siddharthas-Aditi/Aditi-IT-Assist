"""B2: the governance agent filters by trust, creates candidates, and audits."""

from unittest.mock import patch

import pytest

from app.services.agents.web_research import (
    ControlledWebResearchAgent,
    build_default_web_research_agent,
)
from app.services.web_search_service import DomainTrust, WebSearchResult

# Patch target: bypass the registry's web_fallback_allowed check for tests that
# focus on ControlledWebResearchAgent's own filtering/audit logic. Tests of the
# registry flag itself live in test_web_fallback_routing.py.
_ALLOW_FALLBACK = "app.services.agents.web_research.is_web_fallback_allowed_for"


class _FakeProvider:
    def __init__(self, results):
        self._results = results

    async def search(self, query, *, category, system):
        return list(self._results)


class _FakeImprovement:
    def __init__(self):
        self.calls = []

    async def record_web_fallback_used(self, *, url, snippet, category, subtype):
        self.calls.append(url)
        return type("C", (), {"id": f"cand-{len(self.calls)}"})()


class _FakeDb:
    """Minimal AsyncSession stand-in: only `.add` is exercised by AuditService."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_filters_untrusted_and_creates_candidates():
    results = [
        WebSearchResult(
            "Off",
            "https://support.microsoft.com/x",
            "s",
            "support.microsoft.com",
            DomainTrust.OFFICIAL,
        ),
        WebSearchResult(
            "Blog",
            "https://blog.example.com/x",
            "s",
            "blog.example.com",
            DomainTrust.GENERAL_BLOG,
        ),
    ]
    imp = _FakeImprovement()
    agent = ControlledWebResearchAgent(search=_FakeProvider(results), improvement_service=imp)
    with patch(_ALLOW_FALLBACK, return_value=True):
        outcome = await agent.research(
            query="q",
            specialist_name="zoom_meetings",
            category="video-conferencing/zoom",
            subtype="no-audio",
            system="zoom",
        )
    # blog filtered out; official kept; one candidate created for the kept result
    assert all(r.trust_level == DomainTrust.OFFICIAL for r in outcome.results)
    assert len(imp.calls) == len(outcome.results) >= 1
    assert outcome.policy.allowed is True


@pytest.mark.asyncio
async def test_blocked_specialist_returns_empty_and_still_reports_policy():
    agent = ControlledWebResearchAgent(search=_FakeProvider([]))
    outcome = await agent.research(
        query="q",
        specialist_name="outlook",
        category="email/outlook",
        subtype="mailbox-full",
        system="outlook",
    )
    assert outcome.results == ()
    assert outcome.policy.allowed is False


@pytest.mark.asyncio
async def test_completed_research_writes_audit_event():
    results = [
        WebSearchResult(
            "Off",
            "https://support.microsoft.com/x",
            "s",
            "support.microsoft.com",
            DomainTrust.OFFICIAL,
        ),
    ]
    imp = _FakeImprovement()
    db = _FakeDb()
    agent = ControlledWebResearchAgent(
        search=_FakeProvider(results), improvement_service=imp, db=db
    )
    with patch(_ALLOW_FALLBACK, return_value=True):
        await agent.research(
            query="q",
            specialist_name="zoom_meetings",
            category="video-conferencing/zoom",
            subtype="no-audio",
            system="zoom",
        )

    assert len(db.added) == 1
    event = db.added[0]
    assert event.action == "web_research.completed"
    assert event.resource_type == "web_research"
    assert event.new_value["specialist"] == "zoom_meetings"
    assert event.new_value["results_out"] == 1
    assert event.new_value["candidate_ids"] == ["cand-1"]


@pytest.mark.asyncio
async def test_blocked_research_writes_audit_event():
    db = _FakeDb()
    agent = ControlledWebResearchAgent(search=_FakeProvider([]), db=db)
    await agent.research(
        query="q",
        specialist_name="outlook",
        category="email/outlook",
        subtype="mailbox-full",
        system="outlook",
    )

    assert len(db.added) == 1
    event = db.added[0]
    assert event.action == "web_research.blocked"
    assert event.resource_type == "web_research"


@pytest.mark.asyncio
async def test_audit_failure_never_breaks_research():
    class _ExplodingDb:
        def add(self, obj):
            raise RuntimeError("db is down")

    results = [
        WebSearchResult(
            "Off",
            "https://support.microsoft.com/x",
            "s",
            "support.microsoft.com",
            DomainTrust.OFFICIAL,
        ),
    ]
    agent = ControlledWebResearchAgent(search=_FakeProvider(results), db=_ExplodingDb())
    with patch(_ALLOW_FALLBACK, return_value=True):
        outcome = await agent.research(
            query="q",
            specialist_name="zoom_meetings",
            category="video-conferencing/zoom",
            subtype="no-audio",
            system="zoom",
        )
    assert outcome.policy.allowed is True
    assert len(outcome.results) == 1


def test_build_default_web_research_agent_none_when_no_provider(monkeypatch):
    monkeypatch.setattr("app.services.web_search_service.get_web_search_provider", lambda: None)
    assert build_default_web_research_agent(db=_FakeDb()) is None


def test_build_default_web_research_agent_wires_provider(monkeypatch):
    provider = _FakeProvider([])
    monkeypatch.setattr("app.services.web_search_service.get_web_search_provider", lambda: provider)
    db = _FakeDb()
    agent = build_default_web_research_agent(db=db)
    assert isinstance(agent, ControlledWebResearchAgent)
    assert agent.search is provider
    assert agent.db is db


@pytest.mark.asyncio
async def test_research_with_no_search_provider_returns_empty_not_allowed(monkeypatch):
    """Constructing with search=None (e.g. get_web_search_provider() returned None)

    must never raise AttributeError from `self.search.search(...)`; it should
    degrade to a safe, empty, not-allowed outcome instead.
    """
    monkeypatch.setattr("app.services.web_search_service.get_web_search_provider", lambda: None)
    agent = ControlledWebResearchAgent(search=None)
    assert agent.search is None

    outcome = await agent.research(
        query="q",
        specialist_name="zoom_meetings",
        category="video-conferencing/zoom",
        subtype="no-audio",
        system="zoom",
    )
    assert outcome.results == ()
    assert outcome.candidate_ids == ()
    assert outcome.policy.allowed is False
    assert outcome.policy.reason == "no web search provider configured"
