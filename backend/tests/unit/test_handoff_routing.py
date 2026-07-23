from __future__ import annotations

import uuid

from app.services.specialist_handoff_service import SpecialistLoad, rank_candidates

A = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
B = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
C = uuid.UUID("00000000-0000-0000-0000-0000000000cc")


def test_orders_by_lowest_load():
    out = rank_candidates(
        "email/outlook",
        [SpecialistLoad(A, 3), SpecialistLoad(B, 1), SpecialistLoad(C, 2)],
        recent_category_handlers=set(),
    )
    assert out == [B, C, A]


def test_category_handler_boosted_at_equal_load():
    # A and B both load 2; C recently handled the category -> C ahead of equals.
    out = rank_candidates(
        "network/vpn",
        [SpecialistLoad(A, 2), SpecialistLoad(B, 2), SpecialistLoad(C, 2)],
        recent_category_handlers={C},
    )
    assert out[0] == C


def test_empty_available_returns_empty():
    assert rank_candidates("x", [], set()) == []
