from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from audit_engine.models import BillingClaim, BillingDay, ClientDayKey, SourceIssue
from audit_engine.normalize import normalize_date, normalize_name

# Matches a billing claim line with all fields.
# Format: NAME  MEDICAID  DATE  CODE  GROUP  STAFF  COUNTY  INPUT_RATE  BILLED_RATE  UNITS  TYPE  AMOUNT  OTHER  NET_AMOUNT
BILLING_LINE_PATTERN = re.compile(
    r"^(?P<name>[A-Z][A-Z\-\.' ]+,\s*[A-Z][A-Z\-\.' ]+)\s+"
    r"(?P<medicaid>\d{9,15})\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<service_code>[A-Z0-9]{2,4})\s+"
    r"(?:(?P<group>\d+)\s+)?"
    r"(?:(?P<staff>\d+)\s+)?"
    r"(?P<county>[A-Z]+)\s+"
    r"\$?(?P<input_rate>[\d,]+\.?\d*)\s+"
    r"\$?(?P<billed_rate>[\d,]+\.?\d*)\s+"
    r"(?P<units>\d+)\s+"
    r"(?P<claim_type>[A-Z])\s+"
    r"\$?(?P<amount>[\d,]+\.?\d*)"
)


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(value.strip())
    except ValueError:
        return 0


def parse_billing_files(
    billing_files: list[Path],
    hpc_codes: frozenset[str] | None = None,
) -> tuple[dict[ClientDayKey, BillingDay], list[SourceIssue]]:
    billing_map: dict[ClientDayKey, BillingDay] = {}
    issues: list[SourceIssue] = []

    for billing_file in billing_files:
        text = billing_file.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            match = BILLING_LINE_PATTERN.match(line.strip())
            if not match:
                continue

            raw_name = match.group("name")
            raw_date = match.group("date")
            service_code = match.group("service_code").strip().upper()

            # Filter by HPC codes if provided
            if hpc_codes is not None and service_code not in hpc_codes:
                continue

            client = normalize_name(raw_name)
            if not client:
                issues.append(
                    SourceIssue(
                        issue_type="name_parse_error",
                        source="billing",
                        raw_client=raw_name,
                        raw_date=raw_date,
                        reason="normalized client name is empty",
                        normalized_client=client,
                    )
                )
                continue

            try:
                service_date = normalize_date(raw_date)
            except ValueError:
                issues.append(
                    SourceIssue(
                        issue_type="date_parse_error",
                        source="billing",
                        raw_client=raw_name,
                        raw_date=raw_date,
                        reason="invalid billing service date format",
                        normalized_client=client,
                    )
                )
                continue

            claim = BillingClaim(
                service_code=service_code,
                medicaid_id=match.group("medicaid").strip(),
                units=_parse_int(match.group("units")),
                group_size=_parse_int(match.group("group")) or 1,
                staff_size=_parse_int(match.group("staff")) or 1,
                county=match.group("county").strip(),
                rate=_parse_decimal(match.group("billed_rate")),
                amount=_parse_decimal(match.group("amount")),
            )

            key = ClientDayKey(client=client, service_date=service_date)
            if key not in billing_map:
                billing_map[key] = BillingDay()
            billing_map[key].claims.append(claim)

    return billing_map, issues
