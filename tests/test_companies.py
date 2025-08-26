# tests/test_companies.py
import os
import importlib
import uuid
import pytest
from fastapi.testclient import TestClient

RUN_DB = os.getenv("RUN_DB_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_DB, reason="DB tests disabled. Set RUN_DB_TESTS=1 to enable."
)


def _seed_env(monkeypatch):
    # Copy current process env (you exported these in PowerShell) explicitly into the app's env
    monkeypatch.setenv("POSTGRES_USER", os.getenv("POSTGRES_USER", "postgres"))
    monkeypatch.setenv("POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
    monkeypatch.setenv("POSTGRES_DB", os.getenv("POSTGRES_DB", "detecktiv"))
    monkeypatch.setenv("POSTGRES_HOST", os.getenv("POSTGRES_HOST", "127.0.0.1"))
    monkeypatch.setenv("POSTGRES_PORT", os.getenv("POSTGRES_PORT", "5432"))


def _client(monkeypatch):
    _seed_env(monkeypatch)
    import app.main as main

    importlib.reload(main)
    return TestClient(main.app)


def test_create_and_get_company(monkeypatch):
    client = _client(monkeypatch)

    # Warm-up: check DB health so we fail fast with useful info if env is still wrong
    h = client.get("/health/db")
    assert h.status_code == 200, h.text
    body = h.json()
    assert body.get("db_status") == "ok", f"DB not reachable: {body}"

    # Create
    r = client.post(
        "/companies", json={"name": "Acme Ltd", "website": "https://acme.example"}
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert isinstance(data["id"], int)
    cid = data["id"]
    assert data["name"] == "Acme Ltd"
    assert data["website"] == "https://acme.example"

    # Fetch
    r2 = client.get(f"/companies/{cid}")
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["id"] == cid
    assert data2["name"] == "Acme Ltd"


def test_duplicate_company_conflict(monkeypatch):
    client = _client(monkeypatch)

    base = "Acme-" + uuid.uuid4().hex[:8]
    # create first
    r1 = client.post(
        "/companies", json={"name": base, "website": "https://one.example"}
    )
    assert r1.status_code == 201, r1.text

    # duplicate name -> 409
    r2 = client.post(
        "/companies", json={"name": base, "website": "https://two.example"}
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"] == "company name already exists"


def test_list_companies(monkeypatch):
    client = _client(monkeypatch)

    # create a couple unique companies
    n1 = "Co-" + uuid.uuid4().hex[:6]
    n2 = "Co-" + uuid.uuid4().hex[:6]
    for nm in (n1, n2):
        r = client.post("/companies", json={"name": nm, "website": None})
        assert r.status_code == 201, r.text

    # list
    rlist = client.get("/companies?limit=10&offset=0")
    assert rlist.status_code == 200, rlist.text
    items = rlist.json()
    names = {i["name"] for i in items}
    assert n1 in names and n2 in names
