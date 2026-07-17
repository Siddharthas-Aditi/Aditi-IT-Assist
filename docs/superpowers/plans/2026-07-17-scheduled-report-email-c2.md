# Scheduled Monthly Report Email (C2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the 1st of each month, email the previous month's per-specialist report (PDF + HTML summary) to a configurable recipient list via aiosmtplib SMTP, behind `FEATURE_SCHEDULED_REPORTS`, sent exactly once per month across replicas.

**Architecture:** A pluggable `EmailSender` (SMTP impl via aiosmtplib, reusing existing Office365 SMTP config) + a `ScheduledReportService` that reuses C1's `SpecialistReportService`/`exporters`, guarded by a DB `scheduled_report_runs` unique-`period` claim (migration 011) for replica-safe once-per-month delivery, driven by a daily job on the existing asyncio scheduler.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic / aiosmtplib / pytest / Ruff.

## Global Constraints

- Line ≤100; `cd backend && uv run ruff check . && uv run ruff format --check .` clean (format-check new test files too).
- Behind `FEATURE_SCHEDULED_REPORTS` (default False). Flag off / SMTP unconfigured / no recipients ⇒ safe no-op: no send, no error, no wasted period-claim.
- **Exactly one send per month across replicas** — enforced by the DB unique-`period` claim, not by in-process state.
- The scheduled job never raises into the scheduler loop (isolated try/except like existing sweepers). SMTP password never logged.
- Migration 011 reversible (`memory/known-risks.md` #7). `settings` singleton accessor. Run backend cmds from `backend/` via `uv`.

---

### Task 1: Config + EmailSender (aiosmtplib)

**Files:**
- Modify: `backend/app/core/config.py` (C2 settings) + `backend/.env.example`
- Modify: `backend/pyproject.toml` (add `aiosmtplib>=3.0`)
- Create: `backend/app/services/email/__init__.py`, `backend/app/services/email/sender.py`
- Test: `backend/tests/unit/test_email_sender.py`

**Interfaces:**
- Produces: `EmailAttachment` (dataclass: `filename: str`, `content: bytes`, `mime_type: str`), `EmailSender` protocol (`async send(*, to, subject, html_body, attachments=None)`), `SmtpEmailSender` (`.is_configured`), `EmailNotConfigured` exception, `build_message(...) -> EmailMessage`, `get_email_sender() -> EmailSender | None`; settings `FEATURE_SCHEDULED_REPORTS`, `REPORT_RECIPIENTS`, `SCHEDULED_REPORT_DAY`, `report_recipients()`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_email_sender.py`:

```python
"""C2: email transport — MIME assembly + configured-gate + mocked SMTP send."""

import pytest

from app.services.email import sender as S
from app.services.email.sender import EmailAttachment, EmailNotConfigured, SmtpEmailSender


def test_build_message_has_html_and_attachment():
    msg = S.build_message(
        sender="it@aditi.com",
        to=["lead@aditi.com", "admin@aditi.com"],
        subject="Monthly Report",
        html_body="<p>hi</p>",
        attachments=[EmailAttachment("report.pdf", b"%PDF-1.4 data", "application/pdf")],
    )
    assert msg["To"] == "lead@aditi.com, admin@aditi.com"
    assert msg["Subject"] == "Monthly Report"
    payloads = list(msg.iter_attachments())
    assert len(payloads) == 1
    assert payloads[0].get_filename() == "report.pdf"


def test_is_configured_false_without_creds(monkeypatch):
    monkeypatch.setattr(S.settings, "SMTP_HOST", "smtp.office365.com", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_USER", "", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PASSWORD", "", raising=False)
    assert SmtpEmailSender().is_configured is False


@pytest.mark.asyncio
async def test_send_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(S.settings, "SMTP_USER", "", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PASSWORD", "", raising=False)
    with pytest.raises(EmailNotConfigured):
        await SmtpEmailSender().send(to=["x@aditi.com"], subject="s", html_body="<p>b</p>")


@pytest.mark.asyncio
async def test_send_invokes_aiosmtplib(monkeypatch):
    monkeypatch.setattr(S.settings, "SMTP_HOST", "smtp.office365.com", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PORT", 587, raising=False)
    monkeypatch.setattr(S.settings, "SMTP_USER", "it@aditi.com", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PASSWORD", "secret", raising=False)
    calls = {}

    async def _fake_send(message, **kwargs):
        calls["kwargs"] = kwargs
        calls["to"] = message["To"]

    monkeypatch.setattr(S.aiosmtplib, "send", _fake_send)
    await SmtpEmailSender().send(to=["lead@aditi.com"], subject="s", html_body="<p>b</p>")
    assert calls["to"] == "lead@aditi.com"
    assert calls["kwargs"]["hostname"] == "smtp.office365.com"
    assert calls["kwargs"]["start_tls"] is True
    assert calls["kwargs"]["username"] == "it@aditi.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_email_sender.py -v`
Expected: FAIL — module + deps missing.

- [ ] **Step 3: Add deps + config**

In `backend/pyproject.toml` `dependencies`, add `"aiosmtplib>=3.0",`; run `cd backend && uv sync`.

In `backend/app/core/config.py`, after `IDLE_SWEEPER_ENABLED` (~line 204) add:
```python
    # ── Scheduled report email (C2) ──────────────────────────────────
    FEATURE_SCHEDULED_REPORTS: bool = False
    REPORT_RECIPIENTS: str = ""  # comma-separated emails
    SCHEDULED_REPORT_DAY: int = 1  # day-of-month to send
    SCHEDULED_REPORT_CHECK_INTERVAL_SECONDS: int = 86400  # daily check

    def report_recipients(self) -> list[str]:
        return [e.strip() for e in self.REPORT_RECIPIENTS.split(",") if e.strip()]
```
Document the new keys + reuse of `SMTP_*` in `backend/.env.example`.

- [ ] **Step 4: Add the email sender**

Create `backend/app/services/email/__init__.py` (empty) and `backend/app/services/email/sender.py`:

```python
"""Email transport (C2) — pluggable sender with an aiosmtplib SMTP impl."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailNotConfigured(RuntimeError):
    """Raised when a send is attempted without SMTP credentials."""


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str  # e.g. "application/pdf"


class EmailSender(Protocol):
    async def send(
        self,
        *,
        to: list[str],
        subject: str,
        html_body: str,
        attachments: list[EmailAttachment] | None = None,
    ) -> None: ...


def build_message(
    *,
    sender: str,
    to: list[str],
    subject: str,
    html_body: str,
    attachments: list[EmailAttachment] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content("This report requires an HTML-capable email client.")
    msg.add_alternative(html_body, subtype="html")
    for att in attachments or []:
        maintype, _, subtype = att.mime_type.partition("/")
        msg.add_attachment(
            att.content, maintype=maintype, subtype=subtype or "octet-stream",
            filename=att.filename,
        )
    return msg


class SmtpEmailSender:
    """Sends via aiosmtplib over STARTTLS using the configured SMTP server."""

    @property
    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)

    async def send(
        self,
        *,
        to: list[str],
        subject: str,
        html_body: str,
        attachments: list[EmailAttachment] | None = None,
    ) -> None:
        if not self.is_configured:
            raise EmailNotConfigured("SMTP is not configured")
        message = build_message(
            sender=settings.SMTP_USER, to=to, subject=subject,
            html_body=html_body, attachments=attachments,
        )
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info("report_email_sent", recipients=len(to), subject=subject)


def get_email_sender() -> EmailSender | None:
    sender = SmtpEmailSender()
    return sender if sender.is_configured else None
```

- [ ] **Step 5: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_email_sender.py -v && uv run ruff check app/services/email/ app/core/config.py tests/unit/test_email_sender.py && uv run ruff format --check app/services/email/ app/core/config.py`
Expected: PASS + clean.
```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/.env.example backend/app/services/email/ backend/tests/unit/test_email_sender.py
git commit -m "feat(email): pluggable EmailSender + aiosmtplib SMTP impl (C2)"
```

---

### Task 2: Idempotency model + migration 011

**Files:**
- Create: `backend/app/models/reporting.py` (`ScheduledReportRun`)
- Modify: `backend/app/models/__init__.py` (export it, if models are re-exported there — check)
- Create: `backend/alembic/versions/011_scheduled_report_runs.py`
- Test: `backend/tests/unit/test_scheduled_report_model.py`

**Interfaces:**
- Produces: `ScheduledReportRun` (`id`, `period: str` UNIQUE, `status: str`, `recipient_count: int`, `created_at`, `sent_at: datetime | None`); migration `011_scheduled_report_runs` (revises `010_web_research_findings`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_scheduled_report_model.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_scheduled_report_model.py -v`
Expected: FAIL — model missing.

- [ ] **Step 3: Add the model**

Read `backend/app/models/escalation.py` for the mixin imports (`UUIDPrimaryKeyMixin`, `TimestampMixin`, `Base`). Create `backend/app/models/reporting.py`:

```python
"""Scheduled-report bookkeeping (C2) — replica-safe once-per-month claim."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScheduledReportRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scheduled_report_runs"

    period: Mapped[str] = mapped_column(String(7), unique=True, index=True)  # "YYYY-MM"
    status: Mapped[str] = mapped_column(String(20), default="sending")  # sending|sent|failed
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Confirm the mixin names/location against `escalation.py` (adjust the import if `base.py` differs). If `backend/app/models/__init__.py` re-exports models for Alembic autogenerate/metadata, add `ScheduledReportRun` there.

- [ ] **Step 4: Add migration 011**

Create `backend/alembic/versions/011_scheduled_report_runs.py` (follow the 010 header pattern):

```python
"""Scheduled report runs — replica-safe once-per-month email claim (C2)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "011_scheduled_report_runs"
down_revision = "010_web_research_findings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_report_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="sending"),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_scheduled_report_runs_period", "scheduled_report_runs",
                                ["period"])
    op.create_index("ix_scheduled_report_runs_period", "scheduled_report_runs", ["period"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_report_runs_period", table_name="scheduled_report_runs")
    op.drop_constraint("uq_scheduled_report_runs_period", "scheduled_report_runs",
                       type_="unique")
    op.drop_table("scheduled_report_runs")
```

Confirm the `created_at`/`updated_at` columns match what `TimestampMixin` produces (names + server defaults) — read `base.py` and align (drop/rename if the mixin names differ).

- [ ] **Step 5: Run test + migration round-trip + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_scheduled_report_model.py -v && uv run ruff check app/models/reporting.py alembic/versions/011_scheduled_report_runs.py`
If a dev DB is available: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` (note in report if no DB).
```bash
git add backend/app/models/reporting.py backend/app/models/__init__.py backend/alembic/versions/011_scheduled_report_runs.py backend/tests/unit/test_scheduled_report_model.py
git commit -m "feat(reporting): scheduled_report_runs idempotency table (migration 011)"
```

---

### Task 3: ScheduledReportService (claim → build → send → mark)

**Files:**
- Create: `backend/app/services/reporting/scheduled_report.py`
- Test: `backend/tests/unit/test_scheduled_report_service.py`

**Interfaces:**
- Consumes: `SpecialistReportService`, `exporters.to_pdf`, `get_email_sender`, `settings`, `ScheduledReportRun`, `AuditService`.
- Produces: `ScheduledReportService(db)` with `previous_month_range(now) -> (start, end)` (static/pure), `should_send(now) -> bool`, `period_key(now) -> str`, `async run_once(now) -> str` (returns an outcome string: `"sent"|"skipped_not_day"|"skipped_unconfigured"|"skipped_already"|"failed"`), and a `_summary_html(report) -> str` helper.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_scheduled_report_service.py`:

```python
"""C2: scheduled-report orchestration — date logic + idempotent send."""

from datetime import UTC, datetime

import pytest

from app.services.reporting.scheduled_report import ScheduledReportService


def test_previous_month_range_handles_year_rollover():
    start, end = ScheduledReportService.previous_month_range(datetime(2026, 1, 15, tzinfo=UTC))
    assert (start.year, start.month, start.day) == (2025, 12, 1)
    assert (end.year, end.month, end.day) == (2025, 12, 31)
    assert start.tzinfo is not None and end.tzinfo is not None


def test_period_key_is_previous_month():
    assert ScheduledReportService.period_key(datetime(2026, 7, 1, tzinfo=UTC)) == "2026-06"


def test_should_send_only_on_configured_day(monkeypatch):
    import app.services.reporting.scheduled_report as M

    monkeypatch.setattr(M.settings, "SCHEDULED_REPORT_DAY", 1, raising=False)
    assert ScheduledReportService.should_send(datetime(2026, 7, 1, tzinfo=UTC)) is True
    assert ScheduledReportService.should_send(datetime(2026, 7, 2, tzinfo=UTC)) is False
```

Add a `run_once` test using a fake DB session + monkeypatched `get_email_sender` (returns a fake recorder), `SpecialistReportService.build_report` (returns a small report), and `settings` (flag on, recipients set): assert first `run_once` on day 1 sends once and returns `"sent"`; a second `run_once` for the same period returns `"skipped_already"` (simulate the claim conflict — see Step 3 for the claim mechanism, mock accordingly); flag off / no recipients / no sender → the matching `skipped_*`. Match the real claim mechanism you implement.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_scheduled_report_service.py -v`
Expected: FAIL — service missing.

- [ ] **Step 3: Add the service**

Create `backend/app/services/reporting/scheduled_report.py`:

```python
"""Monthly scheduled-report email orchestration (C2)."""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.reporting import ScheduledReportRun
from app.services.email.sender import EmailAttachment, get_email_sender
from app.services.reporting import exporters
from app.services.reporting.specialist_report_service import SpecialistReportService

logger = get_logger(__name__)


class ScheduledReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def previous_month_range(now: datetime) -> tuple[datetime, datetime]:
        year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
        last = monthrange(year, month)[1]
        start = datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(year, month, last, 23, 59, 59, 999999, tzinfo=UTC)
        return start, end

    @staticmethod
    def period_key(now: datetime) -> str:
        start, _ = ScheduledReportService.previous_month_range(now)
        return f"{start.year:04d}-{start.month:02d}"

    @staticmethod
    def should_send(now: datetime) -> bool:
        return now.day == settings.SCHEDULED_REPORT_DAY

    async def run_once(self, now: datetime) -> str:
        if not settings.FEATURE_SCHEDULED_REPORTS or not self.should_send(now):
            return "skipped_not_day"
        recipients = settings.report_recipients()
        sender = get_email_sender()
        if not recipients or sender is None:
            logger.info("scheduled_report_skipped_unconfigured",
                        recipients=len(recipients), has_sender=sender is not None)
            return "skipped_unconfigured"

        period = self.period_key(now)
        # Replica-safe claim: unique period. Loser skips.
        claim = ScheduledReportRun(period=period, status="sending",
                                   recipient_count=len(recipients))
        self.db.add(claim)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            logger.info("scheduled_report_already_claimed", period=period)
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
                attachments=[EmailAttachment(f"specialist-report-{period}.pdf", pdf,
                                             "application/pdf")],
            )
            claim.status = "sent"
            claim.sent_at = datetime.now(UTC)
            await self.db.commit()
            logger.info("scheduled_report_sent", period=period, recipients=len(recipients))
            return "sent"
        except Exception:
            claim.status = "failed"
            await self.db.commit()
            logger.exception("scheduled_report_send_failed", period=period)
            return "failed"

    def _summary_html(self, report) -> str:
        t = report.totals
        return (
            f"<h2>Specialist Report — {report.period_start:%b %Y}</h2>"
            f"<p>Team totals: {t.total_tickets} tickets, {t.sla_violations} SLA violations, "
            f"{t.reopened} reopened. Full breakdown attached (PDF).</p>"
        )
```

Note: a `failed` claim row keeps the `period` unique constraint occupied. For the next daily tick to retry, `run_once` must treat an existing `failed` row as retryable: before the `flush` claim, check for an existing row for `period`; if it exists with `status=="sent"` → `skipped_already`; if `status in ("sending","failed")` from a prior crashed/failed attempt → reuse/update it and proceed. Implement this pre-check (a `select(ScheduledReportRun).where(period==period)`) so a failed send retries next day but a sent one never resends. Adjust the test accordingly.

- [ ] **Step 4: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_scheduled_report_service.py -v && uv run ruff check app/services/reporting/scheduled_report.py tests/unit/test_scheduled_report_service.py && uv run ruff format --check app/services/reporting/scheduled_report.py`
Expected: PASS + clean.
```bash
git add backend/app/services/reporting/scheduled_report.py backend/tests/unit/test_scheduled_report_service.py
git commit -m "feat(reporting): scheduled-report orchestration with replica-safe claim"
```

---

### Task 4: Scheduler + lifespan wiring

**Files:**
- Modify: `backend/app/services/scheduler.py` (job fn + `start_background_jobs` param)
- Modify: `backend/app/main.py` (pass the flag from settings)
- Test: `backend/tests/unit/test_scheduler_scheduled_report.py`

**Interfaces:**
- Consumes: `ScheduledReportService`, `settings.FEATURE_SCHEDULED_REPORTS`, `SCHEDULED_REPORT_CHECK_INTERVAL_SECONDS`.
- Produces: `start_background_jobs(..., scheduled_reports_enabled=False, scheduled_report_interval_seconds=86400)` registers the job when enabled.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_scheduler_scheduled_report.py`:

```python
"""C2: the scheduled-report job registers only when enabled."""

import pytest

from app.services import scheduler as sched


@pytest.mark.asyncio
async def test_scheduled_report_job_registered_when_enabled(monkeypatch):
    created = []
    real_create_task = sched.asyncio.create_task

    def _spy(coro, name=None):
        created.append(name)
        return real_create_task(coro, name=name)

    monkeypatch.setattr(sched.asyncio, "create_task", _spy)
    async with sched.start_background_jobs(
        idle_sweeper_enabled=False,
        remote_sweeper_enabled=False,
        scheduled_reports_enabled=True,
        scheduled_report_interval_seconds=3600,
    ):
        pass
    assert any(n == "reporting.scheduled_report" for n in created)


@pytest.mark.asyncio
async def test_scheduled_report_job_absent_when_disabled(monkeypatch):
    created = []
    real_create_task = sched.asyncio.create_task
    monkeypatch.setattr(
        sched.asyncio, "create_task",
        lambda coro, name=None: (created.append(name), real_create_task(coro, name=name))[1],
    )
    async with sched.start_background_jobs(
        idle_sweeper_enabled=False, remote_sweeper_enabled=False,
        scheduled_reports_enabled=False,
    ):
        pass
    assert "reporting.scheduled_report" not in created
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_scheduler_scheduled_report.py -v`
Expected: FAIL — param/job don't exist.

- [ ] **Step 3: Add the job + wiring**

In `backend/app/services/scheduler.py`:
- Add `from datetime import UTC` and a job fn:
```python
async def _run_scheduled_report_once() -> str:
    from app.core.database import async_session_factory
    from app.services.reporting.scheduled_report import ScheduledReportService

    async with async_session_factory() as db:
        try:
            from datetime import datetime

            return await ScheduledReportService(db).run_once(datetime.now(UTC))
        except Exception:  # noqa: BLE001 — never let a bad pass kill the loop
            await db.rollback()
            logger.exception("scheduled_report_pass_failed")
            return "failed"
```
- Add params to `start_background_jobs`: `scheduled_reports_enabled: bool = False,
  scheduled_report_interval_seconds: int = 86400,` and a registration block mirroring
  the remote-sweeper one:
```python
    if scheduled_reports_enabled:
        tasks.append(
            asyncio.create_task(
                _run_loop(
                    "reporting.scheduled_report",
                    _run_scheduled_report_once,
                    scheduled_report_interval_seconds,
                ),
                name="reporting.scheduled_report",
            )
        )
```

In `backend/app/main.py`, add to the `start_background_jobs(...)` call:
```python
        scheduled_reports_enabled=settings.FEATURE_SCHEDULED_REPORTS,
        scheduled_report_interval_seconds=settings.SCHEDULED_REPORT_CHECK_INTERVAL_SECONDS,
```

- [ ] **Step 4: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_scheduler_scheduled_report.py -v && uv run ruff check app/services/scheduler.py app/main.py tests/unit/test_scheduler_scheduled_report.py && uv run ruff format --check app/services/scheduler.py app/main.py`
Expected: PASS + clean.
```bash
git add backend/app/services/scheduler.py backend/app/main.py backend/tests/unit/test_scheduler_scheduled_report.py
git commit -m "feat(reporting): wire monthly scheduled-report job into the scheduler"
```

---

### Task 5: Full verification gate

- [ ] **Step 1: Backend gate**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: clean + green (note pre-existing unrelated failures explicitly).

- [ ] **Step 2: Config-safety check**

Confirm the app still boots with the flag OFF (default): `cd backend && uv run python -c "from app.main import app; print('ok')"` — no import/wiring errors.

- [ ] **Step 3: No-op safety check**

Confirm (by reading + the service tests) that with the flag on but SMTP/recipients unconfigured, `run_once` returns `"skipped_unconfigured"` and never claims a period or raises.

- [ ] **Step 4: Commit any fixups**

```bash
git add -A && git commit -m "chore(reporting): C2 verification fixups"  # only if needed
```

---

## Self-Review

**Spec coverage:**
- EmailSender + SMTP + config/flag (spec §1,§2) → Task 1. ✓
- Idempotency table + migration 011 (spec §3) → Task 2. ✓
- ScheduledReportService claim→build→send→mark + prev-month + should_send (spec §4) → Task 3. ✓
- Scheduler + lifespan wiring (spec §5) → Task 4. ✓
- Testing (sender, dates, idempotent send, migration, scheduler registration) → Tasks 1-4 + Task 5 gate. ✓
- Acceptance criteria 1-5 → Tasks 1-5. ✓

**Placeholder scan:** Task 2 (mixin names in `base.py`, `models/__init__.py` re-export), Task 3 (failed-row retry pre-check) are read-then-adapt against real code, each naming the file + exact thing. All sender/service/migration/scheduler code is complete. No TBD/TODO.

**Type consistency:** `EmailSender`/`EmailAttachment`/`get_email_sender`/`SmtpEmailSender` consistent across Tasks 1,3. `ScheduledReportRun.period/status/sent_at` consistent across model (Task 2), migration (Task 2), service (Task 3). `run_once` outcome strings consistent between service + tests. `scheduled_reports_enabled`/`scheduled_report_interval_seconds` consistent across scheduler (Task 4), main.py, and the test.

**Note for implementer:** Task 3's failed-row-retry pre-check is important — implement the `select` for an existing `period` row (sent → skip; sending/failed → reuse+proceed) so a transient SMTP failure retries the next day without ever double-sending a `sent` period. Ensure the service tests cover both the fresh-claim and existing-failed-row paths.
