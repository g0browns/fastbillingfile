from __future__ import annotations

from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from audit_engine.models import (
    ClientDayKey,
    NotesDay,
    NotesDiagnosticSample,
    NotesDiagnostics,
    ShiftNote,
    SourceIssue,
)
from audit_engine.normalize import normalize_date, normalize_name


# ---------------------------------------------------------------------------
# Form discovery
# ---------------------------------------------------------------------------


def discover_shift_note_forms(
    base_url: str,
    api_key: str,
    timeout_seconds: int,
) -> list[dict[str, str]]:
    """Find all enabled forms whose title contains 'Shift Note'."""
    headers = {"APIKEY": api_key, "Accept": "application/json"}
    forms: list[dict[str, str]] = []
    offset = 0
    limit = 100

    while True:
        params = {"limit": str(limit), "offset": str(offset)}
        response = requests.get(
            f"{base_url.rstrip('/')}/user/forms",
            headers=headers,
            params=params,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        # Handle HIPAA redirect
        if payload.get("responseCode") == 301 and isinstance(payload.get("location"), str):
            redirected = payload["location"].strip()
            if redirected:
                response = requests.get(redirected, headers=headers, params=params, timeout=timeout_seconds)
                response.raise_for_status()
                payload = response.json()

        content = payload.get("content", [])
        if isinstance(content, dict):
            content = list(content.values())
        if not content:
            break

        for form in content:
            if not isinstance(form, dict):
                continue
            title = str(form.get("title", ""))
            status = str(form.get("status", ""))
            form_id = str(form.get("id", ""))
            if "shift note" in title.lower() and status == "ENABLED" and form_id:
                forms.append({"id": form_id, "title": title})

        if len(content) < limit:
            break
        offset += limit

    return forms


# ---------------------------------------------------------------------------
# Field extraction helpers (keyed by field `name`, per JOTFORM_FIELD_MAP.md)
# ---------------------------------------------------------------------------


def _build_answers_by_name(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the answers dict by the `name` attribute for consistent lookup."""
    answers = record.get("answers")
    if not isinstance(answers, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in answers.values():
        if isinstance(item, dict):
            name = item.get("name", "")
            if name:
                result[name] = item
    return result


def _extract_client_name(by_name: dict[str, dict[str, Any]]) -> str | None:
    field = by_name.get("clientName")
    if field:
        answer = field.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()

    # Fallback: scan for any field with "client" in name
    for name, item in by_name.items():
        if "client" in name.lower() and name != "clientMood":
            answer = item.get("answer")
            if isinstance(answer, str) and answer.strip():
                return answer.strip()
    return None


def _extract_session_date(by_name: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    """Returns (field_label, raw_date_string)."""
    # Look for fields starting with "sessionDate"
    for name, item in by_name.items():
        if name.startswith("sessionDate"):
            answer = item.get("answer")
            parsed = _coerce_answer_date(answer)
            if not parsed:
                parsed = item.get("prettyFormat")
                if isinstance(parsed, str) and parsed.strip():
                    parsed = parsed.strip()
                else:
                    parsed = None
            label = str(item.get("text", "")).strip() or name
            if parsed:
                return label, parsed

    # Fallback: look for date-like labels
    for name, item in by_name.items():
        label = str(item.get("text", "")).strip().lower()
        if any(tok in label for tok in ("service date", "date of service", "shift date", "session date")):
            answer = item.get("answer")
            parsed = _coerce_answer_date(answer)
            if not parsed:
                parsed = item.get("prettyFormat")
                if isinstance(parsed, str) and parsed.strip():
                    parsed = parsed.strip()
                else:
                    parsed = None
            if parsed:
                return str(item.get("text", "")).strip() or name, parsed
    return None, None


def _coerce_answer_date(answer_value: Any) -> str | None:
    if isinstance(answer_value, str) and answer_value.strip():
        return answer_value.strip()
    if isinstance(answer_value, dict):
        month = str(answer_value.get("month", "")).strip()
        day = str(answer_value.get("day", "")).strip()
        year = str(answer_value.get("year", "")).strip()
        if month and day and year:
            return f"{month}/{day}/{year}"
        pretty = str(answer_value.get("prettyFormat", "")).strip()
        if pretty:
            return pretty
    if isinstance(answer_value, list):
        for item in answer_value:
            parsed = _coerce_answer_date(item)
            if parsed:
                return parsed
    return None


def _extract_string_field(by_name: dict[str, dict[str, Any]], *field_names: str) -> str:
    for name in field_names:
        field = by_name.get(name)
        if field:
            answer = field.get("answer")
            if isinstance(answer, str) and answer.strip():
                return answer.strip()
    return ""


def _extract_staff_name(by_name: dict[str, dict[str, Any]]) -> str:
    # Try dspStaff (fullname field with first/last)
    for name in ("dspStaff", "dspName"):
        field = by_name.get(name)
        if field:
            answer = field.get("answer")
            pretty = field.get("prettyFormat")
            if isinstance(pretty, str) and pretty.strip():
                return pretty.strip()
            if isinstance(answer, dict):
                first = str(answer.get("first", "")).strip()
                last = str(answer.get("last", "")).strip()
                full = f"{first} {last}".strip()
                if full:
                    return full
            if isinstance(answer, str) and answer.strip():
                return answer.strip()

    # Fallback: plain "name" field (some forms use this)
    field = by_name.get("name")
    if field:
        answer = field.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
    return ""


def _extract_int_field(by_name: dict[str, dict[str, Any]], *field_names: str) -> int | None:
    for name in field_names:
        field = by_name.get(name)
        if field:
            answer = field.get("answer")
            if isinstance(answer, (int, float)):
                return int(answer)
            if isinstance(answer, str) and answer.strip():
                try:
                    return int(float(answer.strip()))
                except ValueError:
                    pass
    return None


def _extract_decimal_field(by_name: dict[str, dict[str, Any]], *field_names: str) -> Decimal | None:
    for name in field_names:
        field = by_name.get(name)
        if field:
            answer = field.get("answer")
            if isinstance(answer, (int, float)):
                return Decimal(str(answer))
            if isinstance(answer, str) and answer.strip():
                try:
                    return Decimal(answer.strip().replace(",", ""))
                except InvalidOperation:
                    pass
    return None


def _extract_shift_time(by_name: dict[str, dict[str, Any]]) -> tuple[time | None, time | None, int | None]:
    """Extract start time, end time, and duration from shiftTime field."""
    field = by_name.get("shiftTime")
    if not field:
        return None, None, None
    answer = field.get("answer")
    if not isinstance(answer, dict):
        return None, None, None

    start = _parse_time_components(
        answer.get("hourSelect"), answer.get("minuteSelect"), answer.get("ampm")
    )
    end = _parse_time_components(
        answer.get("hourSelectRange"), answer.get("minuteSelectRange"), answer.get("ampmRange")
    )

    duration = None
    dur_str = str(answer.get("timeRangeDuration", "")).strip()
    if dur_str and ":" in dur_str:
        parts = dur_str.split(":")
        try:
            duration = int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass

    return start, end, duration


def _parse_time_components(hour: Any, minute: Any, ampm: Any) -> time | None:
    h = str(hour or "").strip()
    m = str(minute or "").strip()
    ap = str(ampm or "").strip().upper()
    if not h or not m:
        return None
    try:
        h_int = int(h)
        m_int = int(m)
    except ValueError:
        return None
    if ap == "PM" and h_int != 12:
        h_int += 12
    elif ap == "AM" and h_int == 12:
        h_int = 0
    if h_int > 23 or m_int > 59:
        return None
    return time(h_int, m_int)


def _has_signature(by_name: dict[str, dict[str, Any]]) -> bool:
    field = by_name.get("signature")
    if not field:
        return False
    answer = field.get("answer")
    return isinstance(answer, str) and answer.strip() != ""


def _extract_narrative(by_name: dict[str, dict[str, Any]]) -> tuple[bool, int]:
    text = _extract_string_field(by_name, "shiftActivities")
    return bool(text), len(text)


# ---------------------------------------------------------------------------
# Main fetch
# ---------------------------------------------------------------------------


def fetch_notes_map(
    base_url: str,
    api_key: str,
    form_id: str,
    start_date: date,
    end_date: date,
    timeout_seconds: int,
    auto_discover: bool = True,
) -> tuple[dict[ClientDayKey, NotesDay], list[SourceIssue], NotesDiagnostics]:
    # Determine which forms to fetch
    form_ids: list[str] = []
    if form_id:
        form_ids = [f.strip() for f in form_id.split(",") if f.strip()]

    if not form_ids and auto_discover:
        discovered = discover_shift_note_forms(base_url, api_key, timeout_seconds)
        form_ids = [f["id"] for f in discovered]

    if not form_ids:
        # Fallback to account-wide submissions
        form_ids = [""]

    notes_map: dict[ClientDayKey, NotesDay] = {}
    issues: list[SourceIssue] = []
    diagnostics = NotesDiagnostics()

    for fid in form_ids:
        _fetch_form_submissions(
            base_url=base_url,
            api_key=api_key,
            form_id=fid,
            start_date=start_date,
            end_date=end_date,
            timeout_seconds=timeout_seconds,
            notes_map=notes_map,
            issues=issues,
            diagnostics=diagnostics,
        )

    return notes_map, issues, diagnostics


def _fetch_form_submissions(
    base_url: str,
    api_key: str,
    form_id: str,
    start_date: date,
    end_date: date,
    timeout_seconds: int,
    notes_map: dict[ClientDayKey, NotesDay],
    issues: list[SourceIssue],
    diagnostics: NotesDiagnostics,
) -> None:
    if form_id:
        endpoint = f"{base_url.rstrip('/')}/form/{form_id}/submissions"
    else:
        endpoint = f"{base_url.rstrip('/')}/user/submissions"

    offset = 0
    limit = 1000

    while True:
        submissions, endpoint = _fetch_submissions_page(
            endpoint=endpoint,
            api_key=api_key,
            limit=limit,
            offset=offset,
            timeout_seconds=timeout_seconds,
        )
        if not submissions:
            break

        for record in submissions:
            if not isinstance(record, dict):
                issues.append(
                    SourceIssue(
                        issue_type="record_parse_error",
                        source="notes",
                        raw_client=None,
                        raw_date=None,
                        reason="submission record is not an object",
                    )
                )
                continue

            _process_submission(
                record=record,
                form_id=form_id,
                start_date=start_date,
                end_date=end_date,
                notes_map=notes_map,
                issues=issues,
                diagnostics=diagnostics,
            )

        if len(submissions) < limit:
            break
        offset += limit


def _process_submission(
    record: dict[str, Any],
    form_id: str,
    start_date: date,
    end_date: date,
    notes_map: dict[ClientDayKey, NotesDay],
    issues: list[SourceIssue],
    diagnostics: NotesDiagnostics,
) -> None:
    by_name = _build_answers_by_name(record)
    submission_id = str(record.get("id", "")).strip() or None

    raw_client = _extract_client_name(by_name)
    date_label, raw_service_date = _extract_session_date(by_name)
    normalized_client = normalize_name(raw_client) if raw_client else None

    if not raw_client:
        diagnostics.missing_client_count += 1
        _add_diagnostic_sample(
            diagnostics.missing_client_samples,
            diagnostics.sample_limit,
            submission_id=submission_id,
            raw_client=raw_client,
            raw_date_label=date_label,
            raw_date_value=raw_service_date,
        )
    if not raw_service_date:
        diagnostics.missing_service_date_count += 1
        _add_diagnostic_sample(
            diagnostics.missing_service_date_samples,
            diagnostics.sample_limit,
            submission_id=submission_id,
            raw_client=raw_client,
            raw_date_label=date_label,
            raw_date_value=raw_service_date,
        )
    if not raw_client or not raw_service_date:
        issues.append(
            SourceIssue(
                issue_type="missing_required_fields",
                source="notes",
                raw_client=raw_client,
                raw_date=raw_service_date,
                reason="client or service date missing from note",
                normalized_client=normalized_client,
            )
        )
        return

    client = normalized_client or ""
    if not client:
        issues.append(
            SourceIssue(
                issue_type="name_parse_error",
                source="notes",
                raw_client=raw_client,
                raw_date=raw_service_date,
                reason="normalized client name is empty",
                normalized_client=client,
            )
        )
        return

    try:
        service_date = normalize_date(raw_service_date)
    except ValueError:
        diagnostics.invalid_service_date_count += 1
        _add_diagnostic_sample(
            diagnostics.invalid_service_date_samples,
            diagnostics.sample_limit,
            submission_id=submission_id,
            raw_client=raw_client,
            raw_date_label=date_label,
            raw_date_value=raw_service_date,
        )
        issues.append(
            SourceIssue(
                issue_type="date_parse_error",
                source="notes",
                raw_client=raw_client,
                raw_date=raw_service_date,
                reason="invalid note service date format",
                normalized_client=client,
            )
        )
        return

    if service_date < start_date or service_date > end_date:
        diagnostics.out_of_range_service_date_count += 1
        _add_diagnostic_sample(
            diagnostics.out_of_range_service_date_samples,
            diagnostics.sample_limit,
            submission_id=submission_id,
            raw_client=raw_client,
            raw_date_label=date_label,
            raw_date_value=raw_service_date,
        )
        return

    # Extract all rich fields
    service_code = _extract_string_field(by_name, "serviceCode").upper()
    staff_name = _extract_staff_name(by_name)
    units = _extract_int_field(by_name, "units")
    rate = _extract_decimal_field(by_name, "rate")
    medicaid_id = _extract_string_field(by_name, "medId")
    shift_start, shift_end, duration = _extract_shift_time(by_name)
    sig = _has_signature(by_name)
    has_narr, narr_len = _extract_narrative(by_name)
    service_desc = _extract_string_field(by_name, "service")
    county = _extract_string_field(by_name, "county")

    note = ShiftNote(
        submission_id=submission_id or "",
        form_id=form_id,
        client_name=client,
        session_date=service_date,
        service_code=service_code,
        units=units,
        rate=rate,
        staff_name=normalize_name(staff_name) if staff_name else "",
        shift_start=shift_start,
        shift_end=shift_end,
        duration_minutes=duration,
        medicaid_id=medicaid_id,
        has_signature=sig,
        has_narrative=has_narr,
        narrative_length=narr_len,
        service_description=service_desc,
        county=county,
    )

    key = ClientDayKey(client=client, service_date=service_date)
    if key not in notes_map:
        notes_map[key] = NotesDay()

    # Check for duplicate submission IDs
    if submission_id:
        existing_ids = {n.submission_id for n in notes_map[key].notes}
        if submission_id in existing_ids:
            notes_map[key].duplicate_note_ids.add(submission_id)
            issues.append(
                SourceIssue(
                    issue_type="duplicate_note_id",
                    source="notes",
                    raw_client=raw_client,
                    raw_date=raw_service_date,
                    reason=f"duplicate note id encountered: {submission_id}",
                    normalized_client=client,
                    normalized_date=service_date,
                )
            )

    notes_map[key].notes.append(note)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _fetch_submissions_page(
    endpoint: str,
    api_key: str,
    limit: int,
    offset: int,
    timeout_seconds: int,
) -> tuple[list[dict[str, Any]], str]:
    headers = {"APIKEY": api_key, "Accept": "application/json"}
    params = {"limit": str(limit), "offset": str(offset)}
    response = requests.get(endpoint, headers=headers, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    response_code = payload.get("responseCode")
    if response_code == 301 and isinstance(payload.get("location"), str):
        redirected_endpoint = payload["location"].strip()
        if redirected_endpoint:
            response = requests.get(redirected_endpoint, headers=headers, params=params, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            endpoint = redirected_endpoint
    content = payload.get("content")
    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)], endpoint
    if isinstance(content, dict):
        return [item for item in content.values() if isinstance(item, dict)], endpoint
    submissions = payload.get("submissions")
    if isinstance(submissions, list):
        return [item for item in submissions if isinstance(item, dict)], endpoint
    if isinstance(submissions, dict):
        return [item for item in submissions.values() if isinstance(item, dict)], endpoint
    if isinstance(payload.get("responseCode"), int) and payload.get("responseCode") != 200:
        message = str(payload.get("message") or "unknown Jotform API error")
        raise RuntimeError(f"Jotform API error: {message}")
    raise RuntimeError("Jotform response does not include a submissions list")


def _add_diagnostic_sample(
    bucket: list[NotesDiagnosticSample],
    sample_limit: int,
    submission_id: str | None,
    raw_client: str | None,
    raw_date_label: str | None,
    raw_date_value: str | None,
) -> None:
    if len(bucket) >= sample_limit:
        return
    bucket.append(
        NotesDiagnosticSample(
            submission_id=submission_id,
            raw_client=raw_client,
            raw_date_label=raw_date_label,
            raw_date_value=raw_date_value,
        )
    )
