"""Knowledge article lifecycle — pure transition and validation rules.

This module contains **no I/O**. It is the single source of truth for:

- which status transitions are legal (``draft → in_review → approved →
  published → archived`` plus revisions/restores),
- which permission each transition requires,
- what metadata an article must have before it can be published.

Keeping this logic pure makes the governance rules trivially unit-testable and
reusable by both the API layer (UI gating) and the management service
(enforcement).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.permissions import P

# ─────────────────────────────────────────────────────────────────────
# Status graph
# ─────────────────────────────────────────────────────────────────────

DRAFT = "draft"
IN_REVIEW = "in_review"
APPROVED = "approved"
PUBLISHED = "published"
ARCHIVED = "archived"

#: Only ``published`` articles are visible to the employee-facing chat agent.
PUBLISHED_STATUSES: frozenset[str] = frozenset({PUBLISHED})


class LifecycleError(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""


@dataclass(frozen=True)
class LifecycleAction:
    """A named lifecycle transition with its guard rules."""

    key: str
    label: str
    from_states: frozenset[str]
    to_state: str
    permission: str
    #: Whether reaching ``to_state`` requires the publish-readiness checklist.
    requires_publish_validation: bool = False
    #: Whether this transition should snapshot a new immutable version.
    snapshots_version: bool = False


LIFECYCLE_ACTIONS: dict[str, LifecycleAction] = {
    "submit_for_review": LifecycleAction(
        key="submit_for_review",
        label="Submit for review",
        from_states=frozenset({DRAFT}),
        to_state=IN_REVIEW,
        permission=P.KNOWLEDGE_SUBMIT_REVIEW,
    ),
    "approve": LifecycleAction(
        key="approve",
        label="Approve",
        from_states=frozenset({IN_REVIEW}),
        to_state=APPROVED,
        permission=P.KNOWLEDGE_APPROVE,
    ),
    "request_changes": LifecycleAction(
        key="request_changes",
        label="Request changes",
        from_states=frozenset({IN_REVIEW}),
        to_state=DRAFT,
        permission=P.KNOWLEDGE_REVIEW,
    ),
    "reject": LifecycleAction(
        key="reject",
        label="Reject",
        from_states=frozenset({IN_REVIEW, APPROVED}),
        to_state=DRAFT,
        permission=P.KNOWLEDGE_REVIEW,
    ),
    "publish": LifecycleAction(
        key="publish",
        label="Publish",
        from_states=frozenset({APPROVED}),
        to_state=PUBLISHED,
        permission=P.KNOWLEDGE_PUBLISH,
        requires_publish_validation=True,
        snapshots_version=True,
    ),
    "archive": LifecycleAction(
        key="archive",
        label="Archive",
        from_states=frozenset({DRAFT, IN_REVIEW, APPROVED, PUBLISHED}),
        to_state=ARCHIVED,
        permission=P.KNOWLEDGE_ARCHIVE,
        snapshots_version=True,
    ),
    "restore": LifecycleAction(
        key="restore",
        label="Restore to draft",
        from_states=frozenset({ARCHIVED}),
        to_state=DRAFT,
        permission=P.KNOWLEDGE_ARCHIVE,
    ),
    "create_revision": LifecycleAction(
        key="create_revision",
        label="Create new draft revision",
        from_states=frozenset({PUBLISHED}),
        to_state=DRAFT,
        permission=P.KNOWLEDGE_UPDATE_ALL,
        snapshots_version=True,
    ),
}


# ─────────────────────────────────────────────────────────────────────
# Publish-readiness validation
# ─────────────────────────────────────────────────────────────────────

#: Fields that must be present (and non-empty) before an article is publishable.
REQUIRED_FOR_PUBLISH: tuple[str, ...] = (
    "title",
    "short_summary",
    "category",
    "audience",
    "citation_label",
)

#: Minimum fields required to submit an article for review.
REQUIRED_FOR_SUBMIT: tuple[str, ...] = (
    "title",
    "category",
)


def validate_for_submit(article: dict) -> list[str]:
    """Return issues that block a *submit-for-review* action.

    Looser than the publish gate — we want authors to get early reviewer
    feedback even if the article is incomplete, but we still enforce that the
    minimum viable information is present.
    """
    issues: list[str] = []

    for field in REQUIRED_FOR_SUBMIT:
        value = article.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            issues.append(f"Missing required field: {field}")

    # Must have *something* actionable for reviewers to evaluate.
    has_body = any(article.get(f) for f in ("resolution_steps", "troubleshooting_steps", "content"))
    if not has_body:
        issues.append(
            "Article must include at least resolution steps, troubleshooting steps, "
            "or body content before submitting for review"
        )

    return issues


def validate_for_publish(article: dict) -> list[str]:
    """Return a list of human-readable issues blocking publication.

    An empty list means the article passes the governance checklist. ``article``
    is a plain dict view of the article so this stays storage-agnostic.
    """
    issues: list[str] = []

    for field in REQUIRED_FOR_PUBLISH:
        value = article.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            issues.append(f"Missing required field: {field}")

    # Must carry at least some actionable body for retrieval grounding.
    has_body = any(article.get(f) for f in ("resolution_steps", "troubleshooting_steps", "content"))
    if not has_body:
        issues.append(
            "Article must include resolution steps, troubleshooting steps, or body content"
        )

    tags = article.get("tags") or []
    if len(tags) < 1:
        issues.append("At least one tag is required for retrieval filtering")

    if not article.get("ownership_group_id"):
        issues.append("An ownership group must be assigned before publishing")

    return issues


# ─────────────────────────────────────────────────────────────────────
# Transition resolution
# ─────────────────────────────────────────────────────────────────────


def resolve_transition(action_key: str) -> LifecycleAction:
    """Look up a lifecycle action by key, raising ``LifecycleError`` if unknown."""
    action = LIFECYCLE_ACTIONS.get(action_key)
    if action is None:
        raise LifecycleError(f"Unknown lifecycle action: {action_key!r}")
    return action


def can_perform(action_key: str, current_status: str) -> bool:
    """Return whether ``action_key`` is legal from ``current_status``."""
    action = LIFECYCLE_ACTIONS.get(action_key)
    return bool(action and current_status in action.from_states)


def next_states(current_status: str) -> dict[str, str]:
    """Map of ``action_key → resulting status`` available from a status."""
    return {
        key: action.to_state
        for key, action in LIFECYCLE_ACTIONS.items()
        if current_status in action.from_states
    }


def assert_transition(action_key: str, current_status: str) -> LifecycleAction:
    """Resolve and validate a transition, raising on an illegal move."""
    action = resolve_transition(action_key)
    if current_status not in action.from_states:
        raise LifecycleError(
            f"Cannot '{action_key}' from status '{current_status}'. "
            f"Allowed source states: {sorted(action.from_states)}"
        )
    return action
