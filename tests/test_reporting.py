from datetime import date
from pathlib import Path

from audit_engine.models import AuditRow, AuditStatus, NotesDiagnostics
from audit_engine.reporting import build_audit_result, write_markdown_report


def test_exception_rows_only_include_critical_warning_review(tmp_path: Path):
    rows = [
        AuditRow(
            client="a",
            service_date=date(2025, 1, 1),
            billed=True,
            scheduled=True,
            shift_notes_present=True,
            scheduled_shift_count=1,
            shift_note_count=1,
            missing_shift_notes=0,
            billing_service_codes=["APC"],
            status=AuditStatus.COMPLIANT,
            exception_reason="ok",
        ),
        AuditRow(
            client="b",
            service_date=date(2025, 1, 2),
            billed=True,
            scheduled=True,
            shift_notes_present=False,
            scheduled_shift_count=1,
            shift_note_count=0,
            missing_shift_notes=1,
            billing_service_codes=["APC"],
            status=AuditStatus.CRITICAL_BILLED_WITHOUT_NOTE,
            exception_reason="missing",
        ),
        AuditRow(
            client="c",
            service_date=date(2025, 1, 3),
            billed=False,
            scheduled=True,
            shift_notes_present=False,
            scheduled_shift_count=1,
            shift_note_count=0,
            missing_shift_notes=1,
            billing_service_codes=[],
            status=AuditStatus.REVENUE_SCHEDULED_NOT_BILLED,
            exception_reason="rev",
        ),
    ]
    result = build_audit_result(rows, [], NotesDiagnostics())
    assert len(result.exception_rows) == 1
    assert result.exception_rows[0].status == AuditStatus.CRITICAL_BILLED_WITHOUT_NOTE

    out = tmp_path / "report.md"
    write_markdown_report(result, out)
    content = out.read_text(encoding="utf-8")
    assert "SECTION 1 — EXECUTIVE SUMMARY" in content
    assert "SECTION 4 — EXCEPTION REPORT" in content

