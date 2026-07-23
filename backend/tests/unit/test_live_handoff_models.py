from __future__ import annotations

from app.models.live_handoff import (
    LIVE_HANDOFF_OFFER_STATES,
    SPECIALIST_AVAILABILITY_STATUSES,
    LiveHandoffOffer,
    SpecialistAvailability,
)


def test_enum_tuples():
    assert SPECIALIST_AVAILABILITY_STATUSES == ("available", "away")
    assert set(LIVE_HANDOFF_OFFER_STATES) == {
        "offered",
        "accepted",
        "expired",
        "broadened",
        "fallback",
    }


def test_table_names_and_columns():
    assert SpecialistAvailability.__tablename__ == "specialist_availability"
    assert LiveHandoffOffer.__tablename__ == "live_handoff_offers"
    # key columns exist
    assert "status" in SpecialistAvailability.__table__.columns
    assert "last_heartbeat_at" in SpecialistAvailability.__table__.columns
    for col in ("ticket_id", "offered_to", "expires_at", "round_index", "state"):
        assert col in LiveHandoffOffer.__table__.columns
