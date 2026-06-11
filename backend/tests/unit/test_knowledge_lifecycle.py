"""Unit tests for the knowledge article lifecycle rules (pure logic)."""

import pytest

from app.core.permissions import P
from app.services.knowledge import lifecycle


class TestTransitions:
    def test_draft_can_submit_for_review(self):
        assert lifecycle.can_perform("submit_for_review", "draft")

    def test_draft_cannot_publish(self):
        assert not lifecycle.can_perform("publish", "draft")

    def test_only_approved_can_publish(self):
        assert lifecycle.can_perform("publish", "approved")
        assert not lifecycle.can_perform("publish", "in_review")

    def test_published_can_archive_and_revise(self):
        states = lifecycle.next_states("published")
        assert states.get("archive") == "archived"
        assert states.get("create_revision") == "draft"

    def test_archived_restore_to_draft(self):
        assert lifecycle.can_perform("restore", "archived")
        assert lifecycle.resolve_transition("restore").to_state == "draft"

    def test_assert_transition_raises_on_illegal(self):
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.assert_transition("publish", "draft")

    def test_unknown_action_raises(self):
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.resolve_transition("nonexistent")

    def test_publish_requires_validation_and_snapshots(self):
        action = lifecycle.resolve_transition("publish")
        assert action.requires_publish_validation
        assert action.snapshots_version
        assert action.permission == P.KNOWLEDGE_PUBLISH

    def test_submit_requires_submit_permission(self):
        assert (
            lifecycle.resolve_transition("submit_for_review").permission
            == P.KNOWLEDGE_SUBMIT_REVIEW
        )


class TestPublishValidation:
    def _complete_article(self) -> dict:
        return {
            "title": "Fix Outlook",
            "short_summary": "How to fix Outlook sync.",
            "category": "email/outlook",
            "audience": "employee",
            "citation_label": "Fix Outlook",
            "tags": ["outlook"],
            "ownership_group_id": "group-1",
            "resolution_steps": [{"step_number": 1, "instruction": "Restart"}],
        }

    def test_complete_article_passes(self):
        assert lifecycle.validate_for_publish(self._complete_article()) == []

    def test_missing_summary_flagged(self):
        article = self._complete_article()
        article["short_summary"] = ""
        issues = lifecycle.validate_for_publish(article)
        assert any("short_summary" in i for i in issues)

    def test_missing_body_flagged(self):
        article = self._complete_article()
        article["resolution_steps"] = []
        issues = lifecycle.validate_for_publish(article)
        assert any("resolution steps" in i.lower() for i in issues)

    def test_missing_tags_flagged(self):
        article = self._complete_article()
        article["tags"] = []
        assert any("tag" in i.lower() for i in lifecycle.validate_for_publish(article))

    def test_missing_ownership_flagged(self):
        article = self._complete_article()
        article["ownership_group_id"] = None
        assert any("ownership" in i.lower() for i in lifecycle.validate_for_publish(article))
