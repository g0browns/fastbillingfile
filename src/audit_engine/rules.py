from __future__ import annotations

from datetime import time

from audit_engine.matching import analyze_staff_coverage, match_claim_to_note, match_claim_to_shift, match_shift_to_time_entry
from audit_engine.models import (
    AuditRow,
    AuditStatus,
    BillingClaim,
    BillingDay,
    ClientDayKey,
    NotesDay,
    ScheduleDay,
    ScheduleShift,
    ShiftNote,
    TimeEntry,
)
from audit_engine.normalize import times_match


def evaluate_client_day(
    key: ClientDayKey,
    billing_day: BillingDay | None,
    schedule_day: ScheduleDay | None,
    notes_day: NotesDay | None,
    has_source_issue: bool,
    paper_notes_exempt: bool = False,
) -> list[AuditRow]:
    """Evaluate a client-day and return one AuditRow per billing claim.

    Also returns rows for orphan schedule/notes (revenue opportunities).
    """
    rows: list[AuditRow] = []

    # Compute staff coverage once per client-day
    coverage = analyze_staff_coverage(schedule_day, notes_day)

    if billing_day and billing_day.claims:
        for claim in billing_day.claims:
            row = _evaluate_claim(
                key=key,
                claim=claim,
                billing_day=billing_day,
                schedule_day=schedule_day,
                notes_day=notes_day,
                has_source_issue=has_source_issue,
                coverage=coverage,
                paper_notes_exempt=paper_notes_exempt,
            )
            rows.append(row)
    elif schedule_day and schedule_day.shift_count > 0 and not (billing_day and billing_day.billed):
        # Scheduled but not billed
        rows.append(_make_orphan_row(
            key=key,
            schedule_day=schedule_day,
            notes_day=notes_day,
            status=AuditStatus.REVENUE_SCHEDULED_NOT_BILLED,
            reason="Scheduled shifts exist but day is not billed",
            coverage=coverage,
        ))
    elif notes_day and notes_day.notes and not (billing_day and billing_day.billed):
        # Notes exist but not billed
        rows.append(_make_orphan_row(
            key=key,
            schedule_day=schedule_day,
            notes_day=notes_day,
            status=AuditStatus.REVENUE_NOTES_NOT_BILLED,
            reason="Shift notes exist but day is not billed",
            coverage=coverage,
        ))

    return rows


def _evaluate_claim(
    key: ClientDayKey,
    claim: BillingClaim,
    billing_day: BillingDay,
    schedule_day: ScheduleDay | None,
    notes_day: NotesDay | None,
    has_source_issue: bool,
    coverage: dict[str, object],
    paper_notes_exempt: bool,
) -> AuditRow:
    """Run the 6-check evaluation for a single billing claim."""
    matched_note = match_claim_to_note(claim, notes_day)
    matched_shift = match_claim_to_shift(claim, schedule_day, matched_note)
    matched_time = match_shift_to_time_entry(matched_shift, schedule_day)

    findings: list[str] = []

    # --- Check 1: Note exists ---
    note_exists = matched_note is not None

    # --- Check 2: Required elements ---
    missing_elements: list[str] = []
    if matched_note:
        if not matched_note.service_code:
            missing_elements.append("service code")
        if matched_note.units is None:
            missing_elements.append("units")
        if not matched_note.staff_name:
            missing_elements.append("staff name")
        if not matched_note.has_signature:
            missing_elements.append("signature")
        if not matched_note.has_narrative:
            missing_elements.append("narrative")
    elements_complete = note_exists and len(missing_elements) == 0
    if paper_notes_exempt and not note_exists:
        elements_complete = True

    # --- Check 3: Staff match ---
    staff_on_note = matched_note.staff_name if matched_note else ""
    staff_on_schedule = matched_shift.staff_name if matched_shift else ""
    staff_phone_number = matched_shift.staff_phone if matched_shift else ""
    if not staff_on_schedule and matched_time and matched_time.staff_name:
        staff_on_schedule = matched_time.staff_name
    if not staff_phone_number and matched_time and matched_time.staff_phone:
        staff_phone_number = matched_time.staff_phone
    staff_match: bool | None = None
    if staff_on_note and staff_on_schedule:
        staff_match = staff_on_note == staff_on_schedule

    # --- Check 4: Time match ---
    note_start = matched_note.shift_start if matched_note else None
    note_end = matched_note.shift_end if matched_note else None
    sched_start: time | None = None
    sched_end: time | None = None
    if matched_shift and matched_shift.start_time:
        sched_start = matched_shift.start_time.time()
    if matched_shift and matched_shift.end_time:
        sched_end = matched_shift.end_time.time()
    time_ok: bool | None = None
    if note_start and sched_start:
        time_ok = times_match(note_start, note_end, sched_start, sched_end, tolerance_minutes=30)

    # --- Check 5: Service code match ---
    service_code_on_note = matched_note.service_code if matched_note else ""
    code_match: bool | None = None
    if service_code_on_note and claim.service_code:
        code_match = service_code_on_note == claim.service_code

    # --- Check 6: EVV match ---
    evv_clock_in = ""
    evv_clock_out = ""
    evv_hours: float | None = None
    if matched_time:
        if matched_time.clock_in:
            evv_clock_in = matched_time.clock_in.strftime("%I:%M %p")
        if matched_time.clock_out:
            evv_clock_out = matched_time.clock_out.strftime("%I:%M %p")
        evv_hours = matched_time.hours

    # --- Units match ---
    units_on_note = matched_note.units if matched_note else None
    units_match: bool | None = None
    if units_on_note is not None and claim.units > 0:
        units_match = units_on_note == claim.units

    # --- Staff coverage ---
    scheduled_staff = coverage.get("scheduled_staff", [])
    staff_with_notes = coverage.get("staff_with_notes", [])
    staff_missing_notes = coverage.get("staff_missing_notes", [])
    if paper_notes_exempt:
        staff_missing_notes = []

    # --- Determine status (most severe first) ---
    status, reason = _assign_status(
        has_source_issue=has_source_issue,
        note_exists=note_exists,
        scheduled=bool(schedule_day and schedule_day.shift_count > 0),
        elements_complete=elements_complete,
        missing_elements=missing_elements,
        staff_match=staff_match,
        code_match=code_match,
        units_match=units_match,
        time_ok=time_ok,
        has_evv=matched_time is not None,
        duplicate_notes=bool(notes_day and notes_day.duplicate_note_ids),
        staff_missing_notes=staff_missing_notes,
        findings=findings,
        paper_notes_exempt=paper_notes_exempt,
    )

    return AuditRow(
        client=key.client,
        service_date=key.service_date,
        billed=True,
        scheduled=bool(schedule_day and schedule_day.shift_count > 0),
        shift_notes_present=note_exists,
        scheduled_shift_count=schedule_day.shift_count if schedule_day else 0,
        shift_note_count=notes_day.note_count if notes_day else 0,
        missing_shift_notes=0 if paper_notes_exempt else max(0, (schedule_day.shift_count if schedule_day else 0) - (notes_day.note_count if notes_day else 0)),
        billing_service_codes=[claim.service_code],
        status=status,
        exception_reason=reason,
        suspected_mismatch=has_source_issue,
        duplicate_shift_notes=bool(notes_day and notes_day.duplicate_note_ids),
        medicaid_id=claim.medicaid_id,
        billing_units=claim.units,
        billing_rate=str(claim.rate),
        staff_on_note=staff_on_note,
        staff_on_schedule=staff_on_schedule,
        staff_phone_number=staff_phone_number,
        staff_match=staff_match,
        service_code_on_note=service_code_on_note,
        service_code_match=code_match,
        units_on_note=units_on_note,
        units_match=units_match,
        note_has_signature=matched_note.has_signature if matched_note else None,
        note_has_narrative=matched_note.has_narrative if matched_note else None,
        evv_clock_in=evv_clock_in,
        evv_clock_out=evv_clock_out,
        evv_hours=evv_hours,
        time_match=time_ok,
        findings=findings,
        scheduled_staff=scheduled_staff,
        staff_with_notes=staff_with_notes,
        staff_missing_notes=staff_missing_notes,
        paper_notes_exempt=paper_notes_exempt,
    )


def _assign_status(
    has_source_issue: bool,
    note_exists: bool,
    scheduled: bool,
    elements_complete: bool,
    missing_elements: list[str],
    staff_match: bool | None,
    code_match: bool | None,
    units_match: bool | None,
    time_ok: bool | None,
    has_evv: bool,
    duplicate_notes: bool,
    staff_missing_notes: list[str],
    findings: list[str],
    paper_notes_exempt: bool,
) -> tuple[AuditStatus, str]:
    if has_source_issue:
        findings.append("Source parsing/matching issue requires manual review")
        return AuditStatus.REVIEW_NAME_OR_DATE_MISMATCH, "Source parsing/matching issue requires manual review"

    if duplicate_notes:
        findings.append("Duplicate shift note identifiers detected")
        return AuditStatus.REVIEW_NAME_OR_DATE_MISMATCH, "Duplicate shift note identifiers detected"

    if not note_exists and not paper_notes_exempt:
        findings.append("No shift note found for this billed claim")
        return AuditStatus.CRITICAL_BILLED_WITHOUT_NOTE, "Billed day has no shift notes"

    if not scheduled:
        findings.append("No schedule entry found for this billed claim")
        return AuditStatus.CRITICAL_BILLED_WITHOUT_SCHEDULE, "Billed day has no schedule entry"

    if staff_match is False:
        findings.append("Staff on note does not match staff on schedule")
        return AuditStatus.CRITICAL_STAFF_MISMATCH, "Staff on note does not match staff on schedule"

    if code_match is False:
        findings.append("Service code mismatch: billing vs note")
        return AuditStatus.CRITICAL_SERVICE_CODE_MISMATCH, "Service code on note does not match billing"

    # Warnings (non-critical but need attention)
    warning_findings: list[str] = []

    if staff_missing_notes:
        names = ", ".join(n.title() for n in staff_missing_notes)
        warning_findings.append(f"Missing shift notes from: {names}")

    if not elements_complete:
        detail = ", ".join(missing_elements)
        warning_findings.append(f"Missing required elements: {detail}")

    if units_match is False:
        warning_findings.append("Units on note do not match units billed")

    if time_ok is False:
        warning_findings.append("Shift times do not match within tolerance")

    if not has_evv:
        warning_findings.append("No EVV clock in/out record found")

    if warning_findings:
        findings.extend(warning_findings)
        # Return the most significant warning
        if staff_missing_notes:
            names = ", ".join(n.title() for n in staff_missing_notes)
            return AuditStatus.WARNING_MISSING_STAFF_NOTES, f"Missing notes from: {names}"
        if not elements_complete:
            return AuditStatus.WARNING_MISSING_REQUIRED_ELEMENTS, f"Missing: {', '.join(missing_elements)}"
        if units_match is False:
            return AuditStatus.WARNING_UNITS_MISMATCH, "Units on note do not match units billed"
        if time_ok is False:
            return AuditStatus.WARNING_TIME_DISCREPANCY, "Shift times do not match within tolerance"
        if not has_evv:
            return AuditStatus.WARNING_NO_EVV, "No EVV clock in/out record found"

    if paper_notes_exempt and not note_exists:
        findings.append("Client is exempt from Jotform requirement (paper notes)")
        return AuditStatus.COMPLIANT, "Paper notes client excluded from Jotform note requirement"

    findings.append("All checks passed")
    return AuditStatus.COMPLIANT, "Billed claim has matching schedule, note, and all required elements"


def _make_orphan_row(
    key: ClientDayKey,
    schedule_day: ScheduleDay | None,
    notes_day: NotesDay | None,
    status: AuditStatus,
    reason: str,
    coverage: dict[str, object],
) -> AuditRow:
    return AuditRow(
        client=key.client,
        service_date=key.service_date,
        billed=False,
        scheduled=bool(schedule_day and schedule_day.shift_count > 0),
        shift_notes_present=bool(notes_day and notes_day.notes),
        scheduled_shift_count=schedule_day.shift_count if schedule_day else 0,
        shift_note_count=notes_day.note_count if notes_day else 0,
        missing_shift_notes=0,
        billing_service_codes=[],
        status=status,
        exception_reason=reason,
        findings=[reason],
        scheduled_staff=coverage.get("scheduled_staff", []),
        staff_with_notes=coverage.get("staff_with_notes", []),
        staff_missing_notes=coverage.get("staff_missing_notes", []),
    )
