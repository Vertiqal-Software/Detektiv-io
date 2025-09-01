#!/usr/bin/env python3
"""
detecktiv.io Startup Script
Performs diagnostics and starts the application with proper error handling
"""
import os
import sys
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv


def print_banner():
    """Print startup banner."""
    print("=" * 60)
    print("🔍 detecktiv.io - UK IT Sales Intelligence Platform")
    print("=" * 60)


def load_environment():
    """Load environment variables from .env file."""
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded environment from {env_file}")
    else:
        print(f"⚠️  No .env file found. Using environment variables.")

    # Show key configuration (without secrets)
    print(f"📋 Configuration:")
    print(f"   POSTGRES_HOST: {os.getenv('POSTGRES_HOST', 'localhost')}")
    print(f"   POSTGRES_PORT: {os.getenv('POSTGRES_PORT', '5432')}")
    print(f"   POSTGRES_DB:   {os.getenv('POSTGRES_DB', 'detecktiv')}")
    print(f"   POSTGRES_USER: {os.getenv('POSTGRES_USER', 'postgres')}")
    print(f"   API_PORT:      {os.getenv('API_PORT', '8000')}")
    # Router inclusion/diagnostic flags
    print(f"   DEBUG:               {os.getenv('DEBUG', 'false')}")
    print(f"   API_ROUTER_DEBUG:    {os.getenv('API_ROUTER_DEBUG', '0')}")
    print(f"   API_STRICT_IMPORTS:  {os.getenv('API_STRICT_IMPORTS', '0')}")


def check_python_dependencies():
    """Check if required Python packages are installed."""
    print("\n🔧 Checking Python dependencies...")

    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "alembic",
        "psycopg2",
        "pydantic",
        "dotenv",  # python-dotenv installs as 'dotenv' module
    ]

    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} - MISSING")
            missing_packages.append(package)

    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Run: pip install -r requirements.txt")
        return False

    print("✅ All required packages are installed")
    return True


def check_database_connection():
    """Test database connectivity."""
    print("\n🔗 Testing database connection...")

    try:
        import psycopg2

        config = {
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "detecktiv"),
        }

        # Try to connect
        conn = psycopg2.connect(**config)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            if result and result[0] == 1:
                print("✅ Database connection successful")
                return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"   Host: {config.get('host')}")
        print(f"   Port: {config.get('port')}")
        print(f"   Database: {config.get('database')}")
        print(f"   User: {config.get('user')}")
        print("\n💡 Troubleshooting tips:")
        print("   1. Make sure PostgreSQL is running")
        print("   2. Check your .env file has correct database settings")
        print("   3. If using Docker: run 'docker compose up -d postgres'")
        print("   4. Test connection with: psql -h localhost -p 5432 -U postgres -d detecktiv")
        return False

    finally:
        try:
            conn.close()  # type: ignore
        except Exception:
            pass


def check_alembic_config():
    """Check Alembic configuration."""
    print("\n📋 Checking Alembic configuration...")

    alembic_ini = Path("alembic.ini")
    if not alembic_ini.exists():
        print("❌ alembic.ini not found")
        return False

    migrations_dir = Path("db/migrations")
    if not migrations_dir.exists():
        print("❌ migrations directory not found")
        return False

    versions_dir = migrations_dir / "versions"
    if not versions_dir.exists():
        print("❌ migrations/versions directory not found")
        return False

    # Count migration files
    migration_files = list(versions_dir.glob("*.py"))
    print(f"✅ Found {len(migration_files)} migration files")

    # OPTIONAL: validate the graph if tool exists
    validator = Path("tools/validate_migrations.py")
    if validator.exists():
        print("🔎 Validating migration graph...")
        try:
            result = subprocess.run(
                [sys.executable, str(validator)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                print("✅ Migration graph OK")
            else:
                print("❌ Migration graph check reported issues:")
                print(result.stdout.strip() or "(no stdout)")
                print(result.stderr.strip() or "(no stderr)")
                # Non-fatal; we still continue to allow dev iteration
        except Exception as e:
            print(f"⚠️  Skipped validate_migrations.py (error: {e})")

    return True


def run_migrations():
    """Run database migrations."""
    print("\n🔄 Running database migrations...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            print("✅ Migrations completed successfully")
            return True
        else:
            print(f"❌ Migration failed:")
            print(f"   STDOUT: {result.stdout.strip()}")
            print(f"   STDERR: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ Migration timed out after 60 seconds")
        return False
    except Exception as e:
        print(f"❌ Migration failed with exception: {e}")
        return False


def _route_exists(app, path: str, method: str | None = None) -> bool:
    """Utility to check if a route (and optional method) is mounted."""
    try:
        for r in app.routes:
            r_path = getattr(r, "path", None)
            if r_path == path:
                if method is None:
                    return True
                methods = getattr(r, "methods", set()) or set()
                if method.upper() in methods:
                    return True
    except Exception:
        pass
    return False


def test_app_import_and_preflight():
    """Test that we can import the main application and check critical routes."""
    print("\n🔍 Testing application import & preflight routes...")

    try:
        from app.main import app
        print("✅ Application import successful")

        # Preflight: confirm key modular routes are mounted
        auth_ok = _route_exists(app, "/v1/auth/login", "POST")
        me_ok = _route_exists(app, "/v1/users/me", "GET")
        print(f"   Preflight /v1/auth/login (POST): {auth_ok}")
        print(f"   Preflight /v1/users/me   (GET) : {me_ok}")

        # Guidance if missing
        if not auth_ok or not me_ok:
            print("⚠️  One or more modular routes are not mounted.")
            print("   Hints:")
            print("   - Ensure app/api/router.py includes app.api.auth and app.api.users")
            print("   - Ensure app/main.py includes the router and/or fallback block")
            print("   - Set API_ROUTER_DEBUG=1 and API_STRICT_IMPORTS=1 in .env for detailed import errors")

        return True
    except Exception as e:
        print(f"❌ Application import failed: {e}")
        print("\n💡 Check for:")
        print("   1. Syntax errors in app/main.py")
        print("   2. Missing dependencies")
        print("   3. Database connection issues")
        return False


def start_application(port=8000, reload=True):
    """Start the FastAPI application with uvicorn."""
    print(f"\n🚀 Starting detecktiv.io API on port {port}...")
    print(f"   Reload mode: {'ON' if reload else 'OFF'}")
    print(f"   URL: http://localhost:{port}")
    print(f"   Health check: http://localhost:{port}/health")
    print(f"   API docs: http://localhost:{port}/docs")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)

    try:
        import uvicorn
        # Use string import to keep reload friendly
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            reload=reload,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server failed to start: {e}")
        return False


def main():
    """Main startup sequence."""
    print_banner()

    # Load environment
    load_environment()

    # Check dependencies
    if not check_python_dependencies():
        sys.exit(1)

    # Test database connection
    if not check_database_connection():
        print("\n💡 To start just PostgreSQL with Docker:")
        print("   docker compose up -d postgres")
        sys.exit(1)

    # Check Alembic configuration (+ optional graph validation)
    if not check_alembic_config():
        sys.exit(1)

    # Run migrations
    if not run_migrations():
        sys.exit(1)

    # Test app import + preflight critical routes
    if not test_app_import_and_preflight():
        sys.exit(1)

    # Get port from environment or argument
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("DEVELOPMENT_MODE", "true").lower() == "true"

    # Start the application
    start_application(port=port, reload=reload)


if __name__ == "__main__":
    main()
