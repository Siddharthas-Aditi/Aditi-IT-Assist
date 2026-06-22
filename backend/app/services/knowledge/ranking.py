"""Hybrid retrieval ranking (Phase 6).

Pure, dependency-free scoring used by the governed retrieval service. Keeping
this module free of DB / ORM / provider imports makes the ranking logic
exhaustively unit-testable and lets the retrieval eval harness reuse it on an
in-memory corpus.

The blend combines four signals into a single 0..1 score:

* **vector** — semantic cosine similarity between the query embedding and the
  article's best-matching chunk (supplied by the pgvector query; ``None`` when
  no embedding is available);
* **keyword** — lexical term overlap (the legacy signal, retained as a floor so
  vector retrieval can never do *worse* than keyword on exact-term matches);
* **usage** — a small boost for frequently-used content;
* **quality** — a small boost for curated/high-quality articles.

When the vector signal is absent (no provider, or a candidate has no embedding),
the vector weight is redistributed onto the keyword signal so the score stays
calibrated to 0..1 and the ranking degrades gracefully to pure keyword.

Versioned (`RANKING_VERSION`) so audits/analytics can join on the ranking
behaviour the same way they join on `REGISTRY_VERSION` / `TOOL_REGISTRY_VERSION`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Bump on any change to weights or blending behaviour.
RANKING_VERSION = "1.0.0"


@dataclass(frozen=True)
class HybridWeights:
    """Blend weights. Sum to 1.0 so the composite score stays in 0..1."""

    vector: float = 0.60
    keyword: float = 0.30
    usage: float = 0.07
    quality: float = 0.03

    def validate(self) -> None:
        total = self.vector + self.keyword + self.usage + self.quality
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"HybridWeights must sum to 1.0, got {total}")


DEFAULT_WEIGHTS = HybridWeights()


@dataclass(frozen=True)
class RankCandidate:
    """Lightweight ranking input — adapts ORM articles or eval dicts alike."""

    key: str
    text: str
    tags: tuple[str, ...] = ()
    usage_count: int = 0
    quality_score: float = 0.0
    embedding: list[float] | None = None


@dataclass(frozen=True)
class RankedItem:
    key: str
    score: float
    vector_score: float | None
    keyword_score: float


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float | None:
    """Cosine similarity in [-1, 1], or ``None`` if either vector is missing/empty.

    Defensive about length mismatch (returns ``None``) and zero-norm vectors
    (returns 0.0) so a malformed embedding never raises into retrieval.
    """
    if not a or not b or len(a) != len(b):
        return None
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def keyword_overlap_score(query: str, text: str, tags: tuple[str, ...] = ()) -> float:
    """Fraction of meaningful query terms present in the text/tags, in [0, 1]."""
    terms = {t for t in query.lower().split() if len(t) > 2}
    if not terms:
        return 0.3  # neutral prior for term-less queries (mirrors legacy _rank)
    haystack = (text or "").lower()
    tag_text = " ".join(str(t) for t in tags).lower()
    overlap = sum(1 for t in terms if t in haystack or t in tag_text)
    return overlap / len(terms)


def _usage_boost(usage_count: int) -> float:
    return min(1.0, max(0, usage_count) / 200.0)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def hybrid_score(
    *,
    vector: float | None,
    keyword: float,
    usage_count: int = 0,
    quality_score: float = 0.0,
    weights: HybridWeights = DEFAULT_WEIGHTS,
) -> float:
    """Blend the signals into a single 0..1 score.

    ``vector`` is the raw cosine similarity in [-1, 1]; it is clamped to [0, 1]
    (negative similarity contributes nothing). When ``vector`` is ``None`` the
    vector weight is folded into the keyword weight so the result stays in 0..1
    and pure-keyword behaviour is preserved.
    """
    kw = _clamp01(keyword)
    usage = _usage_boost(usage_count) * weights.usage
    quality = _clamp01(quality_score) * weights.quality

    if vector is None:
        # Degrade to keyword-only for the semantic portion.
        semantic = (weights.vector + weights.keyword) * kw
    else:
        v = _clamp01(vector)
        semantic = weights.vector * v + weights.keyword * kw

    return _clamp01(semantic + usage + quality)


def rank(
    query: str,
    candidates: list[RankCandidate],
    *,
    query_embedding: list[float] | None = None,
    vector_scores: dict[str, float] | None = None,
    weights: HybridWeights = DEFAULT_WEIGHTS,
) -> list[RankedItem]:
    """Rank candidates by the hybrid score, highest first.

    Vector similarity is sourced in priority order:
      1. ``vector_scores[key]`` if provided (the production path — pgvector
         computes per-article best-chunk similarity in the database);
      2. else cosine of ``query_embedding`` against ``candidate.embedding`` if
         both are present (used by the eval harness and any in-memory path);
      3. else ``None`` → keyword-only for that candidate.
    """
    ranked: list[RankedItem] = []
    for c in candidates:
        v: float | None = None
        if vector_scores is not None and c.key in vector_scores:
            v = vector_scores[c.key]
        elif query_embedding is not None:
            v = cosine_similarity(query_embedding, c.embedding)

        kw = keyword_overlap_score(query, c.text, c.tags)
        score = hybrid_score(
            vector=v,
            keyword=kw,
            usage_count=c.usage_count,
            quality_score=c.quality_score,
            weights=weights,
        )
        ranked.append(
            RankedItem(key=c.key, score=round(score, 4), vector_score=v, keyword_score=round(kw, 4))
        )

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


__all__ = [
    "DEFAULT_WEIGHTS",
    "RANKING_VERSION",
    "HybridWeights",
    "RankCandidate",
    "RankedItem",
    "cosine_similarity",
    "hybrid_score",
    "keyword_overlap_score",
    "rank",
]
