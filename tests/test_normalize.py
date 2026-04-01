from audit_engine.normalize import normalize_date, normalize_name


def test_normalize_name_last_first():
    assert normalize_name("SIMPSON, BETHANY") == "bethany simpson"


def test_normalize_name_trim_and_commas():
    assert normalize_name("  Bethany,   Simpson  ") == "simpson bethany"


def test_normalize_date_slash_format():
    assert normalize_date("02/10/2025").isoformat() == "2025-02-10"


def test_normalize_date_iso_format():
    assert normalize_date("2025-03-12T09:30:00").isoformat() == "2025-03-12"

