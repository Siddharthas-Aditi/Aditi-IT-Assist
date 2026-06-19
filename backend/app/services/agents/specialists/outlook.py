"""Outlook specialist — proof-of-pattern implementation.

Owns the ``email/outlook`` scope. Delegates fine-grained subtype handling to
its sub-agents (mailbox_full, not_receiving, sending_failure, startup), each
of which is a small playbook over the grounded KB content.

Design notes
------------
The specialist is intentionally small. The "work" lives in three places:

1. **The registry** (:mod:`app.services.agents.registry`) declares scope.
2. **The base contract** (:mod:`.base`) declares the interface.
3. **This file** picks steps, advances past tried/failed ones, and renders
   a natural message.

Other specialists will look almost identical — copying this file and
swapping the registry lookup is the recommended starting point.

Grounding contract
------------------
The specialist may ONLY rely on the steps inside ``inp.knowledge_results``.
It must not invent steps; it must not pull in steps from another subtype's
article. The :func:`_advance_steps` helper enforces this by filtering to
articles whose ``subcategory`` matches the active subtype (when one is set).
This is the same rule the legacy ``resolution.py`` enforced — preserved here
so behavior is unchanged when the supervisor delegates to this specialist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.registry import AGENT_REGISTRY, SpecialistAgentSpec
from app.services.agents.specialists.base import (
    KnowledgeImprovementHint,
    ResolutionStep,
    SpecialistInput,
    SpecialistOutput,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.agents.diagnostic_state import DiagnosticContext

# Pull the spec from the registry at import time. If it's missing, registry
# is misconfigured — fail loudly.
_SPEC = AGENT_REGISTRY.get("outlook")
if not isinstance(_SPEC, SpecialistAgentSpec):
    raise RuntimeError(
        "Outlook specialist registered without a SpecialistAgentSpec — "
        "fix app/services/agents/registry.py"
    )


# Steps-per-turn (progressive disclosure). Matches the legacy resolution
# node's batch size so user experience is unchanged during rollout.
_BATCH_SIZE = 3


# Subtype → natural-language opener. Keyed on the canonical subtype slug so
# we never leak slugs to the user. Falls back to a generic line if missing.
_OPENERS = {
    "mailbox-full": (
        "It looks like your mailbox is full — that'll stop new mail "
        "until we free up some space."
    ),
    "not-receiving-emails": (
        "Got it — new emails aren't coming through. "
        "Let's narrow down where they're getting caught."
    ),
    "sending-failure": (
        "Sounds like outbound mail isn't going out. "
        "Let's check the usual culprits."
    ),
    "outlook-slow": "If Outlook is dragging, a couple of quick checks usually sort it.",
    "outlook-crash": (
        "If Outlook isn't opening or keeps crashing, "
        "there are a few reliable fixes to try."
    ),
    "offline-mode": "Looks like Outlook is stuck in offline mode — easy to flip back.",
}


class OutlookSpecialist:
    """Specialist agent for Microsoft Outlook + Exchange + M365 email."""

    spec = _SPEC

    def can_handle(self, inp: SpecialistInput) -> bool:
        """Defense in depth — the supervisor already filtered by category."""
        ctx = inp.diag_ctx
        return (
            (ctx.issue_category or "") in self.spec.categories
            or (ctx.normalized_system or "") in self.spec.systems
        )

    async def handle(self, inp: SpecialistInput) -> SpecialistOutput:
        """Produce the specialist's turn.

        Algorithm:
          1. Collect candidate steps from grounded articles, scoped to the
             active subtype where possible (no cross-subtype bleed).
          2. Drop steps already presented or marked failed.
          3. Take the next batch (configurable size).
          4. Render a natural message + structured step list.
          5. If no steps remain, signal escalation with a knowledge hint so
             the Improvement Agent knows the KB is short.
        """
        diag_ctx = inp.diag_ctx
        ordered, remaining = _advance_steps(inp)

        if not remaining:
            # Specialist is exhausted within its KB — escalate, and signal a
            # knowledge gap for the Improvement Agent to review.
            hint = KnowledgeImprovementHint(
                reason="specialist exhausted all grounded steps without resolution",
                issue_subtype=diag_ctx.issue_subtype,
                notes=(
                    f"Subtype {diag_ctx.issue_subtype!r} ran out of grounded steps "
                    f"after {diag_ctx.resolution_attempts} attempts."
                ),
                confidence=0.7,
            )
            return SpecialistOutput(
                message="",  # supervisor will route to escalation; no user message here
                steps=(),
                confidence=0.0,
                escalation_signal="exhausted_grounded_steps",
                knowledge_hints=(hint,),
                audit={
                    "event": "specialist.outlook.exhausted",
                    "subtype": diag_ctx.issue_subtype,
                    "attempts": diag_ctx.resolution_attempts,
                },
            )

        batch = remaining[:_BATCH_SIZE]
        steps = tuple(
            ResolutionStep(
                step_number=i,
                instruction=s["instruction"],
                details=s.get("details"),
                citation_title=s.get("source") or None,
            )
            for i, s in enumerate(batch, 1)
        )

        message = _render_message(diag_ctx, steps, is_followup=bool(diag_ctx.failed_steps))
        presented = tuple(s.instruction for s in steps)

        return SpecialistOutput(
            message=message,
            steps=steps,
            confidence=max(0.5, inp.knowledge_confidence),
            presented_steps=presented,
            audit={
                "event": "specialist.outlook.handled",
                "subtype": diag_ctx.issue_subtype,
                "sub_agent": inp.sub_agent.name if inp.sub_agent else None,
                "steps_count": len(steps),
                "remaining_after": max(0, len(remaining) - len(batch)),
            },
        )


# ── Helpers ────────────────────────────────────────────────────────────────


def _advance_steps(inp: SpecialistInput) -> tuple[list[dict], list[dict]]:
    """Build the ordered step plan and the un-tried remaining subset.

    Mirrors the grounding rule in the legacy ``resolution._build_progression``:
    if the active subtype has an article match, draw steps ONLY from those
    articles. This is what stops a mailbox-full conversation from leaking
    "Work Offline" steps from a sibling article.
    """
    ctx = inp.diag_ctx
    subtype = (ctx.issue_subtype or "").replace("_", "-").lower()

    def _matches_subtype(art: dict) -> bool:
        sc = (art.get("subcategory") or art.get("subtype") or art.get("issue_type") or "")
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
            ordered.append({
                "instruction": instruction,
                "details": details,
                "source": art.get("title", ""),
            })

    remaining = [s for s in ordered if not ctx.is_step_exhausted_or_seen(s["instruction"])]
    return ordered, remaining


def _iter_steps(article: dict):
    """Steps live under one of several keys across the legacy/new schemas."""
    return (
        article.get("resolution_steps")
        or article.get("troubleshooting_steps")
        or article.get("steps")
        or []
    )


def _normalize_step(step) -> tuple[str, str | None]:
    if isinstance(step, dict):
        instruction = step.get("instruction") or step.get("step") or str(step)
        details = step.get("details") or step.get("expected_outcome")
        return instruction, details
    return str(step), None


def _norm_key(text: str) -> str:
    return " ".join((text or "").lower().split())


def _render_message(
    diag_ctx: DiagnosticContext,
    steps: tuple[ResolutionStep, ...],
    *,
    is_followup: bool,
) -> str:
    """Compose a natural, conversational reply (NOT a numbered dump).

    The UI renders ``steps`` as a structured panel separately, so the
    message paraphrases the gist in 2-4 sentences. Phrasing varies by
    whether this is the first attempt or a follow-up after failed steps.
    """
    subtype = (diag_ctx.issue_subtype or "").replace("_", "-").lower()
    opener = _OPENERS.get(subtype) or "Let's take a look at your Outlook issue."
    first = steps[0].instruction
    first_lower = first[:1].lower() + first[1:]

    if is_followup:
        return (
            "Thanks for trying those — no worries, let's keep going. "
            f"A good next step is to {first_lower}. "
            "I've laid the exact steps out for you below. Let me know how it goes."
        )

    return (
        f"{opener} "
        f"The best place to start is to {first_lower}. "
        "I've laid out the exact steps just below — give those a go "
        "and let me know if that sorts it."
    )
