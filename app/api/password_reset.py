# app/api/password_reset.py
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.session import get_db
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate
from app.security.deps import require_admin
from app.services.user_service import UserService
from app.security.jwt_simple import (
    issue_password_reset_token,
    decode_and_validate,
    JWTError,
    JWTExpired,
)

router = APIRouter(prefix="/password", tags=["Auth"])
log = logging.getLogger("api.password")


class ForgotRequest(BaseModel):
    email: EmailStr


class ForgotResponse(BaseModel):
    ok: bool = True
    # Dev/testing only when ALLOW_RESET_TOKEN_IN_RESPONSE=1
    reset_token: Optional[str] = None
    reset_link: Optional[str] = None


class ResetRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class ResetResponse(BaseModel):
    ok: bool = True


class AdminCreateLinkRequest(BaseModel):
    user_id: int


class AdminCreateLinkResponse(BaseModel):
    ok: bool = True
    reset_token: str
    reset_link: Optional[str] = None
    expires_at: int


def _frontend_reset_link(token: str) -> Optional[str]:
    """
    If a frontend route handles reset, set:
      RESET_LINK_BASE=https://app.example.com/reset-password
    We'll return RESET_LINK_BASE + '?token=...'
    """
    base = os.getenv("RESET_LINK_BASE")
    if not base:
        return None
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}token={token}"


@router.post("/forgot", response_model=ForgotResponse, status_code=status.HTTP_200_OK)
def forgot_password(payload: ForgotRequest, db: Session = Depends(get_db)) -> ForgotResponse:
    """
    Always return 200 to avoid user enumeration.
    Behavior:
      - If user exists:
          * Dev mode (ALLOW_RESET_TOKEN_IN_RESPONSE=1): return token (and link) in response.
          * Prod mode: email the reset instructions via Mailer (SMTP or console), never return token.
      - If user doesn't exist: still return 200 (no info leak).
    """
    svc = UserService(db)
    user = svc.get_by_email(payload.email)

    resp = ForgotResponse(ok=True)
    if not user:
        # No enumeration: do nothing else.
        return resp

    # Create reset token tied to the user's current token_version
    tok = issue_password_reset_token(user_id=user.id, token_version=user.token_version)
    token = tok["token"]
    link = _frontend_reset_link(token)

    # Dev/testing path: return token directly
    if os.getenv("ALLOW_RESET_TOKEN_IN_RESPONSE", "0") == "1":
        resp.reset_token = token
        resp.reset_link = link
        log.info("password_forgot token_issued_dev user_id=%s", user.id)
        return resp

    # Production path: send email (no token in response)
    try:
        # Import here so the app still starts even if mailer isn't present yet
        from app.services.mailer import get_mailer  # type: ignore
        mailer = get_mailer()
        sent = mailer.send_password_reset(user.email, token, link, tok.get("expires_at"))
        if not sent:
            # We still return 200 to the caller to avoid enumeration or flow leaks
            log.error("password_forgot email_send_failed user_id=%s", user.id)
        else:
            log.info("password_forgot email_sent user_id=%s", user.id)
    except Exception:
        # Never crash the endpoint; keep UX and privacy guarantees
        log.exception("password_forgot email_send_exception user_id=%s", user.id)

    # Do not include token in response in prod path
    log.info("password_forgot token_issued user_id=%s", user.id)
    return resp


@router.post("/reset", response_model=ResetResponse, status_code=status.HTTP_200_OK)
def reset_password(payload: ResetRequest, db: Session = Depends(get_db)) -> ResetResponse:
    """
    Validate the reset token (type='pwreset'), ensure claim 'tv' matches current user.token_version,
    then set the new password. The service bumps token_version to revoke existing tokens.
    """
    try:
        claims = decode_and_validate(payload.token, expected_type="pwreset")
    except JWTExpired:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token expired")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")

    sub = claims.get("sub")
    tv = claims.get("tv")
    if not sub or tv is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token payload")

    try:
        user_id = int(sub)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subject")

    svc = UserService(db)
    user = svc.get(user_id)
    if not user or not user.is_active:
        # Avoid info leaks about account existence/state
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")

    if int(tv) != int(user.token_version):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token no longer valid")

    try:
        svc.update(user, UserUpdate(password=payload.new_password))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        log.exception("password_reset_failed user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset password")

    log.info("password_reset_ok user_id=%s", user.id)
    return ResetResponse(ok=True)


@router.post(
    "/admin/create-reset-link",
    response_model=AdminCreateLinkResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin: generate a password reset token for a user",
)
def admin_create_reset_link(
    payload: AdminCreateLinkRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminCreateLinkResponse:
    svc = UserService(db)
    user = svc.get(payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    tok = issue_password_reset_token(user_id=user.id, token_version=user.token_version)
    token = tok["token"]
    link = _frontend_reset_link(token)
    return AdminCreateLinkResponse(ok=True, reset_token=token, reset_link=link, expires_at=tok["expires_at"])
