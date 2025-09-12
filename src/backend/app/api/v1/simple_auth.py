# app/api/simple_auth.py
# Simple authentication endpoints for MVP
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import os
import secrets

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

# Import database session
try:
    from app.core.session import get_db
except ImportError:
    from app.core.database import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Pydantic models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime


# Simple token generation (for MVP - in production use proper JWT)
def generate_token() -> str:
    return secrets.token_urlsafe(32)


# Simple password hashing (for MVP - in production use proper bcrypt)
def hash_password(password: str) -> str:
    return f"hashed_{password}_{secrets.token_hex(8)}"


def verify_password(password: str, hashed: str) -> bool:
    # Simple verification for MVP
    return hashed.startswith(f"hashed_{password}_")


@router.post("/register", response_model=AuthResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user"""
    try:
        # Check if user already exists
        result = db.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": request.email}
        )
        if result.fetchone():
            raise HTTPException(
                status_code=400,
                detail="Email already registered"
            )
        
        # Create new user
        hashed_password = hash_password(request.password)
        result = db.execute(
            text("""
                INSERT INTO users (email, password_hash, is_active, created_at, updated_at)
                VALUES (:email, :password_hash, true, :now, :now)
                RETURNING id
            """),
            {
                "email": request.email,
                "password_hash": hashed_password,
                "now": datetime.now(timezone.utc)
            }
        )
        
        user_id = result.fetchone()[0]
        db.commit()
        
        # Generate token
        token = generate_token()
        
        return AuthResponse(
            access_token=token,
            user_id=user_id,
            email=request.email
        )
        
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=AuthResponse)  
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login user"""
    try:
        # Find user
        result = db.execute(
            text("SELECT id, email, password_hash, is_active FROM users WHERE email = :email"),
            {"email": request.email}
        )
        user = result.fetchone()
        
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        user_id, email, password_hash, is_active = user
        
        if not is_active:
            raise HTTPException(
                status_code=401,
                detail="Account disabled"
            )
        
        # Verify password
        if not verify_password(request.password, password_hash):
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        # Generate token
        token = generate_token()
        
        # Update last login
        db.execute(
            text("UPDATE users SET last_login_at = :now WHERE id = :user_id"),
            {"now": datetime.now(timezone.utc), "user_id": user_id}
        )
        db.commit()
        
        return AuthResponse(
            access_token=token,
            user_id=user_id,
            email=email
        )
        
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.get("/me", response_model=UserResponse)
def get_current_user(db: Session = Depends(get_db)):
    """Get current user info - simplified for MVP"""
    try:
        # For MVP, just return the first user if any exists
        result = db.execute(
            text("SELECT id, email, is_active, created_at FROM users ORDER BY id LIMIT 1")
        )
        user = result.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="No user found")
        
        user_id, email, is_active, created_at = user
        
        return UserResponse(
            id=user_id,
            email=email,
            is_active=is_active,
            created_at=created_at
        )
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


@router.get("/status")
def auth_status():
    """Check auth system status"""
    return {
        "status": "ok",
        "message": "Simple auth system for MVP",
        "version": "1.0.0"
    }