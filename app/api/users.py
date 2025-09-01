# app/api/users.py
from __future__ import annotations

from typing import Tuple, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.user_service import UserService
from app.security.deps import get_current_user, require_admin

# Optional pagination helper; falls back to static defaults if deps not available
try:
    from app.api.deps import pagination_env
except Exception:  # pragma: no cover
    def pagination_env(
        limit: int = Query(50, ge=1, le=1000, description="Max rows to return"),
        offset: int = Query(0, ge=0, description="Rows to skip for paging"),
    ) -> Tuple[int, int]:
        return limit, offset


router = APIRouter(prefix="/users", tags=["Users"])


def _to_read(u: User) -> UserRead:
    # Support both Pydantic v1 (from_orm) and v2 (model_validate)
    return (
        UserRead.model_validate(u)  # type: ignore[attr-defined]
        if hasattr(UserRead, "model_validate")
        else UserRead.from_orm(u)  # type: ignore[attr-defined]
    )


# -----------------------------------------------------------------------------
# NEW: Paged response model to match frontend expectations ({items,total,page,page_size})
# -----------------------------------------------------------------------------
class UsersPage(BaseModel):
    items: List[UserRead]
    total: int
    page: int
    page_size: int


# -----------------------------------------------------------------------------
# List users (admin) — existing endpoint preserved (non-breaking)
# - Adds optional 'q' search while keeping existing limit/offset contract and
#   response shape (List[UserRead]) to avoid breaking any consumers already relying
#   on this endpoint.
# -----------------------------------------------------------------------------
@router.get(
    "",
    response_model=List[UserRead],
    status_code=status.HTTP_200_OK,
    summary="List users (admin)",
)
def list_users(
    limit_offset: Tuple[int, int] = Depends(pagination_env),
    q: Optional[str] = Query(None, description="Search by email/full name (case-insensitive)"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> List[UserRead]:
    """List users ordered by id DESC. Admin-only. Supports optional 'q' search."""
    limit, offset = limit_offset

    query = db.query(User)

    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.email.ilike(like), User.full_name.ilike(like)))

    rows = (
        query.order_by(User.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_to_read(u) for u in rows]


# -----------------------------------------------------------------------------
# NEW: Paged users listing that matches React client contract exactly
# GET /users/paged?page=&page_size=&q=
# Returns: { items, total, page, page_size }
# -----------------------------------------------------------------------------
@router.get(
    "/paged",
    response_model=UsersPage,
    status_code=status.HTTP_200_OK,
    summary="List users with page/page_size and search (admin)",
)
def list_users_paged(
    page: int = Query(0, ge=0),
    page_size: int = Query(20, ge=1, le=200),
    q: Optional[str] = Query(None, description="Search by email/full name (case-insensitive)"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UsersPage:
    """
    Paginated list for admin use, designed to match frontend expectations:
    - Filtering by 'q' across email and full_name (ILIKE).
    - Returns items + total + page + page_size.
    """
    base = db.query(User)

    if q:
        like = f"%{q.strip()}%"
        base = base.filter(or_(User.email.ilike(like), User.full_name.ilike(like)))

    total = base.with_entities(func.count(User.id)).scalar() or 0

    items = (
        base.order_by(User.id.desc())
        .limit(page_size)
        .offset(page * page_size)
        .all()
    )

    return UsersPage(
        items=[_to_read(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserRead:
    """
    Admin-only: creates a user.
    - Email normalized
    - Password hashed
    - Role defaults to 'analyst' if not specified
    - Admins may set role and flags at creation
    """
    svc = UserService(db)
    try:
        user = svc.create(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        # Conflict for duplicate unique fields
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")
    return _to_read(user)


@router.get(
    "/{user_id}",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get a user by id (self or admin)",
)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    """
    Non-admins can only view themselves. Admins can view any user.
    """
    svc = UserService(db)
    user = svc.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not (current_user.is_superuser or current_user.role == "admin" or current_user.id == user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    return _to_read(user)


@router.get(
    "/by-email",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get a user by email (admin only)",
)
def get_user_by_email(
    email: str = Query(..., min_length=3, max_length=255),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserRead:
    svc = UserService(db)
    user = svc.get_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _to_read(user)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update a user (self or admin; role/flags require admin)",
)
def update_user(
    user_id: int,
    patch: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    """
    - Non-admins may update their own email, full_name, and password.
    - Only admins may update another user, change role/is_active/is_superuser/tenant_id.
    - Password changes bump token_version (service layer), revoking prior tokens.
    """
    svc = UserService(db)
    user = svc.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    is_admin = current_user.is_superuser or current_user.role == "admin"
    is_self = current_user.id == user_id

    if not is_admin and not is_self:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    # Guard privileged fields for non-admins
    if not is_admin:
        forbidden = []
        if patch.role is not None:
            forbidden.append("role")
        if patch.is_active is not None:
            forbidden.append("is_active")
        if patch.is_superuser is not None:
            forbidden.append("is_superuser")
        if getattr(patch, "tenant_id", None) is not None:
            forbidden.append("tenant_id")
        if forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient privileges to update: {', '.join(forbidden)}",
            )

    try:
        updated = svc.update(user, patch, allow_role_change=is_admin and (patch.role is not None))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        # Conflict for duplicate unique fields
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update user")

    return _to_read(updated)


# -----------------------------------------------------------------------------
# Deactivate user (admin) — existing endpoint preserved
# -----------------------------------------------------------------------------
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a user (admin, response_model=None, response_class=Response)",
)
def deactivate_user(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """
    Soft-delete: set is_active = false. Admin-only.
    Returns 204 even if user doesn't exist for idempotency.
    """
    u = db.get(User, user_id)
    if not u:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    u.is_active = False
    try:
        db.add(u)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to deactivate user")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get the authenticated user's profile",
)
def get_me(current_user: User = Depends(get_current_user)) -> UserRead:
    return _to_read(current_user)
