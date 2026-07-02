# Testing Strategy

How we keep Aditi IT Assist correct and safe. Tests are production assets: every
meaningful change ships with tests, and safety-critical behavior is pinned by
evaluation datasets.

## Layers & tools

| Layer | Framework | Coverage target | Location |
|-------|-----------|-----------------|----------|
| Backend services | pytest (async) | 80%+ | `backend/tests/unit`, `backend/tests/` |
| Workflow nodes | pytest + mocked LLM | 100% of happy path | `backend/tests/unit` |
| API integration | pytest + httpx | Critical flows | `backend/tests/api` |
| Frontend components | Vitest + RTL | Key interactions | `frontend/src/**/*.test.tsx` |
| E2E | Playwright | Critical journeys | `frontend/e2e` (needs backend + seed) |

Commands: `make test-backend`, `make test-frontend`, `make test-e2e`, `make test`,
`make test-coverage`.

## Evaluation datasets (the safety net for AI behavior)

These YAML fixtures + their `test_*_eval.py` gate agent behavior and must stay green:

- `backend/tests/data/retrieval_eval.yaml` → `test_retrieval_eval.py` — keyword recall
  baseline; **hybrid ≥ keyword** recall@k.
- `tool_routing_eval.yaml` → `test_tool_routing_eval.py` — typed-spec + allow-list +
  **0 unauthorized** tool calls.
- `mcp_contract_eval.yaml` → `test_mcp_contract_eval.py` — MCP typed-spec + allow-list +
  ceiling + 0-unauthorized.
- `action_safety_eval.yaml` → `test_action_safety_eval.py` — **0 unapproved executions**,
  RBAC-no-bypass, write-action build gating.
- Golden conversations: `docs/development/golden-conversations.md` +
  `failure-cases-and-golden-conversations.md` — regression cases for chat behavior
  (e.g. the "inbox full → password reset" bug must never return).

**Rule**: touch agents, tools, MCP, retrieval, or escalation → run the matching eval
and add a case for the new behavior. Never weaken an eval to make it pass.

## What to test where

- **Pure functions** (grounding, confidence, ranking, escalation policy, subtype
  classifier, kb_gap_tags): exhaustive unit tests — they're deterministic and cheap.
- **Services**: business rules, RBAC, idempotency, audit emission (mock LLM/DB seams).
- **Workflow nodes**: state in → state out with mocked LLM; cover happy path fully.
- **Runtime/approval/tools**: allow-list, RBAC, approval gate, audit-on-every-path
  (including rejections) — read-only, fully unit-testable.
- **Frontend**: key interactions, permission gating, and pure helpers (e.g. badges,
  breadcrumbs); keep non-component helpers in non-component files (react-refresh rule).

## QA checklists (manual, per feature)

Run the matching checklist for user-facing changes:
`admin-qa-checklist.md`, `live-chat-qa-checklist.md`, `chat-escalation-qa-checklist.md`,
`chat-debugging-guide.md`, and the local agentic exerciser `agentic-local-testing.md`.

## Principles
- Test behavior and contracts, not implementation details.
- Mock only at seams (LLM, external MCP, time); never mock away the logic under test.
- A failing test or eval is a real signal — fix the code, don't delete the test.
- New migration → test upgrade **and** downgrade.
