# Sub-project B2 — Governed Web-Research Enrichment for Specialist Handoff

**Date:** 2026-07-17
**Status:** Approved design (pending user spec review)
**Part of:** production-readiness engagement, sub-project B (B2 of B1/B2)

## Problem

When an employee's issue is not covered by the KB, the AI should still help the
resolution — but safely. Two gaps today:

1. There is a **fully-built but dormant** `ControlledWebResearchAgent`
   (`backend/app/services/agents/web_research.py`) with trust-tier filtering and
   KB-candidate creation — but it has **zero callers**.
2. There is an **ungoverned raw web path live** in
   `backend/app/workflows/nodes/resolution.py` (~lines 180-265) that calls
   `WebSearchService` directly and shows raw web results **to the employee**,
   bypassing trust filtering, audit, and candidate creation. This contradicts the
   grounded-answer guarantee (`memory/known-risks.md` #1).

Additionally, web search is hardcoded to **Tavily** and gated only by a missing
`TAVILY_API_KEY` (no feature flag, not in `.env.example`), and the agent's audit is
logger-only (the docstring claims `AuditEvent` but none is written).

## Goal (user-approved decisions)

On a **KB-insufficient escalation**, run one **governed** web-research pass and
attach the findings to the **specialist handoff** — employees never see raw web
content. Web search runs through a **swappable provider** (Google Programmable
Search default), behind a `FEATURE_WEB_RESEARCH` flag, with **trust-tier
filtering**, **real audit**, and **mandatory SME-review KB candidates**. Remove the
ungoverned employee-facing raw web path.

## Non-goals

- No web content shown to employees (specialist-only enrichment).
- No auto-publish / self-learning — candidates are SME-reviewed (existing loop).
- No change to the employee one-step conversational flow (that was B1).
- No promotion of the supervisor to primary (`FEATURE_SUPERVISOR_PRIMARY` stays off).

## Design decisions (approved)

- **Trigger scope:** KB-insufficient escalations only (total miss, subtype
  mismatch, grounded steps exhausted). NOT a bare "I want a human" request with no
  KB attempt.
- **KB-candidate creation stays ON:** every trust-filtered finding becomes an
  SME-review candidate via the existing improvement loop.

## Units of work

### 1. Swappable search provider
- Define a `WebSearchProvider` protocol (async `search(query, *, category, system)
  -> list[WebSearchResult]`) in the web-search module.
- Implement `GoogleProgrammableSearchProvider` (Custom Search JSON API via
  `httpx`; needs API key + CSE id; time-bounded; errors → `[]`).
- Keep the existing Tavily behavior as `TavilySearchProvider` (refactor the current
  `WebSearchService` body into it) so nothing regresses.
- A factory selects the provider from config (`WEB_SEARCH_PROVIDER`); trust
  assessment (`DomainTrust`, `_assess_trust`) stays provider-independent and is
  applied to every provider's results.

### 2. Config + feature flag (`backend/app/core/config.py` + `.env.example`)
- `FEATURE_WEB_RESEARCH: bool = False` (per-env; default off).
- `WEB_SEARCH_PROVIDER: str = "google"` (`google` | `tavily`).
- `GOOGLE_SEARCH_API_KEY`, `GOOGLE_SEARCH_CX` (CSE id); keep `TAVILY_API_KEY`
  readable (move it into Settings for consistency).
- Degrades safely: flag off OR provider unconfigured ⇒ web research is a no-op
  (escalation proceeds without web findings). Document all keys in `.env.example`.

### 3. Activate `ControlledWebResearchAgent` + real audit
- Add real `AuditEvent` writes (research completed / blocked) alongside the existing
  structured logs — the agent currently only logs.
- Keep trust-tier policy (`_DEFAULT_ALLOWED_TIERS` official+vendor; per-specialist
  community opt-in) and KB-candidate creation
  (`KnowledgeImprovementService.record_web_fallback_used`) unchanged.
- Provide a `build_default_web_research_agent(db)` constructor wiring the configured
  provider + improvement service.

### 4. Escalation-time trigger wiring
- At the KB-insufficient escalation decision (the total-miss branch
  `graph.py::route_after_retrieval`, the subtype-mismatch branch, and the
  grounded-exhaustion branch in `resolution.py`), when `FEATURE_WEB_RESEARCH` is on
  run one governed research pass and stash the outcome for the escalation-artifact
  step. Web research runs in the **service layer** (like ticket persistence), not as
  a side effect of a pure workflow node, to keep nodes side-effect-free. Best-effort:
  a web-research failure never blocks escalation/handoff.
- **Remove the ungoverned raw web path** in `resolution.py` (~lines 180-265,
  `_format_web_results_for_user` employee display + raw `WebSearchService()` call).
  The subtype-mismatch case now escalates (with web enrichment attached) instead of
  showing raw web to the employee.

### 5. Persist findings on the escalation context
- Add `web_research_findings` (structured JSON: list of `{title, url, snippet,
  trust_tier, provider}` + a `policy`/`reason` summary) to the `escalation_contexts`
  model (`backend/app/models/escalation.py`) via **Alembic migration 010**
  (reversible up/down).
- `EscalationService.create_escalation_artifacts` accepts and stores the findings
  (idempotent per ticket, as today). Extend the DTOs in
  `backend/app/schemas/escalation.py` (`SpecialistHandoffView`).

### 6. Specialist consumption (backend + frontend)
- `SpecialistQueueService.build_handoff_package` includes `web_research_findings`
  from the persisted context.
- Frontend `features/specialist-chat/HandoffContextPanel.tsx`: render a
  **"Web research (for your review)"** section — clearly labelled unverified
  external sources, each with title, source domain, **trust tier badge**, and link.
  Collapsible, below the AI-attempt summary. `tsc` + eslint clean.

## Data flow

```
employee msg → triage → retrieve
  KB miss / mismatch / exhausted  ── FEATURE_WEB_RESEARCH on ──▶ service layer:
     ControlledWebResearchAgent.research(problem)              (best-effort)
       → provider.search → trust filter → KB candidates + AuditEvent
       → findings attached to escalation_context (migration 010)
  escalation/ticket (explicit-confirm, unchanged) → handoff package includes findings
  specialist opens LiveChatPage → HandoffContextPanel shows "Web research (for review)"
employee NEVER receives web content
```

## Error handling / guardrails

- Flag off / provider unconfigured / provider error / timeout ⇒ web research is a
  no-op; escalation and handoff proceed normally (never blocked).
- Trust filter rejects non-allowlisted domains; blogs never surface.
- Every research call audited (completed/blocked) with an `AuditEvent`.
- Employee-facing responses contain no web content (contract-tested).
- KB candidates are created but never auto-published (SME review).

## Testing

- **Provider:** `GoogleProgrammableSearchProvider.search` parses a mocked Custom
  Search JSON payload; error/timeout → `[]`; Tavily provider still parses its shape.
- **Agent:** trust filtering keeps only allowed tiers; candidate creation called per
  kept result; `AuditEvent` written; disabled/no-provider ⇒ empty outcome; a
  community-opted specialist gets the extra tier.
- **Trigger:** on a KB-miss escalation with the flag on, findings are produced and
  persisted on the escalation context; with the flag off, none and escalation still
  works; a bare "talk to a human" (no KB attempt) does NOT trigger research.
- **Contract:** an employee chat response never contains web-sourced text (assert
  the removed raw path is gone).
- **Handoff:** `build_handoff_package` surfaces the findings; DTO round-trips.
- **Migration:** 010 upgrade/downgrade tested.

## Acceptance criteria

1. On KB-insufficient escalation with `FEATURE_WEB_RESEARCH` on, governed web
   findings are attached to the specialist handoff and visible in
   `HandoffContextPanel`; employees see none.
2. Provider is swappable (Google default, Tavily alternative) and selected via
   config; inert and safe when unconfigured or flag off.
3. The ungoverned employee-facing raw web path is removed.
4. Every research call is trust-filtered, audited (`AuditEvent`), and creates
   SME-review KB candidates.
5. Backend `ruff` + `pytest` green; frontend `tsc` + eslint + vitest green;
   migration 010 reversible.

## Risks (`memory/known-risks.md`)

- #1 grounded retrieval / no hallucinated advice to employees — strengthened
  (raw employee-facing web path removed; web is specialist-only + trust-filtered).
- #3 escalation artifact immutability — findings are captured once at escalation
  (write-once, consistent with the snapshot/context contract).
- #7 migrations — 010 must have a tested downgrade.
- #8 config contract — new settings additive; provider factory validated, falls back
  safely.
