# app/api/admin_bootstrap.py
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import UserService

# Pydantic v1/v2 compatibility
try:
    from pydantic import BaseModel, EmailStr, Field, ConfigDict  # v2
    _HAS_V2 = True
except Exception:  # pragma: no cover
    from pydantic import BaseModel, EmailStr, Field  # v1
    ConfigDict = None  # type: ignore
    _HAS_V2 = False

log = logging.getLogger("api.admin_bootstrap")
router = APIRouter(prefix="/admin", tags=["Admin"])


class _OrmModel(BaseModel):
    if _HAS_V2:
        model_config = ConfigDict(from_attributes=True)  # type: ignore[attr-defined]
    else:  # pragma: no cover
        class Config:
            orm_mode = True


class BootstrapRequest(_OrmModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256, description="Strong admin password")
    full_name: Optional[str] = Field(default=None)
    tenant_id: Optional[int] = Field(default=None, description="Optional initial tenant assignment")


@router.post(
    "/bootstrap",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="One-time creation of the first admin user on a fresh deployment",
)
def bootstrap_admin(payload: BootstrapRequest, db: Session = Depends(get_db)) -> UserRead:
    """
    Create the first admin user *only* when:
      - ENABLE_ADMIN_BOOTSTRAP=1
      - No users exist yet in the database
    This endpoint is intentionally unauthenticated, but heavily guarded by the env flag and the zero-user check.
    """
    if os.getenv("ENABLE_ADMIN_BOOTSTRAP", "0") != "1":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bootstrap is disabled")

    # Check zero-user condition
    existing_count = db.query(User).count()
    if existing_count > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bootstrap already completed")

    # Create admin using the service (handles hashing, validation, normalization)
    svc = UserService(db)
    try:
        admin = svc.create(
            UserCreate(
                email=payload.email,
                password=payload.password,
                full_name=payload.full_name,
                tenant_id=payload.tenant_id,
                is_active=True,
                is_superuser=True,
                role="admin",
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log.exception("admin_bootstrap_failed email=%s", payload.email)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Bootstrap failed")

    log.warning("admin_bootstrap_success id=%s email=%s", admin.id, admin.email)

    # Strongly encourage disabling the flag immediately after success
    # (We can't change env here; deployment should unset ENABLE_ADMIN_BOOTSTRAP.)
    return UserRead.model_validate(admin) if _HAS_V2 else UserRead.from_orm(admin)  # type: ignore[attr-defined]
