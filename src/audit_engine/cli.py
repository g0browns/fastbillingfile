from __future__ import annotations

import argparse
from pathlib import Path

from audit_engine.config import load_settings
from audit_engine.engine import run_audit
from audit_engine.normalize import normalize_date
from audit_engine.reporting import write_exports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Meadowbrook deterministic compliance audit")
    parser.add_argument("--billing-dir", required=True, help="Directory containing billing TXT files")
    parser.add_argument("--start-date", required=True, help="Inclusive start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Inclusive end date (YYYY-MM-DD)")
    parser.add_argument(
        "--output-dir",
        required=False,
        help="Output directory for exports (default from AUDIT_OUTPUT_DIR)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings()

    billing_dir = Path(args.billing_dir)
    billing_files = sorted(billing_dir.glob("**/*.TXT"))
    if not billing_files:
        raise RuntimeError(f"no billing .TXT files found under {billing_dir}")

    hpc_path = Path(settings.hpc_file_path) if settings.hpc_file_path else None
    result = run_audit(
        billing_files=billing_files,
        when_i_work_base_url=settings.when_i_work_base_url,
        when_i_work_api_token=settings.when_i_work_api_token,
        when_i_work_api_key=settings.when_i_work_api_key,
        when_i_work_email=settings.when_i_work_email,
        when_i_work_password=settings.when_i_work_password,
        when_i_work_user_id=settings.when_i_work_user_id,
        jotform_base_url=settings.jotform_base_url,
        jotform_api_key=settings.jotform_api_key,
        jotform_form_id=settings.jotform_form_id,
        start_date=normalize_date(args.start_date),
        end_date=normalize_date(args.end_date),
        timeout_seconds=settings.timeout_seconds,
        hpc_file_path=hpc_path,
        jotform_auto_discover=settings.jotform_auto_discover,
        billable_only=settings.audit_billable_only,
        paper_notes_exempt_clients=set(),
    )
    output_dir = Path(args.output_dir or settings.audit_output_dir)
    write_exports(result=result, output_dir=output_dir)
    print(f"Audit complete. Exported files to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()

