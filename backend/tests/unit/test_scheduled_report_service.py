"""C2: scheduled-report orchestration — date logic + idempotent send.

Exercises `ScheduledReportService` with a lightweight fake async session (no
Postgres required) — mirrors the FakeSession pattern used by
tests/unit/test_specialist_report_service.py. `SpecialistReportService.build_report`
and `get_email_sender` are monkeypatched at the seam (their own correctness is
covered by their dedicated test modules); this test focuses on: the previous-
month date math (incl. year rollover), the send-day gate, and the replica-safe
claim/retry state machine (fresh claim -> sent, already-sent -> skip, a
crashed/failed prior attempt -> retried, and a concurrent-insert race -> skip).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

import app.services.reporting.scheduled_report as scheduled_report_module
from app.models.reporting import ScheduledReportRun
from app.schemas.reporting import SpecialistReport, SpecialistReportRow
from app.services.reporting.scheduled_report import ScheduledReportService

# ── Pure date-logic tests ───────────────────────────────────────────────────


def test_previous_month_range_handles_year_rollover():
    start, end = ScheduledReportService.previous_month_range(datetime(2026, 1, 15, tzinfo=UTC))
    assert (start.year, start.month, start.day) == (2025, 12, 1)
    assert (end.year, end.month, end.day) == (2025, 12, 31)
    assert start.tzinfo is not None and end.tzinfo is not None


def test_previous_month_range_within_same_year():
    start, end = ScheduledReportService.previous_month_range(datetime(2026, 7, 1, tzinfo=UTC))
    assert (start.year, start.month, start.day) == (2026, 6, 1)
    assert (end.year, end.month, end.day) == (2026, 6, 30)


def test_period_key_is_previous_month():
    assert ScheduledReportService.period_key(datetime(2026, 7, 1, tzinfo=UTC)) == "2026-06"


def test_should_send_only_on_configured_day(monkeypatch):
    monkeypatch.setattr(scheduled_report_module.settings, "SCHEDULED_REPORT_DAY", 1, raising=False)
    assert ScheduledReportService.should_send(datetime(2026, 7, 1, tzinfo=UTC)) is True
    assert ScheduledReportService.should_send(datetime(2026, 7, 2, tzinfo=UTC)) is False


# ── Fake async session ──────────────────────────────────────────────────────


class _ScalarOneResult:
    """Mimics `(await session.execute(select(...))).scalar_one_or_none()`."""

    def __init__(self, row: ScheduledReportRun | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> ScheduledReportRun | None:
        return self._row


class FakeSession:
    """Models the single `scheduled_report_runs` row this service touches.

    `existing` is what the pre-check `SELECT ... WHERE period = :period`
    returns; after a successful `commit()` it is updated to reflect the
    (single) row this test scenario cares about, so a second `run_once` call
    against the same session sees the persisted state — exactly like two
    ticks hitting the same DB row.
    """

    def __init__(self, existing: ScheduledReportRun | None = None) -> None:
        self.existing = existing
        self.added: list = []
        self.raise_integrity_on_next_flush = False
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        return _ScalarOneResult(self.existing)

    def add(self, obj) -> None:
        self.added.append(obj)

    @property
    def claims_added(self) -> list[ScheduledReportRun]:
        """Just the `ScheduledReportRun` rows added (excludes audit events)."""
        return [obj for obj in self.added if isinstance(obj, ScheduledReportRun)]

    async def flush(self) -> None:
        if self.raise_integrity_on_next_flush:
            self.raise_integrity_on_next_flush = False
            raise IntegrityError("insert", {}, Exception("duplicate key: period"))

    async def commit(self) -> None:
        self.commits += 1
        # Track the most recent claim row specifically — a later audit-event
        # `add()` must not shadow it as "the" persisted row on commit.
        if self.claims_added:
            self.existing = self.claims_added[-1]

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSender:
    """Records every send() call instead of touching SMTP."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, *, to, subject, html_body, attachments=None) -> None:
        self.sent.append(
            {"to": to, "subject": subject, "html_body": html_body, "attachments": attachments}
        )


@dataclass
class _Env:
    session: FakeSession
    sender: FakeSender
    service: ScheduledReportService
    build_calls: list = field(default_factory=list)


def _fake_report() -> SpecialistReport:
    totals = SpecialistReportRow(
        agent_id=None, agent_name="Team totals", total_tickets=5, sla_violations=1, reopened=2
    )
    return SpecialistReport(
        period_start=datetime(2026, 6, 1, tzinfo=UTC),
        period_end=datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
        rows=[],
        totals=totals,
    )


def _configure_happy_path(monkeypatch, *, existing: ScheduledReportRun | None = None) -> _Env:
    """Flag on, send day, recipients + sender configured, report builds cleanly."""
    monkeypatch.setattr(
        scheduled_report_module.settings, "FEATURE_SCHEDULED_REPORTS", True, raising=False
    )
    monkeypatch.setattr(scheduled_report_module.settings, "SCHEDULED_REPORT_DAY", 1, raising=False)
    monkeypatch.setattr(
        scheduled_report_module.settings, "REPORT_RECIPIENTS", "lead@aditi.com", raising=False
    )

    session = FakeSession(existing=existing)
    sender = FakeSender()
    monkeypatch.setattr(scheduled_report_module, "get_email_sender", lambda: sender)

    build_calls: list = []

    async def fake_build_report(self, *, start, end):
        build_calls.append((start, end))
        return _fake_report()

    monkeypatch.setattr(
        scheduled_report_module.SpecialistReportService, "build_report", fake_build_report
    )
    monkeypatch.setattr(scheduled_report_module.exporters, "to_pdf", lambda report: b"%PDF-fake")

    service = ScheduledReportService(session)
    return _Env(session=session, sender=sender, service=service, build_calls=build_calls)


# ── run_once: gating paths ──────────────────────────────────────────────────


class TestRunOnceGating:
    async def test_flag_off_skips_without_claiming(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)
        monkeypatch.setattr(
            scheduled_report_module.settings, "FEATURE_SCHEDULED_REPORTS", False, raising=False
        )

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "skipped_not_day"
        assert env.session.added == []
        assert env.session.commits == 0
        assert env.sender.sent == []

    async def test_not_the_send_day_skips(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)

        outcome = await env.service.run_once(datetime(2026, 7, 2, tzinfo=UTC))

        assert outcome == "skipped_not_day"
        assert env.session.added == []
        assert env.sender.sent == []

    async def test_no_recipients_is_unconfigured(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)
        monkeypatch.setattr(
            scheduled_report_module.settings, "REPORT_RECIPIENTS", "", raising=False
        )

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "skipped_unconfigured"
        assert env.session.added == []

    async def test_no_sender_configured_is_unconfigured(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)
        monkeypatch.setattr(scheduled_report_module, "get_email_sender", lambda: None)

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "skipped_unconfigured"
        assert env.session.added == []


# ── run_once: claim / retry state machine ───────────────────────────────────


class TestRunOnceClaim:
    async def test_fresh_claim_sends_and_marks_sent(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "sent"
        assert len(env.sender.sent) == 1
        assert env.sender.sent[0]["to"] == ["lead@aditi.com"]
        assert len(env.session.claims_added) == 1
        claim = env.session.claims_added[0]
        assert claim.period == "2026-06"
        assert claim.status == "sent"
        assert claim.sent_at is not None
        assert len(env.build_calls) == 1

    async def test_second_run_after_sent_is_skipped_already(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)
        now = datetime(2026, 7, 1, tzinfo=UTC)

        first = await env.service.run_once(now)
        second = await env.service.run_once(now)

        assert first == "sent"
        assert second == "skipped_already"
        # Only one send ever went out, even though run_once was called twice.
        assert len(env.sender.sent) == 1

    async def test_already_sent_row_present_upfront_skips_without_resend(self, monkeypatch):
        existing = ScheduledReportRun(period="2026-06", status="sent", recipient_count=1)
        env = _configure_happy_path(monkeypatch, existing=existing)

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "skipped_already"
        assert env.sender.sent == []
        assert env.session.added == []

    async def test_prior_failed_claim_is_retried_and_can_now_succeed(self, monkeypatch):
        existing = ScheduledReportRun(period="2026-06", status="failed", recipient_count=1)
        env = _configure_happy_path(monkeypatch, existing=existing)

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "sent"
        assert len(env.sender.sent) == 1
        # Reused the existing row rather than inserting a new claim.
        assert env.session.claims_added == []
        assert existing.status == "sent"
        assert existing.sent_at is not None

    async def test_prior_stuck_sending_claim_is_retried(self, monkeypatch):
        existing = ScheduledReportRun(period="2026-06", status="sending", recipient_count=1)
        env = _configure_happy_path(monkeypatch, existing=existing)

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "sent"
        assert existing.status == "sent"

    async def test_concurrent_insert_race_yields_skipped_already(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)
        env.session.raise_integrity_on_next_flush = True

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "skipped_already"
        assert env.session.rollbacks == 1
        assert env.sender.sent == []

    async def test_send_failure_marks_claim_failed_and_returns_failed(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)

        async def boom(**_kwargs):
            raise RuntimeError("smtp down")

        env.sender.send = boom

        outcome = await env.service.run_once(datetime(2026, 7, 1, tzinfo=UTC))

        assert outcome == "failed"
        assert len(env.session.claims_added) == 1
        assert env.session.claims_added[0].status == "failed"

    async def test_failed_send_retries_next_tick_and_succeeds(self, monkeypatch):
        env = _configure_happy_path(monkeypatch)
        now = datetime(2026, 7, 1, tzinfo=UTC)

        async def boom(**_kwargs):
            raise RuntimeError("smtp down")

        env.sender.send = boom
        first = await env.service.run_once(now)
        assert first == "failed"

        # Restore a working sender for the retry tick (same session — the
        # failed row now persists as `existing` after the commit above).
        async def works(**_kwargs):
            env.sender.sent.append(_kwargs)

        env.sender.send = works
        second = await env.service.run_once(now)

        assert second == "sent"
        assert len(env.sender.sent) == 1
