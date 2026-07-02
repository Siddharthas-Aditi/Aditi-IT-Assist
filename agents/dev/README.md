# agents/dev/ — Developer-Role Agent Guides

> **Not to be confused with `agents/0X-*.md`**, which document the **runtime product
> agents** in the LangGraph workflow (orchestrator, triage, resolution, …). The files
> here are **operating guides for the coding agent / developer** doing the work,
> organized by engineering role.

Pick the guide that matches the change you're making and read it alongside the
`memory/` context, the relevant `skills/playbooks/*`, and the owning `docs/**`.

| Role guide | Use when you're… |
|------------|------------------|
| `backend-architect.md` | Adding/refactoring backend services, APIs, repositories |
| `frontend-admin-ux.md` | Building UI, especially admin/support/operations flows |
| `ai-workflow.md` | Changing agents, workflow nodes, retrieval, tools, MCP |
| `support-workflow.md` | Working on tickets, escalation, queue, live handoff |
| `security-compliance.md` | Reviewing RBAC, audit, data isolation, secrets, governance |
| `qa-hardening.md` | Writing tests, evals, hardening, regression prevention |
| `documentation.md` | Updating docs, memory, agent specs, plans |

Each guide states its mandate, must-read context, a working method, and the hard
constraints (invariants) it must never violate. They all defer to
`docs/development/engineering-workflow.md` for the end-to-end process.
