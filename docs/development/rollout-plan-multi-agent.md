# Multi-Agent Rollout Plan

> How we get from Phase-1 keystones to the full multi-agent architecture
> without breaking production. This is the engineering plan: feature flags,
> dual-run strategy, evaluation gates, risks, and what's deferred.

---

## 1. Phasing

### Phase 0 — Bug fix layer (shipped)
Conversational intent classifier + service-layer ticket guard + golden tests.
Eliminates the `ITA-000007` class of bugs without changing the workflow
graph. **Behind no flag — always on.**

### Phase 1 — Architecture keystones (this delivery)

| Artifact | Status |
|---|---|
| Agent registry (`registry.py`) | ✓ |
| Supervisor (`supervisor.py`) | ✓ |
| Specialist contract (`specialists/base.py`) | ✓ |
| Outlook specialist | ✓ |
| Controlled web research service | ✓ |
| Knowledge candidate model + service | ✓ |
| Specialist queue service + API | ✓ |
| `HandoffPackage` schema | ✓ |
| Tests for registry + supervisor | ✓ |
| Full doc set (architecture + product) | ✓ |

The supervisor + specialist code is **in the tree but not wired into the
LangGraph** yet — that's Phase 2. This is deliberate: shipping the
declarative pieces first lets reviewers vet the contracts before behavior
changes go live.

### Phase 2 — Supervisor-driven graph (next sprint)
- Add a `FEATURE_SUPERVISOR_ROUTING=true` env flag.
- In `app/workflows/graph.py`, when the flag is on, route through a new
  `supervisor_node` that calls `supervisor.decide()` and emits a
  conditional edge for each `NextAction`. The legacy
  triage→retrieve→resolve nodes still exist; the supervisor *chooses* to
  call them.
- Add a `specialist_dispatch_node` that invokes the right
  `SpecialistAgent.handle(...)` based on `decision.agent`.
- Migrate the other six specialists (`access_mfa`, `zoom_meetings`,
  `device_intune`, `sixth_sense`, `hardware`, `network_vpn`) from "registry
  declaration only" to full implementations following the Outlook template.
- Build the IT specialist UI for the queue + handoff package pane.
- Run **dual-mode evaluation**: every request runs through both the legacy
  graph and the supervisor graph; differences logged. Promote when delta is
  within tolerance on the golden set.

### Phase 3 — Improvement loop UI + observability (sprint after)
- SME review queue UI for `KnowledgeCandidate`.
- Promotion flow: candidate → draft `KnowledgeArticle` → publish.
- Observability dashboards (per spec in
  [`multi-agent-support-architecture.md` §6](../architecture/multi-agent-support-architecture.md)).
- Knowledge Improvement Agent as an async worker that runs nightly over
  unresolved sessions and negative feedback.

### Phase 4 — Open agent boundaries (later)
- LLM-backed specialist response composer (separate `response` agent).
- Multi-system routing (one user message → two specialists if needed).
- Real-time co-browse handoff inside the queue UI.

---

## 2. Feature flags

| Flag | Default | Purpose |
|---|---|---|
| `FEATURE_INTENT_CLASSIFIER` | `true` | Phase 0. Off only for emergency rollback. |
| `FEATURE_SUPERVISOR_ROUTING` | `false` | Phase 2. Routes via the new supervisor. |
| `FEATURE_SPECIALIST_HANDLERS` | `false` | Phase 2. Calls specialist `handle()` instead of legacy resolution. |
| `FEATURE_WEB_FALLBACK` | `false` | Phase 2. Enables the controlled web-research path. |
| `FEATURE_QUEUE_UI` | `false` | Phase 2. Exposes the specialist UI; the API can ship sooner. |
| `FEATURE_KB_CANDIDATES` | `true` after migration | Phase 2/3. Opt-in candidate creation from resolutions. |

All flags read from `app.core.config.Settings`; default values keep
production behavior unchanged.

---

## 3. Migration script + DB changes

Phase 1 adds one new table: `knowledge_candidates`. Migration
`003_knowledge_candidates.py` (to be written before Phase-2 deploy)
creates the table and the two enums
(`knowledge_candidate_state`, `knowledge_candidate_source`). Existing
tables are untouched.

No data backfill is needed — candidates accrue forward from the deploy
moment.

---

## 4. Dual-run / shadow evaluation

For the supervisor rollout we run **both** routers for every request:

1. Legacy graph produces the actual response served to the user.
2. The supervisor runs in shadow on the same state; its decision is
   logged but not acted on.
3. Diff log entries on cases where they disagree.
4. When the diff rate on the golden set is < 2% for two weeks, promote
   the supervisor to primary.

This is non-disruptive — the user sees no change until promotion.

---

## 5. Evaluation gates

The supervisor + specialist migration is gated on these metrics
(measured on the golden conversation set):

| Metric | Target before promotion |
|---|---|
| Intent classification accuracy | ≥ 95% on Scenarios 14, 15 |
| Specialist routing accuracy | ≥ 98% (correct specialist or sub-agent) |
| False-positive ticket creation | 0 in 1,000 sessions |
| Loop detection latency | ≤ 2 turns after onset |
| Handoff package completeness | 100% of fields populated when source data exists |
| Atomic claim correctness | 1,000-iteration stress test, 0 duplicates |
| Knowledge candidate dedup rate | ≥ 80% for repeat signals |

CI runs all of these on every PR that touches `agents/`, `workflows/`, or
`schemas/specialist_queue.py`.

---

## 6. Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Supervisor misroutes a common subtype | M | High (user-visible) | Dual-run shadow eval; rollback flag flip; subtype unit tests pin every specialist's scope. |
| Specialist regression vs. legacy resolution | M | Medium | Phase 2 Outlook ships behind flag; A/B against legacy for one week before promotion. |
| Atomic claim race condition | L | High (duplicate work) | DB-level `WHERE assigned_to IS NULL` is the source of truth; load-test with 50 parallel claims. |
| Web fallback leaks untrusted content | L | High (brand) | Five-gate policy; trust-tier curation is a PR-reviewed allowlist; mandatory candidate flag. |
| Knowledge candidate noise overwhelms SMEs | M | Medium | 30-day dedup window + confidence ranking; per-source quotas (Phase 3). |
| Handoff package schema drift | M | High | `schema_version` pin; consumer parses by version; deprecation policy on schema bumps. |
| Specialist sub-agent dispatch loop | L | High | Global handoff cap (8) + per-agent cap (3) enforced in supervisor before any agent runs. |
| Removed `--future__ annotations` breaks pickling / serialization | L | Low | Pydantic + SQLAlchemy explicit runtime types; tests load both schemas + models. |

---

## 7. What's explicitly **deferred** (acknowledged debt)

- **Specialist agents 2–7 still delegate to legacy resolution.** They're
  registered in the registry (so the supervisor routes correctly), but
  their `handle()` will, for now, call into the existing
  `resolution_node`. Migration in Phase 2.
- **Frontend specialist queue UI** — API ships in Phase 1; UI in Phase 2.
- **Async Knowledge Improvement Agent worker** — service exists; nightly
  worker job in Phase 3.
- **LLM-backed response composer** as a separate agent. Phase 4.
- **Observability dashboards.** Logs exist; Grafana panels in Phase 3.
- **Migration `003_knowledge_candidates.py`.** Must be written before
  Phase 2 deploy (the model is in code; the DDL is not).
- **Permission additions.** New permissions for `specialist_queue:*`
  routes need to be added to `app.core.permissions` and seeded; the
  current routes use the existing `ticket:assign` permission as a
  conservative default.

---

## 8. Sign-offs needed for promotion

| Phase | Approver | Evidence |
|---|---|---|
| Phase 1 merge | Tech lead | This doc + reviewed PR |
| Phase 2 supervisor on | Tech lead + IT operations | Two weeks of shadow eval, all gates green |
| Phase 2 web fallback on | Security + tech lead | Trust-tier allow-list reviewed; gate-5 audit log reviewed |
| Phase 3 KB Improvement worker on | KB owner + tech lead | Review queue tooling validated; SME training done |

---

## 9. Rollback plan

Each Phase-2 flag is independently revertible:

- `FEATURE_SUPERVISOR_ROUTING=false` → reverts to legacy linear graph,
  intent classifier remains active.
- `FEATURE_SPECIALIST_HANDLERS=false` → supervisor still routes but every
  delegation falls back to the legacy resolution node.
- `FEATURE_WEB_FALLBACK=false` → supervisor never proposes web fallback;
  affected specialists escalate at the soft cap instead.
- `FEATURE_QUEUE_UI=false` → API remains live (queue accessible to ops);
  UI hidden.

No DB rollback needed in any of these cases; the `knowledge_candidates`
table can stay empty.
