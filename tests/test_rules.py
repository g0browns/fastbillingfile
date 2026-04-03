from datetime import date, datetime

from audit_engine.models import BillingClaim, BillingDay, ClientDayKey, NotesDay, ScheduleDay, ScheduleShift, ShiftNote, TimeEntry
from audit_engine.rules import evaluate_client_day


def _key() -> ClientDayKey:
    return ClientDayKey(client="bethany simpson", service_date=date(2025, 2, 10))


_SHIFT_COUNTER = 0


def _next_id() -> str:
    global _SHIFT_COUNTER
    _SHIFT_COUNTER += 1
    return str(_SHIFT_COUNTER)


def _time_entry(shift_id: str = "") -> TimeEntry:
    return TimeEntry(
        shift_id=shift_id,
        clock_in=datetime(2025, 2, 10, 8, 0),
        clock_out=datetime(2025, 2, 10, 12, 0),
        hours=4.0,
    )


def _shift_with_evv(staff_name: str = "") -> tuple[ScheduleShift, TimeEntry]:
    sid = _next_id()
    s = ScheduleShift(
        shift_id=sid,
        staff_name=staff_name,
        start_time=datetime(2025, 2, 10, 8, 0),
        end_time=datetime(2025, 2, 10, 12, 0),
    )
    t = TimeEntry(
        shift_id=sid,
        staff_name=staff_name,
        clock_in=datetime(2025, 2, 10, 8, 0),
        clock_out=datetime(2025, 2, 10, 12, 0),
        hours=4.0,
    )
    return s, t


def _billing_day() -> BillingDay:
    return BillingDay(claims=[BillingClaim(service_code="ATN")])


def _note() -> ShiftNote:
    return ShiftNote(service_code="ATN", units=4, staff_name="jane doe", has_signature=True, has_narrative=True, narrative_length=50)


def test_critical_billed_without_schedule_precedes_other_conditions():
    [row] = evaluate_client_day(
        key=_key(),
        billing_day=_billing_day(),
        schedule_day=None,
        notes_day=NotesDay(notes=[_note()]),
        has_source_issue=False,
    )
    assert row.status.value == "CRITICAL - BILLED WITHOUT SCHEDULE"


def test_warning_incomplete_notes_for_billed_scheduled_day():
    s1, t1 = _shift_with_evv(staff_name="jane doe")
    s2, t2 = _shift_with_evv(staff_name="john smith")
    s3, t3 = _shift_with_evv(staff_name="mary jones")
    [row] = evaluate_client_day(
        key=_key(),
        billing_day=_billing_day(),
        schedule_day=ScheduleDay(shifts=[s1, s2, s3], time_entries=[t1, t2, t3]),
        notes_day=NotesDay(notes=[_note()]),
        has_source_issue=False,
    )
    assert row.status.value == "WARNING - MISSING STAFF NOTES"
    assert row.missing_shift_notes == 2


def test_compliant_requires_exact_note_match():
    s1, t1 = _shift_with_evv(staff_name="jane doe")
    s2, t2 = _shift_with_evv(staff_name="jane doe")
    [row] = evaluate_client_day(
        key=_key(),
        billing_day=_billing_day(),
        schedule_day=ScheduleDay(shifts=[s1, s2], time_entries=[t1, t2]),
        notes_day=NotesDay(notes=[_note(), _note()]),
        has_source_issue=False,
    )
    assert row.status.value == "COMPLIANT"


def test_review_name_or_date_mismatch_overrides_other_states():
    s1, t1 = _shift_with_evv(staff_name="jane doe")
    s2, t2 = _shift_with_evv(staff_name="jane doe")
    [row] = evaluate_client_day(
        key=_key(),
        billing_day=_billing_day(),
        schedule_day=ScheduleDay(shifts=[s1, s2], time_entries=[t1, t2]),
        notes_day=NotesDay(notes=[_note(), _note()]),
        has_source_issue=True,
    )
    assert row.status.value == "REVIEW - NAME OR DATE MISMATCH"
