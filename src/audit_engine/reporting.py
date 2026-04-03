from __future__ import annotations

import csv
import json
from datetime import date
from dataclasses import asdict
from io import BytesIO, StringIO
from pathlib import Path

from audit_engine.models import AuditResult, AuditRow, AuditStatus, AuditSummary, NotesDiagnostics, SourceIssue
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ---------------------------------------------------------------------------
# Cached PDF styles (avoid recreating on every generation)
# ---------------------------------------------------------------------------
_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle(
    "ShiftNoteTitle",
    parent=_STYLES["Title"],
    fontName="Helvetica-Bold",
    fontSize=24,
    alignment=TA_CENTER,
    spaceAfter=6,
)
_SPAN_STYLE = ParagraphStyle(
    "ShiftNoteSpan",
    parent=_STYLES["Heading3"],
    fontName="Helvetica-Bold",
    fontSize=13,
    alignment=TA_LEFT,
    spaceAfter=10,
)
_CELL_STYLE = ParagraphStyle(
    "ShiftNoteCell",
    parent=_STYLES["BodyText"],
    fontName="Helvetica",
    fontSize=8,
    leading=10,
)
_ACTION_STYLE = ParagraphStyle(
    "ShiftNoteActionCell",
    parent=_CELL_STYLE,
    leading=9,
)


def build_summary(rows: list[AuditRow]) -> AuditSummary:
    total = len(rows)
    compliant = sum(1 for row in rows if row.status == AuditStatus.COMPLIANT)
    critical = sum(1 for row in rows if row.status.value.startswith("CRITICAL"))
    warning = sum(1 for row in rows if row.status.value.startswith("WARNING"))
    revenue = sum(1 for row in rows if row.status.value.startswith("REVENUE OPPORTUNITY"))
    review = sum(1 for row in rows if row.status.value.startswith("REVIEW"))
    pct = (compliant / total * 100.0) if total else 0.0
    return AuditSummary(
        total_client_days=total,
        compliant_pct=round(pct, 2),
        compliant_count=compliant,
        critical_count=critical,
        warning_count=warning,
        revenue_opportunity_count=revenue,
        review_count=review,
    )


def build_status_breakdown(rows: list[AuditRow]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for row in rows:
        breakdown[row.status.value] = breakdown.get(row.status.value, 0) + 1
    return dict(sorted(breakdown.items(), key=lambda item: item[0]))


def build_audit_result(
    rows: list[AuditRow], matching_issues: list[SourceIssue], notes_diagnostics: NotesDiagnostics
) -> AuditResult:
    summary = build_summary(rows)
    breakdown = build_status_breakdown(rows)
    exception_rows = [row for row in rows if row.status != AuditStatus.COMPLIANT and not row.status.value.startswith("REVENUE OPPORTUNITY")]
    assumptions = [
        "Only HPC service codes are included in the audit",
        "Session Date in JotForm = Service Date in billing",
        "Sites in When I Work = Clients",
        "Time entries in When I Work = EVV clock in/out",
    ]
    return AuditResult(
        summary=summary,
        status_breakdown=breakdown,
        audit_rows=rows,
        exception_rows=exception_rows,
        matching_issues=matching_issues,
        notes_diagnostics=notes_diagnostics,
        assumptions=assumptions,
    )


def write_exports(result: AuditResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(result, output_dir / "audit_result.json")
    write_csv(result.audit_rows, output_dir / "audit_table.csv")
    write_markdown_report(result, output_dir / "audit_report.md")


def write_json(result: AuditResult, path: Path) -> None:
    serializable = {
        "summary": asdict(result.summary),
        "status_breakdown": result.status_breakdown,
        "audit_rows": [_row_to_json(row) for row in result.audit_rows],
        "exception_rows": [_row_to_json(row) for row in result.exception_rows],
        "matching_issues": [_issue_to_json(issue) for issue in result.matching_issues],
        "notes_diagnostics": asdict(result.notes_diagnostics),
        "assumptions": result.assumptions,
    }
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


def write_csv(rows: list[AuditRow], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Client",
                "Date",
                "Medicaid ID",
                "Service Code (Billing)",
                "Service Code (Note)",
                "Service Code Match",
                "Units (Billing)",
                "Units (Note)",
                "Units Match",
                "Staff on Note",
                "Staff on Schedule",
                "Staff Match",
                "Note Has Signature",
                "Note Has Narrative",
                "EVV Clock In",
                "EVV Clock Out",
                "EVV Hours",
                "Time Match",
                "Status",
                "Exception Reason",
                "Findings",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "Client": row.client,
                    "Date": row.service_date.isoformat(),
                    "Medicaid ID": row.medicaid_id,
                    "Service Code (Billing)": ", ".join(row.billing_service_codes),
                    "Service Code (Note)": row.service_code_on_note,
                    "Service Code Match": _bool_display(row.service_code_match),
                    "Units (Billing)": row.billing_units,
                    "Units (Note)": row.units_on_note if row.units_on_note is not None else "",
                    "Units Match": _bool_display(row.units_match),
                    "Staff on Note": row.staff_on_note,
                    "Staff on Schedule": row.staff_on_schedule,
                    "Staff Match": _bool_display(row.staff_match),
                    "Note Has Signature": _bool_display(row.note_has_signature),
                    "Note Has Narrative": _bool_display(row.note_has_narrative),
                    "EVV Clock In": row.evv_clock_in,
                    "EVV Clock Out": row.evv_clock_out,
                    "EVV Hours": f"{row.evv_hours:.2f}" if row.evv_hours is not None else "",
                    "Time Match": _bool_display(row.time_match),
                    "Status": row.status.value,
                    "Exception Reason": row.exception_reason,
                    "Findings": "; ".join(row.findings),
                }
            )


def write_markdown_report(result: AuditResult, path: Path) -> None:
    lines: list[str] = []
    summary = result.summary
    lines.extend(
        [
            "# Meadowbrook Billing Audit Report",
            "",
            "## SECTION 1 — EXECUTIVE SUMMARY",
            f"- Total claims audited: {summary.total_client_days}",
            f"- % compliant: {summary.compliant_pct}%",
            f"- Compliant: {summary.compliant_count}",
            f"- Critical: {summary.critical_count}",
            f"- Warning: {summary.warning_count}",
            f"- Revenue Opportunities: {summary.revenue_opportunity_count}",
            f"- Review: {summary.review_count}",
            "",
            "## SECTION 2 — STATUS BREAKDOWN",
        ]
    )
    for status, count in result.status_breakdown.items():
        lines.append(f"- {status}: {count}")

    lines.extend(["", "## SECTION 3 — AUDIT TABLE", ""])
    lines.append("| Client | Date | Code | Units | Staff Match | Code Match | Signature | Narrative | EVV | Status |")
    lines.append("|---|---|---|---:|---|---|---|---|---|---|")
    for row in result.audit_rows:
        code = ", ".join(row.billing_service_codes)
        lines.append(
            f"| {row.client} | {row.service_date.isoformat()} | {code} | {row.billing_units} | "
            f"{_bool_display(row.staff_match)} | {_bool_display(row.service_code_match)} | "
            f"{_bool_display(row.note_has_signature)} | {_bool_display(row.note_has_narrative)} | "
            f"{_bool_display(row.evv_hours is not None)} | {row.status.value} |"
        )

    lines.extend(["", "## SECTION 4 — EXCEPTION REPORT", ""])
    for row in result.exception_rows:
        lines.append(
            f"- **{row.client}** {row.service_date.isoformat()} [{', '.join(row.billing_service_codes)}] — "
            f"{row.status.value}: {row.exception_reason}"
        )
        if row.findings:
            for f in row.findings:
                lines.append(f"  - {f}")

    lines.extend(["", "## SECTION 5 — FIELD-LEVEL FINDINGS", ""])
    has_findings = False
    for row in result.audit_rows:
        if row.findings and row.status != AuditStatus.COMPLIANT:
            has_findings = True
            lines.append(f"- **{row.client}** {row.service_date.isoformat()} [{', '.join(row.billing_service_codes)}]")
            for f in row.findings:
                lines.append(f"  - {f}")
    if not has_findings:
        lines.append("- No field-level findings")

    lines.extend(["", "## SECTION 6 — MATCHING ISSUES", ""])
    if result.matching_issues:
        for issue in result.matching_issues:
            lines.append(
                f"- [{issue.source}] {issue.issue_type} :: client={issue.raw_client} date={issue.raw_date} reason={issue.reason}"
            )
    else:
        lines.append("- NONE")

    lines.extend(["", "## SECTION 7 — ASSUMPTIONS", ""])
    for assumption in result.assumptions:
        lines.append(f"- {assumption}")

    path.write_text("\n".join(lines), encoding="utf-8")


def _bool_display(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "Yes" if value else "No"


def _row_to_json(row: AuditRow) -> dict[str, object]:
    return {
        "client": row.client,
        "date": row.service_date.isoformat(),
        "billed": row.billed,
        "scheduled": row.scheduled,
        "shift_notes_present": row.shift_notes_present,
        "scheduled_shift_count": row.scheduled_shift_count,
        "shift_note_count": row.shift_note_count,
        "missing_shift_notes": row.missing_shift_notes,
        "billing_service_codes": row.billing_service_codes,
        "status": row.status.value,
        "exception_reason": row.exception_reason,
        "suspected_mismatch": row.suspected_mismatch,
        "duplicate_shift_notes": row.duplicate_shift_notes,
        "medicaid_id": row.medicaid_id,
        "billing_units": row.billing_units,
        "billing_rate": row.billing_rate,
        "staff_on_note": row.staff_on_note,
        "staff_on_schedule": row.staff_on_schedule,
        "staff_phone_number": row.staff_phone_number,
        "staff_match": row.staff_match,
        "service_code_on_note": row.service_code_on_note,
        "service_code_match": row.service_code_match,
        "units_on_note": row.units_on_note,
        "units_match": row.units_match,
        "note_has_signature": row.note_has_signature,
        "note_has_narrative": row.note_has_narrative,
        "evv_clock_in": row.evv_clock_in,
        "evv_clock_out": row.evv_clock_out,
        "evv_hours": row.evv_hours,
        "time_match": row.time_match,
        "findings": row.findings,
        "paper_notes_exempt": row.paper_notes_exempt,
    }


def _issue_to_json(issue: SourceIssue) -> dict[str, object]:
    return {
        "issue_type": issue.issue_type,
        "source": issue.source,
        "raw_client": issue.raw_client,
        "raw_date": issue.raw_date,
        "reason": issue.reason,
        "normalized_client": issue.normalized_client,
        "normalized_date": issue.normalized_date.isoformat() if issue.normalized_date else None,
    }


def _is_shift_note_followup(row: AuditRow) -> bool:
    if row.paper_notes_exempt:
        return False
    if row.missing_shift_notes > 0:
        return True
    if row.status in {
        AuditStatus.CRITICAL_BILLED_WITHOUT_NOTE,
        AuditStatus.WARNING_INCOMPLETE_NOTES,
        AuditStatus.WARNING_MISSING_STAFF_NOTES,
        AuditStatus.REVIEW_NOTES_WITHOUT_SCHEDULE,
    }:
        return True
    return False


def _issue_found_text(row: AuditRow) -> str:
    if row.missing_shift_notes > 0:
        return f"Missing {row.missing_shift_notes} shift note(s)"
    if row.exception_reason:
        return row.exception_reason
    return row.status.value


def _staff_that_worked(row: AuditRow) -> str:
    if row.staff_on_schedule.strip():
        return row.staff_on_schedule
    if row.staff_on_note.strip():
        return row.staff_on_note
    return "Unassigned in schedule"


def _action_text(row: AuditRow) -> str:
    staff = _staff_that_worked(row)
    if row.missing_shift_notes > 0:
        if staff != "Unassigned in schedule":
            return f"Collect shift note from {staff}"
        return "Collect shift note; determine responsible staff"
    if row.status == AuditStatus.WARNING_INCOMPLETE_NOTES:
        return "Collect remaining shift notes"
    if row.status == AuditStatus.WARNING_MISSING_STAFF_NOTES:
        return "Collect missing staff-specific shift note"
    return "Review and collect required shift note documentation"


def build_shift_note_audit_rows(rows: list[AuditRow]) -> list[dict[str, str]]:
    report_rows: list[dict[str, str]] = []
    for row in rows:
        if not _is_shift_note_followup(row):
            continue
        report_rows.append(
            {
                "Clients Name": row.client,
                "Date": row.service_date.isoformat(),
                "Issue found": _issue_found_text(row),
                "Staff that worked": _staff_that_worked(row),
                "Staff Phone Number": row.staff_phone_number.strip() or "Not available",
                "Action": _action_text(row),
            }
        )
    report_rows.sort(key=lambda item: (item["Clients Name"], item["Date"]))
    return report_rows


def build_shift_note_audit_csv_bytes(rows: list[AuditRow], start_date: date, end_date: date) -> bytes:
    report_rows = build_shift_note_audit_rows(rows)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Shift Note Audit"])
    writer.writerow(["Span Date", f"{start_date.isoformat()} to {end_date.isoformat()}"])
    writer.writerow([])
    writer.writerow(["Clients Name", "Date", "Issue found", "Staff that worked", "Staff Phone Number", "Action"])
    for row in report_rows:
        writer.writerow(
            [
                row["Clients Name"],
                row["Date"],
                row["Issue found"],
                row["Staff that worked"],
                row["Staff Phone Number"],
                row["Action"],
            ]
        )
    return buffer.getvalue().encode("utf-8")


def build_shift_note_audit_pdf_bytes(rows: list[AuditRow], start_date: date, end_date: date) -> bytes:
    report_rows = build_shift_note_audit_rows(rows)
    out = BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=landscape(letter),
        leftMargin=0.35 * inch,
        rightMargin=0.35 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch,
    )
    content: list[object] = []

    content.append(Paragraph("Shift Note Audit", _TITLE_STYLE))
    content.append(Paragraph(f"Span Date: {start_date.isoformat()} to {end_date.isoformat()}", _SPAN_STYLE))
    content.append(Spacer(1, 0.08 * inch))

    table_data = [
        [
            "Clients Name",
            "Date",
            "Issue found",
            "Staff that worked",
            "Staff Phone Number",
            "Action",
        ]
    ]
    for row in report_rows:
        table_data.append(
            [
                row["Clients Name"],
                row["Date"],
                row["Issue found"],
                row["Staff that worked"],
                row["Staff Phone Number"],
                Paragraph(
                    f"{row['Action']}<br/>"
                    "Received Note: ____________________  Date: __________  Initials: ______",
                    _ACTION_STYLE,
                ),
            ]
        )

    if len(table_data) == 1:
        content.append(Paragraph("No shift note follow-up rows for the selected span.", _STYLES["Normal"]))
    else:
        available_width = doc.width
        column_weights = [0.16, 0.10, 0.18, 0.18, 0.14, 0.24]
        col_widths = [available_width * weight for weight in column_weights]
        table = Table(
            table_data,
            colWidths=col_widths,
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9edf3")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa3af")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                    ("ALIGN", (1, 1), (1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ]
            )
        )
        content.append(table)

    doc.build(content)
    return out.getvalue()
