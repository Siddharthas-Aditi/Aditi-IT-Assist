"""Shared specialist helpers — step progression + message rendering.

Every specialist needs the same three building blocks:

1. ``advance_steps(inp)`` — collect grounded steps, filter to the active
   subtype, drop ones already presented or failed, return (ordered, remaining).
2. ``compose_specialist_output(...)`` — turn the next batch into a
   :class:`SpecialistOutput` with steps + presented_steps + audit entry,
   handling the exhausted-grounded-steps escalation signal.
3. ``render_message(...)`` — render a natural prose reply based on a
   per-specialist opener map.

Factoring these out lets every specialist file stay ~40-60 lines: one
opener dict, one ``handle()`` that calls these helpers. The Outlook
specialist remains the reference implementation but the helpers below are
what every other specialist (and Outlook itself in Phase-2 refactor) uses.

This module has no IO and no LLM call — pure functions over typed inputs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.specialists.base import (
    KnowledgeImprovementHint,
    ResolutionStep,
    SpecialistOutput,
)

if TYPE_CHECKING:
    from app.services.agents.diagnostic_state import DiagnosticContext
    from app.services.agents.specialists.base import SpecialistInput


# Batch size matches the legacy resolution node so user-visible behavior
# is unchanged during the supervisor rollout.
BATCH_SIZE = 3

# Fallback opener used when a specialist hasn't defined a subtype-specific
# line. Generic but still natural; keeps the chat from leaking subtype
# slugs to the user.
_FALLBACK_OPENER = "Let's take a look at what's going on."


def advance_steps(
    inp: SpecialistInput,
) -> tuple[list[dict], list[dict]]:
    """Build the ordered step plan and the un-tried remaining subset.

    Mirrors the grounding rule the legacy resolution node used: when the
    active subtype has at least one matching article, draw steps only from
    those articles — never bleed across subtypes. Without a subtype match,
    fall back to all grounded results in rank order.
    """
    ctx = inp.diag_ctx
    subtype = (ctx.issue_subtype or "").replace("_", "-").lower()

    def _matches_subtype(art: dict) -> bool:
        sc = art.get("subcategory") or art.get("subtype") or art.get("issue_type") or ""
        return bool(subtype) and sc.replace("_", "-").lower() == subtype

    matched = [a for a in inp.knowledge_results if _matches_subtype(a)]
    source_articles = matched or list(inp.knowledge_results)

    ordered: list[dict] = []
    seen: set[str] = set()
    for art in source_articles:
        for raw in _iter_steps(art):
            instruction, details = _normalize_step(raw)
            key = _norm_key(instruction)
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(
                {
                    "instruction": instruction,
                    "details": details,
                    "source": art.get("title", ""),
                }
            )

    remaining = [s for s in ordered if not ctx.is_step_exhausted_or_seen(s["instruction"])]
    return ordered, remaining


def compose_specialist_output(
    inp: SpecialistInput,
    *,
    specialist_name: str,
    openers: dict[str, str],
    followup_lead_in: str = "Thanks for trying those — let's keep going.",
    first_lead_in: str | None = None,
) -> SpecialistOutput:
    """Standard specialist turn: advance, batch, render, audit.

    A specialist's ``handle()`` is almost always one call to this function.
    The only per-specialist data is the openers dict (subtype slug → natural
    line) and the lead-in phrases.

    On exhaustion, emits a ``KnowledgeImprovementHint`` so the SME review
    queue can pick up the gap — never silently escalates.
    """
    diag_ctx = inp.diag_ctx
    ordered, remaining = advance_steps(inp)

    if not remaining:
        hint = KnowledgeImprovementHint(
            reason="specialist exhausted all grounded steps without resolution",
            issue_subtype=diag_ctx.issue_subtype,
            notes=(
                f"Specialist {specialist_name!r} ran out of grounded steps for "
                f"subtype {diag_ctx.issue_subtype!r} after "
                f"{diag_ctx.resolution_attempts} attempts."
            ),
            confidence=0.7,
        )
        return SpecialistOutput(
            message="",
            steps=(),
            confidence=0.0,
            escalation_signal="exhausted_grounded_steps",
            knowledge_hints=(hint,),
            audit={
                "event": f"specialist.{specialist_name}.exhausted",
                "subtype": diag_ctx.issue_subtype,
                "attempts": diag_ctx.resolution_attempts,
            },
        )

    batch = remaining[:BATCH_SIZE]
    steps = tuple(
        ResolutionStep(
            step_number=i,
            instruction=s["instruction"],
            details=s.get("details"),
            citation_title=s.get("source") or None,
        )
        for i, s in enumerate(batch, 1)
    )

    message = render_message(
        diag_ctx,
        steps,
        openers=openers,
        is_followup=bool(diag_ctx.failed_steps),
        followup_lead_in=followup_lead_in,
        first_lead_in=first_lead_in,
    )

    return SpecialistOutput(
        message=message,
        steps=steps,
        confidence=max(0.5, inp.knowledge_confidence),
        presented_steps=tuple(s.instruction for s in steps),
        audit={
            "event": f"specialist.{specialist_name}.handled",
            "subtype": diag_ctx.issue_subtype,
            "sub_agent": inp.sub_agent.name if inp.sub_agent else None,
            "steps_count": len(steps),
            "remaining_after": max(0, len(remaining) - len(batch)),
        },
    )


def render_message(
    diag_ctx: DiagnosticContext,
    steps: tuple[ResolutionStep, ...],
    *,
    openers: dict[str, str],
    is_followup: bool,
    followup_lead_in: str = "Thanks for trying those — let's keep going.",
    first_lead_in: str | None = None,
) -> str:
    """Compose a natural, conversational reply (NOT a numbered dump).

    The UI renders ``steps`` as a structured panel separately, so the
    message paraphrases the gist in 2-4 sentences. Phrasing varies by
    whether this is the first attempt or a follow-up after failed steps,
    which keeps the agent from sounding stuck on a template.
    """
    if not steps:
        return ""
    subtype = (diag_ctx.issue_subtype or "").replace("_", "-").lower()
    opener = openers.get(subtype) or _FALLBACK_OPENER
    first_instruction = steps[0].instruction
    first_lower = first_instruction[:1].lower() + first_instruction[1:]

    if is_followup:
        return (
            f"{followup_lead_in} "
            f"A good next step is to {first_lower}. "
            "I've laid the exact steps out for you just below — give those "
            "a go and let me know how it goes."
        )

    lead = first_lead_in or opener
    return (
        f"{lead} "
        f"The best place to start is to {first_lower}. "
        "I've laid out the exact steps just below — give those a go "
        "and let me know if that sorts it."
    )


# ── Internals ──────────────────────────────────────────────────────────


def _iter_steps(article: dict) -> list:
    return (
        article.get("resolution_steps")
        or article.get("troubleshooting_steps")
        or article.get("steps")
        or []
    )


def _normalize_step(step: object) -> tuple[str, str | None]:
    if isinstance(step, dict):
        instruction = step.get("instruction") or step.get("step") or str(step)
        details = step.get("details") or step.get("expected_outcome")
        return instruction, details
    return str(step), None


def _norm_key(text: str) -> str:
    return " ".join((text or "").lower().split())


__all__ = [
    "BATCH_SIZE",
    "advance_steps",
    "compose_specialist_output",
    "render_message",
]
