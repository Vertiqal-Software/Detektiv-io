# app/api/auth.py
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
import os
from typing import Dict, Any

from app.security.deps import require_user, admin_credentials
from app.security.jwt_simple import jwt_encode

router = APIRouter(tags=["Auth"])

class LoginRequest(BaseModel):
    username: str = Field(..., example="admin")
    password: str = Field(..., example="change-me")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    creds = admin_credentials()
    if payload.username != creds["username"] or payload.password != creds["password"]:
        # Do not reveal which of user/pass is wrong
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    expires = int(os.getenv("JWT_EXPIRES_MINUTES", "60")) * 60
    claims = {
        "sub": "admin",
        "username": creds["username"],
        "role": "admin",
    }
    token = jwt_encode(claims, expires_in=expires)
    return {"access_token": token, "expires_in": expires}

@router.get("/auth/me")
def me(user: Dict[str, Any] = Depends(require_user)):
    return {"user": {"username": user["username"], "role": user.get("role", "user")}}
