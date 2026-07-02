---
applyTo: "**/{tests,e2e}/**,**/*.{test,spec}.{ts,tsx,py}"
---
# Testing instructions

Apply these on top of `.github/copilot-instructions.md`. Full strategy:
`docs/development/testing-strategy.md`.

- Every meaningful change ships with tests. Test behavior and contracts, not internals.
- Backend: pytest (async), mock only at seams (LLM, external MCP, time). Cover service
  rules, RBAC, idempotency, and audit emission. Workflow nodes: state-in → state-out
  with a mocked LLM; cover the happy path fully.
- Frontend: Vitest + RTL for key interactions and permission gating; test pure helpers.
- **Eval datasets are gates, never weaken them.** When you touch agents/tools/MCP/
  retrieval/escalation, run and extend the matching fixture in `backend/tests/data/`:
  `retrieval_eval`, `tool_routing_eval`, `mcp_contract_eval`, `action_safety_eval`.
  Keep the golden-conversation regressions passing.
- New migration → test both `upgrade` and `downgrade`.
- A failing test/eval is a real signal: fix the code, don't delete the assertion.

Commands: `make test-backend`, `make test-frontend`, `make test-e2e`, `make test`.
