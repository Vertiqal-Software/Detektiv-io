# app/core/tenant.py
"""
Tenant utilities for backward compatibility.
Re-exports from domain modules.
"""
from __future__ import annotations

from typing import Optional, Dict, Any
import os
import logging

from fastapi import Request

logger = logging.getLogger("api.tenant")

def get_tenant_from_request(request: Request) -> Optional[str]:
    """
    Extract tenant identifier from request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Tenant identifier or None
    """
    # Check header first
    tenant = request.headers.get("X-Tenant-Id")
    if tenant and tenant.strip():
        return tenant.strip()
    
    # Check request state
    try:
        tenant = getattr(request.state, "tenant_id", None)
        if isinstance(tenant, str) and tenant.strip():
            return tenant.strip()
    except Exception:
        pass
    
    return None


def resolve_tenant_id(request: Request) -> Optional[int]:
    """
    Resolve tenant string key to numeric ID.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Tenant ID or None
    """
    try:
        # First check if we already have a numeric ID
        tenant_id = getattr(request.state, "tenant_id", None)
        if isinstance(tenant_id, int):
            return tenant_id
            
        # Try to resolve from string key
        tenant_key = get_tenant_from_request(request)
        if not tenant_key:
            return None
            
        # Import here to avoid circular dependencies
        from app.models.base import SessionLocal
        
        with SessionLocal() as session:
            from sqlalchemy import text
            result = session.execute(
                text("SELECT id FROM tenants WHERE tenant_key = :key LIMIT 1"),
                {"key": tenant_key}
            ).first()
            
            if result:
                return int(result[0])
                
    except Exception as e:
        logger.warning("Failed to resolve tenant ID: %s", e)
    
    return None


def get_default_tenant_id() -> Optional[int]:
    """
    Get the default 'public' tenant ID.
    
    Returns:
        Public tenant ID or None
    """
    try:
        from app.models.base import SessionLocal
        from sqlalchemy import text
        
        with SessionLocal() as session:
            result = session.execute(
                text("SELECT id FROM tenants WHERE tenant_key = 'public' LIMIT 1")
            ).first()
            
            if result:
                return int(result[0])
                
    except Exception as e:
        logger.warning("Failed to get default tenant ID: %s", e)
    
    return None