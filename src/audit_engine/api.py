from __future__ import annotations

import os
import secrets
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from audit_engine.config import load_settings
from audit_engine.engine import run_audit
from audit_engine.models import AuditResult
from audit_engine.normalize import normalize_date, normalize_name
from audit_engine.reporting import build_shift_note_audit_csv_bytes, build_shift_note_audit_pdf_bytes


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"

security = HTTPBasic()

APP_USERNAME = os.getenv("APP_USERNAME", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    if not APP_USERNAME or not APP_PASSWORD:
        raise HTTPException(status_code=500, detail="APP_USERNAME / APP_PASSWORD not configured")
    username_ok = secrets.compare_digest(credentials.username.encode(), APP_USERNAME.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), APP_PASSWORD.encode())
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


app = FastAPI(title="Meadowbrook Audit API", version="0.1.0", dependencies=[Depends(verify_credentials)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:8001", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/audit")
def audit(
    billing_dir: str = Query(..., description="Directory containing billing TXT files"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
) -> dict[str, object]:
    settings = load_settings()
    files = sorted(Path(billing_dir).glob("**/*.TXT"))
    if not files:
        return {"error": f"no billing files found in {billing_dir}"}

    result = _run_with_settings(settings, files, start_date, end_date)
    return _result_payload(result)


@app.post("/audit/upload")
async def audit_upload(
    start_date: str = Form(..., description="YYYY-MM-DD"),
    end_date: str = Form(..., description="YYYY-MM-DD"),
    billing_file: UploadFile = File(..., description="Billing TXT file"),
    paper_notes_clients: str = Form("", description="Comma/newline separated client names excluded from Jotform requirement"),
) -> dict[str, object]:
    result = await _run_audit_upload_request(start_date, end_date, billing_file, paper_notes_clients)
    return _result_payload(result)


@app.post("/reports/shift-note/pdf")
async def download_shift_note_pdf(
    start_date: str = Form(..., description="YYYY-MM-DD"),
    end_date: str = Form(..., description="YYYY-MM-DD"),
    billing_file: UploadFile = File(..., description="Billing TXT file"),
    paper_notes_clients: str = Form("", description="Comma/newline separated client names excluded from Jotform requirement"),
) -> Response:
    result = await _run_audit_upload_request(start_date, end_date, billing_file, paper_notes_clients)
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    pdf_bytes = build_shift_note_audit_pdf_bytes(result.audit_rows, start, end)
    filename = f"shift_note_audit_{start.isoformat()}_{end.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/reports/shift-note/csv")
async def download_shift_note_csv(
    start_date: str = Form(..., description="YYYY-MM-DD"),
    end_date: str = Form(..., description="YYYY-MM-DD"),
    billing_file: UploadFile = File(..., description="Billing TXT file"),
    paper_notes_clients: str = Form("", description="Comma/newline separated client names excluded from Jotform requirement"),
) -> Response:
    result = await _run_audit_upload_request(start_date, end_date, billing_file, paper_notes_clients)
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    csv_bytes = build_shift_note_audit_csv_bytes(result.audit_rows, start, end)
    filename = f"shift_note_audit_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_paper_notes_clients(raw_value: str) -> set[str]:
    if not raw_value:
        return set()
    normalized: set[str] = set()
    text = raw_value.replace(";", ",")
    for part in text.replace("\r", "\n").split("\n"):
        for token in part.split(","):
            name = normalize_name(token)
            if name:
                normalized.add(name)
    return normalized


async def _run_audit_upload_request(
    start_date: str,
    end_date: str,
    billing_file: UploadFile,
    paper_notes_clients: str,
) -> AuditResult:
    if not billing_file.filename:
        raise HTTPException(status_code=400, detail="billing_file is required")
    file_name = billing_file.filename.lower()
    if not file_name.endswith(".txt"):
        raise HTTPException(status_code=400, detail="billing_file must be a .TXT file")

    settings = load_settings()
    file_bytes = await billing_file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="billing_file is empty")

    with NamedTemporaryFile(delete=False, suffix=".TXT") as handle:
        handle.write(file_bytes)
        temp_path = Path(handle.name)

    try:
        return _run_with_settings(
            settings,
            [temp_path],
            start_date,
            end_date,
            paper_notes_clients=_parse_paper_notes_clients(paper_notes_clients),
        )
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _run_with_settings(settings, billing_files, start_date, end_date, paper_notes_clients: set[str] | None = None):
    hpc_path = Path(settings.hpc_file_path) if settings.hpc_file_path else None
    return run_audit(
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
        start_date=normalize_date(start_date),
        end_date=normalize_date(end_date),
        timeout_seconds=settings.timeout_seconds,
        hpc_file_path=hpc_path,
        jotform_auto_discover=settings.jotform_auto_discover,
        billable_only=settings.audit_billable_only,
        paper_notes_exempt_clients=paper_notes_clients or set(),
    )


def _result_payload(result: AuditResult) -> dict[str, object]:
    # Keep response shape stable for frontend rendering.
    return {
        "summary": asdict(result.summary),
        "status_breakdown": result.status_breakdown,
        "audit_rows": [
            {
                "client": row.client,
                "date": row.service_date.isoformat(),
                "billed": row.billed,
                "scheduled": row.scheduled,
                "shift_notes_present": row.shift_notes_present,
                "scheduled_shift_count": row.scheduled_shift_count,
                "shift_note_count": row.shift_note_count,
                "missing_shift_notes": row.missing_shift_notes,
                "billing_service_codes": row.billing_service_codes,
                "status": row.status.value,
                "exception_reason": row.exception_reason,
                "medicaid_id": row.medicaid_id,
                "billing_units": row.billing_units,
                "billing_rate": row.billing_rate,
                "staff_on_note": row.staff_on_note,
                "staff_on_schedule": row.staff_on_schedule,
                "staff_phone_number": row.staff_phone_number,
                "staff_match": row.staff_match,
                "service_code_on_note": row.service_code_on_note,
                "service_code_match": row.service_code_match,
                "units_on_note": row.units_on_note,
                "units_match": row.units_match,
                "note_has_signature": row.note_has_signature,
                "note_has_narrative": row.note_has_narrative,
                "evv_clock_in": row.evv_clock_in,
                "evv_clock_out": row.evv_clock_out,
                "evv_hours": row.evv_hours,
                "time_match": row.time_match,
                "findings": row.findings,
                "paper_notes_exempt": row.paper_notes_exempt,
            }
            for row in result.audit_rows
        ],
        "exceptions": [
            {
                "client": row.client,
                "date": row.service_date.isoformat(),
                "status": row.status.value,
                "reason": row.exception_reason,
            }
            for row in result.exception_rows
        ],
        "matching_issues": [
            {
                "issue_type": issue.issue_type,
                "source": issue.source,
                "raw_client": issue.raw_client,
                "raw_date": issue.raw_date,
                "reason": issue.reason,
                "normalized_client": issue.normalized_client,
                "normalized_date": issue.normalized_date.isoformat() if issue.normalized_date else None,
            }
            for issue in result.matching_issues
        ],
        "notes_diagnostics": asdict(result.notes_diagnostics),
        "assumptions": result.assumptions,
    }

