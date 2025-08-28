from __future__ import annotations

"""
Purpose:
- Ensure the FastAPI app imports cleanly (no missing routers/import errors).
- Verify the root and /health endpoints respond without needing DB or CH_API_KEY.
- This would have caught the earlier "cannot import name 'router' from app.api.companies_house".
"""

import os
from fastapi.testclient import TestClient

# Make sure DB-dependent behavior stays off for this test
os.environ.pop("RUN_DB_TESTS", None)


def test_app_import_and_basic_routes():
    # Import after env adjustments
    import app.main as main  # noqa: WPS433

    client = TestClient(main.app)

    # Root
    r = client.get("/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("name") == "detecktiv-io API"
    assert "/health" in body.get("health", "/health")

    # Health (no DB required)
    r2 = client.get("/health")
    assert r2.status_code == 200
    assert r2.json() == {"status": "ok"}

    # Minimal sanity: OpenAPI schema should load
    r3 = client.get("/openapi.json")
    assert r3.status_code == 200
    spec = r3.json()
    assert spec.get("openapi", "").startswith("3.")
    # Routers advertised in "/" should actually appear in the spec paths
    paths = spec.get("paths", {})
    assert isinstance(paths, dict)

    # --- Additions: extra safety checks that don't require DB or CH_API_KEY ---

    # 1) Security headers are applied by middleware on a trivial request
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    # request-id middleware should always return a header
    assert r.headers.get("x-request-id")

    # 2) Companies House router should be present in the OpenAPI (no call made)
    # We don't hit CH endpoints (no API key), we just check the spec contains their paths.
    has_ch_prefix = any(p.startswith("/companies-house") for p in paths.keys())
    assert has_ch_prefix, "Companies House routes missing from OpenAPI spec"

    # 3) Companies router should be present in the OpenAPI as well
    has_companies = any(
        p == "/companies" or p.startswith("/companies/") for p in paths.keys()
    )
    assert has_companies, "Companies routes missing from OpenAPI spec"
