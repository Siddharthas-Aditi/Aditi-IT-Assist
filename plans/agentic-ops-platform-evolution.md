# Aditi IT Assist — Agentic IT-Ops Platform Evolution

> **Status:** Proposal / RFC — awaiting tech-lead + IT-operations sign-off.
> **Author:** Staff+ architecture review, 2026-06-22.
> **Scope:** Take Aditi IT Assist from a *declared* multi-agent system to a
> *working* agentic IT-Ops platform: autonomous agents that take real actions
> via tool calling, MCP-based access to external systems, semantic RAG, and
> background/parallel agent execution.
> **Relationship to existing docs:** This extends — does not replace —
> [`rollout-plan-multi-agent.md`](../docs/development/rollout-plan-multi-agent.md)
> and [`multi-agent-support-architecture.md`](../docs/architecture/multi-agent-support-architecture.md).
> Their Phases 0–4 stand. The phases here are numbered **5–8** and assume
> Phase 2 (supervisor-primary) has been promoted first.

---

## 0. Executive summary

Aditi IT Assist already has the *skeleton* of a strong multi-agent platform:
a declarative agent registry, a pure-function supervisor, seven typed
specialists, grounding guardrails, KB governance, a live-handoff queue, and a
disciplined feature-flag rollout culture. That work is real and well-built.

What is **not** there — and what this document plans — is the part that makes
it "agents working independently on real tasks":

1. **Agents are not autonomous.** Specialists are deterministic functions that
   batch pre-written KB steps. They run no LLM loop and make no decisions. The
   supervisor that *would* make decisions is in shadow mode and changes
   nothing.
2. **Agents cannot take actions.** The LLM abstraction has no tool/function
   calling. Remote Help, ticketing, email, and Intune are stubs returning mock
   data. The only real external call is Tavily web search.
3. **There is no MCP.** Zero references in the codebase. Agents have no
   protocolized way to reach external IT systems (Entra, Intune, ServiceNow,
   mail).
4. **RAG is keyword search.** pgvector columns, migrations, config, and an
   embedding client all exist, but embeddings are never generated and
   retrieval is term-overlap scoring (`source="db_keyword"`).
5. **Nothing runs in the background or in parallel.** One synchronous
   `graph.ainvoke()` per chat turn. No task runner, no async agents.

The plan closes these gaps in four tracks (all prioritized by the requester),
sequenced into four phases with explicit typed contracts, feature flags,
evaluation datasets, and human-in-the-loop guardrails — consistent with the
project's existing engineering discipline.

---

## 1. Current-state audit (evidence-based)

### 1.1 Multi-agent orchestration — declared, not driving

| Claim | Reality | Evidence |
|---|---|---|
| LangGraph workflow exists | ✅ True | `backend/app/workflows/graph.py` — 7 nodes, linear: `triage → supervisor_shadow → policy → retrieve → resolve → escalate → draft_ticket → END` |
| Supervisor routes the conversation | ❌ **Shadow only** | `workflows/nodes/supervisor_shadow.py` invokes `supervisor.decide()`, logs it, and writes `supervisor_decision` onto state for analytics — but the unconditional edge `supervisor_shadow → policy` and the legacy `route_after_*` functions still drive every routing choice; the decision is never consumed. Gated by `FEATURE_SUPERVISOR_SHADOW=true`, `FEATURE_SUPERVISOR_PRIMARY=false`. |
| Specialists are agents | ❌ **Deterministic functions** | `services/agents/specialists/_progression.py::compose_specialist_output` — collect grounded steps, drop tried, batch 3, render text. No LLM loop, no tool calls. Outlook is the only bespoke one; the other six are ~50–70 line wrappers. |
| Agents run independently / in parallel | ❌ **Synchronous, single-turn** | `chat_service.py` calls `graph.ainvoke(state)` once per message and waits. No `asyncio.create_task`, no queue, no worker for agent work. |

The supervisor itself (`services/agents/supervisor.py::decide`) is a clean,
well-tested **pure function** with handoff caps, loop detection, and confidence
floors. It is genuinely good — it just isn't allowed to act yet.

### 1.2 RAG — keyword retrieval, vector path stubbed

| Component | State | Evidence |
|---|---|---|
| Retrieval scoring | ❌ Keyword overlap | `services/knowledge/retrieval.py::_rank` — `overlap = sum(1 for t in terms if t in haystack ...)`; result tagged `source="db_keyword"`. |
| Embeddings | ❌ Never generated | `services/knowledge/indexing.py` — `EmbeddingClient.available = False`; `AzureOpenAIEmbeddingClient` exists but `get_embedding_client()` returns the no-op stub unless Azure creds are set; chunks marked `embedding_status="indexed"` with **null vectors**. |
| pgvector column | ⚠️ Present, unused | `models/knowledge.py` — `KnowledgeChunk.embedding: Vector(3072)`, migration `006_add_knowledge_chunks_embedding`. Column is always NULL in practice. |
| Vector search query | ❌ Not implemented | No `ORDER BY embedding <-> :q` anywhere in `knowledge_repository.py`. |
| Grounding guardrail | ✅ Real & good | `services/agents/grounding.py::ground_results` — cross-domain rejection + subtype-aware rerank (subtype match +0.55, symptom overlap +0.30, system hit +0.35). |
| Citations | ✅ Grounded | `workflows/nodes/retrieval.py::_build_citations` — built only from articles that passed grounding. |

Net: the *governance and grounding* layers of RAG are production-grade; the
*retrieval engine underneath them* is a keyword matcher. This is the single
highest-leverage fix because every agent's answer quality depends on it.

### 1.3 MCP & action integrations — mostly absent

| Capability | State | Evidence |
|---|---|---|
| MCP (any) | ❌ None | Zero matches for `mcp` / "Model Context Protocol" in repo; not in `pyproject.toml`. |
| LLM tool/function calling | ❌ None | `services/llm_service.py` — `complete()` / `complete_json()` only; no `tools=` param passed to `litellm.acompletion`. |
| Microsoft Remote Help | ❌ Stub | `services/remote_support/providers/microsoft_remote_help.py` — `# STUB: Generate mock session info`; returns fabricated UUIDs. `AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET` not even defined in config. |
| External ticketing | ❌ Draft only | `workflows/nodes/ticketing.py` — `ticket_created: False`; persistence is internal DB only, no ServiceNow/Jira. |
| Email (SMTP) | ❌ Configured, unused | `config.py` SMTP_* present; no send path wired. |
| Web search (Tavily) | ✅ Real | `services/web_search_service.py` — real `httpx` POST to `api.tavily.com`, wrapped by `ControlledWebResearchAgent` with trust-tier + policy gates. |
| Azure OpenAI (LLM) | ✅ Real when configured | `llm_service.py` routes via LiteLLM to Azure. |

---

## 2. Target: a modern agentic IT-Ops platform

The destination is a system where, for a given employee request, the
supervisor routes to a specialist **agent** that can:

- reason over a turn with an LLM loop, bounded by the registry's caps;
- **retrieve** grounded knowledge via semantic RAG;
- **call tools** — read-only diagnostics first (check Entra account lock state,
  Intune compliance, mailbox quota), then *gated* write actions (reset MFA,
  unlock account, create a ServiceNow incident, send mail) — each tool reached
  over **MCP**;
- run **autonomously and in the background** for long-running or batch work
  (nightly knowledge improvement, proactive incident sweeps, multi-step
  remediations) without blocking a chat turn;
- stay inside hard guardrails: every write action is **typed, audited, policy-
  gated, and (by default) human-approved**.

This must honor the existing anti-goals from
`multi-agent-support-architecture.md §1`: no inventing answers when the KB is
silent, no agent ping-pong, no silent self-modification of the KB, no hidden
state machines.

### 2.1 Design principles (carried from CLAUDE.md / project instructions)

- **Explicit contracts over prompt magic.** Every tool is a typed Pydantic
  schema with a versioned name; every agent capability is declared in the
  registry. No capability is reachable that isn't declared.
- **Versioned configs.** `REGISTRY_VERSION`, `TOOL_REGISTRY_VERSION`,
  `HandoffPackage.schema_version`, and a new `MCP_PROFILE_VERSION` all pin to
  audit/analytics joins.
- **Typed models end-to-end.** Tool inputs/outputs are Pydantic v2; MCP results
  are parsed into typed DTOs, never passed as raw dicts into agent logic.
- **Evaluation datasets gate every promotion.** Golden conversations already
  exist; we add a retrieval eval set and a tool-routing eval set.
- **Human-review guardrails by default.** Write/destructive actions are
  proposal → approval → execute, never auto-fire, until an action is
  explicitly allow-listed for auto-execution with sign-off.

---

## 3. Architecture additions

### 3.1 Tool-calling layer (new)

```
                ┌────────────────────────────────────────────┐
   specialist   │            AgentToolRuntime                 │
   agent  ──────▶  - exposes declared tools to the LLM        │
   (LLM loop)  │  - validates tool call args (Pydantic)       │
                │  - dispatches to a ToolProvider              │
                │  - enforces per-tool RBAC + approval gate    │
                │  - records an AuditEvent per call            │
                └───────────────┬─────────────────────────────┘
                                ▼
                ┌───────────────────────────────┐
                │         ToolProvider           │  (abstraction, like auth providers)
                ├───────────────────────────────┤
                │  LocalToolProvider  (KB, ticket draft, quota calc) │
                │  McpToolProvider    (Entra, Intune, ServiceNow, mail) │
                └───────────────────────────────┘
```

**New contracts (proposed):**

- `services/agents/tools/base.py` — `ToolSpec` (name, version, description,
  `args_model: type[BaseModel]`, `result_model`, `side_effect: Literal["read","write","destructive"]`,
  `required_permissions`, `approval: Literal["none","human","auto_allowlisted"]`,
  `mcp_server: str | None`).
- `TOOL_REGISTRY: dict[str, ToolSpec]` + `TOOL_REGISTRY_VERSION` — the single
  declarative source of truth, mirroring `AGENT_REGISTRY`. Specialists declare
  which tools they may use via a new `allowed_tools: tuple[str, ...]` field on
  `SpecialistAgentSpec`.
- `AgentToolRuntime.run_turn(...)` — bounded LLM tool-use loop (max tool calls
  per turn from the registry cap; reuses existing handoff/loop guardrails).
- Extend `LLMService` with a `complete_with_tools(messages, tools=...)` method
  that passes tool schemas to `litellm.acompletion(tools=...)` and returns
  structured tool-call requests. Keep `complete()`/`complete_json()` intact.

### 3.2 MCP client layer (new — "agents consume MCP tools")

Agents act as an **MCP client**. External IT systems are reached through MCP
servers (vendor-provided or thin in-house wrappers), surfaced to the tool
runtime as `McpToolProvider`.

```
ToolProvider (McpToolProvider)
   │  uses mcp python SDK (stdio / streamable-http transports)
   ▼
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Entra/Graph  │   Intune     │  ServiceNow  │   Mail/Graph │  ← MCP servers
│ (account,    │ (device      │ (incidents)  │  (send,      │
│  MFA, locks) │  compliance) │              │   read)      │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**New contracts (proposed):**

- `services/agents/mcp/profiles.py` — `McpServerProfile` (server id, transport,
  endpoint/command, auth ref via secrets manager, `trust_tier`,
  `allowed_tools`, `default_side_effect_ceiling`). Declarative, versioned
  (`MCP_PROFILE_VERSION`), PR-reviewed allow-list — the same governance pattern
  as the web-fallback trust tiers.
- `McpToolProvider` — connects to a profile's server, lists its tools, **maps
  each MCP tool into a `ToolSpec`** (so MCP tools and local tools are
  indistinguishable to the agent and equally governed), and dispatches calls.
- Tool discovery is **allow-listed, not automatic**: a server may expose 40
  tools; only those named in the profile become callable. This prevents an
  upstream server change from silently widening agent capability.
- Secrets via `app.core.config.Settings` + secrets manager — never inline
  (CLAUDE.md no-hardcoded-secrets rule).

**Why consume rather than expose (this phase):** the requested value is agents
that *do things* in Aditi's IT estate. Exposing Assist as an MCP server is
deferred (noted in §8) — it adds surface area without serving the immediate
"agents take action" goal.

### 3.3 Real vector RAG (replace keyword engine)

- Wire `get_embedding_client()` to actually return
  `AzureOpenAIEmbeddingClient` when configured; **generate embeddings during
  indexing** (`indexing.py`) — populate `KnowledgeChunk.embedding`, set
  `embedding_status` honestly (`pending` until vector exists).
- Add a pgvector similarity query to `knowledge_repository.py`:
  `ORDER BY embedding <=> :query_vec LIMIT k` over **published** chunks only
  (governance unchanged).
- **Hybrid retrieval:** blend vector score with the existing keyword score and
  usage/quality boosts; keep the grounding guardrail and subtype rerank
  *unchanged* on top — they already work and are the safety net.
- Backfill job: embed all currently-published articles (one-off async task,
  Phase-6 runner).
- Keep the YAML keyword path strictly as the **degraded-mode fallback** when no
  embedding provider is configured (dev), and label it as such in the trace.

### 3.4 Autonomous & background agents (new runner)

- `services/agents/runtime/task_runner.py` — an async, in-process task runner
  (extends the existing asyncio lifespan loop that already runs the idle
  sweeper). Backed by a typed `AgentTask` model + table (status, agent, input,
  result, audit linkage) so work is durable and observable.
- Two execution modes:
  - **Interactive** (existing): synchronous chat turn, now with a bounded
    tool-use loop.
  - **Background/autonomous** (new): supervisor or a schedule enqueues an
    `AgentTask`; the runner executes it off the request path. First consumers:
    the **Knowledge Improvement Agent** (already specced as a deferred nightly
    worker) and a **proactive diagnostics agent** (e.g., sweep open tickets,
    pre-fetch Intune/Entra state, attach to handoff packages).
- Parallelism is bounded by a worker-concurrency setting; every background
  action obeys the same tool RBAC + approval gates as interactive ones.

---

## 4. Phased delivery (extends existing Phases 0–4)

> Precondition: **Phase 2 (supervisor-primary) is promoted first.** Autonomous
> agents are pointless while the supervisor can't route. If Phase 2 hasn't
> shipped, do it before Phase 5 here.

### Phase 5 — Tool-calling foundation (no external writes yet) — ✅ LANDED 2026-06-22 (behind `FEATURE_AGENT_TOOLS`, default off)
- ✅ `complete_with_tools` on `LLMService`; `ToolSpec` + `TOOL_REGISTRY`
  (`TOOL_REGISTRY_VERSION`); `AgentToolRuntime` with arg validation, RBAC,
  audit, and the approval gate (default `human` for write/destructive).
- ✅ Local read-only tools only: `kb_search`, `mailbox_quota_estimate`,
  `ticket_draft`. No MCP, no writes.
- ✅ Outlook (reference specialist) gained `allowed_tools` and a bounded LLM
  tool-use loop behind `FEATURE_AGENT_TOOLS` (dormant unless flag on + LLM
  configured + authorized `tool_context`); falls back to deterministic path.
- ✅ Eval + tests: `backend/tests/data/tool_routing_eval.yaml`,
  `tests/unit/test_tool_routing_eval.py` (0-unauthorized gate + contract pins),
  `test_agent_tools.py`, `test_outlook_tool_path.py`. Docs:
  `docs/architecture/agent-tooling.md`.
- **Gate to exit (full promotion):** tool-routing eval set ≥ 95% correct tool
  selection (LLM-gated CI job); 0 unauthorized tool calls in 1,000 sessions;
  latency budget met. Deterministic guardrail + 0-unauthorized assertions are
  already green in CI; the ≥95% selection check runs where an LLM is configured.

### Phase 6 — Semantic RAG — ✅ LANDED 2026-06-22 (behind `FEATURE_VECTOR_RETRIEVAL`, default off)
- ✅ Real embedding client (`AzureOpenAIEmbeddingClient`) selected by
  `get_embedding_client()`; embeddings populate `KnowledgeChunk.embedding`.
- ✅ pgvector similarity query (`KnowledgeRepository.article_vector_scores`,
  `cosine_distance`, best-chunk per article).
- ✅ Hybrid ranking (`services/knowledge/ranking.py`, `RANKING_VERSION`):
  vector + keyword + usage + quality, config-tunable weights, keyword floor so
  vector never regresses keyword. Wired into `KnowledgeRetrievalService` with
  graceful fallback; `source=db_hybrid|db_keyword`.
- ✅ Honest indexing status (chunks `pending` until a real vector exists) +
  `backfill_embeddings()` and `scripts/backfill_embeddings.py`.
- ✅ Retrieval eval set (`tests/data/retrieval_eval.yaml`) +
  `test_retrieval_eval.py` (keyword baseline target; **hybrid ≥ keyword**
  recall@k). Unit: `test_hybrid_ranking.py`, `test_vector_retrieval.py`.
- **Gate to exit (full promotion):** recall@5 ≥ agreed target and strictly ≥
  keyword baseline on the production corpus (embedding-gated CI job); grounding
  rejection rate unchanged or better; p95 retrieval latency within budget.
  Deterministic baseline + "hybrid ≥ keyword" assertions are green in CI; the
  production-model recall runs where an embedding provider is configured.

### Phase 7 — MCP read-only integrations — ✅ LANDED 2026-06-22 (behind `FEATURE_MCP_TOOLS`, per-server, default off)
- ✅ `McpServerProfile` registry (`MCP_PROFILE_VERSION`) + `McpBackedTool` +
  `McpSession` abstraction (protocol + lazy SDK adapter + injectable provider).
- ✅ Read-only tools: `entra_account_status`, `intune_device_compliance`,
  `mailbox_quota_status` (msgraph), `servicenow_incident_lookup` (servicenow) —
  all typed `ToolSpec`s with `mcp_server` set.
- ✅ Agents diagnose against live systems; **no writes** (side-effect ceiling
  enforced at build time).
- ✅ Per-server enablement (`FEATURE_MCP_TOOLS` + `MCP_ENABLED_SERVERS`); typed
  `integration:*` permissions; timeout + graceful degradation to KB-only; runtime
  audit now records `args_hash` + `result_hash` on every call.
- ✅ Eval/gate: `tests/data/mcp_contract_eval.yaml` + `test_mcp_contract_eval.py`
  (typed-spec + allow-list + ceiling + 0-unauthorized); unit `test_mcp_tools.py`.
- **Gate to exit (full promotion):** security review of the per-server allow-list;
  live failure/timeout drill against a real server; audit review. The contract
  + 0-unauthorized + degradation assertions are green in CI; the live SDK path
  (`SdkMcpSession`) is exercised by integration tests where a server is reachable.

### Phase 8 — Gated write actions + background agents — ✅ LANDED 2026-06-22 (behind `FEATURE_AGENT_WRITE_ACTIONS` / `FEATURE_BACKGROUND_AGENTS`, default off)
- ✅ Write MCP tools (`entra_unlock_account`, `reset_mfa`,
  `servicenow_create_incident`) — all `side_effect=write`, `approval=human`,
  idempotent via `idempotency_key`. New `integration:*_write` perms (it_lead+).
  No destructive tools.
- ✅ Two gates: build gate (`FEATURE_AGENT_WRITE_ACTIONS` — write tools only
  constructed when on; Phase-7 stays read-only) + always-on execution gate
  (runtime never executes a human-gated tool without an approval token).
- ✅ Propose→approve→execute: `ProposedAction` + `AgentToolRuntime.execute_approved`
  re-dispatches the exact invocation through the full gate; approval never
  bypasses RBAC; audit records args+result hashes.
- ✅ Background agents: `app/services/agents/tasks/` — typed `AgentTask`,
  `AgentTaskStore` (in-memory; DB-backed seam documented), `AgentTaskRunner`
  (bounded concurrency, retry-then-fail, audit). Reference handlers (knowledge
  improvement sweep, proactive diagnostics) + lifespan integration.
- ✅ Eval/gate: `tests/data/action_safety_eval.yaml` + `test_action_safety_eval.py`
  (**0 unapproved executions**, RBAC-no-bypass, build gating); runner unit tests.
- **Gate to exit (full promotion):** security + IT-ops sign-off on the write
  allow-list and any future auto-allowlisting; live drill against real servers;
  multi-instance deployments swap in a DB-backed task store. The
  0-unapproved-execution, idempotency, and rollback assertions are green in CI.

---

## Status: all four requested tracks (Phases 5–8) have landed behind flags, plus operability surfaces.

Autonomous agents + tool calling (5), semantic RAG (6), MCP consumption (7), and
gated write actions + background agents (8) are implemented, tested, and
documented — each default-off and independently revertible.

**Operability surfaces (for local testing & ops) are now built too:** the
agent-ops API (`/agent-ops`), the **approval queue** API + Operations UI
(propose → approve → execute), the Admin **Agent Operations** page (MCP/RAG
status + background-task monitor), agent-activity in the chat debug view, and a
**mock MCP** path so the whole stack runs locally with no external systems. Dev
flags are set in `.env`; see `docs/development/agentic-local-testing.md`.

Remaining work is operational promotion (real provider/server config + secrets,
security sign-offs, live drills, a DB-backed store for multi-instance) and the
optional supervisor-primary promotion (existing Phase 2) to let agents drive
chat directly — not new architecture.

---

## 5. Feature flags (new — additive to §2 of the rollout plan)

| Flag | Default | Purpose |
|---|---|---|
| `FEATURE_AGENT_TOOLS` | `false` | Phase 5. Enables the LLM tool-use loop for opted-in specialists. |
| `FEATURE_VECTOR_RETRIEVAL` | `false` | Phase 6. Semantic + hybrid retrieval; off = keyword path. |
| `FEATURE_MCP_TOOLS` | `false` | Phase 7. Per-server enablement of MCP-backed tools. |
| `FEATURE_AGENT_WRITE_ACTIONS` | `false` | Phase 8. Allows write/destructive tools (still human-approved). |
| `FEATURE_BACKGROUND_AGENTS` | `false` | Phase 8. Enables the async task runner / autonomous agents. |

All default to production-safe (off). Each is independently revertible with no
DB rollback, matching the existing rollout discipline.

---

## 6. Evaluation datasets (new — required before promotion)

| Dataset | Purpose | Gate |
|---|---|---|
| **Tool-routing eval** | (request → expected tool[s] + args) | ≥ 95% correct selection; 0 wrong-side-effect calls |
| **Retrieval eval** | (query → expected published article ids) | recall@5 ≥ baseline & target; grounding precision held |
| **Action-safety eval** | (scenario → expected approval gate behavior) | 100% of write actions blocked without approval |
| **Golden conversations** (existing) | end-to-end regression | unchanged pass rate |

CI runs these on any PR touching `agents/`, `workflows/`, `tools/`, `mcp/`, or
`knowledge/`, mirroring the existing CI gate policy.

---

## 7. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Agent fires an unintended write action | L | **Critical** | Default `approval="human"`; write tools off until Phase 8; per-tool RBAC; full audit; idempotency required. |
| MCP server widens tool surface upstream | M | High | Per-profile allow-list; only named tools become `ToolSpec`s; profile version pinned + PR-reviewed. |
| LLM hallucinates tool args | M | Medium | Pydantic validation rejects bad args before dispatch; invalid call → reprompt within bounded loop, then escalate. |
| Vector retrieval regresses vs keyword | M | Medium | Dual-run eval; hybrid (vector+keyword) so keyword floor is retained; promote only on recall gate. |
| Background agent runs amok / cost blowout | L | High | Bounded worker concurrency; per-task token/time caps; tasks durable + cancellable; same audit + approval gates. |
| Secret leakage via MCP auth | L | Critical | Secrets via config/secrets manager only; never in profile files or logs; SSL verify on. |
| Tool-loop latency hurts chat UX | M | Medium | Per-turn tool-call cap; read tools cached; long work pushed to background runner. |
| Scope creep blurs grounding anti-goals | M | Medium | Tools never bypass grounding; KB answers still grounded; no auto-KB mutation (candidates stay review-gated). |

---

## 8. Explicitly deferred

- **Expose Aditi Assist as an MCP server** (the "expose" direction). Valuable
  later for letting other internal tools call Assist's KB/ticketing, but out of
  scope for the "agents take action" goal. Revisit after Phase 8.
- **WebSocket push** for live chat (already deferred in the existing plan).
- **Auto-execution of write actions** beyond a tiny, signed-off allow-list.
- **Multi-system fan-out** (one message → parallel specialists). The background
  runner makes this feasible; defer the routing change until Phase 8 is stable.
- **Cross-encoder reranker model.** Hybrid + existing grounding rerank first;
  add a learned reranker only if eval shows it's needed.

---

## 9. Sign-offs needed

| Phase | Approver | Evidence |
|---|---|---|
| Phase 5 (tools, read-only local) | Tech lead | Tool-routing eval green; audit review |
| Phase 6 (vector RAG) | Tech lead + KB owner | Retrieval eval ≥ target; dual-run report |
| Phase 7 (MCP read-only) | Security + tech lead | Allow-list review; audit log review; failure-mode test |
| Phase 8 (writes + background) | Security + IT operations + tech lead | Action-safety eval 100%; blast-radius docs; rollback drill |

---

## 10. Immediate next step

If approved, the first PR is **Phase 5, scoped tight**: add
`complete_with_tools` to `LLMService`, the `ToolSpec`/`TOOL_REGISTRY`
contracts, `AgentToolRuntime` with the approval gate, and three local
read-only tools wired to the Outlook specialist behind
`FEATURE_AGENT_TOOLS=false` — plus the tool-routing eval set and tests. No
external systems touched, fully reversible, reviewable in isolation. That PR
proves the autonomous-agent + tool-calling contract end-to-end before any MCP
or write action exists.
