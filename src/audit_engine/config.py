from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    when_i_work_api_token: str
    when_i_work_api_key: str
    when_i_work_email: str
    when_i_work_password: str
    when_i_work_base_url: str
    when_i_work_user_id: str
    jotform_api_key: str
    jotform_base_url: str
    jotform_form_id: str
    jotform_auto_discover: bool
    hpc_file_path: str
    audit_output_dir: str
    audit_timezone: str
    timeout_seconds: int
    audit_billable_only: bool


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> str:
    return os.getenv(name, "").strip()


def load_settings() -> Settings:
    when_i_work_api_token = _optional_env("WHEN_I_WORK_API_TOKEN")
    when_i_work_api_key = _optional_env("WHEN_I_WORK_API_KEY")
    when_i_work_email = _optional_env("WHEN_I_WORK_EMAIL")
    when_i_work_password = _optional_env("WHEN_I_WORK_PASSWORD")

    has_token_mode = bool(when_i_work_api_token)
    has_login_mode = bool(when_i_work_email and when_i_work_password)
    if not has_token_mode and not has_login_mode:
        raise RuntimeError(
            "missing When I Work credentials: set WHEN_I_WORK_API_TOKEN or WHEN_I_WORK_EMAIL + WHEN_I_WORK_PASSWORD"
        )

    return Settings(
        when_i_work_api_token=when_i_work_api_token,
        when_i_work_api_key=when_i_work_api_key,
        when_i_work_email=when_i_work_email,
        when_i_work_password=when_i_work_password,
        when_i_work_base_url=_optional_env("WHEN_I_WORK_BASE_URL") or "https://api.wheniwork.com/2",
        when_i_work_user_id=_optional_env("WHEN_I_WORK_USER_ID"),
        jotform_api_key=_required_env("JOTFORM_API_KEY"),
        jotform_base_url=_optional_env("JOTFORM_BASE_URL") or "https://hipaa-api.jotform.com",
        jotform_form_id=_optional_env("JOTFORM_FORM_ID"),
        jotform_auto_discover=_optional_env("JOTFORM_AUTO_DISCOVER") != "false",
        hpc_file_path=_optional_env("HPC_FILE_PATH") or "billingfiles/HPC.txt",
        audit_output_dir=_optional_env("AUDIT_OUTPUT_DIR") or "output",
        audit_timezone=_optional_env("AUDIT_TIMEZONE") or "UTC",
        timeout_seconds=int(os.getenv("AUDIT_REQUEST_TIMEOUT_SECONDS", "30")),
        audit_billable_only=_optional_env("AUDIT_BILLABLE_ONLY") != "false",
    )

