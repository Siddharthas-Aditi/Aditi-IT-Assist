"""Composite confidence scoring for grounded resolutions.

The old confidence was a single number derived almost entirely from the
retriever ("knowledge_confidence + 0.15"), so a *wrong* answer built from a
mismatched article still reported 80–95%. That is the "95% confident, totally
wrong" symptom.

Confidence here is a weighted blend of independent signals, each of which can
independently sink the score, plus explicit penalties for repetition and
unresolved history. The guiding rule:

    If grounding is weak or conflicting, confidence MUST drop — there is no
    path to a high score without a real subtype-matching, on-domain article.

The breakdown is returned alongside the final score so it can be surfaced in the
debug view and logged, making "why was confidence X?" answerable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class ConfidenceBreakdown:
    """The component signals behind a resolution-confidence score."""

    system_match: float = 0.0       # entity/system recognition confidence
    subtype_match: float = 0.0      # subtype classification confidence
    retrieval_relevance: float = 0.0  # top grounded article relevance
    grounding: float = 0.0          # did a real on-subtype/on-domain article back this
    playbook_fit: float = 0.0       # is the chosen subtype part of the playbook
    loop_penalty: float = 0.0       # repetition / stuck-state penalty
    unresolved_penalty: float = 0.0  # prior failed attempts penalty
    final: float = 0.0

    def to_dict(self) -> dict:
        return {k: round(v, 3) for k, v in asdict(self).items()}


# Component weights (must sum to 1.0 across the positive signals).
_WEIGHTS = {
    "system_match": 0.10,
    "subtype_match": 0.20,
    "retrieval_relevance": 0.30,
    "grounding": 0.25,
    "playbook_fit": 0.15,
}


def compute_resolution_confidence(
    *,
    system_match: float,
    subtype_match: float,
    retrieval_relevance: float,
    has_subtype_article: bool,
    same_family: bool,
    playbook_fit: bool,
    loop_counter: int = 0,
    failed_attempts: int = 0,
) -> ConfidenceBreakdown:
    """Blend signals into a calibrated resolution confidence.

    Args:
        system_match: Entity recognition confidence (0–1).
        subtype_match: Subtype classification confidence (0–1).
        retrieval_relevance: Top grounded article relevance (0–1).
        has_subtype_article: A kept article matched the identified subtype.
        same_family: The chosen article is in the issue's own category family.
        playbook_fit: The subtype is a known subtype of the category playbook.
        loop_counter: How many no-progress rounds have occurred.
        failed_attempts: How many prior resolution attempts the user rejected.
    """
    # Grounding is the gate: a subtype-matching, on-family article earns full
    # grounding; an on-family-but-generic article earns partial; anything else
    # (which the domain guard should already have removed) earns ~zero.
    if has_subtype_article and same_family:
        grounding = 1.0
    elif same_family and retrieval_relevance >= 0.4:
        grounding = 0.55
    elif same_family:
        grounding = 0.3
    else:
        grounding = 0.0

    bd = ConfidenceBreakdown(
        system_match=_clamp(system_match),
        subtype_match=_clamp(subtype_match),
        retrieval_relevance=_clamp(retrieval_relevance),
        grounding=grounding,
        playbook_fit=1.0 if playbook_fit else 0.5,
    )

    positive = (
        _WEIGHTS["system_match"] * bd.system_match
        + _WEIGHTS["subtype_match"] * bd.subtype_match
        + _WEIGHTS["retrieval_relevance"] * bd.retrieval_relevance
        + _WEIGHTS["grounding"] * bd.grounding
        + _WEIGHTS["playbook_fit"] * bd.playbook_fit
    )

    bd.loop_penalty = min(0.4, 0.15 * max(0, loop_counter))
    bd.unresolved_penalty = min(0.3, 0.12 * max(0, failed_attempts))

    # Hard ceiling when there is no real grounding — mismatched answers can
    # never look confident, regardless of other signals.
    final = positive - bd.loop_penalty - bd.unresolved_penalty
    if grounding == 0.0:
        final = min(final, 0.25)
    elif grounding < 0.6:
        final = min(final, 0.6)

    bd.final = round(_clamp(final), 3)
    return bd


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
