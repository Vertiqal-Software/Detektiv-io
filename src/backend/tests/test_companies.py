"""
API tests for companies endpoints
These tests run against the actual database when RUN_DB_TESTS=1
"""

import os
import uuid
import pytest
from fastapi.testclient import TestClient

# Skip if database tests are disabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Database tests disabled. Set RUN_DB_TESTS=1 to enable.",
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from app.main import app

    return TestClient(app)


def test_health_endpoint(client):
    """Test basic health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "detecktiv-io"


def test_database_health_endpoint(client):
    """Test database health endpoint."""
    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "url" in data
    # Password should be masked in the URL
    assert "***" in data["url"] or not os.getenv("POSTGRES_PASSWORD")


def test_create_company_success(client):
    """Test successful company creation."""
    company_data = {
        "name": f"Test Company {uuid.uuid4().hex[:8]}",
        "website": "https://example.com",
    }

    response = client.post("/companies", json=company_data)
    assert response.status_code == 201

    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == company_data["name"]
    assert data["website"] == company_data["website"]
    assert "created_at" in data

    # Verify we can retrieve the created company
    company_id = data["id"]
    get_response = client.get(f"/companies/{company_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == company_id


def test_create_company_duplicate_name(client):
    """Test that duplicate company names are rejected."""
    company_name = f"Duplicate Test {uuid.uuid4().hex[:8]}"
    company_data = {"name": company_name, "website": "https://example1.com"}

    # Create first company
    response1 = client.post("/companies", json=company_data)
    assert response1.status_code == 201

    # Try to create second company with same name
    company_data["website"] = "https://example2.com"  # Different website, same name
    response2 = client.post("/companies", json=company_data)
    assert response2.status_code == 409
    assert "company name already exists" in response2.json()["detail"]


def test_create_company_without_website(client):
    """Test creating a company without a website."""
    company_data = {"name": f"No Website Company {uuid.uuid4().hex[:8]}"}

    response = client.post("/companies", json=company_data)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == company_data["name"]
    assert data["website"] is None


def test_get_company_not_found(client):
    """Test getting a company that doesn't exist."""
    # Use a very high ID that's unlikely to exist
    response = client.get("/companies/999999")
    assert response.status_code == 404
    assert "Company not found" in response.json()["detail"]


def test_list_companies(client):
    """Test listing companies with pagination."""
    # Create a couple of test companies
    company_names = [
        f"List Test Company 1 {uuid.uuid4().hex[:6]}",
        f"List Test Company 2 {uuid.uuid4().hex[:6]}",
    ]

    created_ids = []
    for name in company_names:
        response = client.post("/companies", json={"name": name})
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Test listing companies
    response = client.get("/companies?limit=10&offset=0")
    assert response.status_code == 200

    companies = response.json()
    assert isinstance(companies, list)
    assert len(companies) >= 2  # At least our test companies

    # Check that our created companies are in the list
    company_ids_in_list = [c["id"] for c in companies]
    for created_id in created_ids:
        assert created_id in company_ids_in_list


def test_list_companies_pagination(client):
    """Test pagination parameters."""
    # Test with limit parameter
    response = client.get("/companies?limit=1")
    assert response.status_code == 200
    companies = response.json()
    assert len(companies) <= 1

    # Test with offset parameter
    response = client.get("/companies?limit=5&offset=0")
    assert response.status_code == 200


def test_create_company_invalid_data(client):
    """Test creating company with invalid data."""
    # Test with missing name
    response = client.post("/companies", json={"website": "https://example.com"})
    assert response.status_code == 422  # Validation error

    # Test with empty name
    response = client.post("/companies", json={"name": ""})
    assert response.status_code == 422  # Validation error


@pytest.mark.skipif(
    os.getenv("DEBUG") != "true", reason="Debug endpoint only available in debug mode"
)
def test_debug_env_endpoint(client):
    """Test debug environment endpoint (only in debug mode)."""
    response = client.get("/debug/env")
    assert response.status_code == 200
    data = response.json()
    assert "POSTGRES_HOST" in data
    assert "DATABASE_URL" in data


# Integration test that exercises multiple endpoints
def test_full_company_workflow(client):
    """Test a complete workflow: create, get, list."""
    company_name = f"Workflow Test {uuid.uuid4().hex[:8]}"

    # 1. Create company
    create_response = client.post(
        "/companies",
        json={"name": company_name, "website": "https://workflow-test.com"},
    )
    assert create_response.status_code == 201
    company = create_response.json()
    company_id = company["id"]

    # 2. Get the specific company
    get_response = client.get(f"/companies/{company_id}")
    assert get_response.status_code == 200
    retrieved_company = get_response.json()
    assert retrieved_company["id"] == company_id
    assert retrieved_company["name"] == company_name

    # 3. Verify it appears in the list
    list_response = client.get("/companies")
    assert list_response.status_code == 200
    companies = list_response.json()
    company_ids = [c["id"] for c in companies]
    assert company_id in company_ids
