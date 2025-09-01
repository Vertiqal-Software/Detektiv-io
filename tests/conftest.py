"""
Simplified test configuration for detecktiv.io
Handles database setup and migrations for testing
"""
import os
import sys
import time
import subprocess
from pathlib import Path
import pytest
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def wait_for_database(timeout_seconds=60):
    """Wait for PostgreSQL to be ready for connections."""
    config = {
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', ''),
        'host': os.getenv('POSTGRES_HOST', '127.0.0.1'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'dbname': os.getenv('POSTGRES_DB', 'detecktiv'),
    }
    
    start_time = time.time()
    last_error = None
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Try to connect to the database
            with psycopg2.connect(**config):
                print(f"✓ Database connection successful: {config['host']}:{config['port']}")
                return True
        except Exception as e:
            last_error = e
            print(f"⏳ Waiting for database... ({e})")
            time.sleep(2)
    
    raise RuntimeError(f"Database not ready after {timeout_seconds}s. Last error: {last_error}")


def run_migrations():
    """Run Alembic migrations to ensure database is up to date."""
    repo_root = Path(__file__).parent.parent
    alembic_ini = repo_root / "alembic.ini"
    
    if not alembic_ini.exists():
        raise FileNotFoundError(f"alembic.ini not found at {alembic_ini}")
    
    # Run migrations
    cmd = [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"]
    print(f"Running migrations: {' '.join(cmd)}")
    
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )
    
    if result.returncode != 0:
        print(f"Migration failed!")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        raise RuntimeError("Failed to run database migrations")
    
    print("✓ Database migrations completed successfully")


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """
    Session-wide fixture that:
    1. Waits for database to be ready
    2. Runs migrations
    3. Sets test environment variables
    """
    # Only run if database tests are enabled
    if os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("Database tests disabled. Set RUN_DB_TESTS=1 to enable.")
    
    print("\n" + "="*60)
    print("Setting up test database...")
    print("="*60)
    
    # Wait for database to be ready
    wait_for_database()
    
    # Run migrations
    run_migrations()
    
    print("✓ Test database setup complete")
    print("="*60)
    
    yield
    
    # Cleanup could go here if needed
    print("\n✓ Test database cleanup complete")


@pytest.fixture
def db_connection():
    """Provide a database connection for tests that need it."""
    config = {
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', ''),
        'host': os.getenv('POSTGRES_HOST', '127.0.0.1'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'dbname': os.getenv('POSTGRES_DB', 'detecktiv'),
    }
    
    conn = psycopg2.connect(**config)
    try:
        yield conn
    finally:
        conn.close()


# Configure pytest to show more output
def pytest_configure(config):
    """Configure pytest settings."""
    # Add custom markers
    config.addinivalue_line(
        "markers", 
        "db: mark test as requiring database connection"
    )
    
    # Set test environment
    os.environ["RUN_DB_TESTS"] = "1"