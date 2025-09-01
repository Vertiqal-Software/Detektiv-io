# tests/test_password_reset.py
from __future__ import annotations

"""
Password reset flow tests

Covers:
- POST /v1/auth/password-reset/request returns 200 for existing and non-existing emails
- POST /v1/auth/password-reset/confirm resets password with a valid token and revokes old tokens
- Invalid/forged tokens are rejected
- Optional strong-password policy enforcement (env-driven)

These tests run against a temporary SQLite database and override the app's DB
dependency so they do not require a running Postgres instance.
"""

from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.main import app
from app.models.base import Base
from app.models.user import User
from app.core.security import get_password_hash
from app.security.jwt_simple import issue_password_reset_token

# Shared DB dependencies we’ll override so every endpoint uses our SQLite session
from app.core.session import get_db as core_get_db
from app.api.deps import get_db as deps_get_db


# ---------------------------------------------------------------------------
# Test database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def engine(tmp_path_factory: pytest.TempPathFactory):
    db_file = tmp_path_factory.mktemp("pwreset_data") / "pwreset_test.db"
    eng = create_engine(f"sqlite:///{db_file}", future=True)
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


def seed_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: str = "analyst",
    is_active: bool = True,
    full_name: str = "Reset User",
) -> User:
    u = User(
        email=email.strip().lower(),
        full_name=full_name,
        hashed_password=get_password_hash(password),
        role=role,
        is_active=is_active,
        is_superuser=(role == "admin"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def login(client: TestClient, email: str, password: str) -> dict:
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_request_endpoint_always_200(client: TestClient, db_session: Session):
    # Arrange
    email_existing = "exists@example.com"
    seed_user(db_session, email=email_existing, password="OldPass!23")

    # Act: request for existing email
    r1 = client.post("/v1/auth/password-reset/request", json={"email": email_existing})
    assert r1.status_code == 200, r1.text

    # Act: request for non-existing email (should still be 200)
    r2 = client.post(
        "/v1/auth/password-reset/request", json={"email": "nope@example.com"}
    )
    assert r2.status_code == 200, r2.text


def test_confirm_resets_password_and_revokes_tokens(
    client: TestClient, db_session: Session
):
    # Arrange
    email = "resetme@example.com"
    old_pwd = "OldPass!23"
    new_pwd = "NewPass!23"
    user = seed_user(db_session, email=email, password=old_pwd)

    # Get an access/refresh pair (to prove revocation later)
    tokens = login(client, email, old_pwd)
    old_access = tokens["access_token"]

    # Issue a password-reset token (uses current token_version)
    reset_token = issue_password_reset_token(
        user_id=user.id, token_version=int(user.token_version or 0)
    )

    # Act: confirm reset
    r = client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": new_pwd},
    )
    assert r.status_code == 200, r.text

    # Old access token should be revoked now (token_version bump)
    r_old = client.get("/v1/users/me", headers=auth_headers(old_access))
    assert r_old.status_code == 401

    # New login works with new password
    tokens2 = login(client, email, new_pwd)
    r_me = client.get("/v1/users/me", headers=auth_headers(tokens2["access_token"]))
    assert r_me.status_code == 200
    assert r_me.json()["email"] == email


def test_confirm_rejects_invalid_or_mismatched_token(
    client: TestClient, db_session: Session
):
    # Arrange user
    user = seed_user(db_session, email="badtoken@example.com", password="AnyPass!23")

    # 1) Completely invalid token
    r1 = client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": "not-a-jwt", "new_password": "AnotherPass!23"},
    )
    assert r1.status_code in (400, 401), r1.text

    # 2) Token with old tv after bump (simulate reuse)
    #    First, bump token_version to simulate prior reset/ logout
    user.token_version = int(user.token_version or 0) + 1
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Issue token with a PREVIOUS tv (mismatch) — emulate by subtracting 1
    bad_tv = int(user.token_version or 0) - 1
    forged = issue_password_reset_token(user_id=user.id, token_version=bad_tv)
    r2 = client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": forged, "new_password": "StrongPass!99"},
    )
    assert r2.status_code in (400, 401), r2.text


def test_confirm_enforces_strong_password_when_policy_enabled(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    # Enable strong password policy
    monkeypatch.setenv("SECURITY_REQUIRE_STRONG", "1")
    monkeypatch.setenv("SECURITY_MIN_LENGTH", "12")
    monkeypatch.setenv("SECURITY_REQUIRE_CLASSES", "1")

    email = "policy@example.com"
    user = seed_user(db_session, email=email, password="OldStrong!23")

    token = issue_password_reset_token(
        user_id=user.id, token_version=int(user.token_version or 0)
    )

    # Too-weak password (short / lacks classes)
    weak = "short123"
    r = client.post(
        "/v1/auth/password-reset/confirm", json={"token": token, "new_password": weak}
    )
    # Depending on the handler, this could be 400 or 422
    assert r.status_code in (400, 422), r.text
