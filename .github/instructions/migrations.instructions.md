---
applyTo: "backend/alembic/**"
---
# Database migration instructions

Full playbook: `skills/playbooks/database-migrations.md`. Domain model: `memory/domain-model.md`.

- Create migrations with `make db-revision MSG="..."`; inspect the current Alembic
  head first (currently `015_ticket_number_sequence`) and keep the sequence contiguous.
- Every migration MUST have a working, tested `downgrade`. Verify upgrade **and**
  downgrade on a scratch DB before committing.
- Model changes (`app/models/`) and the migration go together; also update Pydantic
  schemas if the shape is exposed via API.
- Bump any typed contract version affected (`SCHEMA_VERSION`, `HandoffPackage`, registry
  `*_VERSION`). Never silently reshape a persisted contract.
- pgvector: a chunk is `indexed` only when it has a real vector, else `pending`. Don't
  assume embeddings exist. Provide/adjust backfill (`scripts/backfill_embeddings.py`) if needed.
- Update `memory/domain-model.md` and the relevant `docs/architecture/*` (e.g.
  `data-model.md`, `retrieval-and-indexing.md`) in the same change.
- Never edit an already-applied migration to change history — add a new one.
