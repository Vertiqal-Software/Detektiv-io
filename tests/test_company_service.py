# tests/test_company_service.py
import pytest
import os
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.models.company import Company
from app.services.company_service import (
    CompanyService,
    CompanyNotFoundError,
    CompanyExistsError,
)
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyFilter

# Skip tests if database testing is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB tests disabled. Set RUN_DB_TESTS=1 to enable.",
)


@pytest.fixture
def db_session():
    """Provide a database session for testing with transaction rollback."""
    with get_db_session() as session:
        # Start a savepoint for isolation
        savepoint = session.begin_nested()

        try:
            yield session
        finally:
            # Always rollback the savepoint
            savepoint.rollback()


@pytest.fixture
def company_service(db_session: Session):
    """Provide a CompanyService instance with test database session."""
    return CompanyService(db_session)


class TestCompanyService:
    """Test cases for CompanyService."""

    def test_create_company_minimal(self, company_service: CompanyService):
        """Test creating a company with minimal required data."""
        company_data = CompanyCreate(name="Test Company Ltd")

        company = company_service.create_company(company_data)

        assert company.id is not None
        assert company.name == "Test Company Ltd"
        assert company.data_source == "manual"
        assert company.country == "GB"  # Default value
        assert company.is_prospect is False  # Default value
        assert isinstance(company.created_at, datetime)

    def test_create_company_full_data(self, company_service: CompanyService):
        """Test creating a company with full data set."""
        company_data = CompanyCreate(
            name="Full Data Company Ltd",
            website="https://example.com",
            email="contact@example.com",
            phone="+44 20 1234 5678",
            address_line1="123 Business Street",
            address_line2="Suite 100",
            city="London",
            county="Greater London",
            postcode="SW1A 1AA",
            country="GB",
            industry="Technology",
            sic_code="62020",
            employee_count=50,
            annual_revenue=1000000,
            companies_house_number="12345678",
            notes="Important client",
        )

        company = company_service.create_company(company_data)

        assert company.name == "Full Data Company Ltd"
        assert company.website == "https://example.com"
        assert company.email == "contact@example.com"
        assert company.phone == "+44 20 1234 5678"
        assert company.address_line1 == "123 Business Street"
        assert company.city == "London"
        assert company.postcode == "SW1A 1AA"
        assert company.industry == "Technology"
        assert company.employee_count == 50
        assert company.annual_revenue == 1000000
        assert company.companies_house_number == "12345678"

    def test_create_company_duplicate_name(self, company_service: CompanyService):
        """Test that creating a company with duplicate name raises error."""
        company_data = CompanyCreate(name="Duplicate Company")

        # Create first company
        company_service.create_company(company_data)

        # Try to create second company with same name
        with pytest.raises(CompanyExistsError, match="already exists"):
            company_service.create_company(company_data)

    def test_get_company_by_id_exists(self, company_service: CompanyService):
        """Test retrieving an existing company by ID."""
        company_data = CompanyCreate(name="Findable Company")
        created_company = company_service.create_company(company_data)

        retrieved_company = company_service.get_company_by_id(created_company.id)

        assert retrieved_company.id == created_company.id
        assert retrieved_company.name == "Findable Company"

    def test_get_company_by_id_not_found(self, company_service: CompanyService):
        """Test retrieving a non-existent company raises error."""
        with pytest.raises(CompanyNotFoundError, match="not found"):
            company_service.get_company_by_id(99999)

    def test_get_company_by_name(self, company_service: CompanyService):
        """Test retrieving a company by name (case-insensitive)."""
        company_data = CompanyCreate(name="Named Company Ltd")
        created_company = company_service.create_company(company_data)

        # Test exact match
        found = company_service.get_company_by_name("Named Company Ltd")
        assert found is not None
        assert found.id == created_company.id

        # Test case-insensitive match
        found = company_service.get_company_by_name("NAMED COMPANY LTD")
        assert found is not None
        assert found.id == created_company.id

        # Test not found
        found = company_service.get_company_by_name("Non-existent Company")
        assert found is None

    def test_update_company(self, company_service: CompanyService):
        """Test updating an existing company."""
        # Create company
        company_data = CompanyCreate(name="Updateable Company")
        company = company_service.create_company(company_data)

        # Update company
        update_data = CompanyUpdate(
            name="Updated Company Name",
            website="https://updated.com",
            industry="Updated Industry",
        )

        updated_company = company_service.update_company(company.id, update_data)

        assert updated_company.id == company.id
        assert updated_company.name == "Updated Company Name"
        assert updated_company.website == "https://updated.com"
        assert updated_company.industry == "Updated Industry"
        assert updated_company.updated_at is not None

    def test_update_company_not_found(self, company_service: CompanyService):
        """Test updating a non-existent company raises error."""
        update_data = CompanyUpdate(name="New Name")

        with pytest.raises(CompanyNotFoundError):
            company_service.update_company(99999, update_data)

    def test_update_company_duplicate_name(self, company_service: CompanyService):
        """Test updating company to duplicate name raises error."""
        # Create two companies
        company1 = company_service.create_company(  # noqa: F841
            CompanyCreate(name="Company One")
        )  # noqa: F841
        company2 = company_service.create_company(CompanyCreate(name="Company Two"))

        # Try to update company2 to have the same name as company1
        update_data = CompanyUpdate(name="Company One")

        with pytest.raises(CompanyExistsError):
            company_service.update_company(company2.id, update_data)

    def test_delete_company(self, company_service: CompanyService):
        """Test deleting a company."""
        company_data = CompanyCreate(name="Deletable Company")
        company = company_service.create_company(company_data)

        # Delete the company
        company_service.delete_company(company.id)

        # Verify it's gone
        with pytest.raises(CompanyNotFoundError):
            company_service.get_company_by_id(company.id)

    def test_delete_company_not_found(self, company_service: CompanyService):
        """Test deleting a non-existent company raises error."""
        with pytest.raises(CompanyNotFoundError):
            company_service.delete_company(99999)

    def test_list_companies_basic(self, company_service: CompanyService):
        """Test listing companies with basic pagination."""
        # Create test companies
        for i in range(5):
            company_service.create_company(CompanyCreate(name=f"Test Company {i}"))

        # List companies
        companies, total_count = company_service.list_companies(limit=3, offset=0)

        assert len(companies) <= 3
        assert total_count >= 5
        assert all(isinstance(company, Company) for company in companies)

    def test_list_companies_with_filters(self, company_service: CompanyService):
        """Test listing companies with filters."""
        # Create test companies with different attributes
        company_service.create_company(
            CompanyCreate(name="UK Tech Company", country="GB", industry="Technology")
        )
        company_service.create_company(
            CompanyCreate(name="US Finance Company", country="US", industry="Finance")
        )

        # Filter by country
        filters = CompanyFilter(country="GB")
        companies, total_count = company_service.list_companies(filters=filters)

        assert total_count >= 1
        assert all(company.country == "GB" for company in companies)

        # Filter by industry
        filters = CompanyFilter(industry="tech")  # Partial match
        companies, total_count = company_service.list_companies(filters=filters)

        assert any("Technology" in (company.industry or "") for company in companies)

    def test_search_companies(self, company_service: CompanyService):
        """Test searching companies by text."""
        # Create companies with searchable data
        company_service.create_company(
            CompanyCreate(
                name="Searchable Software Ltd",
                website="https://searchable.com",
                email="info@searchable.com",
            )
        )
        company_service.create_company(
            CompanyCreate(name="Different Company", website="https://different.com")
        )

        # Search by name
        results = company_service.search_companies("searchable", limit=10)
        assert len(results) >= 1
        assert any("Searchable" in company.name for company in results)

        # Search by website
        results = company_service.search_companies("searchable.com", limit=10)
        assert len(results) >= 1

        # Search with no results
        results = company_service.search_companies("nonexistent", limit=10)
        assert len(results) == 0

    def test_mark_as_prospect(self, company_service: CompanyService):
        """Test marking a company as a prospect."""
        company = company_service.create_company(CompanyCreate(name="Prospect Company"))

        # Initially not a prospect
        assert company.is_prospect is False
        assert company.prospect_stage is None

        # Mark as prospect
        updated_company = company_service.mark_as_prospect(company.id, stage="lead")

        assert updated_company.is_prospect is True
        assert updated_company.prospect_stage == "lead"

    def test_get_companies_by_postcode(self, company_service: CompanyService):
        """Test getting companies by postcode area."""
        # Create companies with different postcodes
        company_service.create_company(
            CompanyCreate(name="London Company 1", postcode="SW1A 1AA")
        )
        company_service.create_company(
            CompanyCreate(name="London Company 2", postcode="SW1B 2BB")
        )
        company_service.create_company(
            CompanyCreate(name="Manchester Company", postcode="M1 1AA")
        )

        # Search by postcode prefix
        sw1_companies = company_service.get_companies_by_postcode("SW1")
        assert len(sw1_companies) >= 2
        assert all(company.postcode.startswith("SW1") for company in sw1_companies)

        # Search by full postcode
        exact_companies = company_service.get_companies_by_postcode("SW1A 1AA")
        assert len(exact_companies) >= 1
        assert exact_companies[0].postcode == "SW1A 1AA"


class TestCompanyServiceIntegration:
    """Integration tests for CompanyService with external dependencies."""

    def test_update_from_companies_house_data(self, company_service: CompanyService):
        """Test updating company from Companies House data format."""
        # Create a company
        company = company_service.create_company(CompanyCreate(name="Test Company"))

        # Mock Companies House data
        ch_data = {
            "company_name": "Updated Company Name Ltd",
            "company_number": "12345678",
            "company_status": "active",
            "registered_office_address": {
                "address_line_1": "123 Test Street",
                "address_line_2": "Floor 2",
                "locality": "London",
                "region": "Greater London",
                "postal_code": "SW1A 1AA",
                "country": "England",
            },
            "sic_codes": ["62020", "62090"],
        }

        # Update company with Companies House data
        updated_company = company_service.update_from_companies_house(
            company.id, ch_data
        )

        assert updated_company.name == "Updated Company Name Ltd"
        assert updated_company.companies_house_number == "12345678"
        assert updated_company.companies_house_status == "active"
        assert updated_company.address_line1 == "123 Test Street"
        assert updated_company.city == "London"
        assert updated_company.postcode == "SW1A 1AA"
        assert updated_company.sic_code == "62020"  # First SIC code
        assert updated_company.data_source == "companies_house"
        assert updated_company.last_updated_from_source is not None
