# tests/test_companies_house_api.py
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("CH_API_KEY") and not os.getenv("COMPANIES_HOUSE_API_KEY"),
    reason="CH_API_KEY not set; skipping Companies House tests",
)

# To avoid calling live API during normal runs, require opt-in
pytestmark2 = pytest.mark.skipif(
    os.getenv("RUN_CH_INTEGRATION_TESTS") != "1",
    reason="Set RUN_CH_INTEGRATION_TESTS=1 to run live CH API tests",
)

from main import app  # noqa: E402

client = TestClient(app)


@pytestmark2
def test_basic_search():
    r = client.get("/companies-house/companies/search", params={"q": "Acme"})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body or "total_results" in body


@pytestmark2
def test_company_profile_minimal():
    # A known public test entity; replace as needed
    r = client.get("/companies-house/company/00000006")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
