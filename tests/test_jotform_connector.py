from datetime import date

from audit_engine.connectors.jotform import fetch_notes_map


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


def test_jotform_paginates_and_parses_content(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(
                {
                    "content": [
                        {
                            "id": "n1",
                            "created_at": "2025-02-15 09:00:00",
                            "client_name": "SIMPSON, BETHANY",
                            "answers": {
                                "3": {"text": "Service Date", "answer": {"month": "02", "day": "10", "year": "2025"}}
                            },
                        }
                    ]
                }
            )
        return _FakeResponse({"content": []})

    monkeypatch.setattr("audit_engine.connectors.jotform.requests.get", fake_get)
    notes_map, issues, diagnostics = fetch_notes_map(
        base_url="https://api.jotform.com",
        api_key="key",
        form_id="",
        start_date=date(2025, 2, 10),
        end_date=date(2025, 2, 10),
        timeout_seconds=30,
    )
    assert not issues
    assert len(notes_map) == 1
    key = next(iter(notes_map.keys()))
    assert key.client == "bethany simpson"
    assert key.service_date.isoformat() == "2025-02-10"
    assert notes_map[key].note_count == 1
    assert diagnostics.missing_client_count == 0
    assert diagnostics.missing_service_date_count == 0


def test_jotform_missing_service_date_is_flagged(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse({"content": [{"id": "n1", "client_name": "SIMPSON, BETHANY"}]})

    monkeypatch.setattr("audit_engine.connectors.jotform.requests.get", fake_get)
    notes_map, issues, diagnostics = fetch_notes_map(
        base_url="https://api.jotform.com",
        api_key="key",
        form_id="",
        start_date=date(2025, 2, 10),
        end_date=date(2025, 2, 10),
        timeout_seconds=30,
    )
    assert len(notes_map) == 0
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_required_fields"
    assert diagnostics.missing_service_date_count == 1


def test_jotform_session_date_is_accepted_as_service_date(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(
                {
                    "content": [
                        {
                            "id": "n2",
                            "client_name": "Emanuele, Patricia",
                            "answers": {
                                "73": {"text": "Session Date:", "answer": {"month": "03", "day": "12", "year": "2025"}}
                            },
                        }
                    ]
                }
            )
        return _FakeResponse({"content": []})

    monkeypatch.setattr("audit_engine.connectors.jotform.requests.get", fake_get)
    notes_map, issues, diagnostics = fetch_notes_map(
        base_url="https://api.jotform.com",
        api_key="key",
        form_id="",
        start_date=date(2025, 3, 12),
        end_date=date(2025, 3, 12),
        timeout_seconds=30,
    )
    assert not issues
    assert len(notes_map) == 1
    key = next(iter(notes_map.keys()))
    assert key.client == "patricia emanuele"
    assert key.service_date.isoformat() == "2025-03-12"
    assert diagnostics.missing_service_date_count == 0


def test_jotform_diagnostic_sample_cap(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        items = [{"id": str(i), "client_name": "Sample User"} for i in range(25)]
        return _FakeResponse({"content": items})

    monkeypatch.setattr("audit_engine.connectors.jotform.requests.get", fake_get)
    notes_map, issues, diagnostics = fetch_notes_map(
        base_url="https://api.jotform.com",
        api_key="key",
        form_id="",
        start_date=date(2025, 2, 10),
        end_date=date(2025, 2, 10),
        timeout_seconds=30,
    )
    assert len(notes_map) == 0
    assert diagnostics.missing_service_date_count == 25
    assert len(diagnostics.missing_service_date_samples) == diagnostics.sample_limit
    assert len(issues) == 25


def test_jotform_invalid_and_out_of_range_diagnostics(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(
                {
                    "content": [
                        {
                            "id": "bad-date",
                            "client_name": "SIMPSON, BETHANY",
                            "answers": {"73": {"text": "Session Date:", "answer": "not-a-date"}},
                        },
                        {
                            "id": "out-range",
                            "client_name": "SIMPSON, BETHANY",
                            "answers": {"73": {"text": "Session Date:", "answer": {"month": "01", "day": "10", "year": "2025"}}},
                        },
                    ]
                }
            )
        return _FakeResponse({"content": []})

    monkeypatch.setattr("audit_engine.connectors.jotform.requests.get", fake_get)
    notes_map, issues, diagnostics = fetch_notes_map(
        base_url="https://api.jotform.com",
        api_key="key",
        form_id="",
        start_date=date(2025, 2, 10),
        end_date=date(2025, 2, 10),
        timeout_seconds=30,
    )
    assert len(notes_map) == 0
    assert diagnostics.invalid_service_date_count == 1
    assert diagnostics.out_of_range_service_date_count == 1
    assert len(diagnostics.invalid_service_date_samples) == 1
    assert len(diagnostics.out_of_range_service_date_samples) == 1
    assert any(issue.issue_type == "date_parse_error" for issue in issues)

