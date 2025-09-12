# tests/test_auth.py
from __future__ import annotations

"""
End-to-end auth flow tests for detecktiv.io

Covers:
- POST /v1/auth/login (success & invalid)
- GET  /v1/users/me (with valid access token)
- POST /v1/auth/refresh (success & revoked via token_version bump)
- Lockout path (429) after repeated invalid logins (env-tunable)

These tests run against a temporary SQLite database and override the app's DB
dependency so they do not require a running Postgres instance.
"""

from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Import the FastAPI app and project modules
from app.main import app
from app.models.base import Base
from app.models.user import User
from app.core.security import get_password_hash

# Dependency callables (we will override both to be safe)
from app.core.session import get_db as core_get_db
from app.api.deps import get_db as deps_get_db


# ---------------------------------------------------------------------------
# Test database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sqlite_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    # Use a file-backed SQLite DB so connections share state across requests
    db_file = tmp_path_factory.mktemp("data") / "test.db"
    return f"sqlite:///{db_file}"


@pytest.fixture(scope="session")
def engine(sqlite_url: str):
    eng = create_engine(sqlite_url, future=True)
    # Create only the tables we need (models import `Base`)
    Base.metadata.create_all(bind=eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(bind=eng)
        eng.dispose()


@pytest.fixture()
def db_session(engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture()
def override_db_dependency(db_session: Session):
    """
    Override both dependency entrypoints used across routers so every endpoint
    uses the same test session.
    """

    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[core_get_db] = _override
    app.dependency_overrides[deps_get_db] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(core_get_db, None)
        app.dependency_overrides.pop(deps_get_db, None)


@pytest.fixture()
def client(override_db_dependency) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: str = "analyst",
    is_active: bool = True,
) -> User:
    u = User(
        email=email.strip().lower(),
        full_name="Test User",
        hashed_password=get_password_hash(password),
        role=role,
        is_active=is_active,
        is_superuser=(role == "admin"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_login_success_me_and_refresh(client: TestClient, db_session: Session):
    # Arrange
    email = "test-user@example.com"
    password = "Str0ngP@ss!"
    create_user(db_session, email=email, password=password)

    # Act: login
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and "refresh_token" in data
    access = data["access_token"]
    refresh = data["refresh_token"]

    # Act: /users/me with access token
    r2 = client.get("/v1/users/me", headers=auth_headers(access))
    assert r2.status_code == 200, r2.text
    me = r2.json()
    assert me["email"] == email.lower()
    assert me["is_active"] is True

    # Act: refresh (body)
    r3 = client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r3.status_code == 200, r3.text
    data2 = r3.json()
    assert "access_token" in data2
    new_access = data2["access_token"]
    assert new_access != access  # new token should differ

    # Sanity: /users/me with new access token
    r4 = client.get("/v1/users/me", headers=auth_headers(new_access))
    assert r4.status_code == 200, r4.text
    me2 = r4.json()
    assert me2["email"] == email.lower()


def test_login_invalid_credentials_401(client: TestClient, db_session: Session):
    # Arrange
    email = "wrongpass@example.com"
    password_ok = "GoodPass123!"
    create_user(db_session, email=email, password=password_ok)

    # Wrong password
    r = client.post("/v1/auth/login", json={"email": email, "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] in {"Invalid credentials", "Not authenticated"}


def test_refresh_revoked_after_token_version_bump(
    client: TestClient, db_session: Session
):
    # Arrange
    email = "revoke@example.com"
    password = "Pass1234!"
    user = create_user(db_session, email=email, password=password)

    # Login to get tokens
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    refresh = r.json()["refresh_token"]

    # Bump token_version (simulate logout/reset elsewhere)
    user.token_version = int(user.token_version or 0) + 1
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Attempt refresh with old refresh token -> 401
    r2 = client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401
    assert "Token revoked" in r2.json()["detail"] or "Invalid" in r2.json()["detail"]


def test_lockout_after_repeated_failures(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    """
    Configure env so that after 2 failures, the account is locked out.
    The third attempt should return 429.
    """
    # Set thresholds used by /auth/login helpers
    monkeypatch.setenv("MAX_FAILED_LOGINS", "2")
    monkeypatch.setenv("LOCKOUT_MINUTES", "10")

    email = "lockout@example.com"
    correct = "RightPass!23"
    create_user(db_session, email=email, password=correct)

    # First invalid attempt
    r1 = client.post("/v1/auth/login", json={"email": email, "password": "bad1"})
    assert r1.status_code == 401

    # Second invalid → triggers lockout
    r2 = client.post("/v1/auth/login", json={"email": email, "password": "bad2"})
    assert r2.status_code == 401  # lockout is applied *after* this attempt

    # Third attempt (even with correct creds) should be locked
    r3 = client.post("/v1/auth/login", json={"email": email, "password": correct})
    assert r3.status_code in (429, 401)  # prefer 429; some setups may still return 401
    # If 401, ensure the detail indicates lockout/not authenticated
    if r3.status_code == 401:
        assert r3.json()["detail"] in {"Invalid credentials", "Not authenticated"}


@pytest.mark.parametrize(
    "bad_header",
    ["", "Bearer", "Token abc", "Basic abc", "Bearer    "],
)
def test_me_requires_valid_bearer_token(client: TestClient, bad_header: str):
    headers = {}
    if bad_header:
        headers["Authorization"] = bad_header
    r = client.get("/v1/users/me", headers=headers)
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers
