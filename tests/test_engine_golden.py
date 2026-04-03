import asyncio
from pathlib import Path

from audit_engine.engine import run_audit
from datetime import datetime

from audit_engine.models import ClientDayKey, NotesDay, NotesDiagnostics, ScheduleDay, ScheduleShift, ShiftNote, TimeEntry
from audit_engine.normalize import normalize_date


def test_engine_regression_shape(monkeypatch, tmp_path: Path):
    billing_file = tmp_path / "billing.TXT"
    billing_file.write_text(
        "SIMPSON, BETHANY             106391999599   02/10/2025   ATN      1       1     MEDINA   $15.00   $15.00   4   O   $60.00",
        encoding="utf-8",
    )

    async def fake_schedule_map(*args, **kwargs):
        key = ClientDayKey(client="bethany simpson", service_date=normalize_date("2025-02-10"))
        return {key: ScheduleDay(
            shifts=[
                ScheduleShift(shift_id="s1", staff_name="jane doe", start_time=datetime(2025, 2, 10, 8, 0), end_time=datetime(2025, 2, 10, 12, 0)),
                ScheduleShift(shift_id="s2", staff_name="john smith", start_time=datetime(2025, 2, 10, 13, 0), end_time=datetime(2025, 2, 10, 17, 0)),
            ],
            time_entries=[
                TimeEntry(shift_id="s1", staff_name="jane doe", clock_in=datetime(2025, 2, 10, 8, 0), clock_out=datetime(2025, 2, 10, 12, 0), hours=4.0),
                TimeEntry(shift_id="s2", staff_name="john smith", clock_in=datetime(2025, 2, 10, 13, 0), clock_out=datetime(2025, 2, 10, 17, 0), hours=4.0),
            ],
        )}, []

    async def fake_notes_map(*args, **kwargs):
        key = ClientDayKey(client="bethany simpson", service_date=normalize_date("2025-02-10"))
        return {key: NotesDay(notes=[ShiftNote(service_code="ATN", units=4, staff_name="jane doe", has_signature=True, has_narrative=True, narrative_length=50)])}, [], NotesDiagnostics()

    monkeypatch.setattr("audit_engine.engine.fetch_schedule_map", fake_schedule_map)
    monkeypatch.setattr("audit_engine.engine.fetch_notes_map", fake_notes_map)

    result = asyncio.run(
        run_audit(
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
    )

    assert result.summary.total_client_days == 1
    assert result.audit_rows[0].status.value == "WARNING - MISSING STAFF NOTES"
    assert result.audit_rows[0].missing_shift_notes == 1
    assert result.notes_diagnostics.missing_client_count == 0
