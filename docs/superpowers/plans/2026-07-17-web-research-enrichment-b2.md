# Governed Web-Research Enrichment (B2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a KB-insufficient escalation, run one governed web-research pass and attach the findings to the specialist handoff (never shown to employees), via a swappable search provider (Google Programmable Search default), with trust filtering, real audit, and SME-review KB candidates — and remove the existing ungoverned employee-facing raw web path.

**Architecture:** A `WebSearchProvider` protocol with Google + Tavily implementations, selected by config behind `FEATURE_WEB_RESEARCH`. The already-built `ControlledWebResearchAgent` becomes live (with real `AuditEvent` audit). `ChatService` runs it best-effort at escalation and stashes findings in `state`; `EscalationService` persists them on `escalation_contexts` (migration 010); the specialist handoff package + `HandoffContextPanel` surface them.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic / pytest / Ruff (backend); React 18 / TypeScript / Vitest / ESLint (frontend).

## Global Constraints

- Backend line ≤ 100; `cd backend && uv run ruff check . && uv run ruff format --check .` clean.
- Frontend strict TS, no `any`; `cd frontend && npm run lint` (max-warnings=0) + `npm run typecheck` clean.
- **Employees NEVER receive web-sourced content** (contract-tested). Web research is specialist-only.
- Feature-gated: `FEATURE_WEB_RESEARCH` default False; unconfigured provider / flag off / provider error ⇒ web research is a safe no-op that never blocks escalation or handoff.
- KB candidates are created for SME review, never auto-published (existing improvement loop).
- Migration 010 must have a tested reversible downgrade (`memory/known-risks.md` #7).
- `settings` singleton accessor is `from app.core.config import settings` (there is no `get_settings()`).
- Run backend cmds from `backend/` via `uv`; frontend from `frontend/` via `npm`.

---

### Task 1: Swappable search provider + config

**Files:**
- Modify: `backend/app/services/web_search_service.py` (extract a `WebSearchProvider` protocol; refactor the Tavily body into `TavilySearchProvider`; add `GoogleProgrammableSearchProvider`; add `get_web_search_provider()` factory; keep trust assessment shared)
- Modify: `backend/app/core/config.py` (feature flag + provider config, after the B1 `RESOLUTION_*` block)
- Modify: `backend/.env.example` (document the new keys)
- Test: `backend/tests/unit/test_web_search_providers.py` (create)

**Interfaces:**
- Consumes: `WebSearchResult`, `DomainTrust`, `_assess_trust`, `_trust_score` (already in the module).
- Produces: `class WebSearchProvider(Protocol)` with `async def search(self, query: str, *, category: str, system: str) -> list[WebSearchResult]`; `TavilySearchProvider`; `GoogleProgrammableSearchProvider`; `get_web_search_provider() -> WebSearchProvider | None` (None when unconfigured); `settings.FEATURE_WEB_RESEARCH`, `settings.WEB_SEARCH_PROVIDER`, `settings.GOOGLE_SEARCH_API_KEY`, `settings.GOOGLE_SEARCH_CX`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_web_search_providers.py`:

```python
"""B2: swappable web-search providers parse results and assess trust."""

import pytest

from app.services import web_search_service as W


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Minimal async-context httpx.AsyncClient stand-in."""

    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _FakeResponse(self._payload)

    async def post(self, *a, **k):
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_google_provider_parses_and_assesses_trust(monkeypatch):
    payload = {
        "items": [
            {"title": "Fix keyboard", "link": "https://support.microsoft.com/kb/1",
             "snippet": "Try the on-screen keyboard."},
            {"title": "Random blog", "link": "https://someblog.example.com/post",
             "snippet": "..."},
        ]
    }
    monkeypatch.setattr(W.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(payload))
    provider = W.GoogleProgrammableSearchProvider(api_key="k", cx="cx")
    results = await provider.search("keyboard not working", category="hardware", system="windows")
    assert results, "expected parsed results"
    assert results[0].trust_level == W.DomainTrust.OFFICIAL  # microsoft ranks first
    assert any(r.domain.endswith("microsoft.com") for r in results)


@pytest.mark.asyncio
async def test_google_provider_returns_empty_on_error(monkeypatch):
    class _Boom:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise RuntimeError("network down")
    monkeypatch.setattr(W.httpx, "AsyncClient", lambda *a, **k: _Boom())
    provider = W.GoogleProgrammableSearchProvider(api_key="k", cx="cx")
    assert await provider.search("q", category="c", system="s") == []


def test_factory_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(W.settings, "FEATURE_WEB_RESEARCH", False, raising=False)
    assert W.get_web_search_provider() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_web_search_providers.py -v`
Expected: FAIL — `GoogleProgrammableSearchProvider` / `get_web_search_provider` / `W.httpx` / `W.settings` don't exist yet.

- [ ] **Step 3: Add config settings**

In `backend/app/core/config.py`, after the B1 `RESOLUTION_MISS_ESCALATE_THRESHOLD` line add:

```python
    # ── Web research (B2) ────────────────────────────────────────────
    FEATURE_WEB_RESEARCH: bool = False
    # Which provider backs governed web research: "google" | "tavily".
    WEB_SEARCH_PROVIDER: str = "google"
    GOOGLE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_CX: str = ""  # Programmable Search Engine ID
    # (TAVILY_API_KEY kept for the alternative provider.)
    TAVILY_API_KEY: str = ""
```

- [ ] **Step 4: Refactor the service into providers**

In `backend/app/services/web_search_service.py`:
- Add module imports at top: `import httpx` and `from typing import Protocol`, and `from app.core.config import settings`.
- Keep `DomainTrust`, `WebSearchResult`, and the trust helpers. Move `_assess_trust`, `_extract_domain`, `_trust_score` to module-level functions (or a shared mixin) so both providers reuse them.
- Define the protocol and providers:

```python
class WebSearchProvider(Protocol):
    async def search(self, query: str, *, category: str, system: str) -> list[WebSearchResult]:
        ...


def _rank_and_limit(results: list[WebSearchResult], limit: int = 3) -> list[WebSearchResult]:
    results.sort(key=lambda x: _trust_score(x.trust_level), reverse=True)
    return results[:limit]


class GoogleProgrammableSearchProvider:
    """Google Custom Search JSON API (Programmable Search Engine)."""

    def __init__(self, api_key: str, cx: str) -> None:
        self.api_key = api_key
        self.cx = cx

    async def search(self, query: str, *, category: str, system: str) -> list[WebSearchResult]:
        if not (self.api_key and self.cx):
            return []
        q = f"{category} {system} {query} help solution".strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"key": self.api_key, "cx": self.cx, "q": q, "num": 10},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # network/timeout/http error → degrade to empty
            logger.warning("google_search_failed error=%s", exc)
            return []
        items = data.get("items", []) or []
        results = [
            WebSearchResult(
                title=it.get("title", ""),
                url=it.get("link", ""),
                snippet=it.get("snippet", ""),
                domain=_extract_domain(it.get("link", "")),
                trust_level=_assess_trust(it.get("link", "")),
            )
            for it in items
            if it.get("link")
        ]
        return _rank_and_limit(results)


class TavilySearchProvider:
    """Tavily search API (kept as an alternative provider)."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, *, category: str, system: str) -> list[WebSearchResult]:
        if not self.api_key:
            return []
        q = f"{category} {system} {query} help solution".strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": self.api_key, "query": q, "max_results": 10,
                          "topic": "IT Help"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("tavily_search_failed error=%s", exc)
            return []
        items = data.get("results", []) or []
        results = [
            WebSearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                domain=_extract_domain(r.get("url", "")),
                trust_level=_assess_trust(r.get("url", "")),
            )
            for r in items
            if r.get("url")
        ]
        return _rank_and_limit(results)


def get_web_search_provider() -> WebSearchProvider | None:
    """Return the configured provider, or None when web research is off/unconfigured."""
    if not settings.FEATURE_WEB_RESEARCH:
        return None
    if settings.WEB_SEARCH_PROVIDER == "google":
        if settings.GOOGLE_SEARCH_API_KEY and settings.GOOGLE_SEARCH_CX:
            return GoogleProgrammableSearchProvider(
                settings.GOOGLE_SEARCH_API_KEY, settings.GOOGLE_SEARCH_CX
            )
        return None
    if settings.WEB_SEARCH_PROVIDER == "tavily":
        if settings.TAVILY_API_KEY:
            return TavilySearchProvider(settings.TAVILY_API_KEY)
        return None
    return None
```

Keep the existing `WebSearchService` class present for now (Task 4 removes its only live caller). Replace `logging.getLogger` usage as needed; keep `logger` defined. Ensure `_assess_trust`/`_extract_domain`/`_trust_score` are module-level and referenced by both providers and the legacy class.

- [ ] **Step 5: Document env keys**

In `backend/.env.example`, add under an appropriate section:
```
# Web research (B2) — specialist-only; off by default
FEATURE_WEB_RESEARCH=false
WEB_SEARCH_PROVIDER=google
GOOGLE_SEARCH_API_KEY=
GOOGLE_SEARCH_CX=
TAVILY_API_KEY=
```

- [ ] **Step 6: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_web_search_providers.py -v && uv run ruff check app/services/web_search_service.py app/core/config.py tests/unit/test_web_search_providers.py && uv run ruff format --check app/services/web_search_service.py app/core/config.py`
Expected: PASS + clean.
```bash
git add backend/app/services/web_search_service.py backend/app/core/config.py backend/.env.example backend/tests/unit/test_web_search_providers.py
git commit -m "feat(web): swappable web-search provider (Google default) behind FEATURE_WEB_RESEARCH"
```

---

### Task 2: Activate ControlledWebResearchAgent (real audit + default constructor)

**Files:**
- Modify: `backend/app/services/agents/web_research.py` (write `AuditEvent`s; add `build_default_web_research_agent`)
- Test: `backend/tests/unit/test_web_research_agent.py` (create)

**Interfaces:**
- Consumes: `ControlledWebResearchAgent`, `WebResearchOutcome`, `get_web_search_provider` (Task 1), `AuditEvent` model, `KnowledgeImprovementService`.
- Produces: audit rows on completed/blocked research; `build_default_web_research_agent(db) -> ControlledWebResearchAgent | None` (None when no provider configured). The agent accepts any object with the provider `search` signature (the `search=` param is typed to the provider protocol).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_web_research_agent.py`:

```python
"""B2: the governance agent filters by trust, creates candidates, and audits."""

import pytest

from app.services.agents.web_research import ControlledWebResearchAgent
from app.services.web_search_service import DomainTrust, WebSearchResult


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


@pytest.mark.asyncio
async def test_filters_untrusted_and_creates_candidates():
    results = [
        WebSearchResult("Off", "https://support.microsoft.com/x", "s", "support.microsoft.com",
                        DomainTrust.OFFICIAL),
        WebSearchResult("Blog", "https://blog.example.com/x", "s", "blog.example.com",
                        DomainTrust.GENERAL_BLOG),
    ]
    imp = _FakeImprovement()
    agent = ControlledWebResearchAgent(search=_FakeProvider(results), improvement_service=imp)
    outcome = await agent.research(
        query="q", specialist_name="outlook", category="email/outlook",
        subtype="not-receiving-emails", system="windows",
    )
    # blog filtered out; official kept; one candidate created for the kept result
    assert all(r.trust_level == DomainTrust.OFFICIAL for r in outcome.results)
    assert len(imp.calls) == len(outcome.results) >= 1
    assert outcome.policy.allowed is True
```

(Confirm `"outlook"` is a real specialist name with `web_fallback_allowed=True`; if not, use one that is — grep `web_fallback_allowed` in `backend/app/services/agents/registry.py`.)

- [ ] **Step 2: Run test to verify it fails or passes-without-audit**

Run: `cd backend && uv run pytest tests/unit/test_web_research_agent.py -v`
Expected: the trust/candidate test may already PASS (agent logic exists). If it passes, that is fine — the audit addition below is verified separately. If the specialist name is wrong it FAILS on `policy.allowed`.

- [ ] **Step 3: Add real audit + default constructor**

In `backend/app/services/agents/web_research.py`:
- Accept an optional `db` session on the constructor for audit writes:
  `def __init__(self, *, search=None, improvement_service=None, db=None)`, store `self.db = db`.
- After the `logger.info("web_research_completed", ...)` and each `logger.warning("web_research_blocked", ...)`, if `self.db is not None`, write an `AuditEvent` (import the model + follow an existing `AuditEvent(...)` construction in the codebase — grep `AuditEvent(` for the field names, e.g. `event_type`, `actor`, `metadata`/`details`). Use event types `web_research.completed` and `web_research.blocked`; include specialist, result counts, tiers, and (for completed) the candidate ids. Wrap the audit write in try/except so audit failure never breaks research.
- Add at module level:

```python
def build_default_web_research_agent(db) -> "ControlledWebResearchAgent | None":
    """Wire the configured provider + improvement service, or None when off."""
    from app.services.web_search_service import get_web_search_provider

    provider = get_web_search_provider()
    if provider is None:
        return None
    from app.services.knowledge.improvement import KnowledgeImprovementService

    return ControlledWebResearchAgent(
        search=provider,
        improvement_service=KnowledgeImprovementService(db),
        db=db,
    )
```

Note: `ControlledWebResearchAgent.__init__` currently defaults `search` to `WebSearchService()`; change the annotation/typing so a `WebSearchProvider` is accepted (both expose the same `search(query, *, category, system)` signature). Do not force a hard dependency on the concrete `WebSearchService`.

- Add `build_default_web_research_agent` to `__all__`.

- [ ] **Step 4: Extend the test with audit**

Append a test that constructs the agent with a fake `db` (a session stub whose `.add` records objects) and asserts an audit object was added after a completed research call. Match the real `AuditEvent` constructor fields you found in Step 3.

- [ ] **Step 5: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_web_research_agent.py -v && uv run ruff check app/services/agents/web_research.py tests/unit/test_web_research_agent.py && uv run ruff format --check app/services/agents/web_research.py`
Expected: PASS + clean.
```bash
git add backend/app/services/agents/web_research.py backend/tests/unit/test_web_research_agent.py
git commit -m "feat(web): activate ControlledWebResearchAgent with real audit + default constructor"
```

---

### Task 3: Migration 010 + model field + escalation-service persistence + DTO

**Files:**
- Modify: `backend/app/models/escalation.py` (`web_research_findings` on `EscalationContext`)
- Create: `backend/alembic/versions/010_web_research_findings.py`
- Modify: `backend/app/services/escalation_service.py` (`create_escalation_artifacts` reads `state["web_research_findings"]` and stores it)
- Modify: `backend/app/schemas/escalation.py` (add findings to the handoff DTO)
- Test: `backend/tests/unit/test_web_research_persistence.py` (create) + migration check

**Interfaces:**
- Produces: `EscalationContext.web_research_findings: Mapped[list | None]`; migration `010_web_research_findings` (revises `009_chat_escalation_artifacts`); `create_escalation_artifacts` persists findings from `state`; DTO field on `SpecialistHandoffView`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_web_research_persistence.py`:

```python
"""B2: web-research findings from state are persisted on the escalation context."""

from app.models.escalation import EscalationContext


def test_model_has_web_research_findings_column():
    assert "web_research_findings" in EscalationContext.__table__.columns
```

(A fuller service-level persistence test is added in Step 5 once the field exists.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_web_research_persistence.py -v`
Expected: FAIL — column missing.

- [ ] **Step 3: Add the model field**

In `backend/app/models/escalation.py`, on `EscalationContext` (near `kb_gap_tags`, ~line 145) add:
```python
    web_research_findings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 4: Add migration 010**

Create `backend/alembic/versions/010_web_research_findings.py`:

```python
"""Web-research findings on escalation context (B2).

Adds a JSONB column holding trust-filtered external findings captured at
escalation for the specialist handoff. Employees never see this content.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010_web_research_findings"
down_revision = "009_chat_escalation_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "escalation_contexts",
        sa.Column("web_research_findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("escalation_contexts", "web_research_findings")
```

- [ ] **Step 5: Persist findings in the escalation service**

In `backend/app/services/escalation_service.py::create_escalation_artifacts`, where the `EscalationContext(...)` is constructed (read the constructor block after line 221), read `state.get("web_research_findings")` and pass it to the model's `web_research_findings=`. Findings shape (list of dicts): `{"title","url","snippet","trust_tier","provider"}`. Keep idempotency (existing-context early return unchanged).

Append a service test to `test_web_research_persistence.py` that calls `create_escalation_artifacts` with `state={"web_research_findings": [ {...} ], ...}` against a test DB session and asserts the stored context has them. Use the same DB-session test fixtures the existing `test_escalation_artifacts.py` uses (read it for the pattern).

- [ ] **Step 6: Add the DTO field**

In `backend/app/schemas/escalation.py`, add `web_research_findings: list[dict] | None = None` to `SpecialistHandoffView` (and any handoff-context response schema that mirrors the context). Keep it optional/back-compatible.

- [ ] **Step 7: Run tests + migration round-trip + lint + commit**

Run:
```
cd backend && uv run pytest tests/unit/test_web_research_persistence.py tests/unit/test_escalation_artifacts.py -v
uv run ruff check app/models/escalation.py app/services/escalation_service.py app/schemas/escalation.py alembic/versions/010_web_research_findings.py
```
If a test DB is available, verify the migration: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` (note in the report if no DB is available to run alembic).
```bash
git add backend/app/models/escalation.py backend/alembic/versions/010_web_research_findings.py backend/app/services/escalation_service.py backend/app/schemas/escalation.py backend/tests/unit/test_web_research_persistence.py
git commit -m "feat(web): persist web-research findings on escalation context (migration 010)"
```

---

### Task 4: Trigger at escalation + remove the ungoverned employee-facing web path

**Files:**
- Modify: `backend/app/services/agents/chat_service.py` (run governed research best-effort at KB-insufficient escalation; inject `state["web_research_findings"]` before `_create_escalation_artifacts`)
- Modify: `backend/app/workflows/nodes/resolution.py` (REMOVE the raw employee-facing web path ~lines 180-265 + `_format_web_results_for_user`)
- Test: `backend/tests/unit/test_web_research_trigger.py` (create)

**Interfaces:**
- Consumes: `build_default_web_research_agent` (Task 2); the escalation `state`.
- Produces: on a KB-insufficient escalation with the flag on, `state["web_research_findings"]` is populated (list of `{title,url,snippet,trust_tier,provider}`) before artifacts are created; the resolution node no longer performs any employee-facing web call.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_web_research_trigger.py`:

```python
"""B2: governed research runs at KB-insufficient escalation; never shows web to employee."""

import inspect

from app.workflows.nodes import resolution as R


def test_resolution_node_has_no_employee_web_path():
    # The ungoverned raw web path must be gone: no _format_web_results_for_user,
    # no direct WebSearchService use in the resolution node.
    src = inspect.getsource(R)
    assert "_format_web_results_for_user" not in src
    assert "WebSearchService(" not in src
```

Add a trigger test that constructs `ChatService` with a fake web-research agent (monkeypatch `build_default_web_research_agent` to return a fake whose `research` yields one `WebResearchOutcome`) and asserts that, on a KB-insufficient escalation path, `state["web_research_findings"]` is set before artifact creation, while a bare live-agent request (no KB attempt) does NOT trigger research. Match the real `ChatService` escalation entry points (`_persist_and_queue` / `_create_escalation_artifacts`, ~lines 648-740) — read them for the exact hook point.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_web_research_trigger.py -v`
Expected: FAIL — the raw path still exists in resolution.py.

- [ ] **Step 3: Remove the ungoverned employee-facing web path**

In `backend/app/workflows/nodes/resolution.py`, remove the `if quality.should_try_web_search and knowledge_results:` block that calls `WebSearchService()` and returns `_format_web_results_for_user(...)` to the user (~lines 180-265), and delete the now-unused `_format_web_results_for_user` function. The subtype-mismatch case must fall through to the normal escalation path (set escalation reason + route to escalate) WITHOUT showing web content to the employee. Keep the `RetrievalQualityAnalyzer` usage only if still needed for logging; otherwise remove the mismatch-web branch entirely and let low/zero grounded results escalate as they already do. Ensure existing tests that referenced the mismatch-web behavior are updated (Task 6 sweep will catch stragglers).

- [ ] **Step 4: Add the governed trigger in ChatService**

In `backend/app/services/agents/chat_service.py`, at the escalation-artifact hook (inside `_persist_and_queue` before `_create_escalation_artifacts`, or at the top of `_create_escalation_artifacts`), add a best-effort governed research pass:

```python
    async def _maybe_run_web_research(self, session_id: str, state: dict | None) -> None:
        """Best-effort governed web research at a KB-insufficient escalation.
        Populates state['web_research_findings']; never raises."""
        if not state:
            return
        diag = state.get("diagnostic_context") or {}
        # KB-insufficient = a real KB attempt happened (steps tried, or KB miss/mismatch),
        # NOT a bare "I want a human" with no attempt.
        kb_attempted = bool(
            diag.get("failed_steps")
            or diag.get("suggested_steps")
            or state.get("knowledge_results") is not None
        )
        bare_human_request = bool(diag.get("live_agent_requested")) and not kb_attempted
        if bare_human_request:
            return
        try:
            from app.services.agents.web_research import build_default_web_research_agent

            svc = self.ticket_service
            agent = build_default_web_research_agent(svc.db) if svc else None
            if agent is None:
                return
            query = diag.get("exact_problem_statement") or state.get("symptom") or ""
            if not query:
                return
            outcome = await agent.research(
                query=query,
                specialist_name=state.get("routed_specialist") or diag.get("issue_category") or "",
                category=state.get("issue_category") or diag.get("issue_category"),
                subtype=diag.get("issue_subtype"),
                system=diag.get("normalized_system"),
                session_id=session_id,
            )
            state["web_research_findings"] = [
                {"title": r.title, "url": r.url, "snippet": r.snippet,
                 "trust_tier": r.trust_level.value, "provider": settings.WEB_SEARCH_PROVIDER}
                for r in outcome.results
            ]
        except Exception as exc:  # never block handoff
            logger.warning("web_research_trigger_failed", session_id=session_id, error=str(exc))
```

Call `await self._maybe_run_web_research(session_id, state)` immediately before `await self._create_escalation_artifacts(...)`. Ensure `settings` and `logger` are imported in the file (they are — verify). Note: `specialist_name` must be a real registry name for the agent's policy gate to allow research; if `routed_specialist` isn't set, research will be blocked by policy (safe no-op). Read how `routed_specialist` is populated (supervisor shadow) and use it; if unavailable, the call safely returns empty.

- [ ] **Step 5: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_web_research_trigger.py -v && uv run ruff check app/services/agents/chat_service.py app/workflows/nodes/resolution.py && uv run ruff format --check app/services/agents/chat_service.py app/workflows/nodes/resolution.py`
Expected: PASS + clean.
```bash
git add backend/app/services/agents/chat_service.py backend/app/workflows/nodes/resolution.py backend/tests/unit/test_web_research_trigger.py
git commit -m "feat(web): governed research at escalation; remove ungoverned employee-facing web path"
```

---

### Task 5: Surface findings in the specialist handoff (backend + frontend)

**Files:**
- Read then Modify: `backend/app/services/specialist_queue_service.py` (`build_handoff_package` / `_package_from_context` — include `web_research_findings`)
- Read then Modify: the `HandoffPackage` schema (grep for `class HandoffPackage`) — add the findings field
- Read then Modify: `frontend/src/features/specialist-chat/HandoffContextPanel.tsx` (render a "Web research (for your review)" section)
- Test: extend the specialist-handoff API test (`backend/tests/api/test_specialist_queue_handoff.py`) + a frontend test for the panel

**Interfaces:**
- Consumes: `EscalationContext.web_research_findings`; `HandoffPackage`.
- Produces: `HandoffPackage` carries `web_research_findings`; the panel shows them with trust badges; nothing shown to employees.

- [ ] **Step 1: Read the shapes**

Run: `cd backend && grep -n "class HandoffPackage\|web_research\|_package_from_context" app/schemas/*.py app/services/specialist_queue_service.py` and read `_package_from_context` (~line 358) + the `HandoffPackage` schema. Read `frontend/src/features/specialist-chat/HandoffContextPanel.tsx` to see how existing context sections (e.g. `ai_attempted_steps`, `kb_articles_referenced`) are rendered, and the TS type for the handoff data.

- [ ] **Step 2: Write the failing tests**

Backend: extend `backend/tests/api/test_specialist_queue_handoff.py` — when an escalation context has `web_research_findings`, the handoff package/endpoint returns them. (Follow the existing test's setup for seeding a context + calling the endpoint.)

Frontend: add a test in `frontend/src/features/specialist-chat/` that `HandoffContextPanel`, given handoff data with `web_research_findings`, renders the "Web research" heading, a source link, and a trust-tier badge; and given none, renders no such section. Match the real component props — read them first.

- [ ] **Step 3: Run tests to verify they fail**

Run the backend + frontend tests; expected FAIL (field/section not present).

- [ ] **Step 4: Implement backend surfacing**

Add `web_research_findings` to the `HandoffPackage` schema (optional list, default None/empty) and populate it in `_package_from_context` from `context.web_research_findings`. Keep back-compat (older contexts have None → empty).

- [ ] **Step 5: Implement the frontend section**

In `HandoffContextPanel.tsx`, add the findings field to the handoff TS type and render a collapsible "Web research (for your review)" section (only when non-empty), each item showing title (link), source domain, and a trust-tier badge, with a clear "unverified external sources" label. Reuse existing section/badge styling for consistency. No `any`.

- [ ] **Step 6: Run tests + lint/typecheck + commit**

Run: `cd backend && uv run pytest tests/api/test_specialist_queue_handoff.py -v` and `cd frontend && npm run lint && npm run typecheck && npx vitest run src/features/specialist-chat`
Expected: PASS + clean.
```bash
git add backend/app/services/specialist_queue_service.py backend/app/schemas backend/tests/api/test_specialist_queue_handoff.py frontend/src/features/specialist-chat
git commit -m "feat(web): surface web-research findings in specialist handoff panel"
```

---

### Task 6: Full verification gate

- [ ] **Step 1: Backend regression + gate**

Run: `cd backend && uv run pytest tests/unit/test_web_search_providers.py tests/unit/test_web_research_agent.py tests/unit/test_web_research_persistence.py tests/unit/test_web_research_trigger.py tests/unit/test_workflow_nodes.py tests/unit/test_diagnostic_conversation.py -v`
Then full gate: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
For any failure caused by removing the employee-facing web path (tests that asserted the old mismatch-web behavior), update them to the new correct behavior (escalate, no employee web content) — never weaken. Report each change. Note pre-existing unrelated failures explicitly.

- [ ] **Step 2: Frontend gate**

Run: `cd frontend && npm run lint && npm run typecheck && npx vitest run`
Expected: clean + green.

- [ ] **Step 3: Contract check (employees never see web)**

Run: `cd backend && grep -rn "_format_web_results_for_user\|WebSearchService(" app/workflows/ app/services/agents/chat_service.py` — expect no employee-facing web rendering remains (the only `WebSearchService`/provider use is inside the governed agent path). Document the grep output in the report.

- [ ] **Step 4: Commit any test expectation updates**

```bash
git add backend/tests frontend
git commit -m "test(web): update expectations after removing employee-facing web path"
```

---

## Self-Review

**Spec coverage:**
- Swappable provider + Google default + config/flag (spec §1,§2) → Task 1. ✓
- Activate agent + real audit + candidates (spec §3) → Task 2. ✓
- Escalation-time trigger + remove raw employee path (spec §4) → Task 4. ✓
- Persist findings + migration 010 + DTO (spec §5) → Task 3. ✓
- Specialist consumption backend+frontend (spec §6) → Task 5. ✓
- Testing incl. contract "employees never see web" + migration round-trip (spec) → Tasks 1-6 (Task 4 Step 1 + Task 6 Step 3 contract; Task 3 Step 7 migration). ✓
- Acceptance criteria 1-5 → Tasks 1-6. ✓

**Placeholder scan:** Tasks 2 (AuditEvent fields), 4 (routed_specialist source + hook point), and 5 (HandoffPackage schema / panel props) contain read-then-edit instructions where exact identifiers were not read during planning; each names the file and the concrete thing to look up. All novel code (providers, config, migration, model field, trigger method) is complete. No TBD/TODO.

**Type consistency:** `get_web_search_provider`, `WebSearchProvider`, `build_default_web_research_agent`, `web_research_findings`, and the finding dict shape (`title,url,snippet,trust_tier,provider`) are consistent across Tasks 1-5. Migration `010_web_research_findings` revises `009_chat_escalation_artifacts`. `settings.*` names match Task 1's config additions.

**Note for implementer:** The agent's policy gate blocks research for specialists without `web_fallback_allowed`; if `routed_specialist` is empty at escalation, research is a safe no-op (empty findings) — acceptable. Confirm at least the web-capable specialists (grep `web_fallback_allowed=True` in registry.py) are the ones routed for issues where web help is expected; broader routing tuning is out of B2 scope.
