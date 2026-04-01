from __future__ import annotations

from datetime import date
from pathlib import Path

from audit_engine.connectors.jotform import fetch_notes_map
from audit_engine.connectors.when_i_work import fetch_schedule_map
from audit_engine.hpc_codes import load_hpc_codes
from audit_engine.matching import build_issue_key_set, build_master_client_days, collect_matching_issues
from audit_engine.models import AuditResult, ClientDayKey, BillingDay, ScheduleDay, NotesDay
from audit_engine.normalize import ClientAliasRegistry, normalize_name
from audit_engine.parsers.billing_parser import parse_billing_files
from audit_engine.reporting import build_audit_result
from audit_engine.rules import evaluate_client_day


def _resolve_names_with_aliases(
    source_map: dict[ClientDayKey, object],
    registry: ClientAliasRegistry,
) -> dict[ClientDayKey, object]:
    """Re-key a map using the alias registry to normalize client names."""
    resolved: dict[ClientDayKey, object] = {}
    for key, value in source_map.items():
        canonical = registry.resolve(key.client) if key.client else key.client
        new_key = ClientDayKey(client=canonical, service_date=key.service_date)
        if new_key in resolved:
            # Merge: for ScheduleDay, combine shifts/time_entries; for NotesDay, combine notes
            existing = resolved[new_key]
            if isinstance(existing, ScheduleDay) and isinstance(value, ScheduleDay):
                existing.shifts.extend(value.shifts)
                existing.time_entries.extend(value.time_entries)
            elif isinstance(existing, NotesDay) and isinstance(value, NotesDay):
                existing.notes.extend(value.notes)
            # BillingDay shouldn't need merging but handle it
            elif isinstance(existing, BillingDay) and isinstance(value, BillingDay):
                existing.claims.extend(value.claims)
        else:
            resolved[new_key] = value
    return resolved


def run_audit(
    billing_files: list[Path],
    when_i_work_base_url: str,
    when_i_work_api_token: str,
    when_i_work_api_key: str,
    when_i_work_email: str,
    when_i_work_password: str,
    when_i_work_user_id: str,
    jotform_base_url: str,
    jotform_api_key: str,
    jotform_form_id: str,
    start_date: date,
    end_date: date,
    timeout_seconds: int,
    hpc_file_path: Path | None = None,
    jotform_auto_discover: bool = True,
    billable_only: bool = False,
    paper_notes_exempt_clients: set[str] | None = None,
) -> AuditResult:
    # Load HPC codes
    hpc_codes = None
    if hpc_file_path and hpc_file_path.exists():
        hpc_codes = load_hpc_codes(hpc_file_path)

    # Step 1: Parse billing with HPC filter
    billing_map, billing_issues = parse_billing_files(billing_files, hpc_codes=hpc_codes)

    # Step 2: Build alias registry from billing names
    registry = ClientAliasRegistry()
    billing_client_names = {key.client for key in billing_map}
    registry.seed_from_billing(billing_client_names)

    # Step 3: Fetch schedule (sites + time entries)
    schedule_map, schedule_issues = fetch_schedule_map(
        base_url=when_i_work_base_url,
        api_token=when_i_work_api_token,
        api_key=when_i_work_api_key,
        login_email=when_i_work_email,
        login_password=when_i_work_password,
        user_id=when_i_work_user_id,
        start_date=start_date,
        end_date=end_date,
        timeout_seconds=timeout_seconds,
    )

    # Step 4: Fetch notes (all forms, rich fields)
    notes_map, notes_issues, notes_diagnostics = fetch_notes_map(
        base_url=jotform_base_url,
        api_key=jotform_api_key,
        form_id=jotform_form_id,
        start_date=start_date,
        end_date=end_date,
        timeout_seconds=timeout_seconds,
        auto_discover=jotform_auto_discover,
    )

    # Step 5: Resolve names via alias registry
    schedule_map = _resolve_names_with_aliases(schedule_map, registry)
    notes_map = _resolve_names_with_aliases(notes_map, registry)
    exempt_clients_canonical: set[str] = set()
    for raw_name in paper_notes_exempt_clients or set():
        normalized = normalize_name(raw_name)
        if not normalized:
            continue
        exempt_clients_canonical.add(registry.resolve(normalized))

    # Step 6: Build master keys and evaluate
    matching_issues = collect_matching_issues(billing_issues, schedule_issues, notes_issues)
    issue_keys = build_issue_key_set(matching_issues)
    if billable_only:
        master_keys = list(billing_map.keys())
    else:
        master_keys = build_master_client_days(billing_map, schedule_map, notes_map)

    rows = []
    for key in master_keys:
        row_has_issue = key in issue_keys
        day_rows = evaluate_client_day(
            key=key,
            billing_day=billing_map.get(key),
            schedule_day=schedule_map.get(key),
            notes_day=notes_map.get(key),
            has_source_issue=row_has_issue,
            paper_notes_exempt=key.client in exempt_clients_canonical,
        )
        rows.extend(day_rows)

    return build_audit_result(rows, matching_issues, notes_diagnostics)
