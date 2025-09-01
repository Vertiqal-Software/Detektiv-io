# app/models/user.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Integer,
    func,
    BigInteger,
    ForeignKey,
    CheckConstraint,
    Index,
    text,  # server_default helpers
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base


class User(Base):
    """Application user account.

    Security & auth notes:
        - Email is unique and indexed; enforce non-empty via CHECK.
        - Passwords are stored as *hashed* strings (never plain text).
        - Timestamps use server-side defaults for portability.
        - Optional tenant_id allows future multi-tenant scoping.
        - AuthN/AuthZ supports:
            - role: basic RBAC (admin/analyst/member)  ← (expanded to include 'member')
            - failed_login_count + lockout_until: brute-force protection
            - token_version: JWT invalidation on logout/password-change/compromise
    """
    __tablename__ = "users"

    # Core identity
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Email is unique + indexed
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Auth fields
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # RBAC
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'analyst'"),  # default application role
        doc="Role for RBAC, e.g. 'admin', 'analyst', or 'member'.",
    )

    # Account security: lockout + attempts
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        doc="Consecutive failed login attempts since last successful login or since reset.",
    )
    lockout_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="If set, sign-in is blocked until this timestamp (rate-limit/lockout).",
    )

    # Token revocation (JWT versioning)
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        doc="Increment to invalidate all existing access/refresh tokens for the user.",
    )

    # Optional tenant association (must match tenants.id type -> BigInteger)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,  # keep your existing index flag
    )

    # Audit fields
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,  # reflect migration default
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,  # reflect migration default
    )

    # Relationship (kept simple; SQLAlchemy infers join via FK; avoids circular import by string)
    tenant = relationship("Tenant", lazy="joined")

    # Constraints & indexes
    __table_args__ = (
        CheckConstraint("email <> ''", name="ck_users_email_nonempty"),
        # Expanded to allow 'member' while preserving 'analyst' and 'admin'
        CheckConstraint("role IN ('admin','analyst','member')", name="ck_users_role"),
        CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_nonneg"),
        CheckConstraint("token_version >= 0", name="ck_users_token_version_nonneg"),
        # Helpful composite/coverage indexes for common queries
        Index("ix_users_tenant_email", "tenant_id", "email", unique=False),
        Index("ix_users_active_role", "is_active", "role"),
    )

    # ---------------------------- Validators ---------------------------------

    @validates("email")
    def _validate_email(self, key: str, value: str) -> str:
        """Normalize email to lowercase, trim whitespace, and ensure non-empty."""
        if value is None:
            raise ValueError("email cannot be null")
        v = value.strip().lower()
        if not v:
            raise ValueError("email cannot be empty")
        if len(v) > 255:
            raise ValueError("email too long")
        return v

    @validates("full_name")
    def _validate_full_name(self, key: str, value: Optional[str]) -> Optional[str]:
        """Trim and cap length for full_name if provided."""
        if value is None:
            return None
        v = value.strip()
        return v[:255] if len(v) > 255 else v

    @validates("hashed_password")
    def _validate_password(self, key: str, value: str) -> str:
        """Ensure a non-empty password hash string."""
        if value is None:
            raise ValueError("hashed_password cannot be null")
        v = value.strip()
        if not v:
            raise ValueError("hashed_password cannot be empty")
        return v

    @validates("role")
    def _validate_role(self, key: str, value: str) -> str:
        """Accept only known roles (db constraint also enforces this)."""
        if value is None:
            raise ValueError("role cannot be null")
        v = value.strip().lower()
        if v not in {"admin", "analyst", "member"}:
            raise ValueError("invalid role")
        return v

    @validates("failed_login_count", "token_version")
    def _validate_nonneg(self, key: str, value: int) -> int:
        """Non-negative guards for counters (db constraints also enforce)."""
        if value is None:
            return 0
        if int(value) < 0:
            raise ValueError(f"{key} cannot be negative")
        return int(value)

    # --------------------------- Convenience ---------------------------------

    @property
    def is_admin(self) -> bool:
        return bool(self.is_superuser or (self.role == "admin"))

    # Backwards-compatible alias for projects that use 'password_hash' naming.
    @property
    def password_hash(self) -> str:
        return self.hashed_password

    @password_hash.setter
    def password_hash(self, v: str) -> None:
        self.hashed_password = v

    @property
    def display_role(self) -> str:
        """A UI-friendly role string; you can map 'analyst' to 'member' here if desired."""
        return self.role

    def bump_token_version(self) -> None:
        """Increment token_version to invalidate all existing tokens."""
        self.token_version = int(self.token_version or 0) + 1

    def mark_password_changed(self) -> None:
        """Set password_changed_at and invalidate existing tokens."""
        self.password_changed_at = datetime.now(timezone.utc)
        self.bump_token_version()

    def record_failed_login(self, now: Optional[datetime] = None,
                            max_failures: Optional[int] = None,
                            lockout_minutes: Optional[int] = None) -> None:
        """Increment failed_login_count and apply a temporary lockout if thresholds are provided."""
        self.failed_login_count = int(self.failed_login_count or 0) + 1
        if max_failures and lockout_minutes and self.failed_login_count >= max_failures:
            base = now or datetime.now(timezone.utc)
            self.lockout_until = base + timedelta(minutes=lockout_minutes)

    def reset_failed_logins(self) -> None:
        """Reset counters on successful login (and clear any lockout)."""
        self.failed_login_count = 0
        self.lockout_until = None
        self.last_login_at = datetime.now(timezone.utc)

    def set_password(self, raw_password: str, hasher: Callable[[str], str]) -> None:
        """Hash and set a new password using the provided callable; marks password_changed."""
        if not raw_password or not raw_password.strip():
            raise ValueError("Password cannot be empty")
        self.hashed_password = hasher(raw_password)
        self.mark_password_changed()

    def verify_password(self, raw_password: str, verifier: Callable[[str, str], bool]) -> bool:
        """Verify a raw password against stored hash using the provided callable."""
        return verifier(raw_password, self.hashed_password)

    def __repr__(self) -> str:  # pragma: no cover - representation helper
        status = "active" if self.is_active else "disabled"
        return (
            f"<User id={self.id} email={self.email!r} role={self.role!r} "
            f"{status} super={self.is_superuser}>"
        )
