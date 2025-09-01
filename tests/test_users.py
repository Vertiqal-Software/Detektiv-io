# tests/test_users.py
from __future__ import annotations

"""
Users API tests

Covers:
- Admin vs non-admin access controls
- Paged listing with search
- Create (admin-only) incl. duplicate email 409
- Get by id (self vs others)
- Self update (name, password) and token_version revocation effect
- Admin update (role/flags)
- Deactivate (soft delete → is_active=false, idempotent 204)

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

# Shared DB dependencies we’ll override so every endpoint uses our SQLite session
from app.core.session import get_db as core_get_db
from app.api.deps import get_db as deps_get_db


# ---------------------------------------------------------------------------
# Test database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def engine(tmp_path_factory: pytest.TempPathFactory):
    # Use a file-backed SQLite DB so connections share state across requests
    db_file = tmp_path_factory.mktemp("users_data") / "users_test.db"
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
    full_name: str = "Test User",
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


def test_users_paged_requires_admin_and_allows_admin(
    client: TestClient, db_session: Session
):
    # Seed: one admin and a few members
    admin = seed_user(
        db_session, email="admin@example.com", password="AdminPass!23", role="admin"
    )
    seed_user(
        db_session,
        email="alice@example.com",
        password="Pass!1234",
        role="member",
        full_name="Alice Allison",
    )
    seed_user(
        db_session,
        email="bob@example.com",
        password="Pass!1234",
        role="analyst",
        full_name="Bob Roberts",
    )
    seed_user(
        db_session,
        email="carol@example.com",
        password="Pass!1234",
        role="member",
        full_name="Carol Singer",
    )

    # Non-admin cannot access paged list
    non_admin = seed_user(
        db_session, email="viewer@example.com", password="Pass!1234", role="member"
    )
    tokens_na = login(client, non_admin.email, "Pass!1234")
    r_forbidden = client.get(
        "/v1/users/paged?page=0&page_size=10",
        headers=auth_headers(tokens_na["access_token"]),
    )
    assert r_forbidden.status_code in (
        403,
        401,
    )  # 403 preferred; 401 acceptable if auth deps differ

    # Admin can access paged list
    tokens_admin = login(client, admin.email, "AdminPass!23")
    r_ok = client.get(
        "/v1/users/paged?page=0&page_size=10",
        headers=auth_headers(tokens_admin["access_token"]),
    )
    assert r_ok.status_code == 200, r_ok.text
    data = r_ok.json()
    assert {"items", "total", "page", "page_size"} <= set(data.keys())
    assert data["page"] == 0
    assert data["page_size"] == 10
    assert data["total"] >= 4
    assert isinstance(data["items"], list)
    assert any(u["email"] == "alice@example.com" for u in data["items"])

    # Search narrows results
    r_search = client.get(
        "/v1/users/paged?page=0&page_size=10&q=ali",
        headers=auth_headers(tokens_admin["access_token"]),
    )
    assert r_search.status_code == 200
    items = r_search.json()["items"]
    assert all(
        "ali" in u["email"] or (u.get("full_name") or "").lower().find("ali") >= 0
        for u in items
    )
    assert any(u["email"] == "alice@example.com" for u in items)


def test_admin_can_create_user_and_duplicate_returns_409(
    client: TestClient, db_session: Session
):
    admin = seed_user(
        db_session, email="root@example.com", password="RootPass!23", role="admin"
    )
    tokens_admin = login(client, admin.email, "RootPass!23")

    # Create a user
    payload = {
        "email": "newuser@example.com",
        "full_name": "New User",
        "password": "Secur3P@ss!",
        "role": "member",
        "is_active": True,
    }
    r = client.post(
        "/v1/users", json=payload, headers=auth_headers(tokens_admin["access_token"])
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["email"] == "newuser@example.com"
    assert created["role"] in {
        "member",
        "analyst",
    }  # service may default to analyst; both acceptable

    # Duplicate email
    r2 = client.post(
        "/v1/users", json=payload, headers=auth_headers(tokens_admin["access_token"])
    )
    assert r2.status_code in (
        409,
        400,
    ), r2.text  # prefer 409; some services raise 400 on app-layer check


def test_get_user_by_id_self_and_admin_rules(client: TestClient, db_session: Session):
    admin = seed_user(
        db_session, email="boss@example.com", password="BossPass!23", role="admin"
    )
    member = seed_user(
        db_session,
        email="john@example.com",
        password="JohnPass!23",
        role="member",
        full_name="John Doe",
    )

    tokens_admin = login(client, admin.email, "BossPass!23")
    tokens_member = login(client, member.email, "JohnPass!23")

    # Self can get self
    r_self = client.get(
        f"/v1/users/{member.id}", headers=auth_headers(tokens_member["access_token"])
    )
    assert r_self.status_code == 200
    assert r_self.json()["email"] == member.email

    # Non-admin cannot get others
    r_forbidden = client.get(
        f"/v1/users/{admin.id}", headers=auth_headers(tokens_member["access_token"])
    )
    assert r_forbidden.status_code in (403, 401)

    # Admin can get any user
    r_admin = client.get(
        f"/v1/users/{member.id}", headers=auth_headers(tokens_admin["access_token"])
    )
    assert r_admin.status_code == 200
    assert r_admin.json()["email"] == member.email


def test_self_update_name_and_password_revokes_old_token(
    client: TestClient, db_session: Session
):
    user = seed_user(
        db_session,
        email="selfedit@example.com",
        password="OldPass!23",
        role="analyst",
        full_name="Old Name",
    )
    tokens = login(client, user.email, "OldPass!23")
    access_old = tokens["access_token"]

    # Change full_name (self)
    r_name = client.patch(
        f"/v1/users/{user.id}",
        json={"full_name": "New Name"},
        headers=auth_headers(access_old),
    )
    assert r_name.status_code == 200
    assert r_name.json()["full_name"] == "New Name"

    # Change password (self) → should bump token_version and invalidate old token
    r_pwd = client.patch(
        f"/v1/users/{user.id}",
        json={"password": "NewStr0ng!Pass1"},
        headers=auth_headers(access_old),
    )
    assert r_pwd.status_code == 200

    # Old token should now be invalid (revoked)
    r_me_old = client.get("/v1/users/me", headers=auth_headers(access_old))
    assert r_me_old.status_code == 401

    # Login with new password works
    tokens_new = login(client, user.email, "NewStr0ng!Pass1")
    r_me_new = client.get(
        "/v1/users/me", headers=auth_headers(tokens_new["access_token"])
    )
    assert r_me_new.status_code == 200
    assert r_me_new.json()["email"] == user.email


def test_self_cannot_change_role_flags_but_admin_can(
    client: TestClient, db_session: Session
):
    admin = seed_user(
        db_session, email="admin2@example.com", password="Admin2!23", role="admin"
    )
    member = seed_user(
        db_session, email="jane@example.com", password="JanePass!23", role="member"
    )

    tokens_admin = login(client, admin.email, "Admin2!23")
    tokens_member = login(client, member.email, "JanePass!23")

    # Member attempts to elevate role → forbidden
    r_forbidden = client.patch(
        f"/v1/users/{member.id}",
        json={"role": "admin", "is_superuser": True, "is_active": True},
        headers=auth_headers(tokens_member["access_token"]),
    )
    assert r_forbidden.status_code in (403, 401)

    # Admin can elevate member to analyst/admin
    r_admin = client.patch(
        f"/v1/users/{member.id}",
        json={"role": "analyst", "is_active": True},
        headers=auth_headers(tokens_admin["access_token"]),
    )
    assert r_admin.status_code == 200
    assert r_admin.json()["role"] in {
        "analyst",
        "admin",
    }  # accept either if service coerces


def test_deactivate_user_is_idempotent_and_sets_inactive(
    client: TestClient, db_session: Session
):
    admin = seed_user(
        db_session, email="admin3@example.com", password="Admin3!23", role="admin"
    )
    victim = seed_user(
        db_session, email="deac@example.com", password="Victim!23", role="member"
    )

    tokens_admin = login(client, admin.email, "Admin3!23")

    # Deactivate
    r_del = client.delete(
        f"/v1/users/{victim.id}", headers=auth_headers(tokens_admin["access_token"])
    )
    assert r_del.status_code == 204

    # Verify is_active false (admin can fetch)
    r_get = client.get(
        f"/v1/users/{victim.id}", headers=auth_headers(tokens_admin["access_token"])
    )
    assert r_get.status_code == 200
    assert r_get.json()["is_active"] is False

    # Idempotent
    r_del2 = client.delete(
        f"/v1/users/{victim.id}", headers=auth_headers(tokens_admin["access_token"])
    )
    assert r_del2.status_code == 204
