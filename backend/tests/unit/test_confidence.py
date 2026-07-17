"""Tests for the composite resolution-confidence scorer."""

from app.services.agents.confidence import compute_resolution_confidence


class TestConfidence:
    def test_grounded_subtype_match_is_high(self):
        bd = compute_resolution_confidence(
            system_match=0.9,
            subtype_match=0.9,
            retrieval_relevance=0.85,
            has_subtype_article=True,
            same_family=True,
            playbook_fit=True,
        )
        assert bd.final >= 0.7
        assert bd.grounding == 1.0

    def test_cross_domain_or_ungrounded_is_capped_low(self):
        bd = compute_resolution_confidence(
            system_match=0.6,
            subtype_match=0.0,
            retrieval_relevance=0.3,
            has_subtype_article=False,
            same_family=False,
            playbook_fit=False,
        )
        # No grounding → must be capped low regardless of other signals.
        assert bd.grounding == 0.0
        assert bd.final <= 0.25

    def test_generic_same_family_is_moderate(self):
        bd = compute_resolution_confidence(
            system_match=0.8,
            subtype_match=0.0,
            retrieval_relevance=0.5,
            has_subtype_article=False,
            same_family=True,
            playbook_fit=False,
        )
        assert 0.0 < bd.final <= 0.6

    def test_loop_and_unresolved_penalties_reduce_score(self):
        base = compute_resolution_confidence(
            system_match=0.9,
            subtype_match=0.9,
            retrieval_relevance=0.85,
            has_subtype_article=True,
            same_family=True,
            playbook_fit=True,
        )
        penalized = compute_resolution_confidence(
            system_match=0.9,
            subtype_match=0.9,
            retrieval_relevance=0.85,
            has_subtype_article=True,
            same_family=True,
            playbook_fit=True,
            loop_counter=2,
            failed_attempts=2,
        )
        assert penalized.final < base.final
        assert penalized.loop_penalty > 0 and penalized.unresolved_penalty > 0
