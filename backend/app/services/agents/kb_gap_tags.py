"""KB-gap tagging — a typed, controlled vocabulary for knowledge gaps.

When an AI conversation escalates, we record *why* the knowledge base could not
resolve it, as structured tags rather than free text. This powers later
human-reviewed knowledge improvement (which articles to write, which runbooks
are missing) without any uncontrolled self-learning.

The vocabulary is explicit and versioned (a production asset). New tags are added
here deliberately; callers must use :data:`KB_GAP_TAGS` membership, not ad-hoc
strings. :func:`derive_kb_gap_tags` is a **pure, deterministic** function — given
the same escalation state it always returns the same tags — so it is trivially
unit-testable and safe to call from the side-effect-free escalation path.
"""

from __future__ import annotations

from enum import StrEnum

KB_GAP_TAG_VOCAB_VERSION = "1.0"


class KbGapTag(StrEnum):
    """Controlled vocabulary of knowledge-gap reasons at escalation time."""

    NO_MATCHING_ARTICLE = "no_matching_article"
    ARTICLE_SUGGESTED_BUT_UNRESOLVED = "article_suggested_but_unresolved"
    SPECIALIST_ONLY_RESOLUTION_NEEDED = "specialist_only_resolution_needed"
    UNCLEAR_PROBLEM_STATEMENT = "unclear_problem_statement"
    REPEATED_ESCALATION_PATTERN = "repeated_escalation_pattern"
    MISSING_RUNBOOK = "missing_runbook"
    POLICY_OR_ACCESS_EXCEPTION = "policy_or_access_exception"


# Frozen set of valid string values, for validation at the boundary.
KB_GAP_TAGS: frozenset[str] = frozenset(t.value for t in KbGapTag)

# Keywords that strongly indicate a policy / access exception rather than a
# technical fault the KB could plausibly cover.
_POLICY_KEYWORDS = (
    "permission",
    "access denied",
    "not authorized",
    "approval",
    "policy",
    "exception",
    "license",
    "entitlement",
    "provision",
)


def is_valid_kb_gap_tag(value: str) -> bool:
    """Return True iff ``value`` is part of the controlled vocabulary."""
    return value in KB_GAP_TAGS


def derive_kb_gap_tags(
    *,
    knowledge_results: list | None,
    has_problem_statement: bool,
    steps_attempted: list | None,
    escalation_reason: str | None,
    repeated_escalation: bool = False,
    specialist_only_signal: bool = False,
) -> list[str]:
    """Derive the KB-gap tags for one escalation. Pure & deterministic.

    Args:
        knowledge_results: KB articles the retrieval node returned (may be empty).
        has_problem_statement: Whether a minimally-useful problem statement exists.
        steps_attempted: Troubleshooting steps the AI walked the user through.
        escalation_reason: The recorded escalation reason text (used for keyword
            signals like policy/access exceptions and missing runbooks).
        repeated_escalation: True if this user/session has escalated the same
            issue family before (caller supplies; default False).
        specialist_only_signal: True if grounding/diagnostics flagged the issue as
            requiring specialist-only action (e.g. account unlock, MFA reset).

    Returns:
        A de-duplicated, stable-ordered list of tag string values drawn from
        :data:`KB_GAP_TAGS`.
    """
    results = knowledge_results or []
    steps = steps_attempted or []
    reason = (escalation_reason or "").lower()

    tags: list[KbGapTag] = []

    # 1. Did the KB return anything at all?
    if not results:
        tags.append(KbGapTag.NO_MATCHING_ARTICLE)
    elif steps:
        # Articles existed and were walked through, but the issue persisted.
        tags.append(KbGapTag.ARTICLE_SUGGESTED_BUT_UNRESOLVED)

    # 2. Was the problem ever pinned down?
    if not has_problem_statement:
        tags.append(KbGapTag.UNCLEAR_PROBLEM_STATEMENT)

    # 3. Specialist-only resolution (privileged action / no self-serve fix).
    if specialist_only_signal:
        tags.append(KbGapTag.SPECIALIST_ONLY_RESOLUTION_NEEDED)

    # 4. Policy / access exception.
    if any(kw in reason for kw in _POLICY_KEYWORDS):
        tags.append(KbGapTag.POLICY_OR_ACCESS_EXCEPTION)

    # 5. Missing runbook: KB had a topical article but no actionable steps were
    #    available to give (results present yet no steps attempted).
    if results and not steps:
        tags.append(KbGapTag.MISSING_RUNBOOK)

    # 6. Repeated escalation pattern.
    if repeated_escalation:
        tags.append(KbGapTag.REPEATED_ESCALATION_PATTERN)

    # De-duplicate while preserving first-seen order.
    seen: set[KbGapTag] = set()
    ordered: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            ordered.append(t.value)
    return ordered


__all__ = [
    "KB_GAP_TAGS",
    "KB_GAP_TAG_VOCAB_VERSION",
    "KbGapTag",
    "derive_kb_gap_tags",
    "is_valid_kb_gap_tag",
]
