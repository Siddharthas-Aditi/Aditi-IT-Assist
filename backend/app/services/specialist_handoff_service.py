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
