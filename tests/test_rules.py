from datetime import date

from audit_engine.models import BillingDay, ClientDayKey, NotesDay, ScheduleDay
from audit_engine.rules import evaluate_client_day


def _key() -> ClientDayKey:
    return ClientDayKey(client="bethany simpson", service_date=date(2025, 2, 10))


def test_critical_billed_without_schedule_precedes_other_conditions():
    row = evaluate_client_day(
        key=_key(),
        billing_day=BillingDay(),
        schedule_day=None,
        notes_day=NotesDay(note_count=1),
        has_source_issue=False,
    )
    assert row.status.value == "CRITICAL - BILLED WITHOUT SCHEDULE"


def test_warning_incomplete_notes_for_billed_scheduled_day():
    row = evaluate_client_day(
        key=_key(),
        billing_day=BillingDay(),
        schedule_day=ScheduleDay(shift_count=3),
        notes_day=NotesDay(note_count=1),
        has_source_issue=False,
    )
    assert row.status.value == "WARNING - INCOMPLETE NOTES"
    assert row.missing_shift_notes == 2


def test_compliant_requires_exact_note_match():
    row = evaluate_client_day(
        key=_key(),
        billing_day=BillingDay(),
        schedule_day=ScheduleDay(shift_count=2),
        notes_day=NotesDay(note_count=2),
        has_source_issue=False,
    )
    assert row.status.value == "COMPLIANT"


def test_review_name_or_date_mismatch_overrides_other_states():
    row = evaluate_client_day(
        key=_key(),
        billing_day=BillingDay(),
        schedule_day=ScheduleDay(shift_count=2),
        notes_day=NotesDay(note_count=2),
        has_source_issue=True,
    )
    assert row.status.value == "REVIEW - NAME OR DATE MISMATCH"

