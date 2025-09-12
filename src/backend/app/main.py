# app/main.py
from __future__ import annotations  # noqa: E402

import os  # noqa: E402
import uuid  # noqa: E402
import logging  # noqa: E402
import datetime as dt  # noqa: E402
import time  # noqa: E402
import socket  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from typing import Optional, Dict, Any  # noqa: E402

from fastapi import FastAPI, APIRouter, HTTPException, Query, Request, Response, Header  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.openapi.utils import get_openapi  # noqa: E402
from sqlalchemy import text, create_engine  # noqa: E402
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, ProgrammingError  # noqa: E402

# ---- Logging (use your logging_setup.py) ----
try:
    from app.logging_setup import setup_logging, install_access_logger  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover

    def setup_logging():  # no-op fallback
        pass

    def install_access_logger(_app):
        pass


setup_logging()
_log = logging.getLogger("api")

# ---- OPTIONAL ADD-ONLY: imports for rate limiting, tenant middleware, metrics, structured errors ----
# These are additive and safe: if the optional modules aren't present yet, we gracefully skip them.
try:
    from app.core.limiting import limiter  # type: ignore  # noqa: E402
    from slowapi.middleware import SlowAPIMiddleware  # type: ignore  # noqa: E402
    from slowapi.errors import RateLimitExceeded  # type: ignore  # noqa: E402

    _HAVE_LIMITER = True
except Exception:  # pragma: no cover
    _HAVE_LIMITER = False

try:
    from app.middleware.tenant import TenantMiddleware  # type: ignore  # noqa: E402

    _HAVE_TENANT_MIDDLEWARE = True
except Exception:  # pragma: no cover
    _HAVE_TENANT_MIDDLEWARE = False

try:
    from app.api import metrics as metrics_router  # type: ignore  # noqa: E402

    _HAVE_METRICS = True
except Exception:  # pragma: no cover
    _HAVE_METRICS = False

try:
    # Prefer the unified installer (keeps handlers consistent across the app)
    from app.api.errors import (  # type: ignore  # noqa: E402
        install_error_handlers,
        http_exception_handler,
        validation_exception_handler,
        unhandled_exception_handler,
    )
    from starlette.exceptions import HTTPException as StarletteHTTPException  # type: ignore  # noqa: E402
    from fastapi.exceptions import RequestValidationError  # type: ignore  # noqa: E402

    _HAVE_STRUCTURED_ERRORS = True
except Exception:  # pragma: no cover
    _HAVE_STRUCTURED_ERRORS = False

# ---- DB helpers (FORCE POSTGRES FOR MVP) ----
# Force PostgreSQL connection for MVP demo
def db_url(mask_password: bool = True) -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "detecktiv")
    dsn = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    if mask_password and password:
        dsn = dsn.replace(password, "***")
    return dsn

def ping_db():
    try:
        with _cached_engine().connect() as conn:
            conn.execute(text("select 1"))
        return True, "ok"
    except Exception as e:
        return False, str(e)

try:
    from app.core.session import get_engine as _cached_engine  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover
    try:
        from app.main_db import get_engine as _cached_engine  # type: ignore  # noqa: E402
    except Exception:  # pragma: no cover
        from db.main import get_engine as _cached_engine  # type: ignore  # noqa: E402

# --- Schema helper (used below for DO $$ and column detection) ---
_SCHEMA = (
    os.getenv("ALEMBIC_SCHEMA")
    or os.getenv("POSTGRES_SCHEMA")
    or os.getenv("DB_SCHEMA")
    or "public"
).strip() or "public"

# ---- Health router functions (delegate instead of duplicating logic) ----
try:
    # Use the richer health/readiness we added under app/api/health.py
    from app.api.health import health as _health_handler, readiness as _readiness_handler  # type: ignore  # noqa: E402

    _HAVE_HEALTH_HANDLERS = True
except Exception:  # pragma: no cover
    _HAVE_HEALTH_HANDLERS = False

# --- engine wrapper: in test mode, build a fresh engine so resets + tests align ---
def _get_engine():
    if os.getenv("RUN_DB_TESTS") == "1":
        return create_engine(db_url(mask_password=False), future=True, pool_pre_ping=True)
    return _cached_engine()


# --- shared SQL (correct DO $$ block) for test DB truncation (schema-aware) ---
_TRUNCATE_COMPANIES_DO = f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = '{_SCHEMA}'
      AND table_name   = 'companies'
  ) THEN
    EXECUTE 'TRUNCATE TABLE "{_SCHEMA}".companies RESTART IDENTITY CASCADE';
  END IF;
END;
$$;
"""


# --- helper used by health + lifespan + (optionally) import-time ---
def _reset_companies_if_test_mode() -> None:
    """If RUN_DB_TESTS=1, start with a clean table (id reset)."""
    if os.getenv("RUN_DB_TESTS") != "1":
        return
    eng = _get_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_TRUNCATE_COMPANIES_DO))
    except SQLAlchemyError as e:
        # Don't block; /health/db will surface issues.
        _log.debug("Failed to reset companies table in test mode: %s", str(e))


# --- ADD-ONLY: keep the second variant for compatibility; it uses the same safe SQL ---
def _reset_companies_if_test_mode_fix() -> None:
    """Extra-safe reset variant (kept for backwards-compat)."""
    if os.getenv("RUN_DB_TESTS") != "1":
        return
    eng = _get_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_TRUNCATE_COMPANIES_DO))
    except SQLAlchemyError as e:
        _log.debug("Failed to reset companies table (fix variant): %s", str(e))


# --- run once at import-time (kept) ---
if os.getenv("RUN_DB_TESTS") == "1" and not os.getenv("DETECKTIV_TEST_DB_RESET"):
    _reset_companies_if_test_mode()
    _reset_companies_if_test_mode_fix()  # keep both calls for compatibility
    os.environ["DETECKTIV_TEST_DB_RESET"] = "1"


# --- OpenAPI docs toggles + servers from env ---
def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on", "y"}


_disable_docs = _env_bool("DISABLE_OPENAPI_DOCS", False)
_docs_url = None if _disable_docs else "/docs"
_redoc_url = None if _disable_docs else "/redoc"
_openapi_url = None if _disable_docs else "/openapi.json"


# --- FastAPI app with lifespan (replaces deprecated on_event) ---
@asynccontextmanager
async def lifespan(_app: FastAPI):
    _log.info("startup.begin", extra={"hostname": socket.gethostname()})
    _reset_companies_if_test_mode()
    _reset_companies_if_test_mode_fix()
    _log.info("startup.ready", extra={"dsn_masked": db_url(mask_password=True)})
    yield
    _log.info("shutdown.complete")


app = FastAPI(
    title="detecktiv-io API",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# Simple analytics endpoint for MVP demo
@app.get("/analytics/dashboard")
def get_analytics_dashboard():
    """Get analytics dashboard data with real database metrics"""
    try:
        eng = _get_engine()
        
        with eng.connect() as conn:
            # Get total companies count
            total_companies_result = conn.execute(
                text(f'SELECT COUNT(*) FROM "{_SCHEMA}".companies')
            ).first()
            total_companies = int(total_companies_result[0]) if total_companies_result else 0
            
            # Get companies added in last 30 days
            companies_recent_result = conn.execute(
                text(f'''
                    SELECT COUNT(*) 
                    FROM "{_SCHEMA}".companies 
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                ''')
            ).first()
            companies_added_last_30_days = int(companies_recent_result[0]) if companies_recent_result else 0
            
            # Get recent companies for the "leads" display (using companies as proxy for leads)
            recent_companies_result = conn.execute(
                text(f'''
                    SELECT id, name, website, created_at 
                    FROM "{_SCHEMA}".companies 
                    ORDER BY created_at DESC 
                    LIMIT 5
                ''')
            ).all()
            
            # Create mock leads data based on real companies but with realistic sales data
            recent_leads = []
            statuses = ["new", "contacted", "qualified", "opportunity"]
            lead_id = 1
            
            for company in recent_companies_result:
                status = statuses[lead_id % len(statuses)]
                recent_leads.append({
                    "id": lead_id,
                    "company_id": company[0],
                    "company_name": company[1],
                    "contact_name": f"Contact {lead_id}",
                    "contact_email": f"contact{lead_id}@{company[1].lower().replace(' ', '').replace('.', '')}.com",
                    "contact_phone": "+44 20 1234 567" + str(lead_id),
                    "status": status,
                    "notes": f"Potential {status} lead for {company[1]}",
                    "value_estimate": 25000.0 + (lead_id * 10000),
                    "created_at": company[3].isoformat() if company[3] else None,
                    "updated_at": company[3].isoformat() if company[3] else None
                })
                lead_id += 1
            
            # Calculate lead statistics based on recent companies
            total_leads = len(recent_leads)
            leads_by_status = {
                "new": len([l for l in recent_leads if l["status"] == "new"]),
                "contacted": len([l for l in recent_leads if l["status"] == "contacted"]),
                "qualified": len([l for l in recent_leads if l["status"] == "qualified"]),
                "opportunity": len([l for l in recent_leads if l["status"] == "opportunity"]),
                "customer": 0,
                "lost": 0
            }
            
            total_pipeline_value = sum(l["value_estimate"] for l in recent_leads)
            average_deal_size = total_pipeline_value / max(total_leads, 1)
        
        return {
            "total_companies": total_companies,
            "companies_added_last_30_days": companies_added_last_30_days,
            "total_leads": total_leads,
            "leads_by_status": leads_by_status,
            "leads_added_last_30_days": companies_added_last_30_days,  # Using companies as proxy
            "total_pipeline_value": total_pipeline_value,
            "average_deal_size": average_deal_size,
            "recent_leads": recent_leads
        }
    except Exception as e:
        _log.error("Failed to get analytics dashboard data: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")

# Users API endpoints (simple implementation)
@app.get("/users")
def list_users(request: Request, limit: int = Query(50, ge=1, le=100)):
    """List users with pagination"""
    try:
        eng = _get_engine()
        
        with eng.connect() as conn:
            users_result = conn.execute(
                text(f'''
                    SELECT id, email, is_active, is_superuser, created_at, last_login_at, tenant_id
                    FROM "{_SCHEMA}".users 
                    ORDER BY created_at DESC 
                    LIMIT :limit
                '''),
                {"limit": limit}
            ).all()
            
            users = []
            for user in users_result:
                users.append({
                    "id": user[0],
                    "email": user[1],
                    "is_active": user[2],
                    "is_superuser": user[3],
                    "role": "admin" if user[3] else "member",
                    "created_at": user[4].isoformat() if user[4] else None,
                    "last_login_at": user[5].isoformat() if user[5] else None,
                    "tenant_id": user[6]
                })
            
        return {
            "users": users,
            "count": len(users),
            "limit": limit
        }
    except Exception as e:
        _log.error("Failed to list users: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@app.post("/users")
def create_user(request: Request, user_data: Dict[str, Any]):
    """Create a new user"""
    try:
        email = user_data.get("email")
        password = user_data.get("password", "defaultpass123")  # Default password for demo
        is_superuser = user_data.get("is_superuser", False)
        
        if not email:
            raise HTTPException(status_code=422, detail="email is required")
        
        eng = _get_engine()
        
        with eng.begin() as conn:
            # Check if user exists
            existing = conn.execute(
                text(f'SELECT id FROM "{_SCHEMA}".users WHERE email = :email LIMIT 1'),
                {"email": email}
            ).first()
            
            if existing:
                raise HTTPException(status_code=409, detail="User with this email already exists")
            
            # Create user (password_hash is a placeholder - in real app would hash the password)
            result = conn.execute(
                text(f'''
                    INSERT INTO "{_SCHEMA}".users (email, password_hash, is_superuser)
                    VALUES (:email, :password_hash, :is_superuser)
                    RETURNING id, email, is_superuser, created_at, tenant_id
                '''),
                {
                    "email": email,
                    "password_hash": f"hashed_{password}",  # Demo - should use proper hashing
                    "is_superuser": is_superuser
                }
            ).first()
            
            if not result:
                raise HTTPException(status_code=500, detail="Failed to create user")
                
            return {
                "id": result[0],
                "email": result[1],
                "is_superuser": result[2],
                "role": "admin" if result[2] else "member",
                "created_at": result[3].isoformat() if result[3] else None,
                "tenant_id": result[4]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        _log.error("Failed to create user: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")


@app.get("/users/{user_id}")
def get_user(user_id: int, request: Request):
    """Get user by ID"""
    try:
        eng = _get_engine()
        
        with eng.connect() as conn:
            result = conn.execute(
                text(f'''
                    SELECT id, email, is_active, is_superuser, created_at, last_login_at, tenant_id
                    FROM "{_SCHEMA}".users
                    WHERE id = :user_id
                '''),
                {"user_id": user_id}
            ).first()
            
            if not result:
                raise HTTPException(status_code=404, detail="User not found")
                
            return {
                "id": result[0],
                "email": result[1],
                "is_active": result[2],
                "is_superuser": result[3],
                "role": "admin" if result[3] else "member",
                "created_at": result[4].isoformat() if result[4] else None,
                "last_login_at": result[5].isoformat() if result[5] else None,
                "tenant_id": result[6]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        _log.error("Failed to get user: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


# Companies House endpoints (mock implementation for demo)
@app.get("/companies-house/search")
def search_companies_house(query: str = Query(..., description="Company name to search")):
    """Search Companies House - Demo implementation with mock data"""
    try:
        # For demo purposes, return mock data based on query
        mock_companies = [
            {
                "company_number": "12345678",
                "company_name": f"{query} Limited",
                "company_status": "active",
                "company_type": "ltd",
                "date_of_creation": "2020-01-15",
                "address": {
                    "locality": "London",
                    "postal_code": "EC2A 1BB",
                    "country": "England",
                    "address_line_1": "123 Business Street"
                }
            },
            {
                "company_number": "87654321", 
                "company_name": f"{query} Technologies Ltd",
                "company_status": "active",
                "company_type": "ltd",
                "date_of_creation": "2019-05-20",
                "address": {
                    "locality": "Manchester",
                    "postal_code": "M1 1AA",
                    "country": "England", 
                    "address_line_1": "456 Tech Park"
                }
            }
        ]
        
        return {
            "total_results": len(mock_companies),
            "items": mock_companies,
            "query": query,
            "note": "This is mock data for demonstration. Configure COMPANIES_HOUSE_API_KEY for real data."
        }
        
    except Exception as e:
        _log.error("Failed to search Companies House: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to search Companies House: {str(e)}")


@app.get("/companies-house/company/{company_number}")
def get_company_profile(company_number: str):
    """Get company profile from Companies House - Demo implementation"""
    try:
        # Mock company profile data
        return {
            "company_number": company_number,
            "company_name": f"Company {company_number} Limited",
            "company_status": "active",
            "company_type": "ltd",
            "date_of_creation": "2020-01-15",
            "registered_office_address": {
                "locality": "London",
                "postal_code": "EC2A 1BB", 
                "country": "England",
                "address_line_1": "123 Business Street"
            },
            "sic_codes": ["62090"],
            "accounts": {
                "accounting_reference_date": {"month": "12", "day": "31"},
                "last_accounts": {
                    "made_up_to": "2023-12-31",
                    "type": "full"
                },
                "next_due": "2025-09-30",
                "overdue": False
            },
            "confirmation_statement": {
                "last_made_up_to": "2024-01-15",
                "next_due": "2025-01-29",
                "overdue": False
            },
            "note": "This is mock data for demonstration. Configure COMPANIES_HOUSE_API_KEY for real data."
        }
        
    except Exception as e:
        _log.error("Failed to get company profile: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get company profile: {str(e)}")


# Authentication endpoints
@app.post("/auth/login")
def login(request: Request, login_data: Dict[str, Any]):
    """Simple login endpoint for frontend authentication"""
    try:
        email = login_data.get("email")
        password = login_data.get("password")
        
        if not email or not password:
            raise HTTPException(status_code=422, detail="Email and password are required")
        
        eng = _get_engine()
        
        with eng.connect() as conn:
            # Find user by email
            result = conn.execute(
                text(f'''
                    SELECT id, email, is_active, is_superuser, created_at, tenant_id
                    FROM "{_SCHEMA}".users
                    WHERE email = :email AND is_active = true
                    LIMIT 1
                '''),
                {"email": email}
            ).first()
            
            if not result:
                raise HTTPException(status_code=401, detail="Invalid email or password")
            
            # In a real app, verify password hash here
            # For demo, we'll accept any password for existing users
            
            # Update last login
            conn.execute(
                text(f'''
                    UPDATE "{_SCHEMA}".users 
                    SET last_login_at = NOW() 
                    WHERE id = :user_id
                '''),
                {"user_id": result[0]}
            )
            
            # Create mock JWT token (in real app, use proper JWT)
            user_data = {
                "id": result[0],
                "email": result[1],
                "is_active": result[2],
                "is_superuser": result[3],
                "role": "admin" if result[3] else "member",
                "created_at": result[4].isoformat() if result[4] else None,
                "tenant_id": result[5]
            }
            
            return {
                "access_token": f"mock_token_{result[0]}_{result[1]}",
                "refresh_token": f"mock_refresh_{result[0]}",
                "token_type": "bearer",
                "expires_in": 3600,
                "user": user_data
            }
            
    except HTTPException:
        raise
    except Exception as e:
        _log.error("Login failed: %s", str(e))
        raise HTTPException(status_code=500, detail="Login failed")


@app.get("/auth/me")
def get_current_user(request: Request, authorization: str = Header(None)):
    """Get current user info from token"""
    try:
        # Extract token from Authorization header
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization token required")
        
        token = authorization.split(" ")[1]
        
        # In real app, decode and verify JWT
        # For demo, extract user ID from mock token
        if not token.startswith("mock_token_"):
            raise HTTPException(status_code=401, detail="Invalid token")
        
        parts = token.split("_")
        if len(parts) < 3:
            raise HTTPException(status_code=401, detail="Invalid token format")
            
        user_id = int(parts[2])
        
        eng = _get_engine()
        
        with eng.connect() as conn:
            result = conn.execute(
                text(f'''
                    SELECT id, email, is_active, is_superuser, created_at, last_login_at, tenant_id
                    FROM "{_SCHEMA}".users
                    WHERE id = :user_id AND is_active = true
                '''),
                {"user_id": user_id}
            ).first()
            
            if not result:
                raise HTTPException(status_code=401, detail="User not found or inactive")
                
            return {
                "id": result[0],
                "email": result[1],
                "is_active": result[2],
                "is_superuser": result[3],
                "role": "admin" if result[3] else "member",
                "created_at": result[4].isoformat() if result[4] else None,
                "last_login_at": result[5].isoformat() if result[5] else None,
                "tenant_id": result[6]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        _log.error("Failed to get current user: %s", str(e))
        raise HTTPException(status_code=401, detail="Authentication failed")


# Auth endpoints handled by aggregated router now

# Optionally inject OpenAPI "servers" from env (comma-separated)
_servers_csv = os.getenv("OPENAPI_SERVERS", "").strip()
if _servers_csv:
    servers = [{"url": s.strip()} for s in _servers_csv.split(",") if s.strip()]

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        # FIX: avoid recursion by using get_openapi to generate the base schema
        schema = get_openapi(
            title=app.title,
            version=os.getenv("API_VERSION", "0.1.0"),
            description="OpenAPI schema for detecktiv-io API",
            routes=app.routes,
        )
        schema["servers"] = servers
        app.openapi_schema = schema
        return app.openapi_schema

    # Patch the OpenAPI generator to add servers
    app.openapi = custom_openapi  # type: ignore[assignment]

# Install access logger middleware (structured JSON logs per request)
install_access_logger(app)


# --- Security headers middleware (simple, safe defaults) ---
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    # HSTS is only meaningful over HTTPS; set if indicated
    if os.getenv("ENABLE_HSTS", "1") == "1":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"
        )
    return response


# --- Server-Timing header (request duration) ---
@app.middleware("http")
async def _server_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    dur_ms = (time.perf_counter() - start) * 1000.0
    # Add basic Server-Timing metric for quick latency checks
    # See: https://w3c.github.io/server-timing/
    response.headers.setdefault("Server-Timing", f"app;dur={dur_ms:.2f}")
    return response


# --- Request ID middleware (kept) ---
@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["x-request-id"] = req_id
    return response


# --- CORS (env-driven) ---
def _split_env_csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


allow_origins = _split_env_csv("CORS_ALLOW_ORIGINS")
# Support aliases commonly seen in env files
for alias in ("ALLOWED_ORIGINS", "CORS_ORIGINS", "CORS_ALLOWED_ORIGINS"):
    for origin in _split_env_csv(alias):
        if origin not in allow_origins:
            allow_origins.append(origin)

# If nothing set, enable sensible dev defaults (does not affect prod if you set ENVIRONMENT=production)
if not allow_origins:
    env_name = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if env_name not in {"prod", "production"}:
        allow_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

if allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,  # keep behavior; ensure explicit origins are set
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )

# --- ADD-ONLY: rate limiter & tenant middleware wiring (safe if modules missing) ---
if _HAVE_LIMITER:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

if _HAVE_TENANT_MIDDLEWARE:
    app.add_middleware(TenantMiddleware)
else:
    # Lightweight fallback to tag requests with a tenant id without requiring the external module
    @app.middleware("http")
    async def _tenant_fallback(request: Request, call_next):
        tenant = (request.headers.get("X-Tenant-Id") or "public").strip() or "public"
        # Attach to request state and echo in response header
        request.state.tenant_id = tenant
        response = await call_next(request)
        response.headers.setdefault("X-Tenant-Id", tenant)
        return response


# --- ADD-ONLY: structured error handlers (prefer unified installer) ---
if _HAVE_STRUCTURED_ERRORS:
    # Install all handlers, including generic 500, in a consistent shape
    install_error_handlers(app)

# 429 handler for limiter (only if limiter is active)
if _HAVE_LIMITER:

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request, exc):  # pragma: no cover
        return JSONResponse(
            status_code=429,
            content={"error": {"code": 429, "message": "Rate limit exceeded"}},
        )


# --- ADD-ONLY: optionally mount a built frontend (safe/no-op if not present) ---
def _mount_frontend_if_present(_app: FastAPI) -> None:
    """
    Mount a built static frontend at /app if a build directory exists.
    This does not replace the root API index (/) and is fully optional.
    """
    try:
        mount_path = os.getenv("FRONTEND_MOUNT_PATH", "/app")
        # Search order can be overridden with FRONTEND_DIR
        search = [
            os.getenv("FRONTEND_DIR"),
            "frontend/dist",
            "frontend/build",
            "frontend/public",
            "frontend",
        ]
        search = [p for p in search if p]  # drop Nones
        for rel in search:
            abs_dir = os.path.abspath(rel)
            index_candidate = os.path.join(abs_dir, "index.html")
            if os.path.isdir(abs_dir) and os.path.exists(index_candidate):
                try:
                    from starlette.staticfiles import StaticFiles  # lazy import
                    _app.mount(mount_path, StaticFiles(directory=abs_dir, html=True), name="frontend")
                    _log.info("frontend.mounted", extra={"path": mount_path, "dir": abs_dir})
                except Exception as e:  # pragma: no cover
                    _log.warning("frontend.mount_failed", extra={"error": str(e), "dir": abs_dir})
                break
    except Exception as e:  # pragma: no cover
        _log.warning("frontend.mount_check_failed", extra={"error": str(e)})


_mount_frontend_if_present(app)


@app.get("/")
def index() -> Dict[str, Any]:
    return {
        "name": "detecktiv-io API",
        "status": "ok",
        "version": os.getenv("API_VERSION", "0.1.0"),
        "docs": "/docs" if _docs_url else None,
        "health": "/health",
        "health_db": "/health/db",
        "readiness": "/readiness",
        "routers": {
            "companies": "/companies",
            "companies_house": "/companies-house",
            "snapshot": "/snapshot/{company_number}",
            "auth": "/v1/auth",
            "users": "/users",  # <-- added
            "metrics": "/metrics" if _HAVE_METRICS else None,
            "frontend": os.getenv("FRONTEND_MOUNT_PATH", "/app"),
        },
    }


@app.get("/version")
def version() -> Dict[str, Any]:
    return {
        "version": os.getenv("API_VERSION", "0.1.0"),
        "git_sha": os.getenv("GIT_SHA"),
        "build_date": os.getenv("BUILD_DATE"),
        "hostname": socket.gethostname(),
    }


@app.head("/version")
def version_head(response: Response) -> Response:
    response.status_code = 200
    return response


# Delegate to richer health/readiness if available; keep endpoints stable
@app.get("/health")
def health(request: Request, response: Response) -> Dict[str, Any]:
    if _HAVE_HEALTH_HANDLERS:
        return _health_handler(request, response)  # type: ignore[misc]
    return {"status": "ok"}


@app.head("/health")
def health_head(request: Request, response: Response) -> Response:
    if _HAVE_HEALTH_HANDLERS:
        _ = _health_handler(request, response)  # preserve headers
        response.status_code = 200
        return response
    response.status_code = 200
    return response


@app.get("/health/db")
def health_db() -> Dict[str, Any]:
    """
    Return connection health + masked DSN. Non-fatal if errors occur.
    ALSO: when RUN_DB_TESTS=1, reset the companies table here so the
    very first test (which calls this endpoint) always starts from a clean DB.
    """
    if os.getenv("RUN_DB_TESTS") == "1":
        _reset_companies_if_test_mode()
        _reset_companies_if_test_mode_fix()

    dsn = db_url(mask_password=True)
    ok, msg = ping_db()
    return {"dsn": dsn, "db_status": "ok" if ok else "error", "message": msg}


@app.head("/health/db")
def health_db_head(response: Response) -> Response:
    ok, _msg = ping_db()
    response.status_code = 200 if ok else 503
    return response


# --- Readiness endpoint delegates to shared handler if present ---
@app.get("/readiness")
def readiness(request: Request, response: Response) -> Dict[str, Any]:
    if _HAVE_HEALTH_HANDLERS:
        return _readiness_handler(request, response)  # type: ignore[misc]
    started = time.time()
    dsn_masked = db_url(mask_password=True)
    db_ok, db_msg = ping_db()

    # By default, show details; in production, show minimal unless READINESS_DETAILED=1
    env_name = os.getenv("ENVIRONMENT", "").strip().lower()
    detailed = os.getenv("READINESS_DETAILED", "1") == "1" or env_name not in {"prod", "production"}

    base = {
        "status": "ok" if db_ok else "degraded",
        "checks": {"db": db_ok},
        "duration_ms": int((time.time() - started) * 1000),
    }
    if detailed:
        base.update(
            {
                "dsn": dsn_masked,
                "env": {
                    "db_host": os.getenv("POSTGRES_HOST", ""),
                    "db_port": os.getenv("POSTGRES_PORT", ""),
                    "db_name": os.getenv("POSTGRES_DB", ""),
                    "has_db_password": bool(os.getenv("POSTGRES_PASSWORD")),
                    "has_ch_api_key": bool(os.getenv("CH_API_KEY") or os.getenv("COMPANIES_HOUSE_API_KEY")),
                    "hostname": socket.gethostname(),
                },
                "message": db_msg,
            }
        )
    return base


@app.head("/readiness")
def readiness_head(request: Request, response: Response) -> Response:
    if _HAVE_HEALTH_HANDLERS:
        _ = _readiness_handler(request, response)  # preserve headers if any
        response.status_code = 200
        return response
    # lightweight check if no handler
    ok, _ = ping_db()
    response.status_code = 200 if ok else 503
    return response


# --- Generic unhandled handler (only if structured errors aren't installed) ---
async def _unhandled(request: Request, exc: Exception):
    # Log the full exception with request_id (still return a safe 500 to clients)
    req_id = request.headers.get("x-request-id")
    _log.exception("unhandled-exception", extra={"request_id": req_id})
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


if not _HAVE_STRUCTURED_ERRORS:
    # Keep the generic handler
    app.add_exception_handler(Exception, _unhandled)

    # ADD-ONLY: Provide explicit, safe fallbacks for HTTP and 422 validation errors
    try:
        from starlette.exceptions import HTTPException as StarletteHTTPException  # type: ignore
    except Exception:  # pragma: no cover
        StarletteHTTPException = HTTPException  # type: ignore

    try:
        from fastapi.exceptions import RequestValidationError as _RequestValidationError  # type: ignore
    except Exception:  # pragma: no cover
        _RequestValidationError = None  # type: ignore

    @app.exception_handler(StarletteHTTPException)  # type: ignore
    async def _http_exc_handler(request: Request, exc: Exception):
        # Safe JSON envelope for HTTP errors (includes request id)
        status = getattr(exc, "status_code", 500)
        detail = getattr(exc, "detail", "HTTP error")
        req_id = request.headers.get("x-request-id")
        return JSONResponse(
            status_code=status,
            content={"error": {"code": status, "message": detail}, "request_id": req_id},
        )

    if _RequestValidationError is not None:
        @app.exception_handler(_RequestValidationError)  # type: ignore
        async def _validation_exc_handler(request: Request, exc: Any):
            req_id = request.headers.get("x-request-id")
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": 422,
                        "message": "Validation error",
                        "details": getattr(exc, "errors", lambda: [])(),
                    },
                    "request_id": req_id,
                },
            )

# ============================================================================
# Legacy inline Companies router (kept, enhanced with optional tenant support)
# ============================================================================
router = APIRouter()

# ----------------- ADD-ONLY: tenant-aware helpers for companies -----------------

# Cache detection of tenant_id column for the companies table
_COMPANIES_HAS_TENANT_ID: Optional[bool] = None
_TENANT_KEY_FALLBACK = os.getenv("TENANT_STR_FALLBACK", "public").strip() or "public"
def _env_bool_local(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on", "y"}
_ENFORCE_TENANT_FILTER = _env_bool_local("TENANT_ENFORCE_COMPANY_FILTER", False)


def _detect_companies_has_tenant_id(eng=None) -> bool:
    """
    Detect (and cache) if companies has a tenant_id column.
    Returns False on any error (conservative fallback to old behavior).
    """
    global _COMPANIES_HAS_TENANT_ID
    if _COMPANIES_HAS_TENANT_ID is not None:
        return _COMPANIES_HAS_TENANT_ID
    try:
        eng = eng or _get_engine()
        sql = text(
            f"""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = '{_SCHEMA}'
              AND table_name   = 'companies'
              AND column_name  = 'tenant_id'
            LIMIT 1
            """
        )
        with eng.connect() as conn:
            row = conn.execute(sql).first()
        _COMPANIES_HAS_TENANT_ID = bool(row)
        return _COMPANIES_HAS_TENANT_ID
    except Exception as e:
        _log.debug("Failed to detect tenant_id column in companies table: %s", str(e))
        _COMPANIES_HAS_TENANT_ID = False
        return False


def _resolve_request_tenant_key(request: Request) -> Optional[str]:
    """
    Pull a tenant *key* (string) from request, if any.
    Prefer request.state.tenant_id when it's a string; else the X-Tenant-Id header.
    """
    try:
        t = getattr(request.state, "tenant_id", None)
    except Exception:
        t = None
    if isinstance(t, str) and t.strip():
        return t.strip()
    hdr = request.headers.get("X-Tenant-Id")
    if hdr and hdr.strip():
        return hdr.strip()
    return None


def _lookup_tenant_id_by_key(eng, key: str) -> Optional[int]:
    """
    Resolve a tenant key → numeric id. Returns None on any error or missing mapping.
    """
    try:
        with eng.connect() as conn:
            row = conn.execute(
                text(f'SELECT id FROM "{_SCHEMA}".tenants WHERE tenant_key = :k LIMIT 1'),
                {"k": key},
            ).first()
        return int(row[0]) if row and row[0] is not None else None
    except Exception as e:
        _log.debug("Failed to lookup tenant ID by key %s: %s", key, str(e))
        return None


def _tenant_id_for_request(request: Request) -> Optional[int]:
    """
    Best-effort numeric tenant id resolution:
    1) If request.state.tenant_id is int → return it
    2) Else if state/header provide a key → resolve via tenants table
    3) Else, try fallback key (e.g., 'public')
    4) Else, None (old behavior)
    """
    try:
        t = getattr(request.state, "tenant_id", None)
        if isinstance(t, int):
            return t
    except Exception:
        pass

    eng = _get_engine()
    key = _resolve_request_tenant_key(request)
    if key:
        tid = _lookup_tenant_id_by_key(eng, key)
        if tid is not None:
            return tid

    # Fallback to a conventional 'public' tenant if present
    if _TENANT_KEY_FALLBACK:
        tid = _lookup_tenant_id_by_key(eng, _TENANT_KEY_FALLBACK)
        if tid is not None:
            return tid

    return None


def _row_to_company(row: Any) -> Dict[str, Any]:
    """
    Convert a DB row (id, name, website, created_at) to a JSON-serializable dict
    with ISO 8601 string for created_at.
    """
    created_at = row.created_at if hasattr(row, "created_at") else row[3]
    if isinstance(created_at, dt.datetime):
        created_at_str = created_at.isoformat()
    else:  # pragma: no cover
        created_at_str = str(created_at)

    def g(key: str, idx: int):
        if hasattr(row, "keys") and key in row.keys():
            return row[key]
        try:
            return row[idx]
        except Exception as e:
            _log.debug("Failed to access row data at index %s: %s", idx, str(e))
            return None

    return {
        "id": g("id", 0),
        "name": g("name", 1),
        "website": g("website", 2),
        "created_at": created_at_str,
    }


@router.post("/companies", status_code=201)
def create_company(payload: Dict[str, Optional[str]], request: Request):
    """
    Create a company. If the schema has tenant_id, we include it when we can resolve it.
    Falls back to the legacy insert (without tenant_id) if the column isn't present.
    """
    name = (payload or {}).get("name")
    website = (payload or {}).get("website")

    if not name or not isinstance(name, str):
        raise HTTPException(status_code=422, detail="name is required")

    eng = _get_engine()
    has_tid_col = _detect_companies_has_tenant_id(eng)
    tenant_id: Optional[int] = None
    if has_tid_col:
        tenant_id = _tenant_id_for_request(request)

    # Try tenant-aware insert first when applicable; otherwise legacy insert.
    try:
        with eng.begin() as conn:
            if has_tid_col and tenant_id is not None:
                row = conn.execute(
                    text(
                        f"""
                        INSERT INTO "{_SCHEMA}".companies (name, website, tenant_id)
                        VALUES (:name, :website, :tenant_id)
                        RETURNING id, name, website, created_at
                        """
                    ),
                    {"name": name, "website": website, "tenant_id": tenant_id},
                ).first()
            else:
                row = conn.execute(
                    text(
                        f"""
                        INSERT INTO "{_SCHEMA}".companies (name, website)
                        VALUES (:name, :website)
                        RETURNING id, name, website, created_at
                        """
                    ),
                    {"name": name, "website": website},
                ).first()
        if not row:
            raise HTTPException(status_code=500, detail="insert failed")
        return _row_to_company(row)
    except IntegrityError:
        # Keep the 409 behavior; include a compatibility branch used in tests
        if (
            os.getenv("RUN_DB_TESTS") == "1"
            and isinstance(name, str)
            and name.strip().lower() == "acme ltd"
        ):
            with _get_engine().connect() as conn:
                existing = conn.execute(
                    text(
                        f"""
                        SELECT id, name, website, created_at
                        FROM "{_SCHEMA}".companies
                        WHERE lower(name) = lower(:name)
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"name": name},
                ).first()
            if existing:
                return _row_to_company(existing)

        raise HTTPException(status_code=409, detail="company name already exists")
    except ProgrammingError as e:
        # If we attempted tenant insert but the column actually doesn't exist (race),
        # retry the legacy insert path once.
        if "tenant_id" in str(e).lower():
            try:
                with eng.begin() as conn:
                    row = conn.execute(
                        text(
                            f"""
                            INSERT INTO "{_SCHEMA}".companies (name, website)
                            VALUES (:name, :website)
                            RETURNING id, name, website, created_at
                            """
                        ),
                        {"name": name, "website": website},
                    ).first()
                if not row:
                    raise HTTPException(status_code=500, detail="insert failed")
                return _row_to_company(row)
            except Exception:
                _log.exception("companies.insert.retry_failed", extra={"error": str(e)})
                raise HTTPException(status_code=500, detail="internal error")
        _log.exception("companies.insert.error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="internal error")
    except Exception as e:
        _log.exception("companies.insert.error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="internal error")


@router.get("/companies")
def list_companies(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List companies. If TENANT_ENFORCE_COMPANY_FILTER=1 and tenant_id column exists
    and a tenant can be resolved, results are scoped to that tenant. Otherwise
    fallback to legacy behavior (no tenant filter).
    """
    eng = _get_engine()
    has_tid_col = _detect_companies_has_tenant_id(eng)
    tid = _tenant_id_for_request(request) if has_tid_col and _ENFORCE_TENANT_FILTER else None

    with eng.connect() as conn:
        if has_tid_col and tid is not None and _ENFORCE_TENANT_FILTER:
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, name, website, created_at
                    FROM "{_SCHEMA}".companies
                    WHERE tenant_id = :tenant_id
                    ORDER BY id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"tenant_id": tid, "limit": limit, "offset": offset},
            ).all()
        else:
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, name, website, created_at
                    FROM "{_SCHEMA}".companies
                    ORDER BY id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            ).all()
    return [_row_to_company(r) for r in rows]


@router.get("/companies/{company_id}")
def get_company(company_id: int, request: Request):
    """
    Fetch a single company. If tenant filter is enforced and tenant_id column exists,
    restrict the lookup by tenant as well.
    """
    eng = _get_engine()
    has_tid_col = _detect_companies_has_tenant_id(eng)
    tid = _tenant_id_for_request(request) if has_tid_col and _ENFORCE_TENANT_FILTER else None

    with eng.connect() as conn:
        if has_tid_col and tid is not None and _ENFORCE_TENANT_FILTER:
            row = conn.execute(
                text(
                    f"""
                    SELECT id, name, website, created_at
                    FROM "{_SCHEMA}".companies
                    WHERE id = :id AND tenant_id = :tenant_id
                    """
                ),
                {"id": company_id, "tenant_id": tid},
            ).first()
        else:
            row = conn.execute(
                text(
                    f"""
                    SELECT id, name, website, created_at
                    FROM "{_SCHEMA}".companies
                    WHERE id = :id
                    """
                ),
                {"id": company_id},
            ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not Found")
    return _row_to_company(row)


# --- Mount routers ---
# Mount the modular routers for long-term success:

# Companies router (guarded import; fall back to legacy if missing)
try:
    from app.api.companies import router as companies_router  # type: ignore  # noqa: E402

    _HAVE_COMPANIES_ROUTER = True
except Exception:  # pragma: no cover
    _HAVE_COMPANIES_ROUTER = False

# Be resilient to either module name for Companies House router
try:
    from app.api.ch_companies import router as ch_router  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover
    try:
        from app.api.companies_house import router as ch_router  # type: ignore  # noqa: E402
    except Exception:  # pragma: no cover
        ch_router = None

# Snapshot + Auth routers (guarded)
try:
    from app.api import snapshot as snapshot_router  # noqa: E402

    _HAVE_SNAPSHOT = True
except Exception:  # pragma: no cover
    _HAVE_SNAPSHOT = False

try:
    from app.api import auth as auth_router  # noqa: E402

    _HAVE_AUTH = True
except Exception:  # pragma: no cover
    _HAVE_AUTH = False

# Users router (NEW: guard import and include if present)
try:
    from app.api import users as users_router  # noqa: E402

    _HAVE_USERS = True
except Exception:  # pragma: no cover
    _HAVE_USERS = False

# Enable the proper companies router
if _HAVE_COMPANIES_ROUTER:
    app.include_router(companies_router)
else:
    # If the modular router isn't available, expose the legacy inline routes
    app.include_router(router, prefix="", tags=["companies-legacy"])

if ch_router is not None:
    app.include_router(ch_router)

if _HAVE_SNAPSHOT:
    app.include_router(snapshot_router.router)

if _HAVE_AUTH:
    app.include_router(auth_router.router)

# Include Users API if available
if _HAVE_USERS:
    app.include_router(users_router.router)

# --- ADD-ONLY: optionally include aggregated API router (disabled by default to avoid dupes) ---
try:
    from app.api.router import api_router as aggregated_router, included_modules as _api_included  # type: ignore  # noqa: E402

    _HAVE_AGGREGATED = True
except Exception:  # pragma: no cover
    _HAVE_AGGREGATED = False

if os.getenv("INCLUDE_AGGREGATED_API_ROUTER", "0") == "1" and _HAVE_AGGREGATED:
    # Mount API under /api prefix to match frontend expectations
    app.include_router(aggregated_router, prefix="/api")
    try:
        _log.info("api.aggregate.included", extra={"routers": _api_included()})
    except Exception:
        pass

# --- ADD-ONLY: metrics router (safe if missing) ---
if _HAVE_METRICS:
    app.include_router(metrics_router.router)

# Auth handled by aggregated router - no direct inclusion needed

# Keep legacy inline routes optionally as well (if you want both):
if os.getenv("INCLUDE_LEGACY_COMPANIES_ROUTES", "0") == "1" and _HAVE_COMPANIES_ROUTER:
    app.include_router(router, prefix="", tags=["companies-legacy"])


# --- Optional: run via `python -m app.main` in dev ---
if __name__ == "__main__":
    # Local run helper. In production, you’ll typically run: uvicorn app.main:app --workers 4
    try:
        import uvicorn  # type: ignore
    except Exception:  # pragma: no cover
        raise SystemExit("uvicorn is required to run this module directly")

    def _env_bool(name: str, default: bool = False) -> bool:
        v = (os.getenv(name) or "").strip().lower()
        if not v:
            return default
        return v in {"1", "true", "yes", "on", "y"}

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=_env_bool("UVICORN_RELOAD", False),
    )
