# app/services/user_service.py
from __future__ import annotations

"""
User service layer

- Centralizes CRUD and auth-related operations for User.
- Preserves existing behaviours (do not break authenticate()) and *adds* optional
  lockout-aware authentication helpers so you can opt-in without changing callers.
- Expands allowed roles to include 'member' in addition to 'admin' and 'analyst'.
- Hardens email normalization, password handling, and token revocation paths.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password, needs_rehash
from app.models.user import User  # SQLAlchemy model
from app.schemas.user import UserCreate, UserUpdate  # Pydantic schemas

log = logging.getLogger(__name__)

# --- Configurable guards (env overrides keep this file decoupled from settings) ---
ALLOWED_ROLES = {"admin", "analyst", "member"}  # expanded to include 'member'
MAX_FAILED_LOGINS = int(os.getenv("AUTH_MAX_FAILED_LOGINS", "10"))
LOCKOUT_MINUTES = int(os.getenv("AUTH_LOCKOUT_MINUTES", "15"))


def _normalize_email(email: str) -> str:
    """Basic normalization; adjust later if you add more complex rules."""
    return (email or "").strip().lower()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserService:
    """
    Service layer for user operations.

    Guarantees:
    - Does NOT log plaintext passwords.
    - Enforces unique email at the application layer (DB unique constraint is final guard).
    - Accepts a request-scoped SQLAlchemy Session supplied by the caller.
    """

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # Read helpers
    # -------------------------------------------------------------------------

    def get(self, user_id: int) -> Optional[User]:
        """Fetch a user by id."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by normalized email (or None)."""
        e = _normalize_email(email)
        if not e:
            return None
        return self.db.query(User).filter(User.email == e).one_or_none()

    # -------------------------------------------------------------------------
    # Create
    # -------------------------------------------------------------------------

    def create(self, data: UserCreate) -> User:
        """
        Create a user:
          - normalizes email
          - validates password length (>= 8)
          - hashes password
          - sets default flags and role

        Raises:
          - ValueError for validation issues
          - IntegrityError bubbled up if a race hits the unique constraint
        """
        email = _normalize_email(data.email)
        if not email:
            raise ValueError("Email must not be empty")
        if len(email) > 255:
            raise ValueError("Email too long")

        if not isinstance(data.password, str) or len(data.password.strip()) < 8:
            raise ValueError("Password must be at least 8 characters")

        # Validate role (mirrors DB CHECK constraint)
        role = (getattr(data, "role", "analyst") or "analyst").strip().lower()
        if role not in ALLOWED_ROLES:
            raise ValueError("Invalid role")

        # Application-level uniqueness check (race-safe due to DB unique index)
        if self.get_by_email(email):
            raise ValueError("A user with this email already exists")

        hashed = get_password_hash(data.password.strip())
        now = _utcnow()

        user = User(
            email=email,
            full_name=(data.full_name.strip() if isinstance(data.full_name, str) else data.full_name),
            tenant_id=data.tenant_id,
            hashed_password=hashed,
            is_active=bool(getattr(data, "is_active", True)),
            is_superuser=bool(getattr(data, "is_superuser", False)),
            role=role,
            password_changed_at=now,
            # token_version starts at 0 via DB default
            # created_at/updated_at default on DB side
        )

        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            # Likely a concurrent insert with same email
            raise

        log.info("user_created email=%s id=%s", email, user.id)
        return user

    # -------------------------------------------------------------------------
    # Update (partial)
    # -------------------------------------------------------------------------

    def update(self, user: User, patch: UserUpdate, *, allow_role_change: bool = False) -> User:
        """
        Partially update fields on a user. Hashes password if provided.

        Args:
            user: Target user entity (managed by SQLAlchemy Session).
            patch: Incoming changes (all optional).
            allow_role_change: Caller must explicitly allow role elevation/demotion.
                               Typically only admins should set this True.
        """
        if patch.email is not None:
            new_email = _normalize_email(patch.email)
            if not new_email:
                raise ValueError("Email must not be empty")
            if len(new_email) > 255:
                raise ValueError("Email too long")
            # If changing email, check for conflicts
            existing = self.get_by_email(new_email)
            if existing and existing.id != user.id:
                raise ValueError("A user with this email already exists")
            user.email = new_email

        if patch.full_name is not None:
            user.full_name = patch.full_name.strip() if isinstance(patch.full_name, str) else None

        if patch.tenant_id is not None:
            user.tenant_id = patch.tenant_id

        if patch.is_active is not None:
            user.is_active = bool(patch.is_active)

        if patch.is_superuser is not None:
            user.is_superuser = bool(patch.is_superuser)

        # Role change (guarded)
        if getattr(patch, "role", None) is not None:
            if not allow_role_change:
                raise PermissionError("Role changes require elevated privileges")
            role = (patch.role or "").strip().lower()
            if role not in ALLOWED_ROLES:
                raise ValueError("Invalid role")
            user.role = role  # type: ignore[assignment]

        # Password change → re-hash + increment token_version (revokes existing tokens)
        if patch.password:
            if len(patch.password.strip()) < 8:
                raise ValueError("Password must be at least 8 characters")
            user.hashed_password = get_password_hash(patch.password.strip())
            user.password_changed_at = _utcnow()
            # Bump token version to invalidate all existing JWTs
            user.token_version = int(user.token_version or 0) + 1

        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            raise

        log.info("user_updated id=%s", user.id)
        return user

    # -------------------------------------------------------------------------
    # Auth helpers
    # -------------------------------------------------------------------------

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """
        Verify credentials and return the user if valid and active.

        NOTE:
        - Does NOT update lockout counters/timestamps (handled in the API layer).
        - Transparently **rehashes** stored password if `needs_rehash` returns True.
          This hardens security over time without forcing logouts (no token_version bump).
        """
        e = _normalize_email(email)
        user = self.get_by_email(e)
        if not user:
            return None
        if not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None

        # Opportunistic rehash on successful verification (no token_version change)
        try:
            if needs_rehash(user.hashed_password):
                new_hash = get_password_hash(password)
                if new_hash and new_hash != user.hashed_password:
                    user.hashed_password = new_hash
                    # Do NOT touch password_changed_at here; only on explicit change.
                    self.db.add(user)
                    self.db.commit()
                    self.db.refresh(user)
                    log.info("user_password_rehash id=%s", user.id)
        except Exception:
            # Never break login flow due to a rehash failure
            self.db.rollback()
            log.exception("user_password_rehash_failed id=%s", getattr(user, "id", None))

        return user

    # New, optional: lockout-aware authentication that also manages counters
    def authenticate_with_lockout(self, email: str, password: str,
                                  now: Optional[datetime] = None) -> Tuple[Optional[User], Optional[str]]:
        """
        Verify credentials with built-in lockout handling.

        Returns:
            (user, None) on success
            (None, reason) on failure; reason one of: 'locked', 'invalid', 'inactive', 'not_found'
        """
        e = _normalize_email(email)
        user = self.get_by_email(e)
        if not user:
            return None, "not_found"

        now = now or _utcnow()

        # Locked?
        if self.is_locked(user, now):
            return None, "locked"

        if not user.is_active:
            return None, "inactive"

        if not verify_password(password, user.hashed_password):
            self.record_failed_login(user, now=now)
            return None, "invalid"

        # Success: reset counters and optionally rehash
        self.reset_failed_logins(user, now=now)

        try:
            if needs_rehash(user.hashed_password):
                new_hash = get_password_hash(password)
                if new_hash and new_hash != user.hashed_password:
                    user.hashed_password = new_hash
                    self.db.add(user)
                    self.db.commit()
                    self.db.refresh(user)
                    log.info("user_password_rehash id=%s", user.id)
        except Exception:
            self.db.rollback()
            log.exception("user_password_rehash_failed id=%s", getattr(user, "id", None))

        return user, None

    # -------------------------------------------------------------------------
    # Additional helpers (non-breaking, optional to use)
    # -------------------------------------------------------------------------

    def is_locked(self, user: User, now: Optional[datetime] = None) -> bool:
        """Return True if user is currently locked out."""
        if not user.lockout_until:
            return False
        now = now or _utcnow()
        return user.lockout_until > now

    def record_failed_login(self, user: User, now: Optional[datetime] = None) -> User:
        """Increment failed_login_count and apply a temporary lockout if thresholds are reached."""
        now = now or _utcnow()
        user.failed_login_count = int(user.failed_login_count or 0) + 1
        if MAX_FAILED_LOGINS and LOCKOUT_MINUTES and user.failed_login_count >= MAX_FAILED_LOGINS:
            user.lockout_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            raise
        return user

    def reset_failed_logins(self, user: User, now: Optional[datetime] = None) -> User:
        """Reset counters on successful login (and clear any lockout)."""
        user.failed_login_count = 0
        user.lockout_until = None
        user.last_login_at = now or _utcnow()
        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            raise
        return user

    def verify_unique_email(self, email: str, *, exclude_user_id: Optional[int] = None) -> None:
        """
        Raise ValueError if another user already has this email.
        Helpful before bulk imports or admin edits.
        """
        e = _normalize_email(email)
        existing = self.get_by_email(e)
        if existing and (exclude_user_id is None or existing.id != exclude_user_id):
            raise ValueError("A user with this email already exists")

    def set_password(self, user: User, new_password: str, *, bump_token_version: bool = True) -> User:
        """
        Set a new password for the user (hashes + optional token revocation).
        """
        if not isinstance(new_password, str) or len(new_password.strip()) < 8:
            raise ValueError("Password must be at least 8 characters")
        user.hashed_password = get_password_hash(new_password.strip())
        user.password_changed_at = _utcnow()
        if bump_token_version:
            user.token_version = int(user.token_version or 0) + 1
        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            raise
        log.info("user_password_changed id=%s", user.id)
        return user

    def revoke_tokens(self, user: User) -> User:
        """
        Increment token_version to invalidate all existing tokens for the user.
        """
        user.token_version = int(user.token_version or 0) + 1
        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            raise
        log.info("user_tokens_revoked id=%s", user.id)
        return user

    def ensure_initial_admin(self, email: str, password: str, *, full_name: Optional[str] = None) -> Optional[User]:
        """
        Idempotently create an initial admin account **only if** no users exist.
        Returns the admin user if created, else None.

        WARNING: Only call this from a protected bootstrap path (e.g., admin-only CLI/env flag).
        """
        count = self.db.query(User).count()
        if count > 0:
            return None
        payload = UserCreate(
            email=email,
            password=password,
            full_name=full_name.strip() if isinstance(full_name, str) else full_name,
            role="admin",
            is_active=True,
            is_superuser=True,
            tenant_id=None,
        )
        return self.create(payload)
