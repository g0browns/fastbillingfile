from pathlib import Path

from audit_engine.parsers.billing_parser import parse_billing_files


def test_parse_billing_file_extracts_client_day_and_service_codes(tmp_path: Path):
    fixture = tmp_path / "billing.TXT"
    fixture.write_text(
        "\n".join(
            [
                "SIMPSON, BETHANY             106391999599   02/10/2025   ATN      1       1     MEDINA",
                "SIMPSON, BETHANY             106391999599   02/10/2025   APC      1       1     MEDINA",
                "COHN, MARTIN                 105973135499   03/12/2025   APC      1       1     SUMMIT",
            ]
        ),
        encoding="utf-8",
    )

    billing_map, issues = parse_billing_files([fixture])
    assert not issues
    assert len(billing_map) == 2

    keys = sorted((k.client, k.service_date.isoformat()) for k in billing_map.keys())
    assert keys == [("bethany simpson", "2025-02-10"), ("martin cohn", "2025-03-12")]

    bethany_key = next(key for key in billing_map if key.client == "bethany simpson")
    assert billing_map[bethany_key].service_codes == {"ATN", "APC"}

