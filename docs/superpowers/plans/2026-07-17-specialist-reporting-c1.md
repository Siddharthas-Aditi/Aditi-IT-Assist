# Per-Specialist Reporting Suite (C1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give IT leads/admins a per-specialist performance report (Total Tickets, Reopened, Avg Resolution hrs, SLA Violations, Avg CSAT, DSAT) over a date range (default current month), on an admin page with Recharts charts and CSV/Excel/PDF export.

**Architecture:** A new `SpecialistReportService` aggregates per-`assigned_to` ticket metrics + reuses `FeedbackAnalyticsService.get_agent_summary` for CSAT/DSAT + derives reopened from `status_changed` `TicketEvent`s. Exporters render the typed report to CSV/xlsx/pdf. Endpoints under `/analytics` (it_lead+). Frontend adds React Query hooks + a Recharts page.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / pytest / Ruff (backend); React 18 / TypeScript / Recharts / Vitest / ESLint (frontend).

## Global Constraints

- Backend line ≤100; `cd backend && uv run ruff check . && uv run ruff format --check .` clean (run format-check on new test files too).
- Frontend strict TS, no `any`; `cd frontend && npm run lint` (max-warnings=0) + `npm run typecheck` clean.
- Report is **it_lead + it_admin only** (backend-enforced via `ITLeadUser`); employees/agents get 403.
- **No dummy data**: uncomputable values are `None` → rendered "No data"/dash, never `NaN` (`memory/known-risks.md` #9).
- CSAT/DSAT come from existing `ConversationFeedback` (filter on `submitted_at`). Reopened is derived from existing events (reads 0 until the D reopen action exists — expected).
- Config accessor is `from app.core.config import settings`. Run backend cmds from `backend/` via `uv`; frontend from `frontend/` via `npm`.

---

### Task 1: Report service + schemas

**Files:**
- Create: `backend/app/schemas/reporting.py`
- Create: `backend/app/services/reporting/__init__.py`, `backend/app/services/reporting/specialist_report_service.py`
- Test: `backend/tests/unit/test_specialist_report_service.py`

**Interfaces:**
- Consumes: `Ticket`, `TicketEvent` (`app/models/ticket.py`), `User`, `FeedbackAnalyticsService.get_agent_summary(agent_user_id, *, from_dt, to_dt) -> AgentFeedbackSummary` (fields incl. `csat_avg: float|None`, `negative_count: int`, `sessions_with_feedback: int`).
- Produces: `SpecialistReportRow`, `SpecialistReport` (schemas); `SpecialistReportService(db).build_report(start: datetime, end: datetime) -> SpecialistReport`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_specialist_report_service.py`. Use the DB-session test fixtures the existing service tests use (read `backend/tests/unit/test_feedback_service.py` or `test_escalation_artifacts.py` for the async session fixture pattern). Seed two users (it_agent), tickets assigned to each with known `created_at`/`resolved_at`/`sla_resolution_target`/`status`, a `status_changed` TicketEvent representing a reopen (old_value="resolved", new_value="in_progress") for one, and `ConversationFeedback` rows with ratings. Assert:

```python
# Pseudocode shape — adapt to the real async fixtures.
async def test_build_report_aggregates_per_agent(db_session, seed):
    svc = SpecialistReportService(db_session)
    report = await svc.build_report(start=seed.month_start, end=seed.month_end)
    rows = {r.agent_id: r for r in report.rows}
    a = rows[seed.agent_a.id]
    assert a.total_tickets == 2
    assert a.sla_violations == 1
    assert a.reopened == 1
    assert a.avg_resolution_hours == pytest.approx(seed.expected_avg_hours_a, rel=0.01)
    assert a.csat_avg == pytest.approx(4.5, rel=0.01)   # from seeded ratings
    assert a.dsat == 1                                   # one negative feedback
    # agent with no feedback → csat_avg None ("No data")
    assert rows[seed.agent_b.id].csat_avg is None
    # totals row present
    assert report.totals.total_tickets == a.total_tickets + rows[seed.agent_b.id].total_tickets
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_specialist_report_service.py -v`
Expected: FAIL — module/schemas don't exist.

- [ ] **Step 3: Add schemas**

Create `backend/app/schemas/reporting.py`:

```python
"""Schemas for the per-specialist performance report (C1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SpecialistReportRow(BaseModel):
    agent_id: str | None  # None for the team-totals row
    agent_name: str
    agent_email: str | None = None
    total_tickets: int = 0
    reopened: int = 0
    avg_resolution_hours: float | None = None  # None => "No data"
    sla_violations: int = 0
    csat_avg: float | None = None  # None => "No data"
    dsat: int = 0
    feedback_responses: int = 0


class SpecialistReport(BaseModel):
    period_start: datetime
    period_end: datetime
    rows: list[SpecialistReportRow]
    totals: SpecialistReportRow
```

- [ ] **Step 4: Add the service**

Create `backend/app/services/reporting/__init__.py` (empty) and `backend/app/services/reporting/specialist_report_service.py`:

```python
"""Per-specialist performance report aggregation (C1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketEvent
from app.models.user import User
from app.schemas.reporting import SpecialistReport, SpecialistReportRow
from app.services.feedback_analytics_service import FeedbackAnalyticsService

_ACTIVE_STATUSES = {"open", "in_progress", "escalated", "pending"}
_CLOSED_STATUSES = {"resolved", "closed"}


def _avg_hours(deltas_seconds: list[float]) -> float | None:
    if not deltas_seconds:
        return None
    return round(sum(deltas_seconds) / len(deltas_seconds) / 3600.0, 2)


class SpecialistReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.feedback = FeedbackAnalyticsService(db)

    async def build_report(self, *, start: datetime, end: datetime) -> SpecialistReport:
        # Resolved tickets in range, grouped by assignee.
        stmt = select(Ticket).where(
            Ticket.assigned_to.is_not(None),
            Ticket.resolved_at.is_not(None),
            Ticket.resolved_at >= start,
            Ticket.resolved_at <= end,
        )
        tickets = list((await self.db.execute(stmt)).scalars().all())

        by_agent: dict[str, list[Ticket]] = {}
        for t in tickets:
            by_agent.setdefault(str(t.assigned_to), []).append(t)

        reopened = await self._reopened_counts(start, end)
        agent_ids = set(by_agent) | set(reopened)
        names = await self._agent_names(agent_ids)

        rows: list[SpecialistReportRow] = []
        for agent_id in sorted(agent_ids, key=lambda a: names.get(a, ("", ""))[0]):
            ats = by_agent.get(agent_id, [])
            res_secs = [
                (t.resolved_at - t.created_at).total_seconds()
                for t in ats
                if t.resolved_at and t.created_at
            ]
            sla_viol = sum(
                1
                for t in ats
                if t.sla_resolution_target and t.resolved_at
                and t.resolved_at > t.sla_resolution_target
            )
            import uuid as _uuid

            fb = await self.feedback.get_agent_summary(
                _uuid.UUID(agent_id), from_dt=start, to_dt=end
            )
            name, email = names.get(agent_id, ("Unknown", None))
            rows.append(
                SpecialistReportRow(
                    agent_id=agent_id,
                    agent_name=name,
                    agent_email=email,
                    total_tickets=len(ats),
                    reopened=reopened.get(agent_id, 0),
                    avg_resolution_hours=_avg_hours(res_secs),
                    sla_violations=sla_viol,
                    csat_avg=fb.csat_avg,
                    dsat=fb.negative_count,
                    feedback_responses=fb.sessions_with_feedback,
                )
            )

        totals = self._totals(rows)
        return SpecialistReport(period_start=start, period_end=end, rows=rows, totals=totals)

    async def _reopened_counts(self, start: datetime, end: datetime) -> dict[str, int]:
        """Count reopen events (resolved/closed -> active) per assignee in range."""
        stmt = (
            select(TicketEvent, Ticket.assigned_to)
            .join(Ticket, TicketEvent.ticket_id == Ticket.id)
            .where(
                TicketEvent.event_type == "status_changed",
                TicketEvent.created_at >= start,
                TicketEvent.created_at <= end,
                Ticket.assigned_to.is_not(None),
            )
        )
        counts: dict[str, int] = {}
        for ev, assigned_to in (await self.db.execute(stmt)).all():
            old = (ev.old_value or "").lower()
            new = (ev.new_value or "").lower()
            if old in _CLOSED_STATUSES and new in _ACTIVE_STATUSES:
                counts[str(assigned_to)] = counts.get(str(assigned_to), 0) + 1
        return counts

    async def _agent_names(self, agent_ids: set[str]) -> dict[str, tuple[str, str | None]]:
        if not agent_ids:
            return {}
        import uuid as _uuid

        uuids = [_uuid.UUID(a) for a in agent_ids]
        stmt = select(User).where(User.id.in_(uuids))
        out: dict[str, tuple[str, str | None]] = {}
        for u in (await self.db.execute(stmt)).scalars().all():
            display = getattr(u, "full_name", None) or getattr(u, "name", None) or u.email
            out[str(u.id)] = (display, u.email)
        return out

    def _totals(self, rows: list[SpecialistReportRow]) -> SpecialistReportRow:
        res_hours = [r.avg_resolution_hours for r in rows if r.avg_resolution_hours is not None]
        csats = [r.csat_avg for r in rows if r.csat_avg is not None]
        return SpecialistReportRow(
            agent_id=None,
            agent_name="Team totals",
            total_tickets=sum(r.total_tickets for r in rows),
            reopened=sum(r.reopened for r in rows),
            avg_resolution_hours=(round(sum(res_hours) / len(res_hours), 2) if res_hours else None),
            sla_violations=sum(r.sla_violations for r in rows),
            csat_avg=(round(sum(csats) / len(csats), 2) if csats else None),
            dsat=sum(r.dsat for r in rows),
            feedback_responses=sum(r.feedback_responses for r in rows),
        )
```

Note: verify `User`'s display-name attribute (`full_name` vs `name`) by reading `backend/app/models/user.py`; adjust `_agent_names` to the real field. Verify `Ticket` active/closed status strings against `TICKET_STATUSES` in `ticket.py` and adjust `_ACTIVE_STATUSES`/`_CLOSED_STATUSES` accordingly.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_specialist_report_service.py -v`
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
cd backend && uv run ruff check app/schemas/reporting.py app/services/reporting/ tests/unit/test_specialist_report_service.py && uv run ruff format --check app/schemas/reporting.py app/services/reporting/
cd ..
git add backend/app/schemas/reporting.py backend/app/services/reporting/ backend/tests/unit/test_specialist_report_service.py
git commit -m "feat(reporting): per-specialist report service + schemas"
```

---

### Task 2: Exporters (CSV / Excel / PDF)

**Files:**
- Modify: `backend/pyproject.toml` (add `openpyxl>=3.1`, `reportlab>=4.0`)
- Create: `backend/app/services/reporting/exporters.py`
- Test: `backend/tests/unit/test_report_exporters.py`

**Interfaces:**
- Consumes: `SpecialistReport`.
- Produces: `to_csv(report) -> bytes`, `to_xlsx(report) -> bytes`, `to_pdf(report) -> bytes`; a shared `COLUMNS` ordering + `_cell(value)` that renders `None` as `"-"`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_report_exporters.py`:

```python
import io
from datetime import UTC, datetime

from openpyxl import load_workbook

from app.schemas.reporting import SpecialistReport, SpecialistReportRow
from app.services.reporting import exporters


def _report():
    row = SpecialistReportRow(
        agent_id="a1", agent_name="Alex Agent", agent_email="alex@aditi.com",
        total_tickets=10, reopened=1, avg_resolution_hours=2.5, sla_violations=0,
        csat_avg=4.8, dsat=0, feedback_responses=6,
    )
    empty = SpecialistReportRow(agent_id="a2", agent_name="Blank Agent",
                                total_tickets=0, csat_avg=None, avg_resolution_hours=None)
    totals = SpecialistReportRow(agent_id=None, agent_name="Team totals",
                                 total_tickets=10, reopened=1, avg_resolution_hours=2.5,
                                 sla_violations=0, csat_avg=4.8, dsat=0, feedback_responses=6)
    return SpecialistReport(
        period_start=datetime(2026, 7, 1, tzinfo=UTC),
        period_end=datetime(2026, 7, 31, tzinfo=UTC),
        rows=[row, empty], totals=totals,
    )


def test_csv_has_header_rows_and_dash_for_none():
    data = exporters.to_csv(_report()).decode("utf-8")
    assert "Agent" in data and "Alex Agent" in data and "Team totals" in data
    assert "-" in data  # None rendered as dash for Blank Agent's csat


def test_xlsx_opens_and_has_rows():
    wb = load_workbook(io.BytesIO(exporters.to_xlsx(_report())))
    ws = wb.active
    values = [c.value for c in next(ws.iter_rows())]
    assert "Agent" in values


def test_pdf_starts_with_magic():
    assert exporters.to_pdf(_report())[:4] == b"%PDF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_report_exporters.py -v`
Expected: FAIL — `exporters` module + deps missing.

- [ ] **Step 3: Add deps**

In `backend/pyproject.toml` `dependencies` (after the document libs ~line 32), add:
```
    "openpyxl>=3.1",
    "reportlab>=4.0",
```
Run `cd backend && uv sync` to install.

- [ ] **Step 4: Add the exporters**

Create `backend/app/services/reporting/exporters.py`:

```python
"""Render a SpecialistReport to CSV / XLSX / PDF (C1)."""

from __future__ import annotations

import csv
import io

from app.schemas.reporting import SpecialistReport, SpecialistReportRow

COLUMNS: list[tuple[str, str]] = [
    ("agent_name", "Agent"),
    ("total_tickets", "Total Tickets"),
    ("reopened", "Reopened"),
    ("avg_resolution_hours", "Avg Resolution (hrs)"),
    ("sla_violations", "SLA Violations"),
    ("csat_avg", "Avg CSAT"),
    ("dsat", "DSAT"),
    ("feedback_responses", "Feedback Responses"),
]


def _cell(row: SpecialistReportRow, attr: str) -> str:
    value = getattr(row, attr)
    return "-" if value is None else str(value)


def _all_rows(report: SpecialistReport) -> list[SpecialistReportRow]:
    return [*report.rows, report.totals]


def to_csv(report: SpecialistReport) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in COLUMNS])
    for row in _all_rows(report):
        writer.writerow([_cell(row, attr) for attr, _ in COLUMNS])
    return buf.getvalue().encode("utf-8")


def to_xlsx(report: SpecialistReport) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Specialist Report"
    ws.append([label for _, label in COLUMNS])
    for row in _all_rows(report):
        ws.append([getattr(row, attr) if getattr(row, attr) is not None else "-"
                   for attr, _ in COLUMNS])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(report: SpecialistReport) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(letter))
    header = [label for _, label in COLUMNS]
    data = [header] + [[_cell(r, attr) for attr, _ in COLUMNS] for r in _all_rows(report)]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    doc.build([table])
    return out.getvalue()
```

- [ ] **Step 5: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_report_exporters.py -v && uv run ruff check app/services/reporting/exporters.py tests/unit/test_report_exporters.py && uv run ruff format --check app/services/reporting/exporters.py`
Expected: PASS + clean.
```bash
git add backend/pyproject.toml backend/uv.lock backend/app/services/reporting/exporters.py backend/tests/unit/test_report_exporters.py
git commit -m "feat(reporting): CSV/Excel/PDF exporters for the specialist report"
```

---

### Task 3: API endpoints (report JSON + export download)

**Files:**
- Modify: `backend/app/api/v1/analytics.py` (add two endpoints + a current-month default helper)
- Test: `backend/tests/api/test_specialist_report_api.py`

**Interfaces:**
- Consumes: `SpecialistReportService`, `exporters`, `ITLeadUser`.
- Produces: `GET /analytics/specialist-report?start=&end=` → `SpecialistReport`; `GET /analytics/specialist-report/export?start=&end=&format=csv|xlsx|pdf` → file `Response`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_specialist_report_api.py` following the existing API test pattern (read `backend/tests/api/test_admin.py` for the authenticated-client + role fixtures). Assert: employee → 403; it_lead → 200 with `rows`/`totals`; `export?format=csv` → 200, `content-type` text/csv, `Content-Disposition` attachment; `format=xlsx` → the spreadsheet content-type; `format=pdf` → `application/pdf`; invalid format → 400.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_specialist_report_api.py -v`
Expected: FAIL — endpoints missing.

- [ ] **Step 3: Add the endpoints**

In `backend/app/api/v1/analytics.py`, add:

```python
from datetime import UTC
from calendar import monthrange

from fastapi import HTTPException, Query, Response

from app.schemas.reporting import SpecialistReport
from app.services.reporting.specialist_report_service import SpecialistReportService
from app.services.reporting import exporters


def _default_month_range(
    start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    if start and end:
        return start, end
    now = datetime.now(UTC)
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = monthrange(now.year, now.month)[1]
    last = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
    return start or first, end or last


@router.get("/specialist-report", response_model=SpecialistReport)
async def get_specialist_report(
    lead_user: ITLeadUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: datetime | None = None,
    end: datetime | None = None,
) -> SpecialistReport:
    start_dt, end_dt = _default_month_range(start, end)
    return await SpecialistReportService(db).build_report(start=start_dt, end=end_dt)


_EXPORT = {
    "csv": (exporters.to_csv, "text/csv", "csv"),
    "xlsx": (
        exporters.to_xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "pdf": (exporters.to_pdf, "application/pdf", "pdf"),
}


@router.get("/specialist-report/export")
async def export_specialist_report(
    lead_user: ITLeadUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: datetime | None = None,
    end: datetime | None = None,
    format: str = Query("csv"),
) -> Response:
    if format not in _EXPORT:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
    start_dt, end_dt = _default_month_range(start, end)
    report = await SpecialistReportService(db).build_report(start=start_dt, end=end_dt)
    render, media_type, ext = _EXPORT[format]
    content = render(report)
    filename = f"specialist-report-{start_dt:%Y%m%d}-{end_dt:%Y%m%d}.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/api/test_specialist_report_api.py -v && uv run ruff check app/api/v1/analytics.py tests/api/test_specialist_report_api.py && uv run ruff format --check app/api/v1/analytics.py`
Expected: PASS + clean.
```bash
git add backend/app/api/v1/analytics.py backend/tests/api/test_specialist_report_api.py
git commit -m "feat(reporting): specialist-report API + CSV/xlsx/pdf export endpoint"
```

---

### Task 4: Frontend API hooks + types + Recharts dep

**Files:**
- Modify: `frontend/package.json` (add `recharts`)
- Modify: `frontend/src/features/admin/types.ts` (report types)
- Modify: `frontend/src/features/admin/api.ts` (`useSpecialistReport` + `downloadSpecialistReport`)
- Test: extend an existing admin api test or add `frontend/src/features/admin/report.test.ts` if hooks are unit-tested (else covered by Task 5's page test)

**Interfaces:**
- Consumes: `apiRequest` (JSON), the auth token accessor used by `buildHeaders` (read `frontend/src/lib/api.ts` for how the token is attached; the blob download must send the same `Authorization` header).
- Produces: `SpecialistReportRow`/`SpecialistReport` TS types; `useSpecialistReport(start,end)`; `downloadSpecialistReport(start,end,format)` (fetches the export endpoint as a blob with auth and triggers a browser download).

- [ ] **Step 1: Add recharts**

`cd frontend && npm install recharts` (adds to package.json + lock).

- [ ] **Step 2: Add types**

In `frontend/src/features/admin/types.ts` add:
```ts
export interface SpecialistReportRow {
  agent_id: string | null;
  agent_name: string;
  agent_email: string | null;
  total_tickets: number;
  reopened: number;
  avg_resolution_hours: number | null;
  sla_violations: number;
  csat_avg: number | null;
  dsat: number;
  feedback_responses: number;
}
export interface SpecialistReport {
  period_start: string;
  period_end: string;
  rows: SpecialistReportRow[];
  totals: SpecialistReportRow;
}
```

- [ ] **Step 3: Add the hook + download helper**

In `frontend/src/features/admin/api.ts`:
- Add to `adminKeys`: `specialistReport: (start: string, end: string) => ['admin', 'specialist-report', start, end] as const,`
- Add:
```ts
export function useSpecialistReport(start: string, end: string) {
  return useQuery({
    queryKey: adminKeys.specialistReport(start, end),
    queryFn: () =>
      apiRequest<SpecialistReport>('/analytics/specialist-report', {
        query: { start, end },
      }),
  });
}

export async function downloadSpecialistReport(
  start: string,
  end: string,
  format: 'csv' | 'xlsx' | 'pdf',
): Promise<void> {
  // Read frontend/src/lib/api.ts to reuse the exact base URL + auth header logic.
  const url = buildExportUrl('/analytics/specialist-report/export', { start, end, format });
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = `specialist-report.${format}`;
  a.click();
  URL.revokeObjectURL(href);
}
```
Read `frontend/src/lib/api.ts` and replace `buildExportUrl`/`authHeaders` with the real base-URL builder (`buildUrl`) and header helper (`buildHeaders`) — export them from `lib/api.ts` if not already exported, or add small local equivalents that read the same token source. No `any`.

- [ ] **Step 4: Typecheck + lint + commit**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: clean.
```bash
git add frontend/package.json frontend/package-lock.json frontend/src/features/admin/types.ts frontend/src/features/admin/api.ts
git commit -m "feat(reporting): frontend hooks + types + recharts for specialist report"
```

---

### Task 5: Specialist Report page (table + charts + downloads) + route + nav

**Files:**
- Create: `frontend/src/pages/admin/SpecialistReportPage.tsx`
- Modify: `frontend/src/app/App.tsx` (route under the `/dashboard` AdminLayout block)
- Modify: the AdminLayout nav (find the nav list — read `frontend/src/components/layouts/AdminLayout.tsx`) to add a "Specialist Report" link, gated via `isLeadOrAbove` (`frontend/src/lib/permissions.ts`)
- Test: `frontend/src/pages/admin/SpecialistReportPage.test.tsx`

**Interfaces:**
- Consumes: `useSpecialistReport`, `downloadSpecialistReport` (Task 4); Recharts.
- Produces: the report page rendered at `/dashboard/reports/specialists`.

- [ ] **Step 1: Read the page + layout patterns**

Read `frontend/src/pages/admin/DashboardPage.tsx` (existing page style, PageHeader/Breadcrumbs usage) and `frontend/src/components/layouts/AdminLayout.tsx` (nav structure) so the new page matches conventions.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/pages/admin/SpecialistReportPage.test.tsx`. Mock `useSpecialistReport` (or the `apiRequest`) to return a report with two rows (one with `csat_avg: null`) + totals. Assert: the table renders both agent names + the "Team totals" row; a `null` csat renders as "No data"/"—" (assert the app's chosen empty token); the three download buttons (CSV/Excel/PDF) render; clicking CSV calls `downloadSpecialistReport` with `'csv'` (mock it). Wrap in a QueryClientProvider as other admin tests do (read an existing admin page test for the harness).

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/admin/SpecialistReportPage.test.tsx`
Expected: FAIL — page doesn't exist.

- [ ] **Step 4: Build the page**

Create `SpecialistReportPage.tsx`: a month/date-range picker (default current month — compute first/last of month), the per-agent table with the 8 columns + a visually distinct totals row (render `null` numeric cells as an em-dash / "No data"), three download buttons wired to `downloadSpecialistReport`, and a Recharts `BarChart` (tickets per agent) + a second chart (SLA violations or avg resolution). Use the existing PageHeader/Breadcrumbs components. Handle loading/error/empty states. No `any`; strict types from Task 4.

- [ ] **Step 5: Wire the route + nav**

- In `frontend/src/app/App.tsx`, add inside the `/dashboard` AdminLayout `<Route>` block: `<Route path="reports/specialists" element={<SpecialistReportPage />} />` and import the page.
- In `AdminLayout.tsx`, add a nav link to `/dashboard/reports/specialists` labelled "Specialist Report", shown only when `isLeadOrAbove(user)`.

- [ ] **Step 6: Run test + gates + commit**

Run: `cd frontend && npx vitest run src/pages/admin/SpecialistReportPage.test.tsx && npm run lint && npm run typecheck`
Expected: PASS + clean.
```bash
git add frontend/src/pages/admin/SpecialistReportPage.tsx frontend/src/pages/admin/SpecialistReportPage.test.tsx frontend/src/app/App.tsx frontend/src/components/layouts/AdminLayout.tsx
git commit -m "feat(reporting): specialist report admin page — table, charts, downloads"
```

---

### Task 6: Full verification gate

- [ ] **Step 1: Backend gate**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: clean + green (note any pre-existing unrelated failures explicitly).

- [ ] **Step 2: Frontend gate**

Run: `cd frontend && npm run lint && npm run typecheck && npx vitest run`
Expected: clean + green.

- [ ] **Step 3: RBAC contract check**

Run: `cd backend && uv run pytest tests/api/test_specialist_report_api.py -q` and confirm the employee/agent-403 + lead/admin-200 assertions pass (report is leads/admins only).

- [ ] **Step 4: Manual (if a dev stack is available)**

Seed + run; log in as lead@aditi.com; open the Specialist Report page; confirm the table + charts render for the current month, change the range, and download CSV/Excel/PDF successfully; confirm employee@aditi.com cannot reach it.

- [ ] **Step 5: Commit any fixups**

```bash
git add -A && git commit -m "chore(reporting): C1 verification fixups"  # only if needed
```

---

## Self-Review

**Spec coverage:**
- Report service + metric definitions (spec §metric-defs, §1) → Task 1. ✓
- Schemas (spec §2) → Task 1 Step 3. ✓
- API report + export (spec §3) → Task 3. ✓
- Exporters CSV/Excel/PDF (spec §4) → Task 2. ✓
- Frontend hooks + page + charts + downloads + nav/RBAC (spec §5) → Tasks 4-5. ✓
- Testing (service, exporters, API RBAC, frontend) → Tasks 1-5 + Task 6 gate. ✓
- Acceptance criteria 1-5 → Tasks 1-6. ✓

**Placeholder scan:** Task 1 Step 4 (User display-name field, ticket status strings), Task 4 Step 3 (real `buildUrl`/`buildHeaders` names), and Task 5 (page/nav conventions) are read-then-adapt against real code, each naming the file + exact thing to confirm. All service/exporter/API code is complete. No TBD/TODO.

**Type consistency:** `SpecialistReport`/`SpecialistReportRow` field names identical across schema (Task 1), exporters `COLUMNS` (Task 2), API `response_model` (Task 3), and TS types (Task 4). `build_report(*, start, end)` signature consistent between service and both endpoints. `_EXPORT` formats (csv/xlsx/pdf) match the frontend `downloadSpecialistReport` union.

**Note for implementer:** confirm `FeedbackAnalyticsService.get_agent_summary` param names (`from_dt`/`to_dt`) and `AgentFeedbackSummary` fields (`csat_avg`, `negative_count`, `sessions_with_feedback`) by reading `backend/app/services/feedback_analytics_service.py` before wiring Task 1; adjust attribute names if they differ.
