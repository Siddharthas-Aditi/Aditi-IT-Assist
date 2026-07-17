import io
from datetime import UTC, datetime

from openpyxl import load_workbook

from app.schemas.reporting import SpecialistReport, SpecialistReportRow
from app.services.reporting import exporters


def _report():
    row = SpecialistReportRow(
        agent_id="a1",
        agent_name="Alex Agent",
        agent_email="alex@aditi.com",
        total_tickets=10,
        reopened=1,
        avg_resolution_hours=2.5,
        sla_violations=0,
        csat_avg=4.8,
        dsat=0,
        feedback_responses=6,
    )
    empty = SpecialistReportRow(
        agent_id="a2",
        agent_name="Blank Agent",
        total_tickets=0,
        csat_avg=None,
        avg_resolution_hours=None,
    )
    totals = SpecialistReportRow(
        agent_id=None,
        agent_name="Team totals",
        total_tickets=10,
        reopened=1,
        avg_resolution_hours=2.5,
        sla_violations=0,
        csat_avg=4.8,
        dsat=0,
        feedback_responses=6,
    )
    return SpecialistReport(
        period_start=datetime(2026, 7, 1, tzinfo=UTC),
        period_end=datetime(2026, 7, 31, tzinfo=UTC),
        rows=[row, empty],
        totals=totals,
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
