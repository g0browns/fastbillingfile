from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum


class AuditStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    CRITICAL_BILLED_WITHOUT_NOTE = "CRITICAL - BILLED WITHOUT NOTE"
    CRITICAL_BILLED_WITHOUT_SCHEDULE = "CRITICAL - BILLED WITHOUT SCHEDULE"
    CRITICAL_STAFF_MISMATCH = "CRITICAL - STAFF MISMATCH"
    CRITICAL_SERVICE_CODE_MISMATCH = "CRITICAL - SERVICE CODE MISMATCH"
    WARNING_INCOMPLETE_NOTES = "WARNING - INCOMPLETE NOTES"
    WARNING_MISSING_STAFF_NOTES = "WARNING - MISSING STAFF NOTES"
    WARNING_MISSING_REQUIRED_ELEMENTS = "WARNING - MISSING REQUIRED ELEMENTS"
    WARNING_TIME_DISCREPANCY = "WARNING - TIME DISCREPANCY"
    WARNING_NO_EVV = "WARNING - NO EVV RECORD"
    WARNING_UNITS_MISMATCH = "WARNING - UNITS MISMATCH"
    REVENUE_SCHEDULED_NOT_BILLED = "REVENUE OPPORTUNITY - SCHEDULED NOT BILLED"
    REVENUE_NOTES_NOT_BILLED = "REVENUE OPPORTUNITY - NOTES NOT BILLED"
    REVIEW_NOTES_WITHOUT_SCHEDULE = "REVIEW - NOTES WITHOUT SCHEDULE"
    REVIEW_NAME_OR_DATE_MISMATCH = "REVIEW - NAME OR DATE MISMATCH"


@dataclass(frozen=True)
class ClientDayKey:
    client: str
    service_date: date

    def as_tuple(self) -> tuple[str, str]:
        return self.client, self.service_date.isoformat()


# ---------------------------------------------------------------------------
# Billing models
# ---------------------------------------------------------------------------

@dataclass
class BillingClaim:
    service_code: str
    medicaid_id: str = ""
    units: int = 0
    group_size: int = 1
    staff_size: int = 1
    county: str = ""
    rate: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")


@dataclass
class BillingDay:
    claims: list[BillingClaim] = field(default_factory=list)

    @property
    def billed(self) -> bool:
        return len(self.claims) > 0

    @property
    def service_codes(self) -> set[str]:
        return {c.service_code for c in self.claims}


# ---------------------------------------------------------------------------
# Schedule models (When I Work)
# ---------------------------------------------------------------------------

@dataclass
class ScheduleShift:
    shift_id: str = ""
    staff_name: str = ""
    client_name: str = ""
    position_name: str = ""
    staff_phone: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    break_minutes: int = 0


@dataclass
class TimeEntry:
    time_id: str = ""
    shift_id: str = ""
    client_name: str = ""
    staff_name: str = ""
    staff_phone: str = ""
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    hours: float = 0.0
    is_approved: bool = False


@dataclass
class ScheduleDay:
    shifts: list[ScheduleShift] = field(default_factory=list)
    time_entries: list[TimeEntry] = field(default_factory=list)

    @property
    def shift_count(self) -> int:
        if self.shifts:
            return len(self.shifts)
        # Timesheet-only days still count as scheduled evidence.
        return len(self.time_entries)

    @property
    def shift_ids(self) -> set[str]:
        return {s.shift_id for s in self.shifts}


# ---------------------------------------------------------------------------
# Notes models (JotForm)
# ---------------------------------------------------------------------------

@dataclass
class ShiftNote:
    submission_id: str = ""
    form_id: str = ""
    client_name: str = ""
    session_date: date | None = None
    service_code: str = ""
    units: int | None = None
    rate: Decimal | None = None
    staff_name: str = ""
    shift_start: time | None = None
    shift_end: time | None = None
    duration_minutes: int | None = None
    medicaid_id: str = ""
    has_signature: bool = False
    has_narrative: bool = False
    narrative_length: int = 0
    service_description: str = ""
    county: str = ""


@dataclass
class NotesDay:
    notes: list[ShiftNote] = field(default_factory=list)
    duplicate_note_ids: set[str] = field(default_factory=set)

    @property
    def note_count(self) -> int:
        return len(self.notes)

    @property
    def note_ids(self) -> set[str]:
        return {n.submission_id for n in self.notes if n.submission_id}


# ---------------------------------------------------------------------------
# Issue tracking
# ---------------------------------------------------------------------------

@dataclass
class SourceIssue:
    issue_type: str
    source: str
    raw_client: str | None
    raw_date: str | None
    reason: str
    normalized_client: str | None = None
    normalized_date: date | None = None


# ---------------------------------------------------------------------------
# Audit output
# ---------------------------------------------------------------------------

@dataclass
class AuditRow:
    client: str
    service_date: date
    billed: bool
    scheduled: bool
    shift_notes_present: bool
    scheduled_shift_count: int
    shift_note_count: int
    missing_shift_notes: int
    billing_service_codes: list[str]
    status: AuditStatus
    exception_reason: str
    suspected_mismatch: bool = False
    duplicate_shift_notes: bool = False
    # New field-level audit fields
    medicaid_id: str = ""
    billing_units: int = 0
    billing_rate: str = ""
    staff_on_note: str = ""
    staff_on_schedule: str = ""
    staff_phone_number: str = ""
    staff_match: bool | None = None
    service_code_on_note: str = ""
    service_code_match: bool | None = None
    units_on_note: int | None = None
    units_match: bool | None = None
    note_has_signature: bool | None = None
    note_has_narrative: bool | None = None
    evv_clock_in: str = ""
    evv_clock_out: str = ""
    evv_hours: float | None = None
    time_match: bool | None = None
    findings: list[str] = field(default_factory=list)
    # Staff coverage fields
    scheduled_staff: list[str] = field(default_factory=list)
    staff_with_notes: list[str] = field(default_factory=list)
    staff_missing_notes: list[str] = field(default_factory=list)
    paper_notes_exempt: bool = False


@dataclass
class AuditSummary:
    total_client_days: int
    compliant_pct: float
    compliant_count: int
    critical_count: int
    warning_count: int
    revenue_opportunity_count: int
    review_count: int


@dataclass
class NotesDiagnosticSample:
    submission_id: str | None
    raw_client: str | None
    raw_date_label: str | None
    raw_date_value: str | None


@dataclass
class NotesDiagnostics:
    missing_client_count: int = 0
    missing_service_date_count: int = 0
    invalid_service_date_count: int = 0
    out_of_range_service_date_count: int = 0
    sample_limit: int = 10
    missing_client_samples: list[NotesDiagnosticSample] = field(default_factory=list)
    missing_service_date_samples: list[NotesDiagnosticSample] = field(default_factory=list)
    invalid_service_date_samples: list[NotesDiagnosticSample] = field(default_factory=list)
    out_of_range_service_date_samples: list[NotesDiagnosticSample] = field(default_factory=list)


@dataclass
class AuditResult:
    summary: AuditSummary
    status_breakdown: dict[str, int]
    audit_rows: list[AuditRow]
    exception_rows: list[AuditRow]
    matching_issues: list[SourceIssue]
    notes_diagnostics: NotesDiagnostics
    assumptions: list[str]
