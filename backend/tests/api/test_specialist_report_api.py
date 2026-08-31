"""API tests for the per-specialist report + export endpoints (C1, Task 3).

Unlike most API tests in this suite, `get_db` is NOT overridden here (see
conftest.py) — these requests run against a real test Postgres, so the
it_lead 200 assertions are the real-DB validation of the report SQL built in
Task 1 (`SpecialistReportService.build_report`). Only auth is mocked.
"""

import pytest
from httpx import AsyncClient

from app.core.database import engine

BASE = "/api/v1/analytics"


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    """Dispose the shared async engine's pool after each test.

    pytest-asyncio's default function-scoped event loop means every test in
    this module runs in its own loop, but `app.core.database.engine` is a
    process-wide singleton whose connection pool holds asyncpg connections
    bound to whichever loop created them. Without disposing the pool between
    tests, a later test's loop tries to reuse a connection from a prior
    (now-closed) loop and asyncpg raises `RuntimeError: ... attached to a
    different loop` / `Event loop is closed`. This is test-harness plumbing
    (this module is the first to exercise the real DB via the app's engine
    rather than a mocked/overridden session) — not a defect in the report
    SQL itself.
    """
    yield
    await engine.dispose()


class TestSpecialistReportGating:
    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(f"{BASE}/specialist-report")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get(f"{BASE}/specialist-report")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_agent_forbidden(self, agent_client: AsyncClient):
        resp = await agent_client.get(f"{BASE}/specialist-report")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_it_lead_ok_runs_real_report_sql(self, lead_client: AsyncClient):
        """This actually executes SpecialistReportService.build_report's SQL.

        Even against an empty (or unrelated-fixture) DB, a 200 with `rows`
        and `totals` present proves the join/filter query is valid SQL —
        closing the gap that Task 1's unit tests only exercised a FakeSession.
        """
        resp = await lead_client.get(f"{BASE}/specialist-report")
        assert resp.status_code == 200
        body = resp.json()
        assert "rows" in body
        assert "totals" in body
        assert "period_start" in body
        assert "period_end" in body

    @pytest.mark.asyncio
    async def test_it_admin_ok(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"{BASE}/specialist-report")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_it_lead_ok_with_explicit_range(self, lead_client: AsyncClient):
        resp = await lead_client.get(
            f"{BASE}/specialist-report",
            params={"start": "2026-01-01T00:00:00Z", "end": "2026-01-31T23:59:59Z"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "rows" in body
        assert "totals" in body

    @pytest.mark.asyncio
    async def test_it_lead_ok_with_bare_date_range(self, lead_client: AsyncClient):
        """Regression: bare `YYYY-MM-DD` params (as sent by SpecialistReportPage).

        FastAPI/pydantic parses a bare date as naive midnight. Before the
        `_normalize_range` fix, an explicit bare-date `end` stayed naive
        midnight (never promoted to end-of-day since `_default_month_range`
        only fills in end-of-day when BOTH bounds are None) and the whole
        last day was excluded by the `<= end` boundary; comparing a naive
        datetime against tz-aware DB columns also risked an error. A 200
        with `rows`/`totals` present is the minimum proof the normalized
        naive-vs-tz-aware comparison executes without error end-to-end
        against the real test DB.
        """
        resp = await lead_client.get(
            f"{BASE}/specialist-report",
            params={"start": "2026-07-01", "end": "2026-07-31"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "rows" in body
        assert "totals" in body
        # The resolved end boundary must be promoted to end-of-day, not left
        # at naive midnight (which would silently drop the entire last day).
        assert body["period_end"].startswith("2026-07-31T23:59:59")


class TestSpecialistReportExport:
    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(f"{BASE}/specialist-report/export", params={"format": "csv"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get(
            f"{BASE}/specialist-report/export", params={"format": "csv"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_it_lead_forbidden(self, lead_client: AsyncClient):
        """Regression: was allowed before Workstream 4 (ANALYTICS_EXPORT is admin-only)."""
        resp = await lead_client.get(f"{BASE}/specialist-report/export", params={"format": "csv"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_csv_export(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"{BASE}/specialist-report/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert ".csv" in resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_xlsx_export(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"{BASE}/specialist-report/export", params={"format": "xlsx"})
        assert resp.status_code == 200
        assert (
            resp.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment" in resp.headers["content-disposition"]
        assert ".xlsx" in resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_pdf_export(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"{BASE}/specialist-report/export", params={"format": "pdf"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "attachment" in resp.headers["content-disposition"]
        assert ".pdf" in resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_invalid_format_rejected(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"{BASE}/specialist-report/export", params={"format": "doc"})
        assert resp.status_code == 400
