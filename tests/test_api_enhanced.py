# tests/test_api_enhanced.py
import pytest
import os
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main_enhanced import app
from app.core.database import get_db, get_db_session
from app.models.company import Company

# Skip tests if database testing is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB tests disabled. Set RUN_DB_TESTS=1 to enable.",
)


@pytest.fixture
def db_session():
    """Provide a test database session with rollback."""
    with get_db_session() as session:
        # Start a savepoint
        savepoint = session.begin_nested()

        try:
            yield session
        finally:
            # Always rollback
            savepoint.rollback()


@pytest.fixture
def client(db_session: Session):
    """Provide a test client with database dependency override."""

    def get_test_db():
        return db_session

    app.dependency_overrides[get_db] = get_test_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_basic_health(self, client: TestClient):
        """Test basic health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "detecktiv-api"

    def test_database_health(self, client: TestClient):
        """Test database health check endpoint."""
        response = client.get("/health/db")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "database" in data
        assert data["database"]["connected"] is True

    def test_readiness_check(self, client: TestClient):
        """Test readiness endpoint."""
        response = client.get("/health/ready")

        # Should be 200 or 503 depending on services availability
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]


class TestCompanyEndpoints:
    """Test company CRUD endpoints."""

    def test_create_company_minimal(self, client: TestClient):
        """Test creating a company with minimal required data."""
        company_data = {"name": "Test Company Ltd"}

        response = client.post("/companies", json=company_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Company Ltd"
        assert "id" in data
        assert "created_at" in data
        assert data["country"] == "GB"  # Default value
        assert data["is_prospect"] is False

    def test_create_company_full_data(self, client: TestClient):
        """Test creating a company with comprehensive data."""
        company_data = {
            "name": "Full Data Company Ltd",
            "website": "https://example.com",
            "email": "contact@example.com",
            "phone": "+44 20 1234 5678",
            "address_line1": "123 Business Street",
            "address_line2": "Suite 100",
            "city": "London",
            "county": "Greater London",
            "postcode": "SW1A 1AA",
            "country": "GB",
            "industry": "Technology",
            "sic_code": "62020",
            "employee_count": 50,
            "annual_revenue": 1000000,
            "companies_house_number": "12345678",
            "notes": "Important client",
        }

        response = client.post("/companies", json=company_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Full Data Company Ltd"
        assert data["website"] == "https://example.com"
        assert data["email"] == "contact@example.com"
        assert data["industry"] == "Technology"
        assert data["employee_count"] == 50
        assert data["companies_house_number"] == "12345678"

    def test_create_company_duplicate_name(self, client: TestClient):
        """Test creating company with duplicate name returns 409."""
        company_name = f"Duplicate Company {uuid.uuid4().hex[:8]}"
        company_data = {"name": company_name}

        # Create first company
        response1 = client.post("/companies", json=company_data)
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = client.post("/companies", json=company_data)
        assert response2.status_code == 409
        error_data = response2.json()
        assert "already exists" in error_data["detail"]

    def test_create_company_invalid_data(self, client: TestClient):
        """Test creating company with invalid data returns 422."""
        # Missing required name field
        response = client.post("/companies", json={})
        assert response.status_code == 422

        # Invalid email format
        response = client.post(
            "/companies", json={"name": "Test Company", "email": "invalid-email"}
        )
        assert response.status_code == 422

        # Negative employee count
        response = client.post(
            "/companies", json={"name": "Test Company", "employee_count": -5}
        )
        assert response.status_code == 422

    def test_get_company_by_id(self, client: TestClient):
        """Test retrieving a company by ID."""
        # Create a company first
        company_data = {"name": "Retrievable Company"}
        create_response = client.post("/companies", json=company_data)
        assert create_response.status_code == 201
        created_company = create_response.json()

        # Retrieve the company
        response = client.get(f"/companies/{created_company['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == created_company["id"]
        assert data["name"] == "Retrievable Company"

    def test_get_company_not_found(self, client: TestClient):
        """Test retrieving non-existent company returns 404."""
        response = client.get("/companies/99999")

        assert response.status_code == 404
        error_data = response.json()
        assert "not found" in error_data["detail"]

    def test_update_company(self, client: TestClient):
        """Test updating an existing company."""
        # Create a company
        company_data = {"name": "Updateable Company"}
        create_response = client.post("/companies", json=company_data)
        created_company = create_response.json()

        # Update the company
        update_data = {
            "name": "Updated Company Name",
            "industry": "Updated Industry",
            "is_prospect": True,
            "prospect_stage": "qualified",
        }

        response = client.put(f"/companies/{created_company['id']}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Company Name"
        assert data["industry"] == "Updated Industry"
        assert data["is_prospect"] is True
        assert data["prospect_stage"] == "qualified"
        assert data["updated_at"] is not None

    def test_update_company_not_found(self, client: TestClient):
        """Test updating non-existent company returns 404."""
        update_data = {"name": "New Name"}
        response = client.put("/companies/99999", json=update_data)

        assert response.status_code == 404

    def test_delete_company(self, client: TestClient):
        """Test deleting a company."""
        # Create a company
        company_data = {"name": "Deletable Company"}
        create_response = client.post("/companies", json=company_data)
        created_company = create_response.json()

        # Delete the company
        response = client.delete(f"/companies/{created_company['id']}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/companies/{created_company['id']}")
        assert get_response.status_code == 404

    def test_list_companies_basic(self, client: TestClient):
        """Test listing companies with basic pagination."""
        # Create several test companies
        for i in range(5):
            client.post("/companies", json={"name": f"List Test Company {i}"})

        # List companies
        response = client.get("/companies?limit=3&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert "companies" in data
        assert "total_count" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert len(data["companies"]) <= 3
        assert data["total_count"] >= 5
        assert data["page_size"] == 3

    def test_list_companies_with_filters(self, client: TestClient):
        """Test listing companies with filters."""
        # Create companies with different attributes
        client.post(
            "/companies",
            json={
                "name": "UK Tech Company Filter Test",
                "country": "GB",
                "industry": "Technology",
            },
        )
        client.post(
            "/companies",
            json={
                "name": "US Finance Company Filter Test",
                "country": "US",
                "industry": "Finance",
            },
        )

        # Filter by country
        response = client.get("/companies?country=GB")
        assert response.status_code == 200
        data = response.json()
        uk_companies = [c for c in data["companies"] if c.get("country") == "GB"]
        assert len(uk_companies) >= 1

        # Filter by industry
        response = client.get("/companies?industry=tech")
        assert response.status_code == 200
        data = response.json()
        tech_companies = [
            c for c in data["companies"] if "Technology" in (c.get("industry") or "")
        ]
        assert len(tech_companies) >= 1

    def test_search_companies(self, client: TestClient):
        """Test company search endpoint."""
        # Create a searchable company
        search_term = f"Searchable{uuid.uuid4().hex[:6]}"
        client.post(
            "/companies",
            json={
                "name": f"{search_term} Software Ltd",
                "website": f"https://{search_term.lower()}.com",
                "email": f"info@{search_term.lower()}.com",
            },
        )

        # Search by name
        search_data = {"query": search_term, "limit": 10}

        response = client.post("/companies/search", json=search_data)

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == search_term
        assert "companies" in data
        assert "result_count" in data
        assert data["result_count"] >= 1

        # Verify search results contain the term
        found = any(search_term in company["name"] for company in data["companies"])
        assert found


class TestStatsEndpoints:
    """Test statistics endpoints."""

    def test_get_stats(self, client: TestClient):
        """Test getting application statistics."""
        # Create some test data with different attributes
        client.post(
            "/companies",
            json={"name": "Stats Test Company 1", "country": "GB", "is_prospect": True},
        )
        client.post(
            "/companies",
            json={
                "name": "Stats Test Company 2",
                "country": "US",
                "companies_house_number": "12345678",
            },
        )

        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_companies" in data
        assert "prospects" in data
        assert "companies_house_linked" in data
        assert "by_country" in data

        # Verify counts are reasonable
        assert data["total_companies"] >= 2
        assert data["prospects"] >= 1
        assert data["companies_house_linked"] >= 1
        assert len(data["by_country"]) >= 1


class TestValidationAndErrors:
    """Test input validation and error handling."""

    def test_invalid_json(self, client: TestClient):
        """Test sending invalid JSON returns appropriate error."""
        response = client.post(
            "/companies",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def test_missing_content_type(self, client: TestClient):
        """Test sending data without proper content type."""
        response = client.post("/companies", data='{"name": "Test Company"}')

        # Should still work with FastAPI's automatic content type detection
        assert response.status_code in [201, 422]

    def test_request_id_header(self, client: TestClient):
        """Test that request ID is returned in response headers."""
        custom_request_id = "test-request-123"

        response = client.get("/health", headers={"x-request-id": custom_request_id})

        assert response.status_code == 200
        assert response.headers["x-request-id"] == custom_request_id

    def test_cors_headers(self, client: TestClient):
        """Test CORS headers are present."""
        response = client.options("/health")

        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers

    def test_large_payload_handling(self, client: TestClient):
        """Test handling of reasonably large payloads."""
        # Create a company with a large notes field
        large_notes = "x" * 10000  # 10KB of text

        company_data = {"name": "Large Payload Company", "notes": large_notes}

        response = client.post("/companies", json=company_data)

        assert response.status_code == 201
        data = response.json()
        assert len(data["notes"]) == 10000


class TestAPIDocumentation:
    """Test API documentation endpoints."""

    def test_openapi_schema_available(self, client: TestClient):
        """Test OpenAPI schema is accessible in development."""
        response = client.get("/openapi.json")

        # Should be available in test/development mode
        if response.status_code == 200:
            data = response.json()
            assert "openapi" in data
            assert "info" in data
            assert data["info"]["title"] == "Detecktiv.io API"

    def test_docs_endpoints(self, client: TestClient):
        """Test documentation endpoints."""
        # Swagger UI
        response = client.get("/docs")
        if response.status_code == 200:
            assert (
                "swagger" in response.text.lower() or "openapi" in response.text.lower()
            )

        # ReDoc
        response = client.get("/redoc")
        if response.status_code == 200:
            assert "redoc" in response.text.lower()
