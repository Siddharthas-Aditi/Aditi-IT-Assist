# Sub-project C1 — Per-Specialist Reporting Suite (on-demand)

**Date:** 2026-07-17
**Status:** Approved design (pending user spec review)
**Part of:** production-readiness engagement, sub-project C (C1 of C1/C2)

## Problem

IT leadership needs a per-specialist performance report matching the monthly
format the user shared (per-agent: Total Tickets, Reopened, Avg Resolution Time,
SLA Violations, Avg CSAT, DSAT). Today there is **no per-specialist report
endpoint, no report UI table, and no CSV/Excel/PDF export**. The only per-agent
surface is a workload list showing a truncated UUID + open-ticket count.

The data mostly exists and is reusable:
- CSAT/DSAT: `FeedbackAnalyticsService.get_agent_summary` + `ConversationFeedback`
  (`rating`, `agent_user_id`, `quality_bucket`, `submitted_at`).
- Ticket metrics: `Ticket.assigned_to`, `created_at`, `resolved_at`,
  `sla_resolution_target`, `status`.
- Reopened: derivable from `TicketEvent` rows (`event_type=="status_changed"`,
  `old_value` in resolved/closed → active `new_value`).

## Goal (user-approved decisions)

A leads/admins-only report, default **current month** with a **custom date range**,
showing **one row per specialist + a team-totals row** with the 6 metric columns,
viewable on an admin page with **charts (Recharts)** and downloadable as
**CSV / Excel / PDF**. CSAT/DSAT from existing feedback; **"No data"** where absent.

## Non-goals

- Scheduled monthly email delivery — that is **C2** (separate spec).
- The reopen *action* itself — **sub-project D**. C1 only *derives* the reopened
  count from existing status-change events (reads 0 until reopens occur).
- No new CSAT survey (reuse existing feedback).
- No per-specialist self-view (leads/admins only, per decision).

## Metric definitions (precise)

For a date range `[start, end]` (default: first→last day of current month):
- A specialist = a `User` with an it-staff role who has tickets `assigned_to` them
  resolved in range (plus any with feedback in range).
- **Total Tickets** = count of tickets where `assigned_to == agent` and
  `resolved_at` ∈ range.
- **Avg Resolution Time (hrs)** = mean over those tickets of
  `(resolved_at − created_at)` in hours; "No data" if none.
- **SLA Violations** = count of those tickets where `sla_resolution_target` is set
  and `resolved_at > sla_resolution_target`.
- **Avg CSAT** = `get_agent_summary(agent, from_dt=start, to_dt=end).csat_avg`
  (mean of non-null `rating`); "No data" if no rated feedback in range.
- **DSAT** = `get_agent_summary(...).negative_count` (feedback with
  `quality_bucket=="negative"`).
- **Reopened** = count of tickets `assigned_to == agent` with a `TicketEvent`
  (`event_type=="status_changed"`, `old_value` ∈ {resolved, closed},
  `new_value` ∈ active statuses) whose event timestamp ∈ range.
- **Team totals row** = sums for count columns; weighted/overall mean for
  resolution time and CSAT (documented in code), "No data" if the whole team has
  none.

## Units of work

### 1. Reporting service (`backend/app/services/reporting/specialist_report_service.py`)
- New `SpecialistReportService(db)` with `async def build_report(start, end) ->
  SpecialistReport`.
- Per-agent grouped ticket queries (the existing `AnalyticsService` aggregates are
  org-wide; add per-`assigned_to` grouping here — do NOT bend the global service).
- Reuse `get_agent_summary` per agent for CSAT/DSAT (or add a grouped feedback repo
  query if per-agent looping is too many round-trips; start simple with the
  existing method).
- Reopened derivation via a `TicketEvent` query (join to tickets for `assigned_to`).
- Pure aggregation helpers (resolution-time mean, SLA-violation count, totals) are
  separated and unit-testable without a DB where practical.
- Returns typed rows + totals; unknown/empty values represented so the API can
  render "No data" (None), never `NaN`.

### 2. Schemas (`backend/app/schemas/reporting.py`)
- `SpecialistReportRow` (agent_id, agent_name, agent_email, total_tickets,
  reopened, avg_resolution_hours: float | None, sla_violations, csat_avg: float |
  None, dsat, feedback_responses: int) and `SpecialistReport` (period_start,
  period_end, rows: list, totals: SpecialistReportRow-like).

### 3. API (`backend/app/api/v1/analytics.py` or a new `reporting.py` router)
- `GET /analytics/specialist-report?start=&end=` (`ITLeadUser`) → `SpecialistReport`.
- `GET /analytics/specialist-report/export?start=&end=&format=csv|xlsx|pdf`
  (`ITLeadUser`) → streamed file with correct content-type + filename. Default
  range = current month when params omitted.
- Follow the existing analytics.py pattern (inline service instantiation, RBAC
  dependency).

### 4. Export renderers (`backend/app/services/reporting/exporters.py`)
- `to_csv(report) -> bytes` (stdlib `csv`), `to_xlsx(report) -> bytes` (openpyxl),
  `to_pdf(report) -> bytes` (reportlab: a titled table with the period + rows +
  totals). Deterministic output (no timestamps embedded that break tests, or pass
  a fixed "generated for period" label). "No data" cells rendered as a dash.
- Add `openpyxl` and `reportlab` to backend deps (`pyproject.toml`).

### 5. Frontend (`frontend/src/features/admin/` + `frontend/src/pages/admin/`)
- Add **Recharts** to `frontend/package.json`.
- API hooks in `features/admin/api.ts`: `useSpecialistReport(start,end)` and export
  download helpers (fetch the export endpoint as a blob, trigger download).
- New **SpecialistReportPage** (route under `/dashboard`, in the AdminLayout nav):
  month/date-range picker (monthly default), the per-agent table + totals row,
  charts (tickets per agent; avg resolution time; SLA violations) via Recharts,
  and CSV/Excel/PDF download buttons. "No data" rendered explicitly.
- Gate the nav entry via `lib/permissions.ts` mirroring backend (UI gating is not
  security — backend re-checks).

## Data flow

```
GET /analytics/specialist-report?start&end (it_lead+)
  → SpecialistReportService.build_report(start,end)
       ├─ per-agent ticket aggregation (assigned_to, resolved_at∈range)
       ├─ reopened from status_changed TicketEvents
       └─ get_agent_summary(agent, start, end) → CSAT/DSAT
  → SpecialistReport (rows + totals)  → JSON | csv | xlsx | pdf
Frontend: table + Recharts + download buttons
```

## Error handling / guardrails

- RBAC: it_lead+ enforced in the endpoint (backend), UI nav mirrors it.
- No dummy data; uncomputable rates → None → "No data" in UI/exports
  (`memory/known-risks.md` #9).
- Empty range / no specialists → empty rows + zeroed/"No data" totals, HTTP 200.
- Export failures return a clean error, never a partial file.
- Large ranges: queries are grouped/bounded; N+1 feedback lookups acceptable at
  current scale (note as a future optimization if agent count grows large).

## Testing

- **Service unit:** per-agent aggregation (2 agents, known tickets) → correct Total
  Tickets, Avg Resolution hrs, SLA Violations; reopened derived from seeded
  status_changed events; CSAT/DSAT from seeded feedback; empty agent → None/"No
  data"; totals row math.
- **Exporters:** `to_csv/to_xlsx/to_pdf` produce non-empty, well-formed output with
  the right headers/rows; "No data" rendered as dash; xlsx opens (openpyxl
  round-trip), pdf starts with `%PDF`.
- **API:** RBAC (employee/agent 403, lead/admin 200); response shape; default range
  = current month; export content-types + filename.
- **Frontend:** table renders rows + totals + "No data"; charts render; download
  buttons call the export endpoint; RBAC-gated nav. `tsc` + eslint + vitest clean.

## Acceptance criteria

1. Leads/admins get a per-specialist report (6 columns + totals) for the current
   month by default and any custom range.
2. CSV, Excel, and PDF exports download with correct content and formatting.
3. CSAT/DSAT come from existing feedback; absent → "No data"; reopened derived from
   status-change events.
4. Charts render on the admin page; employees/agents cannot access the report.
5. Backend `ruff` + `pytest` green; frontend `tsc` + eslint + vitest green; new deps
   (openpyxl, reportlab, recharts) added.

## Risks (`memory/known-risks.md`)

- #4 RBAC/data isolation — report is leads/admins only; backend-enforced.
- #9 no dummy data — "No data" for uncomputable values.
- New deps: openpyxl/reportlab/recharts are widely-used, self-contained; pin
  reasonable versions.
- Reopened column reads 0 until the D reopen action exists — documented, expected.
