# app/schemas/user.py
"""
Pydantic schemas for User entities.

Design goals:
- Never expose hashed_password in API responses.
- Keep create/update payloads simple and safe.
- Work with both Pydantic v1 and v2 (ORM compatibility).
- Add RBAC 'role' field with safe defaults ('analyst') and validation.
- Extend roles to include a third, non-admin role: 'member' (backwards compatible).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

# Pydantic v1/v2 compatibility shims
try:
    from pydantic import BaseModel, EmailStr, Field, ConfigDict  # v2
    _HAS_V2 = True
except Exception:  # pragma: no cover
    from pydantic import BaseModel, EmailStr, Field  # v1
    ConfigDict = None  # type: ignore
    _HAS_V2 = False


# Allowed roles (mirrors DB CHECK constraint: admin | analyst | member)
Role = Literal["admin", "analyst", "member"]


class _OrmModel(BaseModel):
    """
    Base that enables loading from SQLAlchemy ORM objects.
    Compatible across Pydantic v1 and v2.
    """
    if _HAS_V2:
        model_config = ConfigDict(from_attributes=True)  # type: ignore[attr-defined]
    else:  # pragma: no cover
        class Config:
            orm_mode = True


# ---------- Shared base ----------
class UserBase(_OrmModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, description="Display name (optional)")
    tenant_id: Optional[int] = Field(
        default=None,
        description="Optional tenant scope; null means global/system user",
    )


# ---------- Create / Update payloads ----------
class UserCreate(UserBase):
    """
    Payload for creating a user. The plaintext password is accepted here
    (server will hash it using app.security.passwords.* helpers).
    'role' is optional; servers SHOULD enforce that only admins can set it.
    """
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Plaintext password to be hashed by the server",
    )
    # Default to 'analyst'; service layer enforces admin-only elevation.
    role: Role = Field(default="analyst", description="RBAC role (admin, analyst, member)")
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)

    # --- lightweight hygiene (service does stronger policy checks) ---
    if not _HAS_V2:  # pydantic v1 validators
        from pydantic import validator as _validator  # type: ignore

        @_validator("full_name")
        def _trim_full_name_v1(cls, v: Optional[str]) -> Optional[str]:
            if v is None:
                return v
            v = v.strip()
            return v or None

        @_validator("password")
        def _strip_password_v1(cls, v: str) -> str:
            v2 = v.strip()
            if not v2:
                raise ValueError("Password cannot be empty")
            return v2
    else:
        # pydantic v2 field validators
        from pydantic import field_validator as _field_validator  # type: ignore

        @_field_validator("full_name")
        @classmethod
        def _trim_full_name_v2(cls, v: Optional[str]) -> Optional[str]:
            if v is None:
                return v
            v = v.strip()
            return v or None

        @_field_validator("password")
        @classmethod
        def _strip_password_v2(cls, v: str) -> str:
            v2 = v.strip()
            if not v2:
                raise ValueError("Password cannot be empty")
            return v2


class UserUpdate(_OrmModel):
    """
    Partial update; all fields optional.
    If 'password' is provided, it will be hashed server-side.
    'role' changes SHOULD be restricted to admins in the service layer.
    """
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    tenant_id: Optional[int] = None
    password: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="New plaintext password; will be hashed if provided",
    )
    role: Optional[Role] = Field(
        default=None,
        description="RBAC role (admin, analyst, member) — service should enforce admin-only",
    )
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None

    # same lightweight hygiene as create
    if not _HAS_V2:
        from pydantic import validator as _validator  # type: ignore

        @_validator("full_name")
        def _trim_full_name_v1(cls, v: Optional[str]) -> Optional[str]:
            if v is None:
                return v
            v = v.strip()
            return v or None

        @_validator("password")
        def _strip_password_v1(cls, v: Optional[str]) -> Optional[str]:
            if v is None:
                return v
            v2 = v.strip()
            if not v2:
                raise ValueError("Password cannot be empty")
            return v2
    else:
        from pydantic import field_validator as _field_validator  # type: ignore

        @_field_validator("full_name")
        @classmethod
        def _trim_full_name_v2(cls, v: Optional[str]) -> Optional[str]:
            if v is None:
                return v
            v = v.strip()
            return v or None

        @_field_validator("password")
        @classmethod
        def _strip_password_v2(cls, v: Optional[str]) -> Optional[str]:
            if v is None:
                return v
            v2 = v.strip()
            if not v2:
                raise ValueError("Password cannot be empty")
            return v2


# ---------- Read models (responses) ----------
class UserRead(_OrmModel):
    """
    Public representation of a user.
    Note: hashed_password is deliberately excluded.
    """
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    tenant_id: Optional[int] = None
    role: Role
    is_active: bool
    is_superuser: bool
    last_login_at: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "Role",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserRead",
]
