from audit_engine.connectors.when_i_work import _resolve_access_token, fetch_schedule_map


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


def test_schedule_map_uses_user_lookup_for_client_name(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/users"):
            return _FakeResponse(
                {"users": [{"id": 101, "first_name": "Bethany", "last_name": "Simpson", "phone": "614-555-0101"}]}
            )
        if url.endswith("/sites"):
            return _FakeResponse({"sites": [{"id": 88, "name": "Bethany Simpson"}]})
        if url.endswith("/positions"):
            return _FakeResponse({"positions": [{"id": 22, "name": "Residential Staff"}]})
        if url.endswith("/times"):
            return _FakeResponse({"times": []})
        if url.endswith("/locations"):
            return _FakeResponse({"locations": [{"id": 55, "name": "Fallback Location"}]})
        if url.endswith("/shifts"):
            return _FakeResponse(
                {
                    "shifts": [
                        {
                            "id": 777,
                            "user_id": 101,
                            "site_id": 88,
                            "position_id": 22,
                            "location_id": 55,
                            "start_time": "Mon, 10 Feb 2025 08:00:00 -0500",
                        }
                    ]
                }
            )
        raise AssertionError("unexpected url")

    monkeypatch.setattr("audit_engine.connectors.when_i_work.requests.get", fake_get)
    schedule_map, issues = fetch_schedule_map(
        base_url="https://api.wheniwork.com/2",
        api_token="token",
        api_key="",
        login_email="",
        login_password="",
        user_id="",
        start_date=__import__("datetime").date(2025, 2, 10),
        end_date=__import__("datetime").date(2025, 2, 10),
        timeout_seconds=30,
    )
    assert not issues
    assert len(schedule_map) == 1
    key = next(iter(schedule_map.keys()))
    assert key.client == "bethany simpson"
    assert schedule_map[key].shift_count == 1
    assert schedule_map[key].shifts[0].staff_phone == "614-555-0101"


def test_schedule_excludes_non_client_site_labels(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/users"):
            return _FakeResponse({"users": [{"id": 301, "first_name": "Mary", "last_name": "Hankins"}]})
        if url.endswith("/sites"):
            return _FakeResponse({"sites": [{"id": 901, "name": "Admin Office"}]})
        if url.endswith("/positions"):
            return _FakeResponse({"positions": [{"id": 12, "name": "Management"}]})
        if url.endswith("/locations"):
            return _FakeResponse({"locations": [{"id": 22, "name": "Meadowbrook"}]})
        if url.endswith("/times"):
            return _FakeResponse({"times": []})
        if url.endswith("/shifts"):
            return _FakeResponse(
                {
                    "shifts": [
                        {
                            "id": 55,
                            "user_id": 301,
                            "site_id": 901,
                            "position_id": 12,
                            "location_id": 22,
                            "start_time": "Mon, 27 Jan 2025 08:00:00 -0500",
                        }
                    ]
                }
            )
        raise AssertionError("unexpected url")

    monkeypatch.setattr("audit_engine.connectors.when_i_work.requests.get", fake_get)
    schedule_map, issues = fetch_schedule_map(
        base_url="https://api.wheniwork.com/2",
        api_token="token",
        api_key="",
        login_email="",
        login_password="",
        user_id="",
        start_date=__import__("datetime").date(2025, 1, 27),
        end_date=__import__("datetime").date(2025, 1, 27),
        timeout_seconds=30,
    )
    assert schedule_map == {}
    assert any(issue.issue_type == "non_client_site_excluded" for issue in issues)


def test_resolve_access_token_from_login(monkeypatch):
    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"token": "jwt-token-value"}

        @staticmethod
        def raise_for_status():
            return None

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["json"] = json or {}
        return _Resp()

    monkeypatch.setattr("audit_engine.connectors.when_i_work.requests.post", fake_post)
    token = _resolve_access_token(
        api_token="",
        api_key="dev-key",
        login_email="user@example.com",
        login_password="pw",
        timeout_seconds=30,
    )
    assert token == "jwt-token-value"
    assert captured["url"].endswith("/login")
    assert captured["headers"].get("W-Key") == "dev-key"

