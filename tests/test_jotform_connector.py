import asyncio
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


class _FakeAsyncClient:
    """Mock httpx.AsyncClient that delegates to a callback."""

    def __init__(self, get_fn=None, post_fn=None):
        self._get_fn = get_fn
        self._post_fn = post_fn

    async def get(self, url, **kwargs):
        return self._get_fn(url, **kwargs)

    async def post(self, url, **kwargs):
        return self._post_fn(url, **kwargs)


def test_jotform_paginates_and_parses_content():
    calls = {"count": 0}

    def fake_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(
                {
                    "content": [
                        {
                            "id": "n1",
                            "created_at": "2025-02-15 09:00:00",
                            "answers": {
                                "1": {"name": "clientName", "text": "Client Name", "answer": "SIMPSON, BETHANY"},
                                "3": {"name": "sessionDate", "text": "Service Date", "answer": {"month": "02", "day": "10", "year": "2025"}},
                            },
                        }
                    ]
                }
            )
        return _FakeResponse({"content": []})

    client = _FakeAsyncClient(get_fn=fake_get)
    notes_map, issues, diagnostics = asyncio.run(
        fetch_notes_map(
            client=client,
            base_url="https://api.jotform.com",
            api_key="key",
            form_id="",
            start_date=date(2025, 2, 10),
            end_date=date(2025, 2, 10),
            timeout_seconds=30,
            auto_discover=False,
        )
    )
    assert not issues
    assert len(notes_map) == 1
    key = next(iter(notes_map.keys()))
    assert key.client == "bethany simpson"
    assert key.service_date.isoformat() == "2025-02-10"
    assert notes_map[key].note_count == 1
    assert diagnostics.missing_client_count == 0
    assert diagnostics.missing_service_date_count == 0


def test_jotform_missing_service_date_is_flagged():
    def fake_get(url, **kwargs):
        return _FakeResponse({"content": [{"id": "n1", "answers": {"1": {"name": "clientName", "text": "Client Name", "answer": "SIMPSON, BETHANY"}}}]})

    client = _FakeAsyncClient(get_fn=fake_get)
    notes_map, issues, diagnostics = asyncio.run(
        fetch_notes_map(
            client=client,
            base_url="https://api.jotform.com",
            api_key="key",
            form_id="",
            start_date=date(2025, 2, 10),
            end_date=date(2025, 2, 10),
            timeout_seconds=30,
            auto_discover=False,
        )
    )
    assert len(notes_map) == 0
    assert len(issues) == 1
    assert issues[0].issue_type == "missing_required_fields"
    assert diagnostics.missing_service_date_count == 1


def test_jotform_session_date_is_accepted_as_service_date():
    calls = {"count": 0}

    def fake_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(
                {
                    "content": [
                        {
                            "id": "n2",
                            "answers": {
                                "1": {"name": "clientName", "text": "Client Name", "answer": "Emanuele, Patricia"},
                                "73": {"name": "sessionDate", "text": "Session Date:", "answer": {"month": "03", "day": "12", "year": "2025"}},
                            },
                        }
                    ]
                }
            )
        return _FakeResponse({"content": []})

    client = _FakeAsyncClient(get_fn=fake_get)
    notes_map, issues, diagnostics = asyncio.run(
        fetch_notes_map(
            client=client,
            base_url="https://api.jotform.com",
            api_key="key",
            form_id="",
            start_date=date(2025, 3, 12),
            end_date=date(2025, 3, 12),
            timeout_seconds=30,
            auto_discover=False,
        )
    )
    assert not issues
    assert len(notes_map) == 1
    key = next(iter(notes_map.keys()))
    assert key.client == "patricia emanuele"
    assert key.service_date.isoformat() == "2025-03-12"
    assert diagnostics.missing_service_date_count == 0


def test_jotform_diagnostic_sample_cap():
    def fake_get(url, **kwargs):
        items = [{"id": str(i), "answers": {"1": {"name": "clientName", "text": "Client Name", "answer": "Sample User"}}} for i in range(25)]
        return _FakeResponse({"content": items})

    client = _FakeAsyncClient(get_fn=fake_get)
    notes_map, issues, diagnostics = asyncio.run(
        fetch_notes_map(
            client=client,
            base_url="https://api.jotform.com",
            api_key="key",
            form_id="",
            start_date=date(2025, 2, 10),
            end_date=date(2025, 2, 10),
            timeout_seconds=30,
            auto_discover=False,
        )
    )
    assert len(notes_map) == 0
    assert diagnostics.missing_service_date_count == 25
    assert len(diagnostics.missing_service_date_samples) == diagnostics.sample_limit
    assert len(issues) == 25


def test_jotform_invalid_and_out_of_range_diagnostics():
    calls = {"count": 0}

    def fake_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(
                {
                    "content": [
                        {
                            "id": "bad-date",
                            "answers": {
                                "1": {"name": "clientName", "text": "Client Name", "answer": "SIMPSON, BETHANY"},
                                "73": {"name": "sessionDate", "text": "Session Date:", "answer": "not-a-date"},
                            },
                        },
                        {
                            "id": "out-range",
                            "answers": {
                                "1": {"name": "clientName", "text": "Client Name", "answer": "SIMPSON, BETHANY"},
                                "73": {"name": "sessionDate", "text": "Session Date:", "answer": {"month": "01", "day": "10", "year": "2025"}},
                            },
                        },
                    ]
                }
            )
        return _FakeResponse({"content": []})

    client = _FakeAsyncClient(get_fn=fake_get)
    notes_map, issues, diagnostics = asyncio.run(
        fetch_notes_map(
            client=client,
            base_url="https://api.jotform.com",
            api_key="key",
            form_id="",
            start_date=date(2025, 2, 10),
            end_date=date(2025, 2, 10),
            timeout_seconds=30,
            auto_discover=False,
        )
    )
    assert len(notes_map) == 0
    assert diagnostics.invalid_service_date_count == 1
    assert diagnostics.out_of_range_service_date_count == 1
    assert len(diagnostics.invalid_service_date_samples) == 1
    assert len(diagnostics.out_of_range_service_date_samples) == 1
    assert any(issue.issue_type == "date_parse_error" for issue in issues)
