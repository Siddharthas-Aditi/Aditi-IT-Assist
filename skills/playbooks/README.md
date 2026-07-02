# skills/playbooks/ — Task-Oriented Dev Playbooks

Step-by-step playbooks for **recurring development tasks** in Aditi IT Assist. Distinct
from `skills/{backend,frontend,devops,product}/` (which are *implementation standards*
by technology) — these are *how to safely accomplish a specific kind of change*.

Read the matching playbook before starting the task. Each one: says **when to use it**,
gives an **approach/checklist**, points to the **relevant files/docs**, and enforces
**iterative validation**.

| Playbook | Use when |
|----------|----------|
| `backend-api-changes.md` | Adding/changing an endpoint, service, or repository |
| `database-migrations.md` | Any schema/model change |
| `frontend-admin-console.md` | Admin/operations UI work |
| `specialist-queue-flow.md` | Queue, claim, assignment, notifications |
| `chat-to-ticket-handoff.md` | Escalation → ticket → handoff logic |
| `live-chat-flow.md` | Live specialist chat lifecycle |
| `rag-and-knowledge-workflow.md` | Retrieval, grounding, KB governance |
| `audit-logging.md` | Adding auditable mutations |
| `testing-and-hardening.md` | Tests, evals, regression prevention |
| `docs-update.md` | Keeping docs + memory current |
| `code-review-self-check.md` | Final self-review before commit/PR |

All playbooks defer to `docs/development/engineering-workflow.md` for the overall process
and `memory/known-risks.md` for invariants.
