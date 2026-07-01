"""Unit tests for the KB-gap controlled vocabulary + derivation (pure functions).

No DB, no LLM. Verifies that escalation reasons map to the right structured
knowledge-gap tags so downstream KB improvement is driven by stable signals.
"""

from app.services.agents.kb_gap_tags import (
    KB_GAP_TAGS,
    KbGapTag,
    derive_kb_gap_tags,
    is_valid_kb_gap_tag,
)


class TestVocabulary:
    def test_all_required_tags_present(self):
        required = {
            "no_matching_article",
            "article_suggested_but_unresolved",
            "specialist_only_resolution_needed",
            "unclear_problem_statement",
            "repeated_escalation_pattern",
            "missing_runbook",
            "policy_or_access_exception",
        }
        assert required <= KB_GAP_TAGS

    def test_validity_check(self):
        assert is_valid_kb_gap_tag(KbGapTag.NO_MATCHING_ARTICLE.value)
        assert not is_valid_kb_gap_tag("totally_made_up_tag")


class TestDerivation:
    def test_no_kb_articles_yields_no_matching_article(self):
        tags = derive_kb_gap_tags(
            knowledge_results=[],
            has_problem_statement=True,
            steps_attempted=["restart"],
            escalation_reason="exhausted grounded steps",
        )
        assert "no_matching_article" in tags

    def test_articles_with_steps_but_unresolved(self):
        tags = derive_kb_gap_tags(
            knowledge_results=[{"id": "a"}],
            has_problem_statement=True,
            steps_attempted=["step1", "step2"],
            escalation_reason="low confidence",
        )
        assert "article_suggested_but_unresolved" in tags
        assert "no_matching_article" not in tags

    def test_unclear_problem_statement(self):
        tags = derive_kb_gap_tags(
            knowledge_results=[],
            has_problem_statement=False,
            steps_attempted=[],
            escalation_reason="",
        )
        assert "unclear_problem_statement" in tags

    def test_policy_or_access_exception_from_reason(self):
        tags = derive_kb_gap_tags(
            knowledge_results=[{"id": "a"}],
            has_problem_statement=True,
            steps_attempted=["s"],
            escalation_reason="User lacks permission — access denied to share",
        )
        assert "policy_or_access_exception" in tags

    def test_missing_runbook_when_article_but_no_steps(self):
        tags = derive_kb_gap_tags(
            knowledge_results=[{"id": "a"}],
            has_problem_statement=True,
            steps_attempted=[],
            escalation_reason="no actionable steps available",
        )
        assert "missing_runbook" in tags

    def test_specialist_only_and_repeated_flags(self):
        tags = derive_kb_gap_tags(
            knowledge_results=[],
            has_problem_statement=True,
            steps_attempted=[],
            escalation_reason="account locked",
            specialist_only_signal=True,
            repeated_escalation=True,
        )
        assert "specialist_only_resolution_needed" in tags
        assert "repeated_escalation_pattern" in tags

    def test_deterministic_and_deduplicated(self):
        kwargs = dict(
            knowledge_results=[],
            has_problem_statement=False,
            steps_attempted=[],
            escalation_reason="permission policy",
        )
        first = derive_kb_gap_tags(**kwargs)
        second = derive_kb_gap_tags(**kwargs)
        assert first == second  # deterministic
        assert len(first) == len(set(first))  # de-duplicated
