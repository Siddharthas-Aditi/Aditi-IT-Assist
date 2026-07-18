"""Render a SpecialistReport to CSV / XLSX / PDF (C1)."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _sanitize(value: str) -> str:
    """Neutralize spreadsheet formula injection by prefixing risky cells."""
    if value and (value[0] in _FORMULA_PREFIXES or value[0] in ("\t", "\r")):
        return "'" + value
    return value


def _cell(row: SpecialistReportRow, attr: str) -> str:
    value = getattr(row, attr)
    if value is None:
        return "-"
    if isinstance(value, str):
        return _sanitize(value)
    return str(value)


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
        cells: list[object] = []
        for attr, _ in COLUMNS:
            value = getattr(row, attr)
            if value is None:
                cells.append("-")
            elif isinstance(value, str):
                cells.append(_sanitize(value))
            else:
                cells.append(value)
        ws.append(cells)
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
