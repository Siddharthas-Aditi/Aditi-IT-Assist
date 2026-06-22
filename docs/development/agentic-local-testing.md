# Agentic Platform — Local Testing Runbook

> How to spin up Aditi IT Assist locally and exercise every Phase 5–8 capability
> (agent tools, semantic RAG, MCP diagnostics, gated write actions, background
> agents) end-to-end — no external Microsoft Graph / ServiceNow / embedding
> provider required.

## 1. What's enabled for local dev

The agentic features default **off** in code (production-safe). For local
testing they're turned on in `.env` (and mirrored in `.env.example`):

```
FEATURE_AGENT_TOOLS=true
FEATURE_VECTOR_RETRIEVAL=true
FEATURE_MCP_TOOLS=true
MCP_ENABLED_SERVERS=["msgraph","servicenow"]
MCP_USE_MOCK=true          # in-memory mock MCP — no real Graph/ServiceNow needed
FEATURE_AGENT_WRITE_ACTIONS=true
FEATURE_BACKGROUND_AGENTS=true
```

`MCP_USE_MOCK=true` routes every MCP call to an in-memory mock that returns
realistic data, so diagnostics and write actions work with the full governance
(allow-list, RBAC, human approval, audit) but touch nothing real. Set it to
`false` once real MCP servers + tokens are configured.

Notes:
- `FEATURE_VECTOR_RETRIEVAL` is safe to leave on: without a configured embedding
  provider it **degrades to keyword retrieval** automatically. To get true
  semantic ranking, configure Azure OpenAI embeddings and run
  `python -m scripts.backfill_embeddings`.
- The chat engine still runs the proven deterministic path with the supervisor
  in shadow mode (unchanged). These features are exposed as operable surfaces +
  the agent debug view, not by changing chat behavior.

## 2. Start the stack

```bash
cp .env.example .env        # if you don't already have one (then re-add secrets)
docker compose up --build -d
docker compose exec backend uv run python -m scripts.seed_enterprise   # first run only — also seeds the new integration:* permissions
docker compose ps           # all services Up (healthy)
```

URLs: frontend http://localhost:5173 · API docs http://localhost:8000/docs.

Seeded users (password = role + "123", e.g. `lead123`):
`employee@aditi.com`, `agent@aditi.com`, `lead@aditi.com`, `admin@aditi.com`,
`auditor@aditi.com`.

> Re-run `seed_enterprise` after pulling these changes so the new
> `integration:directory_read/write` and `integration:ticketing_read/write`
> permissions are granted to the right roles (it_agent gets reads, it_lead+
> gets writes).

## 3. Exercise each capability

### A. Agent activity + RAG in chat  (sign in as `agent@aditi.com` or `admin`)
1. Go to **Support → Chat**, ask an IT question (e.g. "my Outlook mailbox is full").
2. The IT/admin **debug panel** under each agent reply now shows: detected
   system/subtype, **routed specialist** (supervisor shadow decision),
   **retrieval** mode (`db_hybrid`/`db_keyword`), and grounded **citations**.

### B. MCP & RAG status  (sign in as `lead@aditi.com`)
- **Dashboard → Agent Operations**: feature-flag chips, retrieval mode,
  registry/tool/MCP versions, the MCP server table (msgraph, servicenow — both
  enabled, mock), and the live local + MCP tool lists.

### C. Write-action approval queue  (the headline Phase 8 flow)
1. As `agent@aditi.com`: **Operations → Approvals → Propose action**. Pick
   `reset_mfa` (or `entra_unlock_account` / `servicenow_create_incident`), fill
   the args (idempotency key auto-fills), submit. It appears as **pending** —
   nothing has executed.
2. Sign in as `lead@aditi.com` (write permission holder): **Operations →
   Approvals**, **Approve** the pending item. The runtime executes it through
   the mock MCP and the row flips to **approved** with the result
   (e.g. `mfa_reset: true`). **Reject** instead to decline.
3. Try **Approve** as `agent@aditi.com` — blocked (approval never bypasses RBAC).

### D. Background agents  (sign in as `lead@aditi.com`)
- **Dashboard → Agent Operations → Background tasks → Enqueue task**: pick
  `knowledge_improvement_sweep` or `proactive_diagnostics`. The shared runner
  executes it and the row shows `completed` + result. (The runner also polls on
  its own interval via the app lifespan.)

### E. API directly (optional)
`http://localhost:8000/docs` → the **agent-ops** tag: `GET /agent-ops/status`,
`/agent-ops/approvals` (+ propose/approve/reject), `/agent-ops/tasks`.

## 4. Turning it off / production

Flip any flag to `false` in the environment — each is independently revertible
with no schema change. For production: set `MCP_USE_MOCK=false`, configure real
MCP server endpoints + `MCP_*_TOKEN` secrets, configure an embedding provider
for true semantic RAG, and keep `FEATURE_AGENT_WRITE_ACTIONS` gated behind the
documented security + IT-ops sign-off (every write stays human-approved
regardless).

## 5. Tests

```bash
make test-backend      # includes the agentic unit + eval suites
make test-frontend     # vitest
make lint              # ruff + eslint
```

Key agentic suites: `test_agent_tools`, `test_tool_routing_eval`,
`test_hybrid_ranking`, `test_retrieval_eval`, `test_mcp_tools`,
`test_mcp_contract_eval`, `test_action_safety_eval`, `test_agent_task_runner`,
`test_agent_ops_services`.
