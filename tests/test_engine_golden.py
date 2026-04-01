from pathlib import Path

from audit_engine.engine import run_audit
from audit_engine.models import ClientDayKey, NotesDay, NotesDiagnostics, ScheduleDay
from audit_engine.normalize import normalize_date


def test_engine_regression_shape(monkeypatch, tmp_path: Path):
    billing_file = tmp_path / "billing.TXT"
    billing_file.write_text(
        "SIMPSON, BETHANY             106391999599   02/10/2025   ATN      1       1     MEDINA",
        encoding="utf-8",
    )

    def fake_schedule_map(*args, **kwargs):
        key = ClientDayKey(client="bethany simpson", service_date=normalize_date("2025-02-10"))
        return {key: ScheduleDay(shift_count=2)}, []

    def fake_notes_map(*args, **kwargs):
        key = ClientDayKey(client="bethany simpson", service_date=normalize_date("2025-02-10"))
        return {key: NotesDay(note_count=1)}, [], NotesDiagnostics()

    monkeypatch.setattr("audit_engine.engine.fetch_schedule_map", fake_schedule_map)
    monkeypatch.setattr("audit_engine.engine.fetch_notes_map", fake_notes_map)

    result = run_audit(
        billing_files=[billing_file],
        when_i_work_base_url="https://example.com",
        when_i_work_api_token="x",
        when_i_work_api_key="",
        when_i_work_email="",
        when_i_work_password="",
        when_i_work_user_id="",
        jotform_base_url="https://example.com",
        jotform_api_key="y",
        jotform_form_id="",
        start_date=normalize_date("2025-02-10"),
        end_date=normalize_date("2025-02-10"),
        timeout_seconds=10,
    )

    assert result.summary.total_client_days == 1
    assert result.audit_rows[0].status.value == "WARNING - INCOMPLETE NOTES"
    assert result.audit_rows[0].missing_shift_notes == 1
    assert result.notes_diagnostics.missing_client_count == 0

