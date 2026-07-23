"""Live-handoff offer lifecycle: routing + decision (pure) and the DB service.

Pure functions (`rank_candidates`, `decide_next`) hold all the policy and are
unit-tested without I/O. `HandoffService` applies them against the DB and is
driven by both the escalation path (create the first offer) and the periodic
sweeper (advance expired offers).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime


@dataclass(frozen=True)
class SpecialistLoad:
    user_id: uuid.UUID
    active_load: int


def rank_candidates(
    ticket_category: str | None,
    available: list[SpecialistLoad],
    recent_category_handlers: set[uuid.UUID],
) -> list[uuid.UUID]:
    """Best-first ordering: lowest load, category-recent handlers boosted, stable."""

    def sort_key(s: SpecialistLoad) -> tuple[int, int, str]:
        boosted = 0 if s.user_id in recent_category_handlers else 1
        return (s.active_load, boosted, str(s.user_id))

    return [s.user_id for s in sorted(available, key=sort_key)]


@dataclass(frozen=True)
class HandoffDecision:
    action: str  # "hold" | "reoffer" | "broaden" | "fallback"
    next_specialist_id: uuid.UUID | None = None


def decide_next(
    *,
    offered_at: datetime,
    request_started_at: datetime,
    round_index: int,
    candidates_remaining: list[uuid.UUID],
    any_available: bool,
    now: datetime,
    offer_ttl_seconds: int,
    max_rounds: int,
    fallback_seconds: int,
) -> HandoffDecision:
    """Decide how to advance a live-handoff offer. Pure."""
    if (now - request_started_at).total_seconds() >= fallback_seconds:
        return HandoffDecision("fallback")
    if (now - offered_at).total_seconds() < offer_ttl_seconds:
        return HandoffDecision("hold")
    # Offer expired. Try another targeted round unless we've hit the cap.
    if round_index + 1 < max_rounds and candidates_remaining:
        return HandoffDecision("reoffer", candidates_remaining[0])
    # Cap reached or no targeted candidate left → broaden if anyone is Available.
    if any_available:
        return HandoffDecision("broaden")
    return HandoffDecision("fallback")
