from __future__ import annotations

from datetime import time

from audit_engine.models import (
    BillingClaim,
    BillingDay,
    ClientDayKey,
    NotesDay,
    ScheduleDay,
    ScheduleShift,
    ShiftNote,
    SourceIssue,
    TimeEntry,
)


def build_master_client_days(
    billing_map: dict[ClientDayKey, BillingDay],
    schedule_map: dict[ClientDayKey, ScheduleDay],
    notes_map: dict[ClientDayKey, NotesDay],
) -> list[ClientDayKey]:
    all_keys = set(billing_map.keys()) | set(schedule_map.keys()) | set(notes_map.keys())
    return sorted(all_keys, key=lambda key: (key.client, key.service_date.isoformat()))


def collect_matching_issues(
    billing_issues: list[SourceIssue],
    schedule_issues: list[SourceIssue],
    notes_issues: list[SourceIssue],
) -> list[SourceIssue]:
    return [*billing_issues, *schedule_issues, *notes_issues]


def build_issue_key_set(issues: list[SourceIssue]) -> set[ClientDayKey]:
    keyed_issues: set[ClientDayKey] = set()
    for issue in issues:
        if issue.normalized_client and issue.normalized_date:
            keyed_issues.add(
                ClientDayKey(client=issue.normalized_client, service_date=issue.normalized_date)
            )
    return keyed_issues


# ---------------------------------------------------------------------------
# Claim-level matching
# ---------------------------------------------------------------------------


def match_claim_to_note(
    claim: BillingClaim,
    notes_day: NotesDay | None,
) -> ShiftNote | None:
    """Find the best matching shift note for a billing claim."""
    if not notes_day or not notes_day.notes:
        return None

    notes = notes_day.notes

    # Priority 1: exact service code match
    code_matches = [n for n in notes if n.service_code and n.service_code == claim.service_code]
    if len(code_matches) == 1:
        return code_matches[0]
    if len(code_matches) > 1:
        # Multiple notes with same code — pick closest units match
        return min(code_matches, key=lambda n: abs((n.units or 0) - claim.units))

    # Priority 2: if only one note for the day, use it
    if len(notes) == 1:
        return notes[0]

    # Priority 3: no exact code match and multiple notes — try units match
    if claim.units > 0:
        units_matches = [n for n in notes if n.units and abs(n.units - claim.units) <= 2]
        if len(units_matches) == 1:
            return units_matches[0]

    # Fallback: return first note (imperfect but better than nothing)
    return notes[0]


def match_claim_to_shift(
    claim: BillingClaim,
    schedule_day: ScheduleDay | None,
    matched_note: ShiftNote | None,
) -> ScheduleShift | None:
    """Find the best matching schedule shift for a billing claim."""
    if not schedule_day or not schedule_day.shifts:
        return None

    shifts = schedule_day.shifts

    # If we matched a note with a staff name, find the shift with the same staff
    if matched_note and matched_note.staff_name:
        staff_matches = [s for s in shifts if s.staff_name and s.staff_name == matched_note.staff_name]
        if len(staff_matches) == 1:
            return staff_matches[0]
        if len(staff_matches) > 1:
            # Multiple shifts by same staff — pick by time overlap with note
            if matched_note.shift_start:
                return _closest_shift_by_time(staff_matches, matched_note.shift_start)
            return staff_matches[0]

    # If only one shift, use it
    if len(shifts) == 1:
        return shifts[0]

    # Multiple shifts, no note staff — return first
    return shifts[0]


def match_shift_to_time_entry(
    shift: ScheduleShift | None,
    schedule_day: ScheduleDay | None,
) -> TimeEntry | None:
    """Find the time entry (EVV) linked to a specific shift."""
    if not schedule_day or not schedule_day.time_entries:
        return None

    if not shift:
        # Timesheet is source of truth fallback when no usable shift record exists.
        approved = [te for te in schedule_day.time_entries if te.is_approved]
        if len(approved) == 1:
            return approved[0]
        if approved:
            return approved[0]
        return schedule_day.time_entries[0]

    for te in schedule_day.time_entries:
        if te.shift_id and te.shift_id == shift.shift_id:
            return te
    return None


def _closest_shift_by_time(shifts: list[ScheduleShift], target_start: time) -> ScheduleShift:
    """Pick the shift whose start time is closest to the target."""
    target_min = target_start.hour * 60 + target_start.minute

    def diff(s: ScheduleShift) -> int:
        if s.start_time is None:
            return 9999
        s_min = s.start_time.hour * 60 + s.start_time.minute
        return abs(s_min - target_min)

    return min(shifts, key=diff)


# ---------------------------------------------------------------------------
# Staff-level coverage analysis
# ---------------------------------------------------------------------------


def analyze_staff_coverage(
    schedule_day: ScheduleDay | None,
    notes_day: NotesDay | None,
) -> dict[str, object]:
    """Compare scheduled staff vs note staff to find who's missing a note.

    Returns:
        {
            "scheduled_staff": ["mary hankins", "anastashia solomon", ...],
            "note_staff": ["mary hankins", ...],
            "staff_with_notes": ["mary hankins"],
            "staff_missing_notes": ["anastashia solomon"],
            "expected_notes": 2,
            "actual_notes": 1,
            "all_covered": False,
        }
    """
    scheduled_staff: list[str] = []
    if schedule_day:
        for shift in schedule_day.shifts:
            if shift.staff_name:
                scheduled_staff.append(shift.staff_name)
        if not scheduled_staff:
            for entry in schedule_day.time_entries:
                if entry.staff_name:
                    scheduled_staff.append(entry.staff_name)

    note_staff: list[str] = []
    if notes_day:
        for note in notes_day.notes:
            if note.staff_name:
                note_staff.append(note.staff_name)

    scheduled_set = set(scheduled_staff)
    note_set = set(note_staff)

    staff_with_notes = sorted(scheduled_set & note_set)
    staff_missing_notes = sorted(scheduled_set - note_set)

    return {
        "scheduled_staff": sorted(scheduled_set),
        "note_staff": sorted(note_set),
        "staff_with_notes": staff_with_notes,
        "staff_missing_notes": staff_missing_notes,
        "expected_notes": len(scheduled_set),
        "actual_notes": len(note_set & scheduled_set),
        "all_covered": len(staff_missing_notes) == 0 and len(scheduled_set) > 0,
    }
