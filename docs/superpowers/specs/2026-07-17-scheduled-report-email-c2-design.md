# Sub-project C2 — Scheduled Monthly Report Email

**Date:** 2026-07-17
**Status:** Approved design (pending user spec review)
**Part of:** production-readiness engagement, sub-project C (C2 of C1/C2)

## Problem

C1 delivers the per-specialist report on demand. Leadership also wants it
**emailed monthly** (like the report the user shared). Today there is **no email
transport** (only Office365 SMTP config placeholders, unused) and the scheduler is
**fixed-interval asyncio, not cron** — so a "1st of the month" send needs a
daily-checked job, and because prod may run multiple replicas with **no
distributed lock**, a naive send would fire once per replica. C2 builds the email
transport + a replica-safe monthly send.

## Goal (user-approved decisions)

On the 1st of each month, email the **previous month's** per-specialist report as a
**PDF attachment + HTML summary body** to a **configurable recipient list**, via
**aiosmtplib SMTP** (reusing the existing Office365 SMTP config) **behind
`FEATURE_SCHEDULED_REPORTS`** — inert until SMTP + recipients are configured, and
**sent exactly once per month even across replicas**.

## Non-goals

- No new report metrics/logic — reuse C1's `SpecialistReportService` + `exporters`.
- No Microsoft Graph transport now (SMTP chosen; keep the sender pluggable so Graph
  can be added later).
- No per-user email preferences/opt-in (a config recipient list).
- No cron engine — a daily check on the existing asyncio scheduler.

## Units of work

### 1. Email transport (`backend/app/services/email/__init__.py`, `sender.py`)
- `EmailSender` protocol: `async def send(*, to: list[str], subject: str, html_body: str,
  attachments: list[EmailAttachment] | None = None) -> None`. `EmailAttachment`
  = `{filename, content: bytes, mime_type}`.
- `SmtpEmailSender` using **aiosmtplib** (add dep) + STARTTLS on port 587, reading
  `settings.SMTP_HOST/PORT/USER/PASSWORD`. Builds a MIME multipart (HTML + binary
  attachment). `is_configured` = bool(host+user+password). If not configured,
  `send` raises a typed `EmailNotConfigured` (caller treats as no-op/skip).
- `get_email_sender() -> EmailSender | None` factory (None when unconfigured).
- Pure MIME-assembly is separated so it's unit-testable without a live server; the
  actual SMTP send is mocked in tests.

### 2. Config (`backend/app/core/config.py` + `.env.example`)
- `FEATURE_SCHEDULED_REPORTS: bool = False`.
- `REPORT_RECIPIENTS: str = ""` (comma-separated emails) + a parsed helper
  `report_recipients() -> list[str]`.
- `SCHEDULED_REPORT_DAY: int = 1` (day-of-month to send).
- Reuse existing `SMTP_HOST/PORT/USER/PASSWORD`. Document all in `.env.example`.

### 3. Idempotency store + migration 011
- New table `scheduled_report_runs`: `id`, `period` (e.g. `"2026-06"`, **unique**),
  `status` (`sending|sent|failed`), `recipient_count`, `created_at`, `sent_at`.
- Migration `011_scheduled_report_runs` (reversible).
- Model in `backend/app/models/reporting.py`.
- Replica-safe claim: insert a `period` row (unique constraint); the replica that
  wins the insert sends; a conflicting insert (IntegrityError) → another replica
  already claimed it → skip. On send failure, mark `failed` so the next daily tick
  retries; on success, mark `sent`.

### 4. Scheduled-report service (`backend/app/services/reporting/scheduled_report.py`)
- `ScheduledReportService(db)`:
  - `previous_month_range(now) -> (start, end)` — pure, tz-aware UTC, first→last of
    the prior month (unit-tested).
  - `should_send(now) -> bool` — `now.day == settings.SCHEDULED_REPORT_DAY` (the
    per-month idempotency is enforced by the DB claim, not this check).
  - `run_once(now)`: if `should_send`, compute period + range, **claim** the period
    row (skip if already claimed), build the report (`SpecialistReportService`),
    render PDF (`exporters.to_pdf`) + an HTML summary (totals + row count), send via
    `get_email_sender()` to `report_recipients()`, mark `sent`/`failed`. All
    best-effort + audited (`AuditService`); never raises out of the scheduler.
  - No recipients or no sender configured ⇒ log + skip (no claim wasted? — claim
    only after confirming sender+recipients exist).

### 5. Scheduler wiring (`backend/app/services/scheduler.py` + `app/main.py`)
- Add `_run_scheduled_report_once()` opening a short-lived session and calling
  `ScheduledReportService(db).run_once(datetime.now(UTC))`.
- Register in `start_background_jobs(...)` behind `FEATURE_SCHEDULED_REPORTS`,
  mirroring the existing sweeper blocks, on a **daily** interval
  (`SCHEDULED_REPORT_CHECK_INTERVAL_SECONDS`, default 86400). The daily check +
  DB claim gives "once per month, replica-safe".
- `datetime.now(UTC)` is used inside the job (not at registration).

## Data flow

```
daily tick (FEATURE_SCHEDULED_REPORTS on)
  → ScheduledReportService.run_once(now)
      if now.day == SCHEDULED_REPORT_DAY and sender+recipients configured:
        period = prev-month key; range = prev-month [start,end]
        claim scheduled_report_runs(period)  ── conflict? another replica sent → skip
        report = SpecialistReportService.build_report(range)
        pdf = exporters.to_pdf(report); html = summary(report)
        get_email_sender().send(to=recipients, subject, html, [pdf])
        mark sent (or failed → retry next tick); audit
```

## Error handling / guardrails

- Flag off / SMTP unconfigured / no recipients ⇒ safe no-op (never sends, never
  claims a period).
- Replica-safe: DB unique `period` claim ⇒ exactly one send per month.
- Send failure ⇒ row marked `failed`, retried on the next daily tick (still
  idempotent — only one success per period).
- The job never raises into the scheduler loop (isolated try/except like existing
  sweepers).
- No employee data leak: recipients are an explicit admin-config list; content is
  the same leads/admins report.

## Testing

- **EmailSender:** MIME assembly includes HTML + PDF attachment + correct
  recipients/subject; `is_configured` false when creds missing; `SmtpEmailSender`
  calls aiosmtplib with STARTTLS (mock the SMTP client, assert send invoked);
  `EmailNotConfigured` when unconfigured.
- **previous_month_range / should_send:** pure date logic — Jan→prev Dec year
  rollover; correct first/last day; `should_send` true only on the configured day.
- **run_once:** on the send day with sender+recipients → builds report, sends once,
  marks `sent`; **second run same period → skipped** (idempotent claim); send
  failure → `failed` + retried next tick; flag off / unconfigured → no send.
- **Migration 011:** upgrade/downgrade round-trip.
- Regression: existing scheduler tests still green.

## Acceptance criteria

1. With `FEATURE_SCHEDULED_REPORTS` on + SMTP + recipients configured, on
   `SCHEDULED_REPORT_DAY` the previous month's report is emailed once (PDF +
   summary) to all recipients.
2. Exactly one send per month across replicas (DB-claim idempotency; verified by a
   second-run-skips test).
3. Flag off / unconfigured ⇒ no send, no error.
4. Send failures are recorded and retried the next day without duplicate sends.
5. Backend `ruff` + `pytest` green; migration 011 reversible; aiosmtplib added.

## Risks (`memory/known-risks.md`)

- #7 migrations — 011 needs a tested downgrade.
- #9 no dummy data — real report only; no send when nothing configured.
- Multi-replica double-fire — resolved by the DB unique-period claim (the explicit
  reason this table exists).
- Secrets — SMTP password from config/env only; never logged.
