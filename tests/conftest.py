# tests/conftest_enhanced.py
"""
Enhanced test configuration for Detecktiv.io.

This replaces the existing conftest.py with improved fixtures that work with
the new service layer architecture and enhanced database setup.
"""

import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import asyncio  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Generator, AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker, Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import our application components
from app.core.config import settings  # noqa: F401
from app.core.database import get_db_session, get_engine  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.services.company_service import CompanyService  # noqa: E402
from app.schemas.company import CompanyCreate  # noqa: E402

# Test database URL - use a separate test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+psycopg2://{os.getenv('POSTGRES_USER', 'postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD', '')}@"
    f"{os.getenv('POSTGRES_HOST', '127.0.0.1')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/detecktiv_test",
)


def wait_for_db(timeout=30):
    """Wait for the test database to be ready."""
    import psycopg2  # noqa: E402

    # Parse connection parameters from URL
    from urllib.parse import urlparse  # noqa: E402

    parsed = urlparse(TEST_DATABASE_URL)

    conn_params = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "dbname": "postgres",  # Connect to postgres DB first to create test DB
    }

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Test basic connection
            conn = psycopg2.connect(**conn_params)
            conn.close()
            return True
        except Exception:
            time.sleep(0.5)

    return False


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Set up test database and run migrations."""
    # Skip if database tests are not enabled
    if os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("Database tests disabled. Set RUN_DB_TESTS=1 to enable.")

    # Wait for database to be ready
    if not wait_for_db():
        pytest.skip("Test database not available")

    # Import here to avoid issues if database is not available
    import psycopg2  # noqa: E402
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT  # noqa: E402
    from urllib.parse import urlparse  # noqa: E402

    # Parse database URL
    parsed = urlparse(TEST_DATABASE_URL)
    db_name = parsed.path[1:]  # Remove leading '/'

    # Create test database if it doesn't exist
    conn_params = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "dbname": "postgres",
    }

    try:
        conn = psycopg2.connect(**conn_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cursor:
            # Check if test database exists
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cursor.fetchone():
                cursor.execute(f'CREATE DATABASE "{db_name}"')

        conn.close()
    except Exception as e:
        pytest.skip(f"Could not create test database: {e}")

    # Create tables using SQLAlchemy
    engine = create_engine(TEST_DATABASE_URL)
    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        pytest.skip(f"Could not create tables: {e}")
    finally:
        engine.dispose()

    yield

    # Cleanup: Drop test database after all tests
    try:
        conn = psycopg2.connect(**conn_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cursor:
            # Terminate all connections to the test database
            cursor.execute(
                """
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity  # noqa: E402
                WHERE pg_stat_activity.datname = %s
                  AND pid <> pg_backend_pid()
            """,
                (db_name,),
            )

            # Drop test database
            cursor.execute(f'DROP DATABASE IF EXISTS "{db_name}"')

        conn.close()
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture
def db_engine():
    """Provide a database engine for tests."""
    engine = create_engine(
        TEST_DATABASE_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    """
    Provide a database session that rolls back all changes after the test.
    This ensures tests don't interfere with each other.
    """
    connection = db_engine.connect()
    transaction = connection.begin()

    # Create session bound to the connection
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def company_service(db_session: Session) -> CompanyService:
    """Provide a CompanyService instance with test database session."""
    return CompanyService(db_session)


@pytest.fixture
def sample_company_data() -> CompanyCreate:
    """Provide sample company data for tests."""
    return CompanyCreate(
        name="Test Company Ltd",
        website="https://test-company.co.uk",
        email="info@test-company.co.uk",
        phone="+44 20 1234 5678",
        address_line1="123 Test Street",
        address_line2="Suite 100",
        city="London",
        county="Greater London",
        postcode="SW1A 1AA",
        country="GB",
        industry="Technology",
        sic_code="62020",
        employee_count=50,
        annual_revenue=1500000,
        companies_house_number="12345678",
        notes="Sample company for testing",
    )


@pytest.fixture
def created_company(
    company_service: CompanyService, sample_company_data: CompanyCreate
) -> Company:
    """Create a company in the test database and return it."""
    return company_service.create_company(sample_company_data)


@pytest.fixture
def multiple_companies(company_service: CompanyService) -> list[Company]:
    """Create multiple companies for testing list operations."""
    companies = []

    company_data = [
        CompanyCreate(
            name="Alpha Company", country="GB", industry="Technology", is_prospect=True
        ),
        CompanyCreate(
            name="Beta Corp", country="US", industry="Finance", is_prospect=False
        ),
        CompanyCreate(
            name="Gamma Ltd", country="GB", industry="Manufacturing", is_prospect=True
        ),
        CompanyCreate(
            name="Delta Inc", country="CA", industry="Technology", is_prospect=False
        ),
        CompanyCreate(
            name="Epsilon Group", country="GB", industry="Consulting", is_prospect=True
        ),
    ]

    for data in company_data:
        company = company_service.create_company(data)
        companies.append(company)

    return companies


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Provide a test client with database dependency override.
    Uses the test database session.
    """
    from app.main_enhanced import app  # noqa: E402
    from app.core.database import get_db  # noqa: E402

    def get_test_db():
        yield db_session

    # Override the database dependency
    app.dependency_overrides[get_db] = get_test_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Clean up dependency overrides
        app.dependency_overrides.clear()


@pytest.fixture
def client_with_data(
    client: TestClient, multiple_companies: list[Company]
) -> TestClient:
    """Provide a test client with sample data already created."""
    return client


# Async fixtures for testing async services
@pytest_asyncio.fixture
async def async_company_service(db_session: Session) -> CompanyService:
    """Provide an async-compatible CompanyService."""
    return CompanyService(db_session)


@pytest.fixture
def mock_companies_house_response():
    """Mock response data from Companies House API."""
    return {
        "company_name": "Test Company Limited",
        "company_number": "12345678",
        "company_status": "active",
        "date_of_creation": "2020-01-15",
        "registered_office_address": {
            "address_line_1": "123 Test Street",
            "address_line_2": "Suite 200",
            "locality": "London",
            "region": "Greater London",
            "postal_code": "SW1A 1AA",
            "country": "England",
        },
        "sic_codes": ["62020", "62090"],
        "accounts": {"last_accounts": {"made_up_to": "2023-12-31", "type": "full"}},
    }


# Performance testing fixtures
@pytest.fixture
def large_dataset(company_service: CompanyService) -> list[Company]:
    """Create a large dataset for performance testing."""
    companies = []

    for i in range(100):
        company_data = CompanyCreate(
            name=f"Performance Test Company {i:03d}",
            website=f"https://company{i:03d}.com",
            email=f"info@company{i:03d}.com",
            country="GB" if i % 2 == 0 else "US",
            industry="Technology" if i % 3 == 0 else "Finance",
            employee_count=10 + (i * 5),
            annual_revenue=100000 + (i * 50000),
            is_prospect=i % 4 == 0,
        )

        company = company_service.create_company(company_data)
        companies.append(company)

    return companies


# Utility fixtures
@pytest.fixture
def unique_company_name():
    """Generate a unique company name for tests."""
    import uuid  # noqa: E402

    return f"Test Company {uuid.uuid4().hex[:8]}"


@pytest.fixture
def temp_file():
    """Provide a temporary file for testing file operations."""
    import tempfile  # noqa: E402

    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv") as f:
        yield f.name

    # Cleanup
    try:
        os.unlink(f.name)
    except OSError:
        pass


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "api: marks tests as API tests")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Mark tests based on filename patterns
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        elif "unit" in item.nodeid:
            item.add_marker(pytest.mark.unit)
        elif "api" in item.nodeid:
            item.add_marker(pytest.mark.api)

        # Mark slow tests (those that take >5 seconds typically)
        if any(
            marker in item.nodeid for marker in ["large_dataset", "performance", "bulk"]
        ):
            item.add_marker(pytest.mark.slow)
