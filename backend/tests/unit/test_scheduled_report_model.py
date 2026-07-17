"""Model contract test for ScheduledReportRun (C2 idempotency table)."""

from app.models.reporting import ScheduledReportRun


def test_model_table_and_unique_period():
    cols = ScheduledReportRun.__table__.columns
    assert "period" in cols and "status" in cols and "sent_at" in cols
    # period is unique (replica-safe claim)
    assert cols["period"].unique is True or any(
        "period" in [c.name for c in uc.columns]
        for uc in ScheduledReportRun.__table__.constraints
        if hasattr(uc, "columns")
    )
