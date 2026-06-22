"""Unit tests for the hybrid retrieval ranking module (Phase 6).

Pure functions — no DB, no provider. Pins the contract the retrieval service
and the eval harness both rely on:
- cosine similarity edge cases;
- keyword overlap scoring;
- the hybrid blend, including graceful degradation when the vector signal is
  absent (vector weight folds into keyword, score stays in 0..1);
- ranking order and the "vector never regresses keyword" property.
"""

from __future__ import annotations

import pytest

from app.services.knowledge import ranking
from app.services.knowledge.ranking import (
    DEFAULT_WEIGHTS,
    HybridWeights,
    RankCandidate,
    cosine_similarity,
    hybrid_score,
    keyword_overlap_score,
)


class TestWeights:
    def test_default_weights_sum_to_one(self) -> None:
        DEFAULT_WEIGHTS.validate()  # must not raise

    def test_bad_weights_rejected(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            HybridWeights(vector=0.9, keyword=0.9, usage=0.0, quality=0.0).validate()


class TestCosine:
    def test_identical_vectors(self) -> None:
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_missing_or_mismatched_returns_none(self) -> None:
        assert cosine_similarity(None, [1.0]) is None
        assert cosine_similarity([1.0], []) is None
        assert cosine_similarity([1.0, 2.0], [1.0]) is None

    def test_zero_norm_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


class TestKeywordOverlap:
    def test_full_overlap(self) -> None:
        assert keyword_overlap_score("mailbox full quota", "mailbox is full at quota") == 1.0

    def test_partial_overlap(self) -> None:
        score = keyword_overlap_score("mailbox full vpn", "mailbox is full")
        assert score == pytest.approx(2 / 3)

    def test_tags_count(self) -> None:
        assert keyword_overlap_score("zoom audio", "meeting issue", ("zoom", "audio")) == 1.0

    def test_termless_query_neutral_prior(self) -> None:
        assert keyword_overlap_score("a in to", "anything") == 0.3


class TestHybridScore:
    def test_vector_present_blends(self) -> None:
        s = hybrid_score(vector=1.0, keyword=1.0, usage_count=0, quality_score=0.0)
        # vector*1 + keyword*1 weighted = vector+keyword weights
        assert s == pytest.approx(DEFAULT_WEIGHTS.vector + DEFAULT_WEIGHTS.keyword)

    def test_vector_absent_folds_into_keyword(self) -> None:
        # With no vector, a perfect keyword match should yield (vector+keyword) weight.
        s = hybrid_score(vector=None, keyword=1.0)
        assert s == pytest.approx(DEFAULT_WEIGHTS.vector + DEFAULT_WEIGHTS.keyword)

    def test_negative_vector_clamped(self) -> None:
        s = hybrid_score(vector=-0.5, keyword=0.0)
        assert s == 0.0

    def test_usage_and_quality_boost(self) -> None:
        base = hybrid_score(vector=0.0, keyword=0.0)
        boosted = hybrid_score(vector=0.0, keyword=0.0, usage_count=200, quality_score=1.0)
        assert boosted > base
        assert boosted <= 1.0

    def test_score_bounded(self) -> None:
        s = hybrid_score(vector=1.0, keyword=1.0, usage_count=10_000, quality_score=5.0)
        assert 0.0 <= s <= 1.0


class TestRank:
    def _corpus(self) -> list[RankCandidate]:
        return [
            RankCandidate(key="a", text="vpn will not connect network", embedding=[0.0, 1.0]),
            RankCandidate(key="b", text="outlook mailbox full quota", embedding=[1.0, 0.0]),
        ]

    def test_keyword_only_orders_by_overlap(self) -> None:
        ranked = ranking.rank("mailbox full", self._corpus())
        assert ranked[0].key == "b"
        assert ranked[0].vector_score is None  # no vector path

    def test_vector_scores_take_priority(self) -> None:
        ranked = ranking.rank(
            "anything", self._corpus(), vector_scores={"a": 0.95, "b": 0.05}
        )
        assert ranked[0].key == "a"
        assert ranked[0].vector_score == 0.95

    def test_query_embedding_path(self) -> None:
        ranked = ranking.rank("zzz", self._corpus(), query_embedding=[1.0, 0.0])
        # 'b' embedding aligns with the query embedding → wins on the vector signal.
        assert ranked[0].key == "b"
        assert ranked[0].vector_score == pytest.approx(1.0)

    def test_vector_does_not_regress_strong_keyword(self) -> None:
        # A strong keyword match keeps a sensible score even when vector is weak.
        ranked = ranking.rank(
            "outlook mailbox full quota", self._corpus(), vector_scores={"b": 0.0, "a": 0.0}
        )
        top = next(r for r in ranked if r.key == "b")
        assert top.keyword_score == 1.0
        assert top.score > 0.0
