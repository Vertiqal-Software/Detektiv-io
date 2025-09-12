# app/middleware/tenant.py
"""
Tenant resolution middleware.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api.middleware.tenant")


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to resolve tenant from request headers and attach to request state.
    """

    def __init__(
        self, app, default_tenant: str = "public", tenant_header: str = "X-Tenant-Id"
    ):
        super().__init__(app)
        self.default_tenant = default_tenant
        self.tenant_header = tenant_header

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request to resolve tenant.

        Args:
            request: The incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response with tenant headers
        """
        # Extract tenant from header or use default
        tenant_key = request.headers.get(self.tenant_header)
        if not tenant_key or not tenant_key.strip():
            tenant_key = self.default_tenant
        else:
            tenant_key = tenant_key.strip()

        # Attach tenant to request state
        request.state.tenant_id = tenant_key

        # Try to resolve tenant ID if possible
        try:
            tenant_id = self._resolve_tenant_id(tenant_key)
            if tenant_id is not None:
                request.state.tenant_numeric_id = tenant_id
        except Exception as e:
            logger.warning("Failed to resolve tenant ID for %s: %s", tenant_key, e)

        # Process request
        response = await call_next(request)

        # Add tenant to response headers
        response.headers[self.tenant_header] = tenant_key

        return response

    def _resolve_tenant_id(self, tenant_key: str) -> Optional[int]:
        """
        Resolve tenant key to numeric ID.

        Args:
            tenant_key: String tenant identifier

        Returns:
            Numeric tenant ID or None
        """
        try:
            from app.models.base import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as session:
                result = session.execute(
                    text("SELECT id FROM tenants WHERE tenant_key = :key LIMIT 1"),
                    {"key": tenant_key},
                ).first()

                if result:
                    return int(result[0])

        except Exception as e:
            logger.debug("Failed to resolve tenant %s to ID: %s", tenant_key, e)

        return None
