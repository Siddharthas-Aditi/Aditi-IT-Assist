"""Retrieval evaluation harness (Phase 6 gate).

Runs the versioned corpus + labelled queries in
``tests/data/retrieval_eval.yaml`` through the shared ``ranking`` module and
asserts, deterministically (no DB, no live embedding model):

* **keyword baseline** meets the recall@k target — proves keyword retrieval
  works on direct-term queries;
* **hybrid never regresses keyword** — hybrid recall@k ≥ keyword recall@k on the
  same set (the core promotion gate);
* the semantic query is recovered by hybrid (vector signal surfaces a related
  article that weak lexical overlap would rank lower).

Real-corpus recall with the production embedding model belongs in the
embedding-gated CI job.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.services.knowledge import ranking

_DATASET = Path(__file__).parent.parent / "data" / "retrieval_eval.yaml"


def _load() -> dict:
    with _DATASET.open() as fh:
        return yaml.safe_load(fh)


DATA = _load()
CORPUS = [
    ranking.RankCandidate(
        key=c["key"],
        text=c["text"],
        tags=tuple(c.get("tags", [])),
        embedding=c.get("embedding"),
    )
    for c in DATA["corpus"]
]
QUERIES = DATA["queries"]
K = DATA["recall_k"]


def _recall_at_k(*, use_vectors: bool) -> float:
    hits = 0
    for q in QUERIES:
        qemb = q.get("query_embedding") if use_vectors else None
        ranked = ranking.rank(q["query"], CORPUS, query_embedding=qemb)
        top_keys = {r.key for r in ranked[:K]}
        # Credit the query if ANY expected article is in the top-k.
        if top_keys & set(q["expected"]):
            hits += 1
    return hits / len(QUERIES)


def test_dataset_versioned() -> None:
    assert DATA.get("version")
    assert QUERIES and CORPUS


def test_keyword_baseline_meets_target() -> None:
    recall = _recall_at_k(use_vectors=False)
    assert recall >= DATA["keyword_recall_target"], (
        f"keyword recall@{K}={recall:.2f} below target {DATA['keyword_recall_target']}"
    )


def test_hybrid_does_not_regress_keyword() -> None:
    keyword = _recall_at_k(use_vectors=False)
    hybrid = _recall_at_k(use_vectors=True)
    assert hybrid >= keyword, f"hybrid recall@{K}={hybrid:.2f} < keyword {keyword:.2f}"


def test_semantic_query_recovered_by_hybrid() -> None:
    """The storage-semantic query should surface a mailbox/storage article in
    the top-k once the vector signal is in play."""
    q = next(q for q in QUERIES if q["id"] == "q-storage-semantic")
    ranked = ranking.rank(q["query"], CORPUS, query_embedding=q["query_embedding"])
    top_keys = {r.key for r in ranked[:K]}
    assert top_keys & set(q["expected"]), f"hybrid top-{K} missed {q['expected']}: {top_keys}"
