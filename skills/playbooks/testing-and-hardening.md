# Playbook: Testing & Hardening

**When**: adding tests, extending evals, or hardening a change against regressions.
Strategy of record: `docs/development/testing-strategy.md`.

## Approach
1. Identify the behavior/contract to pin. Write the smallest test that fails if it regresses.
2. Choose the right layer:
   - Pure functions (grounding, confidence, ranking, escalation policy, subtype
     classifier, kb_gap_tags) → exhaustive unit tests.
   - Services → business rules, RBAC (allowed **and** denied), idempotency, audit emission.
   - Workflow nodes → state-in→state-out with a mocked LLM (100% happy path).
   - Tools/runtime → allow-list, RBAC, approval gate, audit-on-every-path.
   - Frontend → key interactions + permission gating + pure helpers (Vitest + RTL).
3. AI/tools/MCP/retrieval/escalation change → run and **extend** the matching eval in
   `backend/tests/data/` and add a golden-conversation regression.
4. New migration → test `upgrade` and `downgrade`.

## Evals (gates — never weaken)
`retrieval_eval` · `tool_routing_eval` (0 unauthorized) · `mcp_contract_eval` ·
`action_safety_eval` (0 unapproved executions, RBAC-no-bypass).

## Validate
`make test`, `make lint`, `make typecheck`. For user-facing work, walk the matching
manual QA checklist and trace the workflow end-to-end.

## Rules
Mock only at seams (LLM, external MCP, time). A failing test/eval is a real signal —
fix the code, don't delete the assertion. Never mark work done with failing tests.
