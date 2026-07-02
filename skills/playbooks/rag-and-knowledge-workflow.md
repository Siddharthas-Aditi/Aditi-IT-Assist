# Playbook: RAG, Grounding & Knowledge Governance

**When**: changing retrieval, grounding, ranking, indexing, or KB lifecycle/governance.

## Key files
`services/knowledge/{retrieval,indexing,ranking,lifecycle,management}.py`,
`repositories/knowledge_repository.py`, `services/agents/{grounding,subtype_classifier,
confidence}.py`. Docs: `docs/architecture/knowledge-management.md`,
`retrieval-and-indexing.md`, `retrieval-guardrails.md`, `chat-grounding-rules.md`,
`knowledge-improvement-loop.md`, `docs/security/knowledge-access-control.md`.

## Invariants
1. **Published-only** retrieval for chat; drafts never reach employees.
2. **Subtype scoping**: each article's `subcategory` must equal a real subtype from
   `subtype_classifier.known_subtypes(category)`. No monolithic "all issues" articles.
   `grounding.ground_results` rejects cross-family articles and reranks the subtype match.
3. **Confidence** can't be high without grounding; loop/unresolved penalties apply.
4. **Hybrid ranking** (behind `FEATURE_VECTOR_RETRIEVAL`): weights sum to 1.0
   (`HYBRID_WEIGHT_*`); **keyword floor** so hybrid never scores below keyword; degrade
   to keyword on no provider / embed error / no embedded chunks.
5. **Honest indexing**: chunk `indexed` only with a real vector; article `indexed` only
   when all chunks embedded. Use `backfill_embeddings()` for pre-existing content.
6. **Lifecycle/governance**: `draft → in_review → approved → published → archived`;
   per-action permissions in the service; publish→index, archive→de-index, both snapshot
   a version. Candidates and feedback signals are **human-reviewed only** — no auto-publish.

## Validate
`test_retrieval_eval.py` (keyword baseline recall@k; **hybrid ≥ keyword**),
`test_hybrid_ranking.py`, `test_vector_retrieval.py`, golden conversations. Extend the
eval with any new case. Never weaken the eval to pass.

## Checklist
- [ ] Published-only + subtype-scoped; no cross-family leakage.
- [ ] Ranking weights valid; keyword floor + safe degrade intact.
- [ ] Indexing honest; backfill provided if needed.
- [ ] No auto-publish anywhere; lifecycle permissions enforced.
- [ ] Retrieval eval + golden convos pass.
