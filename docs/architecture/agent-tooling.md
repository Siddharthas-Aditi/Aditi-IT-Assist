# Agent Tooling (Phase 5)

> The typed, governed layer that lets agents *do things* — search the KB,
> estimate a mailbox quota, draft a ticket today; reach external systems over
> MCP (Phase 7) and take gated write actions (Phase 8) later. This document is
> the contract every tool and the runtime line up against.
>
> Status: **landed behind `FEATURE_AGENT_TOOLS` (default off).** Enabling the
> flag with no authorized `tool_context` is a no-op; the deterministic
> specialist path is unchanged until both the flag and a context are present.

See also: [`../../plans/agentic-ops-platform-evolution.md`](../../plans/agentic-ops-platform-evolution.md) (Phase 5),
[`multi-agent-support-architecture.md`](./multi-agent-support-architecture.md),
[`../development/rollout-plan-multi-agent.md`](../development/rollout-plan-multi-agent.md).

## 1. Why a tool layer

Specialists previously could only return canned KB steps. To behave like a real
IT analyst an agent must gather facts and act. Every action is modelled as a
**tool**: a frozen, versioned spec with a typed argument model, a typed result
model, an explicit side-effect classification, RBAC requirements, and an
approval gate. One runtime enforces all of it, so local tools and (later)
MCP-backed tools are indistinguishable to the agent and equally governed.

This preserves the system's anti-goals: no inventing answers (the only path to
KB content is `kb_search` over the published base), no hidden state, no silent
external effects.

## 2. Module map

| Module | Responsibility |
|---|---|
| `app/services/agents/tools/base.py` | Contracts: `ToolSpec`, `ToolContext`, `Tool` protocol, `ToolInvocation`/`ToolOutcome`, `LLMToolResponse`, `SideEffect`/`Approval`/`ToolOutcomeStatus` enums. |
| `app/services/agents/tools/runtime.py` | `AgentToolRuntime` — the single enforcement point: allow-list → existence → arg validation → RBAC → approval gate → execute → audit. Plus the bounded tool-use loop. |
| `app/services/agents/tools/local_tools.py` | Phase-5 read-only tools: `kb_search`, `mailbox_quota_estimate`, `ticket_draft`. |
| `app/services/agents/tools/registry.py` | `TOOL_REGISTRY` + `TOOL_REGISTRY_VERSION` + accessors + `build_default_runtime()`. Enumerated, never dynamic. |
| `app/services/llm_service.py` | `complete_with_tools(messages, tools)` → normalized `LLMToolResponse`. Selection only — never executes a tool. |

## 3. The contract

`ToolSpec` is the only thing the runtime trusts:

```text
name, version, description
args_model:   pydantic model (validated before the tool runs)
result_model: pydantic model
side_effect:  read | write | destructive
required_permissions: tuple of permission codes (app.core.permissions.P)
approval:     none | human | auto_allowlisted
mcp_server:   None for local tools; set in Phase 7
```

A specialist declares which tools it may call via
`SpecialistAgentSpec.allowed_tools`. The runtime rejects any call to a tool not
in that per-agent allow-list — a stale entry can never widen what actually runs.

## 4. The enforcement order (`AgentToolRuntime.dispatch`)

Every invocation passes through these gates, and **every** path (including
rejections) emits an audit event:

1. **Allow-list** — tool ∈ the agent's `allowed_tools`, else `rejected_not_allowed`.
2. **Existence** — tool ∈ `TOOL_REGISTRY`, else `rejected_unknown`.
3. **Arg validation** — `spec.args_model.model_validate(raw_args)`, else `invalid_args`.
4. **RBAC** — `required_permissions ⊆ context.permissions`, else `rejected_forbidden`.
5. **Approval gate** — a `human`-approval tool without an approval token in
   `context.approvals` returns `needs_approval` and **does not execute**.
6. **Execute** — tool failures become a typed `error` outcome; the turn never crashes.

The runtime takes no hard dependency on the LLM provider (passed per loop) or
the DB (audit is an injectable sink, default structlog), so all guardrails are
unit-testable without network or database.

## 5. Bounded tool-use loop

`AgentToolRuntime.run_loop` drives an LLM that exposes
`async complete_with_tools(messages, tools) -> LLMToolResponse`. It appends each
tool result back into the conversation and re-prompts until the model returns
final text, a human-gated tool is hit (loop stops, surfaces `pending_approvals`),
or the iteration cap is reached. The cap is `min(max_iters, 8)` — a hard ceiling
independent of caller input.

## 6. Phase-5 tools

| Tool | Side effect | Approval | Permissions | Notes |
|---|---|---|---|---|
| `kb_search` | read | none | `knowledge:read` | Searches the governed KB; returns titles + snippets. Injectable `search_fn` (defaults to the knowledge service). |
| `mailbox_quota_estimate` | read | none | — | Pure arithmetic: percent used, headroom, status, recommendation. |
| `ticket_draft` | read | none | — | Composes a draft only; `persisted` is always `False`. Real persistence stays in the service layer behind explicit confirmation. |

All three are read-only with no approval. The `write`/`destructive` and
`human`-approval machinery is implemented and tested (see the synthetic
`reset_mfa` probe in tests) but no Phase-5 tool uses it — it exists so Phase 8
reuses this layer unchanged.

## 7. Outlook integration (reference)

`OutlookSpecialist` is the reference wiring. When `FEATURE_AGENT_TOOLS` is on,
an LLM is configured, and `SpecialistInput.tool_context` is supplied, `handle()`
runs `_handle_with_tools` — a bounded loop over `allowed_tools`. The system
prompt forbids inventing steps and requires `kb_search` before recommendations;
confidence stays conservative and cannot be high without grounding. Any failure
in the tool path falls back to the deterministic step path, so enabling the flag
can never regress behaviour below today.

## 8. Evaluation & gates

`backend/tests/data/tool_routing_eval.yaml` is the versioned routing eval set.
`tests/unit/test_tool_routing_eval.py` asserts, deterministically (no LLM):

- every expected tool is declared in the specialist's `allowed_tools`;
- each tool's registered spec matches the expected side-effect and approval gate;
- dispatching the expected tool with valid args + permissions **executes**;
- dispatching without the required permission is **rejected** — the
  *0-unauthorized-calls* gate.

An LLM-selection-accuracy check (the ≥95% routing gate) runs only where an LLM
is configured (`TestLLMSelectionAccuracy`, skipped otherwise) and belongs in the
gated CI job that has a key.

Unit coverage lives in `tests/unit/test_agent_tools.py` (registry, each tool,
all six dispatch gates, the approval-gate safety assertion, the bounded loop)
and `tests/unit/test_outlook_tool_path.py` (deterministic-by-default, opt-in
tool path, safe fallback).

## 9. Configuration

| Setting | Default | Meaning |
|---|---|---|
| `FEATURE_AGENT_TOOLS` | `false` | Master switch for the specialist tool-use loop. |
| `AGENT_TOOLS_MAX_ITERS` | `4` | Max tool calls per turn (hard-capped at 8 in the runtime). |

## 10. Versioning

- `TOOL_REGISTRY_VERSION` bumps on any tool addition/removal or arg/behaviour change.
- `REGISTRY_VERSION` bumped to `1.1.0` for the `allowed_tools` field.
- Audit and analytics join on both versions.
