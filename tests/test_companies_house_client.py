# tests/test_companies_house_client.py
from __future__ import annotations  # noqa: E402

import os  # noqa: E402
import pytest  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

# Ensure the client can initialize without relying on a real API key in the environment
os.environ.setdefault("CH_API_KEY", "test-api-key")

from app.services.companies_house import (  # noqa: E402
    CompaniesHouseClient,
    CompaniesHouseError,
)  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        reason: str = "OK",
        text: str = "",
    ):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.reason = reason
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        # for non-2xx codes, requests would raise HTTPError
        if 400 <= self.status_code:
            import requests  # noqa: E402

            raise requests.HTTPError(f"{self.status_code} {self.reason}")


class FakeSession:
    """
    A very small test double for requests.Session, returning a sequence of FakeResponse objects.
    """

    def __init__(self, responses: List[FakeResponse]):
        self._responses = list(responses)
        self.headers: Dict[str, str] = {}
        self.auth = None
        self.calls: List[Dict[str, Any]] = []

    def get(self, url: str, params: Dict[str, Any], timeout: float):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if not self._responses:
            # default to 200 empty
            return FakeResponse(200, {"ok": True})
        return self._responses.pop(0)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """
    Keep env noise out of tests; set predictable defaults.
    """
    monkeypatch.setenv("CH_TIMEOUT", "0.1")  # keep short timeouts in tests
    # disable per-key throttle by default (override in specific test)
    monkeypatch.delenv("CH_MIN_REQUEST_INTERVAL", raising=False)
    monkeypatch.delenv("CH_BASE_URL", raising=False)
    monkeypatch.delenv("CH_USER_AGENT", raising=False)


def test_401_unauthorized_is_not_retried(monkeypatch):
    session = FakeSession(
        [FakeResponse(401, {"error": "Invalid API key"}, reason="Unauthorized")]
    )
    cli = CompaniesHouseClient(session=session, retry=3, backoff=0.01)

    with pytest.raises(CompaniesHouseError) as ei:
        cli.get_company_profile("00000000")

    # One call only, no retries on 401
    assert len(session.calls) == 1
    assert "401 Unauthorized" in str(ei.value) or "401" in str(ei.value)


def test_429_retry_after_is_honored(monkeypatch):
    # First response 429 with Retry-After: 0.01; then 200 OK
    session = FakeSession(
        [
            FakeResponse(
                429,
                {"error": "rate limited"},
                headers={"Retry-After": "0.01"},
                reason="Too Many Requests",
            ),
            FakeResponse(200, {"items": [], "total_results": 0}),
        ]
    )

    # Make time.sleep a no-op to speed up tests, but record calls
    sleeps: List[float] = []

    def fake_sleep(x: float):
        sleeps.append(x)

    monkeypatch.setattr("time.sleep", fake_sleep)

    cli = CompaniesHouseClient(session=session, retry=2, backoff=0.01)
    out = cli.search_companies("Acme", items_per_page=10, start_index=0)

    assert out["items"] == []
    assert len(session.calls) == 2
    # We should have slept at least once due to 429
    assert sleeps, "Expected a sleep due to 429 handling"


def test_500_then_success_with_retry(monkeypatch):
    # Simulate transient server error (500) then success
    session = FakeSession(
        [
            FakeResponse(
                500, {"error": "server error"}, reason="Internal Server Error"
            ),
            FakeResponse(200, {"items": [{"foo": "bar"}], "total_results": 1}),
        ]
    )
    sleeps: List[float] = []

    def fake_sleep(x: float):
        sleeps.append(x)

    monkeypatch.setattr("time.sleep", fake_sleep)

    cli = CompaniesHouseClient(session=session, retry=1, backoff=0.01)
    out = cli.get_company_officers(
        "00000000", items_per_page=1, start_index=0, max_items=1
    )

    assert out["items"] == [{"foo": "bar"}]
    # one retry -> two total calls
    assert len(session.calls) == 2
    assert sleeps, "Expected at least one backoff sleep for 5xx"


def test_400_bad_request_no_retry(monkeypatch):
    # 400 should not be retried and should provide a helpful message
    session = FakeSession(  # e.g., invalid query params
        [FakeResponse(400, {"error": "invalid parameter"}, reason="Bad Request")]
    )
    cli = CompaniesHouseClient(session=session, retry=3, backoff=0.01)

    with pytest.raises(CompaniesHouseError) as ei:
        cli.search_companies("")

    assert len(session.calls) == 1
    msg = str(ei.value)
    assert "400" in msg and "Bad Request" in msg


def test_min_request_interval_throttle(monkeypatch):
    # Force a minimum interval; we will make two calls and ensure sleep is invoked
    session = FakeSession(
        [FakeResponse(200, {"ok": True}), FakeResponse(200, {"ok": True})]
    )

    # Capture sleep durations
    sleeps: List[float] = []

    def fake_sleep(x: float):
        sleeps.append(x)

    # Make monotonic start at 100.0 and increment by 0.05 between calls
    times = [100.0, 100.05]

    def fake_monotonic():
        return times.pop(0) if times else 100.05

    monkeypatch.setenv("CH_MIN_REQUEST_INTERVAL", "0.25")
    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("time.monotonic", fake_monotonic)

    cli = CompaniesHouseClient(session=session, retry=0, backoff=0.01)
    # two simple GETs
    cli.get_company_profile("00000000")
    cli.get_company_profile("00000001")

    # We should have slept at least (0.25 - 0.05) = 0.20 seconds once
    assert sleeps, "Expected a sleep due to min request interval"
    assert sleeps[0] == pytest.approx(0.20, abs=0.02)
    assert len(session.calls) == 2


def test_pager_stops_on_total_results(monkeypatch):
    # Two pages: first has 2 items, total_results=3; second has 1 item.
    session = FakeSession(
        [
            FakeResponse(200, {"items": [{"i": 1}, {"i": 2}], "total_results": 3}),
            FakeResponse(200, {"items": [{"i": 3}], "total_results": 3}),
        ]
    )
    cli = CompaniesHouseClient(session=session, retry=0, backoff=0.01)
    out = cli.get_company_filing_history("00000000", items_per_page=2, start_index=0)

    assert [x["i"] for x in out["items"]] == [1, 2, 3]
    assert out["total_results"] == 3
    assert len(session.calls) == 2  # stopped after reaching total_results


def test_invalid_json_raises_friendly_error(monkeypatch):
    class BadJSONResponse(FakeResponse):
        def json(self):
            raise ValueError("not json")

    session = FakeSession([BadJSONResponse(200, {})])
    cli = CompaniesHouseClient(session=session, retry=0, backoff=0.01)

    with pytest.raises(CompaniesHouseError) as ei:
        cli.get_company_registers("00000000")

    assert "Invalid JSON" in str(ei.value)
