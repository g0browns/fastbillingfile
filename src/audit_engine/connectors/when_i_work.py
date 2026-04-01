from __future__ import annotations

from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from audit_engine.models import (
    ClientDayKey,
    ScheduleDay,
    ScheduleShift,
    SourceIssue,
    TimeEntry,
)
from audit_engine.normalize import normalize_date, normalize_name


# ---------------------------------------------------------------------------
# Datetime parsing for WIW format: "Fri, 27 Mar 2026 17:30:00 -0400"
# ---------------------------------------------------------------------------

_NON_CLIENT_SITE_EXACT: set[str] = {
    "admin office",
    "main office",
    "office",
    "meadowbrook",
    "ohio job network",
}


def _looks_like_non_client_site(raw_name: str, location_names: set[str]) -> bool:
    """Return True for schedule labels that are clearly business locations."""
    normalized = normalize_name(raw_name)
    if not normalized:
        return False
    if normalized in _NON_CLIENT_SITE_EXACT:
        return True
    if normalized in location_names:
        return True
    if normalized.endswith(" office") or normalized.startswith("office "):
        return True
    if normalized.startswith("admin "):
        return True
    return False


def _parse_wiw_datetime(raw: str) -> datetime | None:
    """Parse When I Work datetime string into a timezone-aware datetime."""
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Lookup map fetchers
# ---------------------------------------------------------------------------


def _fetch_user_name_map(base_url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, str]:
    response = requests.get(f"{base_url.rstrip('/')}/users", headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    users = payload.get("users")
    if not isinstance(users, list):
        return {}
    mapping: dict[str, str] = {}
    for user in users:
        if not isinstance(user, dict):
            continue
        user_id = user.get("id")
        first_name = str(user.get("first_name") or "").strip()
        last_name = str(user.get("last_name") or "").strip()
        full_name = f"{first_name} {last_name}".strip()
        if user_id is not None and full_name:
            mapping[str(user_id)] = full_name
    return mapping


def _normalize_phone(raw_value: object) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    allowed = {"+", "(", ")", "-", " "}
    filtered = "".join(ch for ch in text if ch.isdigit() or ch in allowed)
    return filtered.strip()


def _extract_user_phone(user: dict[str, Any]) -> str:
    # WIW payloads vary by account: check common keys conservatively.
    direct_keys = (
        "phone",
        "phone_number",
        "mobile_phone",
        "cell_phone",
        "mobile",
    )
    for key in direct_keys:
        value = _normalize_phone(user.get(key))
        if value:
            return value

    contact = user.get("contact")
    if isinstance(contact, dict):
        for key in direct_keys:
            value = _normalize_phone(contact.get(key))
            if value:
                return value
    return ""


def _fetch_user_phone_map(base_url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, str]:
    response = requests.get(f"{base_url.rstrip('/')}/users", headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    users = payload.get("users")
    if not isinstance(users, list):
        return {}
    mapping: dict[str, str] = {}
    for user in users:
        if not isinstance(user, dict):
            continue
        user_id = user.get("id")
        phone = _extract_user_phone(user)
        if user_id is not None and phone:
            mapping[str(user_id)] = phone
    return mapping


def _fetch_site_name_map(base_url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, str]:
    """Fetch sites — these are CLIENTS, not business locations."""
    response = requests.get(f"{base_url.rstrip('/')}/sites", headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    sites = payload.get("sites")
    if not isinstance(sites, list):
        return {}
    mapping: dict[str, str] = {}
    for site in sites:
        if not isinstance(site, dict):
            continue
        site_id = site.get("id")
        site_name = str(site.get("name") or "").strip()
        if site_id is not None and site_name:
            mapping[str(site_id)] = site_name
    return mapping


def _fetch_position_name_map(base_url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, str]:
    response = requests.get(f"{base_url.rstrip('/')}/positions", headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    positions = payload.get("positions")
    if not isinstance(positions, list):
        return {}
    mapping: dict[str, str] = {}
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        pos_id = pos.get("id")
        pos_name = str(pos.get("name") or "").strip()
        if pos_id is not None and pos_name:
            mapping[str(pos_id)] = pos_name
    return mapping


def _fetch_location_name_map(base_url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, str]:
    response = requests.get(f"{base_url.rstrip('/')}/locations", headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    locations = payload.get("locations")
    if not isinstance(locations, list):
        return {}
    mapping: dict[str, str] = {}
    for location in locations:
        if not isinstance(location, dict):
            continue
        location_id = location.get("id")
        location_name = str(location.get("name") or "").strip()
        if location_id is not None and location_name:
            mapping[str(location_id)] = location_name
    return mapping


def _fetch_time_entries(
    base_url: str,
    headers: dict[str, str],
    start_date: date,
    end_date: date,
    timeout_seconds: int,
    user_name_by_id: dict[str, str],
    user_phone_by_id: dict[str, str],
    site_name_by_id: dict[str, str],
    location_names_normalized: set[str],
) -> tuple[dict[str, list[TimeEntry]], dict[ClientDayKey, list[TimeEntry]], list[SourceIssue]]:
    """Fetch clock in/out records, indexed by shift_id and client-day."""
    url = f"{base_url.rstrip('/')}/times"
    params = {"start": start_date.isoformat(), "end": end_date.isoformat()}
    response = requests.get(url, headers=headers, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    raw_times = payload.get("times")
    if not isinstance(raw_times, list):
        return {}, {}, []

    by_shift: dict[str, list[TimeEntry]] = {}
    by_client_day: dict[ClientDayKey, list[TimeEntry]] = {}
    issues: list[SourceIssue] = []
    for t in raw_times:
        if not isinstance(t, dict):
            continue
        shift_id = str(t.get("shift_id") or "")
        time_id = str(t.get("id") or "")
        site_id = str(t.get("site_id") or "")
        user_id = str(t.get("user_id") or "")
        staff = user_name_by_id.get(user_id, "")
        staff_phone = user_phone_by_id.get(user_id, "")
        clock_in = _parse_wiw_datetime(t.get("start_time", ""))
        clock_out = _parse_wiw_datetime(t.get("end_time", "")) if t.get("end_time") else None
        hours = float(t.get("length", 0) or 0)
        is_approved = bool(t.get("is_approved"))
        raw_client = site_name_by_id.get(site_id, "") if site_id else ""
        normalized_client = normalize_name(raw_client) if raw_client else ""

        entry = TimeEntry(
            time_id=time_id,
            shift_id=shift_id,
            client_name=normalized_client,
            staff_name=staff,
            staff_phone=staff_phone,
            clock_in=clock_in,
            clock_out=clock_out,
            hours=hours,
            is_approved=is_approved,
        )
        if shift_id:
            by_shift.setdefault(shift_id, []).append(entry)

        raw_start = t.get("start_time", "")
        if not raw_client:
            issues.append(
                SourceIssue(
                    issue_type="missing_required_fields",
                    source="schedule",
                    raw_client=None,
                    raw_date=raw_start or None,
                    reason="timesheet entry has no site assigned (site_id missing or unknown)",
                    normalized_client=None,
                )
            )
            continue

        if _looks_like_non_client_site(raw_client, location_names_normalized):
            issues.append(
                SourceIssue(
                    issue_type="non_client_site_excluded",
                    source="schedule",
                    raw_client=raw_client,
                    raw_date=raw_start or None,
                    reason="timesheet site resolved to business/admin location, excluded from client-day schedule map",
                    normalized_client=normalized_client or None,
                )
            )
            continue

        if not normalized_client:
            issues.append(
                SourceIssue(
                    issue_type="name_parse_error",
                    source="schedule",
                    raw_client=raw_client,
                    raw_date=raw_start or None,
                    reason="timesheet normalized client name is empty",
                    normalized_client=normalized_client or None,
                )
            )
            continue

        if not clock_in:
            issues.append(
                SourceIssue(
                    issue_type="date_parse_error",
                    source="schedule",
                    raw_client=raw_client,
                    raw_date=raw_start or None,
                    reason="could not parse timesheet start_time",
                    normalized_client=normalized_client,
                )
            )
            continue

        key = ClientDayKey(client=normalized_client, service_date=clock_in.date())
        by_client_day.setdefault(key, []).append(entry)
    return by_shift, by_client_day, issues


# ---------------------------------------------------------------------------
# Main fetch
# ---------------------------------------------------------------------------


def fetch_schedule_map(
    base_url: str,
    api_token: str,
    api_key: str,
    login_email: str,
    login_password: str,
    user_id: str,
    start_date: date,
    end_date: date,
    timeout_seconds: int,
) -> tuple[dict[ClientDayKey, ScheduleDay], list[SourceIssue]]:
    issues: list[SourceIssue] = []
    access_token = _resolve_access_token(
        api_token=api_token,
        api_key=api_key,
        login_email=login_email,
        login_password=login_password,
        timeout_seconds=timeout_seconds,
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "W-Token": access_token,
        "Accept": "application/json",
    }
    if user_id:
        headers["W-UserId"] = user_id

    # Fetch lookup maps
    user_name_by_id = _fetch_user_name_map(base_url=base_url, headers=headers, timeout_seconds=timeout_seconds)
    user_phone_by_id = _fetch_user_phone_map(base_url=base_url, headers=headers, timeout_seconds=timeout_seconds)
    site_name_by_id = _fetch_site_name_map(base_url=base_url, headers=headers, timeout_seconds=timeout_seconds)
    position_name_by_id = _fetch_position_name_map(base_url=base_url, headers=headers, timeout_seconds=timeout_seconds)
    location_name_by_id = _fetch_location_name_map(base_url=base_url, headers=headers, timeout_seconds=timeout_seconds)
    location_names_normalized = {
        normalize_name(name) for name in location_name_by_id.values() if normalize_name(name)
    }

    # Fetch time entries (EVV)
    time_entries_by_shift, time_entries_by_client_day, times_issues = _fetch_time_entries(
        base_url=base_url,
        headers=headers,
        start_date=start_date,
        end_date=end_date,
        timeout_seconds=timeout_seconds,
        user_name_by_id=user_name_by_id,
        user_phone_by_id=user_phone_by_id,
        site_name_by_id=site_name_by_id,
        location_names_normalized=location_names_normalized,
    )
    issues.extend(times_issues)

    # Fetch shifts
    url = f"{base_url.rstrip('/')}/shifts"
    params = {"start": start_date.isoformat(), "end": end_date.isoformat(), "limit": 1000}
    response = requests.get(url, headers=headers, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict):
        raw_shifts = payload.get("shifts")
    else:
        raw_shifts = payload
    if not isinstance(raw_shifts, list):
        raise RuntimeError("When I Work response does not include a shifts list")

    schedule_map: dict[ClientDayKey, ScheduleDay] = {}

    for shift in raw_shifts:
        if not isinstance(shift, dict):
            issues.append(
                SourceIssue(
                    issue_type="record_parse_error",
                    source="schedule",
                    raw_client=None,
                    raw_date=None,
                    reason="shift record is not an object",
                )
            )
            continue

        # Resolve client name from site_id (sites = clients)
        site_id = str(shift.get("site_id") or "")
        raw_client = site_name_by_id.get(site_id, "") if site_id else ""

        # Resolve staff name from user_id
        raw_user_id = str(shift.get("user_id") or "")
        staff_name = user_name_by_id.get(raw_user_id, "")
        staff_phone = user_phone_by_id.get(raw_user_id, "")

        # Resolve position from position_id
        raw_position_id = str(shift.get("position_id") or "")
        position_name = position_name_by_id.get(raw_position_id, "")

        # Parse start/end times
        raw_start = shift.get("start_time", "")
        raw_end = shift.get("end_time", "")
        shift_start = _parse_wiw_datetime(raw_start) if raw_start else None
        shift_end = _parse_wiw_datetime(raw_end) if raw_end else None

        shift_id = str(shift.get("id") or "")
        normalized_client = normalize_name(raw_client) if raw_client else None

        if not raw_client:
            issues.append(
                SourceIssue(
                    issue_type="missing_required_fields",
                    source="schedule",
                    raw_client=raw_client or None,
                    raw_date=raw_start or None,
                    reason="no site assigned to shift (site_id missing or unknown)",
                    normalized_client=normalized_client,
                )
            )
            continue

        if _looks_like_non_client_site(raw_client, location_names_normalized):
            issues.append(
                SourceIssue(
                    issue_type="non_client_site_excluded",
                    source="schedule",
                    raw_client=raw_client,
                    raw_date=raw_start or None,
                    reason="site resolved to business/admin location, excluded from client-day schedule map",
                    normalized_client=normalized_client,
                )
            )
            continue

        client = normalized_client or ""
        if not client:
            issues.append(
                SourceIssue(
                    issue_type="name_parse_error",
                    source="schedule",
                    raw_client=raw_client,
                    raw_date=raw_start,
                    reason="normalized client name is empty",
                    normalized_client=client,
                )
            )
            continue

        # Extract date from shift start time
        if not shift_start:
            issues.append(
                SourceIssue(
                    issue_type="date_parse_error",
                    source="schedule",
                    raw_client=raw_client,
                    raw_date=raw_start,
                    reason="could not parse shift start_time",
                    normalized_client=client,
                )
            )
            continue

        service_date = shift_start.date()
        break_minutes = int(shift.get("break_time", 0) or 0)

        schedule_shift = ScheduleShift(
            shift_id=shift_id,
            staff_name=normalize_name(staff_name) if staff_name else "",
            staff_phone=staff_phone,
            client_name=client,
            position_name=position_name,
            start_time=shift_start,
            end_time=shift_end,
            break_minutes=break_minutes,
        )

        key = ClientDayKey(client=client, service_date=service_date)
        if key not in schedule_map:
            schedule_map[key] = ScheduleDay()
        schedule_map[key].shifts.append(schedule_shift)

        # Attach time entries for this shift
        if shift_id and shift_id in time_entries_by_shift:
            schedule_map[key].time_entries.extend(time_entries_by_shift[shift_id])

    # Add timesheet-only coverage: if a client-day has valid time entries, it is schedule evidence.
    for key, entries in time_entries_by_client_day.items():
        if key not in schedule_map:
            schedule_map[key] = ScheduleDay()
        existing_ids = {te.time_id for te in schedule_map[key].time_entries if te.time_id}
        for entry in entries:
            if entry.time_id and entry.time_id in existing_ids:
                continue
            schedule_map[key].time_entries.append(entry)
            if entry.time_id:
                existing_ids.add(entry.time_id)

    return schedule_map, issues


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _resolve_access_token(
    api_token: str,
    api_key: str,
    login_email: str,
    login_password: str,
    timeout_seconds: int,
) -> str:
    if api_token:
        return api_token
    if not login_email or not login_password:
        raise RuntimeError("missing When I Work login credentials")

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["W-Key"] = api_key

    response = requests.post(
        "https://api.login.wheniwork.com/login",
        headers=headers,
        json={"email": login_email, "password": login_password},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()

    person = payload.get("person")
    if isinstance(person, dict):
        person_token = person.get("token")
        if isinstance(person_token, str) and person_token.strip():
            return person_token.strip()
    raise RuntimeError("When I Work login response does not include a token")
