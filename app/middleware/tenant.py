# app/middleware/tenant.py
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant = (request.headers.get("X-Tenant-Id") or "public").strip() or "public"
        # Attach to request for downstream use and add to response headers
        request.state.tenant_id = tenant
        response = await call_next(request)
        response.headers.setdefault("X-Tenant-Id", tenant)
        return response
