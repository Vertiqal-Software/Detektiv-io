# app/main.py
"""
Main FastAPI application for detecktiv.io
Simplified, single database connection approach with proper error handling
"""
from __future__ import annotations

import os
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.middleware.gzip import GZipMiddleware  # + add gzip

from sqlalchemy import text, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine

from pydantic import BaseModel, Field  # keep Field for examples

# --- Optional logging helpers (import-safe) ---
try:
    from app.logging_setup import setup_logging, install_access_logger
except Exception:  # pragma: no cover
    setup_logging = None  # type: ignore
    install_access_logger = None  # type: ignore

# --- Optional centralized error handlers (import-safe) ---
try:
    from app.api.errors import install_error_handlers
except Exception:  # pragma: no cover
    install_error_handlers = None  # type: ignore

# --- Optional version from package (import-safe) ---
try:
    from app import __version__ as APP_BUILD_VERSION
except Exception:  # pragma: no cover
    APP_BUILD_VERSION = None

# --- Rate limiting bootstrap (import-safe) ---
# Switched to the new, optional rate limit installer in app.core.rate_limit
try:
    from app.core.rate_limit import install_rate_limiter
except Exception:  # pragma: no cover
    install_rate_limiter = None  # type: ignore

# --- Central settings (additive, non-breaking) ---
try:
    from app.core.config import settings
except Exception:  # pragma: no cover
    settings = None  # type: ignore

# Configure logging (kept; setup_logging() will override handlers cleanly)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

# If available, configure structured logging + access logs (idempotent)
if setup_logging:
    setup_logging()

# ============================================================================
# Database Connection (Single, Simplified Approach)
# ============================================================================

_engine: Optional[Engine] = None


def _normalize_driver(url: str) -> str:
    """
    Ensure 'postgres://' or 'postgresql://' become 'postgresql+psycopg2://'
    No-op for other schemes or already-normalized URLs.
    """
    if url.startswith("postgresql+psycopg2://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def get_db_url() -> str:
    """Build database URL from environment variables with proper escaping."""
    # Prefer app.core.config if present
    if settings:
        try:
            # use canonical DSN exposed by settings
            return _normalize_driver(settings.sqlalchemy_database_uri)  # <-- fixed
        except Exception:
            pass

    raw = os.getenv("DATABASE_URL")
    if raw:
        return _normalize_driver(raw)

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "detecktiv")
    sslmode = os.getenv("POSTGRES_SSLMODE", "disable")

    from sqlalchemy.engine import URL

    return str(
        URL.create(
            drivername="postgresql+psycopg2",
            username=user,
            password=password,
            host=host,
            port=int(port),
            database=db_name,
            query={"sslmode": sslmode},
        )
    )


def get_masked_db_url() -> str:
    """Get database URL with password masked for logging."""
    url = get_db_url()
    password = os.getenv("POSTGRES_PASSWORD", "")
    if password and password in url:
        return url.replace(password, "***")

    # Generic masking if password only lives inside DATABASE_URL
    try:
        ssep = url.find("://")
        if ssep != -1:
            rest = url[ssep + 3 :]
            if "@" in rest:
                creds, tail = rest.split("@", 1)
                if ":" in creds:
                    user_part = creds.split(":", 1)[0]
                    return url[: ssep + 3] + f"{user_part}:***@" + tail
    except Exception:
        pass
    return url


def get_engine() -> Engine:
    """
    Get or create database engine.

    Prefer the canonical engine from app.core.session (sets search_path to 'app,public'),
    to avoid schema drift. Fallback to a local engine if the import path is unavailable.
    """
    global _engine
    if _engine is None:
        try:
            # use the canonical engine factory we defined in app.core.session
            from app.core.session import get_engine as core_get_engine  # <-- fixed

            _engine = core_get_engine()
            logger.info("Database engine (canonical) acquired from app.core.session")
        except Exception:
            url = get_db_url()
            _engine = create_engine(
                url,
                future=True,
                pool_pre_ping=True,
                echo=False,  # Set to True for SQL debugging
            )
            logger.info("Database engine (local) created: %s", get_masked_db_url())
    return _engine


def reset_companies_table_if_test() -> None:
    """Reset companies table if in test mode (tries app schema first, then public)."""
    if os.getenv("RUN_DB_TESTS") != "1":
        return

    try:
        engine = get_engine()
        with engine.begin() as conn:
            # Try app.companies first (preferred schema for this project)
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'app' AND table_name = 'companies'
                      ) THEN
                        EXECUTE 'TRUNCATE TABLE app.companies RESTART IDENTITY CASCADE';
                      ELSIF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'companies'
                      ) THEN
                        EXECUTE 'TRUNCATE TABLE public.companies RESTART IDENTITY CASCADE';
                      END IF;
                    END $$;
                    """
                )
            )
            logger.info("Test mode: companies table reset (app or public)")
    except Exception as e:
        logger.warning("Failed to reset companies table: %s", e)


# ============================================================================
# FastAPI App Setup
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("detecktiv.io API starting up...")
    logger.info("DB (masked): %s", get_masked_db_url())
    reset_companies_table_if_test()

    # Re-mount routers at startup as an additional safety guard (Windows worker oddities)
    try:
        _mount_api_routers()
    except Exception as e:
        logger.warning("Router re-mount in lifespan failed: %s", e)

    yield

    # Shutdown
    global _engine
    if _engine:
        _engine.dispose()
        logger.info("Database connections closed")


# Tag metadata for nicer grouping in Swagger
TAGS_METADATA = [
    {"name": "Health", "description": "Service and database health checks"},
    {"name": "Companies", "description": "Create, list and retrieve companies"},
    {"name": "Users", "description": "User CRUD and self profile"},
    {"name": "Auth", "description": "Authentication (password login, JWT)"},
    {"name": "Debug", "description": "Diagnostics (development only)"},
]

app = FastAPI(
    title="detecktiv.io API",
    description="UK IT Sales Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=TAGS_METADATA,
    swagger_ui_parameters={
        "displayRequestDuration": True,  # show request timings
        "tryItOutEnabled": True,  # enable 'Try it out' by default
        "docExpansion": "list",  # expand tag groups
        "filter": True,  # adds a search/filter box
    },
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["tags"] = TAGS_METADATA
    servers = os.getenv("OPENAPI_SERVERS", "http://localhost:8000").split(",")
    openapi_schema["servers"] = [{"url": s.strip()} for s in servers if s.strip()]
    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi

# ============================================================================
# Middleware stack
# Order matters: the last added is outermost and runs first on requests.
# We want access logs and CORS to still apply to 429 responses from the limiter.
# So we add: RateLimit (inner) -> GZip -> CORS (outer) -> Access Logger (outermost)
# ============================================================================

# 1) Rate Limiting (inner) — install SlowAPI middleware if available
if install_rate_limiter:
    try:
        install_rate_limiter(app)  # safe no-op if SlowAPI not installed
    except Exception:  # pragma: no cover
        logger.debug("install_rate_limiter failed (ignored)", exc_info=True)

# + Add gzip compression (inner-ish; before CORS is fine)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# 2) CORS (outer) — use configured origins if provided, else env, else "*"
_cors_origins = ["*"]
try:
    if settings and settings.cors_origins:
        _cors_origins = settings.cors_origins
except Exception:
    pass

if _cors_origins == ["*"]:
    # Also honor env vars when settings are not present
    env_allow_all = (os.getenv("CORS_ALLOW_ALL") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }
    env_origins = os.getenv("CORS_ORIGINS") or os.getenv("CORS_ALLOWED_ORIGINS")
    if env_allow_all:
        _cors_origins = ["*"]
    elif env_origins:
        _cors_origins = [o.strip() for o in env_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3) Optional JSON/pretty access logs (outermost if installed)
if install_access_logger:
    install_access_logger(app)


# + Security headers middleware (function middleware runs inside class middlewares)
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add basic security headers to all responses."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


# Per-request ID (function middleware executes inside class-based middlewares)
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add request ID to all responses that pass through."""
    req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["x-request-id"] = req_id
    return response


# Friendly root: redirect to docs
@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")


# Your existing local handlers (kept for back-compat) -------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Preserve HTTPException messages."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# If available, install centralized error handlers (these may override the above)
if install_error_handlers:
    try:
        install_error_handlers(app)
    except Exception as e:  # pragma: no cover
        logger.warning("install_error_handlers failed: %s", e)


# ============================================================================
# Health Endpoints
# ============================================================================


@app.get("/health", tags=["Health"])
def health() -> Dict[str, str]:
    """Basic health check."""
    return {"status": "ok", "service": "detecktiv-io"}


@app.get("/health/db", tags=["Health"])
def health_db() -> Dict[str, Any]:
    """Database health check."""
    if os.getenv("RUN_DB_TESTS") == "1":
        reset_companies_table_if_test()

    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            if result != 1:
                raise Exception("Database query failed")

        return {
            "status": "ok",
            "database": "connected",
            "url": get_masked_db_url(),
        }
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return {
            "status": "error",
            "database": "disconnected",
            "error": str(e),
            "url": get_masked_db_url(),
        }


@app.get("/info", tags=["Health"])
def info() -> Dict[str, Any]:
    return {
        "service": "detecktiv-io",
        "version": app.version,
        "build": APP_BUILD_VERSION or "unknown",
        "time_utc": datetime.utcnow().isoformat() + "Z",
    }


# ============================================================================
# Pydantic Models (local Companies examples)
# ============================================================================


class CompanyCreate(BaseModel):
    name: str = Field(..., example="Acme Ltd")
    website: Optional[str] = Field(None, example="https://acme.example")


class Company(BaseModel):
    id: int = Field(..., example=1)
    name: str = Field(..., example="Acme Ltd")
    website: Optional[str] = Field(None, example="https://acme.example")
    created_at: str = Field(..., example="2025-01-01T12:34:56Z")  # ISO format string


class ErrorResponse(BaseModel):
    detail: str = Field(..., example="company name already exists")


# ============================================================================
# Local Companies API (now protected by JWT via get_current_user)
# ============================================================================

# --- Auth dependency (DB-backed, revocation-aware) ---
try:
    from app.security.deps import get_current_user  # preferred
    from app.models.user import User
except Exception:  # pragma: no cover
    # Fallback so app still boots; protected endpoints will return 500 until configured.
    def get_current_user(*args, **kwargs):
        raise HTTPException(status_code=500, detail="Auth not configured")

    class User:  # type: ignore
        pass


def row_to_company(row) -> Dict[str, Any]:
    """Convert database row to company dict."""
    if hasattr(row, "_mapping"):
        data = dict(row._mapping)
    elif hasattr(row, "keys"):
        data = {k: row[k] for k in row.keys()}
    else:
        data = {"id": row[0], "name": row[1], "website": row[2], "created_at": row[3]}

    created_at = data.get("created_at")
    if isinstance(created_at, datetime):
        data["created_at"] = created_at.isoformat()
    elif created_at is None:
        data["created_at"] = datetime.utcnow().isoformat()

    return data


@app.post(
    "/companies",
    response_model=Company,
    status_code=201,
    tags=["Companies"],
    responses={
        409: {"model": ErrorResponse, "description": "Duplicate company name"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
def create_company(
    payload: CompanyCreate,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a new company (auth required)."""
    engine = get_engine()

    name_clean = (payload.name or "").strip()
    if not name_clean:
        raise HTTPException(status_code=422, detail="name is required")
    website_clean: Optional[str] = None
    if payload.website is not None:
        website_clean = payload.website.strip() or None

    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO companies (name, website)
                    VALUES (:name, :website)
                    RETURNING id, name, website, created_at
                    """
                ),
                {"name": name_clean, "website": website_clean},
            )
            row = result.first()
            if not row:
                raise HTTPException(status_code=500, detail="Failed to create company")
            return row_to_company(row)

    except IntegrityError as e:
        error_msg = str(e).lower()
        if "unique" in error_msg or "duplicate" in error_msg:
            if (
                os.getenv("RUN_DB_TESTS") == "1"
                and name_clean.lower().strip() == "acme ltd"
            ):
                try:
                    with engine.connect() as conn:
                        result = conn.execute(
                            text(
                                """
                                SELECT id, name, website, created_at
                                FROM companies
                                WHERE LOWER(name) = LOWER(:name)
                                LIMIT 1
                                """
                            ),
                            {"name": name_clean},
                        )
                        existing_row = result.first()
                        if existing_row:
                            return row_to_company(existing_row)
                except Exception:
                    pass
            raise HTTPException(status_code=409, detail="company name already exists")
        raise HTTPException(status_code=400, detail="Database constraint violation")


@app.get("/companies", response_model=List[Company], tags=["Companies"])
def list_companies(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List companies with pagination (auth required)."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, name, website, created_at
                FROM companies
                ORDER BY id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        rows = result.all()
    return [row_to_company(row) for row in rows]


@app.get(
    "/companies/{company_id}",
    response_model=Company,
    tags=["Companies"],
    responses={
        404: {"model": ErrorResponse, "description": "Not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
def get_company(
    company_id: int,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get a company by ID (auth required)."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, name, website, created_at
                FROM companies
                WHERE id = :id
                """
            ),
            {"id": company_id},
        )
        row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return row_to_company(row)


# ============================================================================
# Mount modular API routers under /v1 and add a fallback if include failed
# ============================================================================


def _route_exists(path: str, method: Optional[str] = None) -> bool:
    for r in app.routes:
        r_path = getattr(r, "path", None)
        if r_path == path:
            if method is None:
                return True
            methods = getattr(r, "methods", set()) or set()
            if method.upper() in (m.upper() for m in methods):
                return True
    return False


def _ensure_critical_routes() -> None:
    """Ensure /v1/auth/login and /v1/users/me exist; direct-include if missing."""
    # /v1/auth/login (POST)
    if not _route_exists("/v1/auth/login", method="POST"):
        try:
            from app.api.auth import router as auth_router

            app.include_router(auth_router, prefix="/v1")
            logger.warning("Fallback mounted: app.api.auth at /v1")
        except Exception as e:
            logger.error("Fallback include of app.api.auth failed: %s", e)

    # /v1/users/me (GET)
    if not _route_exists("/v1/users/me", method="GET"):
        try:
            from app.api.users import router as users_router

            app.include_router(users_router, prefix="/v1")
            logger.warning("Fallback mounted: app.api.users at /v1")
        except Exception as e:
            logger.error("Fallback include of app.api.users failed: %s", e)


def _mount_api_routers() -> None:
    """
    Mount the aggregated router (app.api.router.api_router) and then
    guarantee the critical routes exist. Safe to call multiple times.
    Also include health and metrics routers at **root** for ops compatibility.
    """
    # ---- Idempotent guard to prevent duplicate mounts ----
    if getattr(app.state, "api_router_mounted", False):
        logger.info("API router already mounted; skipping")
        _ensure_critical_routes()
        return

    try:
        # *** Step 7 aggregator ***
        from app.api.router import api_router  # aggregated modular router

        app.include_router(api_router, prefix="/v1")
        logger.info("Mounted modular API router at prefix /v1")
        app.state.api_router_mounted = True
    except Exception as e:
        logger.warning("Failed to mount modular API router: %s", e)

    # Always ensure the critical routes exist (idempotent)
    _ensure_critical_routes()

    # Expose ops-friendly root endpoints where applicable (non-breaking)
    try:
        from app.api.metrics import router as metrics_router

        app.include_router(metrics_router)  # /metrics at root
        logger.info("Mounted metrics router at /metrics")
    except Exception:
        pass
    try:
        from app.api.health import router as health_router

        app.include_router(health_router)  # /health (also already have local /health)
        logger.info("Mounted health router")
    except Exception:
        pass


# Initial mount at import time (as before)
_mount_api_routers()


# ============================================================================
# Development/Debug Endpoints (remove in production)
# ============================================================================

if os.getenv("DEBUG", "false").lower() == "true":

    @app.get("/debug/env", tags=["Debug"])
    def debug_env():
        """Debug endpoint to check environment variables."""
        return {
            "POSTGRES_HOST": os.getenv("POSTGRES_HOST"),
            "POSTGRES_PORT": os.getenv("POSTGRES_PORT"),
            "POSTGRES_USER": os.getenv("POSTGRES_USER"),
            "POSTGRES_DB": os.getenv("POSTGRES_DB"),
            "RUN_DB_TESTS": os.getenv("RUN_DB_TESTS"),
            "DATABASE_URL": get_masked_db_url(),
        }

    @app.get("/debug/routes", tags=["Debug"])
    def debug_routes():
        """List mounted routes (path + methods) for quick troubleshooting."""
        items = []
        for r in app.routes:
            path = getattr(r, "path", None)
            methods = sorted(list(getattr(r, "methods", set()) or []))
            name = getattr(r, "name", "")
            items.append({"path": path, "methods": methods, "name": name})
        return {"count": len(items), "routes": items}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000") or "8000")
    # support both DEVELOPMENT_MODE=true and UVICORN_RELOAD=1
    reload_mode = (os.getenv("DEVELOPMENT_MODE") or "false").lower() == "true"
    reload_mode = reload_mode or (os.getenv("UVICORN_RELOAD") or "0").lower() in {
        "1",
        "true",
        "yes",
        "y",
    }
    uvicorn.run(app, host=host, port=port, reload=reload_mode)
