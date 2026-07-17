"""Monthly scheduled-report email orchestration (C2).

Runs on a daily tick (see `SCHEDULED_REPORT_CHECK_INTERVAL_SECONDS`) and, on
the configured day of month, builds the previous month's specialist report,
renders it to PDF, and emails it to the configured recipients.

Replica-safe: `ScheduledReportRun.period` is unique, so concurrent app
replicas racing the same tick can only have one winner claim a given month.
A crashed/failed attempt leaves its claim row in `status="failed"` (or a
stuck `"sending"`), which is deliberately *reusable* by the next daily tick —
otherwise a transient SMTP outage would permanently skip that month's report.
A `status="sent"` row, in contrast, is never revisited: exactly one
successful send per month.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.logging import get_logger
from app.models.reporting import ScheduledReportRun
from app.services.email.sender import EmailAttachment, get_email_sender
from app.services.reporting import exporters
from app.services.reporting.specialist_report_service import SpecialistReportService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.reporting import SpecialistReport

logger = get_logger(__name__)

# Claim statuses that represent a prior attempt safe to retry (crashed mid-send
# or explicitly failed). A "sent" row is the only terminal, non-retryable state.
_RETRYABLE_STATUSES = ("sending", "failed")


class ScheduledReportService:
    """Claims the month, builds + sends the report, and records the outcome."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def previous_month_range(now: datetime) -> tuple[datetime, datetime]:
        """UTC [start, end] of the calendar month before `now`, handling Jan rollover."""
        year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
        last_day = monthrange(year, month)[1]
        start = datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=UTC)
        return start, end

    @staticmethod
    def period_key(now: datetime) -> str:
        """The previous month as `"YYYY-MM"` — the unique claim key."""
        start, _ = ScheduledReportService.previous_month_range(now)
        return f"{start.year:04d}-{start.month:02d}"

    @staticmethod
    def should_send(now: datetime) -> bool:
        return now.day == settings.SCHEDULED_REPORT_DAY

    async def run_once(self, now: datetime) -> str:
        """Run a single scheduled-report tick. Never raises — the scheduler loop
        calls this unattended, so every failure path must resolve to an outcome
        string rather than propagate.
        """
        try:
            return await self._run_once(now)
        except Exception:
            logger.exception("scheduled_report_run_once_unhandled_error")
            return "failed"

    async def _run_once(self, now: datetime) -> str:
        if not settings.FEATURE_SCHEDULED_REPORTS or not self.should_send(now):
            return "skipped_not_day"

        recipients = settings.report_recipients()
        sender = get_email_sender()
        if not recipients or sender is None:
            logger.info(
                "scheduled_report_skipped_unconfigured",
                recipients=len(recipients),
                has_sender=sender is not None,
            )
            return "skipped_unconfigured"

        period = self.period_key(now)
        claim = await self._claim_period(period, recipient_count=len(recipients))
        if claim is None:
            return "skipped_already"

        try:
            start, end = self.previous_month_range(now)
            report = await SpecialistReportService(self.db).build_report(start=start, end=end)
            pdf = exporters.to_pdf(report)
            html = self._summary_html(report)
            await sender.send(
                to=recipients,
                subject=f"Aditi IT — Specialist Report {period}",
                html_body=html,
                attachments=[
                    EmailAttachment(f"specialist-report-{period}.pdf", pdf, "application/pdf")
                ],
            )
            claim.status = "sent"
            claim.sent_at = datetime.now(UTC)
            await self.db.commit()
            await self._audit_sent(period, recipient_count=len(recipients))
            logger.info("scheduled_report_sent", period=period, recipients=len(recipients))
            return "sent"
        except Exception:
            claim.status = "failed"
            await self.db.commit()
            logger.exception("scheduled_report_send_failed", period=period)
            return "failed"

    async def _claim_period(
        self, period: str, *, recipient_count: int
    ) -> ScheduledReportRun | None:
        """Return a claimed row to proceed with, or `None` if already sent.

        A `"sent"` row for this period means the month was already delivered —
        never resend. A `"sending"`/`"failed"` row means a prior attempt was
        interrupted or failed; it is reused (retried) rather than re-inserted.
        Only when no row exists at all do we insert a fresh claim, and even
        then a concurrent replica may win the unique-index race — that loser
        rolls back and reports `skipped_already`.
        """
        existing = (
            await self.db.execute(
                select(ScheduledReportRun).where(ScheduledReportRun.period == period)
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.status == "sent":
                logger.info("scheduled_report_already_sent", period=period)
                return None
            if existing.status in _RETRYABLE_STATUSES:
                logger.info(
                    "scheduled_report_retrying_claim", period=period, prior_status=existing.status
                )
                existing.status = "sending"
                existing.recipient_count = recipient_count
                return existing
            # Unknown/unexpected status — treat conservatively as non-retryable.
            logger.warning(
                "scheduled_report_unexpected_claim_status",
                period=period,
                status=existing.status,
            )
            return None

        claim = ScheduledReportRun(period=period, status="sending", recipient_count=recipient_count)
        self.db.add(claim)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            logger.info("scheduled_report_already_claimed", period=period)
            return None
        return claim

    async def _audit_sent(self, period: str, *, recipient_count: int) -> None:
        try:
            from app.services.audit_service import AuditService

            await AuditService(self.db).log(
                action="reporting.scheduled_report_sent",
                resource_type="scheduled_report_run",
                resource_id=period,
                description=f"Scheduled specialist report for {period} emailed",
                new_value={"period": period, "recipient_count": recipient_count},
                severity="info",
            )
            await self.db.commit()
        except Exception as exc:  # audit must never break the send path
            logger.warning("scheduled_report_audit_failed", error=str(exc))

    def _summary_html(self, report: SpecialistReport) -> str:
        t = report.totals
        return (
            f"<h2>Specialist Report — {report.period_start:%b %Y}</h2>"
            f"<p>Team totals: {t.total_tickets} tickets, {t.sla_violations} SLA violations, "
            f"{t.reopened} reopened. Full breakdown attached (PDF).</p>"
        )


__all__ = ["ScheduledReportService"]
