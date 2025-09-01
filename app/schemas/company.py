# app/schemas/company.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, validator, EmailStr


class CompanyBase(BaseModel):
    """Base company schema with common fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Company legal name or trading name",
    )

    website: Optional[HttpUrl] = Field(
        default=None, description="Primary company website URL"
    )

    email: Optional[EmailStr] = Field(
        default=None, description="Primary contact email address"
    )

    phone: Optional[str] = Field(
        default=None, max_length=50, description="Primary contact phone number"
    )

    # Address fields
    address_line1: Optional[str] = Field(
        default=None, max_length=255, description="Address line 1"
    )

    address_line2: Optional[str] = Field(
        default=None, max_length=255, description="Address line 2"
    )

    city: Optional[str] = Field(default=None, max_length=100, description="City")

    county: Optional[str] = Field(default=None, max_length=100, description="County")

    postcode: Optional[str] = Field(
        default=None, max_length=20, description="UK postcode"
    )

    country: str = Field(default="GB", max_length=10, description="ISO country code")

    # Business information
    industry: Optional[str] = Field(
        default=None, max_length=100, description="Primary industry sector"
    )

    sic_code: Optional[str] = Field(
        default=None,
        max_length=10,
        description="Standard Industrial Classification code",
    )

    employee_count: Optional[int] = Field(
        default=None, ge=0, description="Approximate number of employees"
    )

    annual_revenue: Optional[int] = Field(
        default=None, ge=0, description="Annual revenue in GBP"
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate company name."""
        if not v or not v.strip():
            raise ValueError("Company name cannot be empty")
        return v.strip()

    @validator("postcode")
    def validate_postcode(cls, v):
        """Validate UK postcode format."""
        if not v:
            return v

        import re

        postcode = v.strip().upper()

        # Basic UK postcode pattern (allows some flexibility)
        uk_pattern = r"^[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}$"

        if not re.match(uk_pattern, postcode):
            # Allow non-UK postcodes for international companies
            if len(postcode) > 20:
                raise ValueError("Postcode too long")

        return postcode

    @validator("phone")
    def validate_phone(cls, v):
        """Basic phone number validation."""
        if not v:
            return v

        # Remove common formatting characters
        cleaned = "".join(c for c in v if c.isdigit() or c in "+- ()")

        if len(cleaned) < 7:  # Minimum reasonable phone length
            raise ValueError("Phone number too short")

        return cleaned


class CompanyCreate(CompanyBase):
    """Schema for creating a new company."""

    # Companies House fields (optional for manual entry)
    companies_house_number: Optional[str] = Field(
        default=None, max_length=20, description="Companies House registration number"
    )

    # Notes for internal use
    notes: Optional[str] = Field(
        default=None, description="Internal notes about the company"
    )


class CompanyUpdate(BaseModel):
    """Schema for updating an existing company."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Company legal name or trading name",
    )

    website: Optional[HttpUrl] = Field(default=None)
    email: Optional[EmailStr] = Field(default=None)
    phone: Optional[str] = Field(default=None, max_length=50)

    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    county: Optional[str] = Field(default=None, max_length=100)
    postcode: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=10)

    industry: Optional[str] = Field(default=None, max_length=100)
    sic_code: Optional[str] = Field(default=None, max_length=10)
    employee_count: Optional[int] = Field(default=None, ge=0)
    annual_revenue: Optional[int] = Field(default=None, ge=0)

    companies_house_number: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = Field(default=None)

    # Prospect fields
    is_prospect: Optional[bool] = Field(default=None)
    prospect_stage: Optional[str] = Field(default=None, max_length=50)


class CompanyResponse(CompanyBase):
    """Schema for company responses."""

    id: int = Field(..., description="Unique company identifier")

    # Companies House fields
    companies_house_number: Optional[str] = Field(default=None)
    companies_house_status: Optional[str] = Field(default=None)

    # Metadata fields
    data_source: str = Field(default="manual")
    last_updated_from_source: Optional[datetime] = Field(default=None)

    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = Field(default=None)

    class Config:
        from_attributes = True  # Enable ORM mode for SQLAlchemy models


class CompanyResponseWithProspect(CompanyResponse):
    """Schema for company responses including prospect information."""

    is_prospect: bool = Field(default=False)
    prospect_stage: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)


class CompanyFilter(BaseModel):
    """Schema for filtering companies."""

    name: Optional[str] = Field(
        default=None, description="Filter by company name (partial match)"
    )

    country: Optional[str] = Field(
        default=None, max_length=10, description="Filter by country code"
    )

    industry: Optional[str] = Field(
        default=None, description="Filter by industry (partial match)"
    )

    postcode: Optional[str] = Field(
        default=None, description="Filter by postcode prefix"
    )

    is_prospect: Optional[bool] = Field(
        default=None, description="Filter by prospect status"
    )

    has_companies_house_data: Optional[bool] = Field(
        default=None, description="Filter by whether company has Companies House data"
    )

    data_source: Optional[str] = Field(
        default=None, description="Filter by data source"
    )


class CompanyList(BaseModel):
    """Schema for paginated company list responses."""

    companies: List[CompanyResponse]
    total_count: int = Field(
        ..., description="Total number of companies matching filters"
    )
    page_size: int = Field(..., description="Number of companies per page")
    page: int = Field(..., description="Current page number (0-based)")
    total_pages: int = Field(..., description="Total number of pages")

    @validator("total_pages", pre=True, always=True)
    def calculate_total_pages(cls, v, values):
        """Calculate total pages based on total_count and page_size."""
        total_count = values.get("total_count", 0)
        page_size = values.get("page_size", 1)

        if page_size <= 0:
            return 0

        return (total_count + page_size - 1) // page_size


class CompanySearch(BaseModel):
    """Schema for company search requests."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Search term for company name, website, or email",
    )

    limit: int = Field(
        default=50, ge=1, le=100, description="Maximum number of results"
    )


class CompanySearchResponse(BaseModel):
    """Schema for company search responses."""

    query: str
    companies: List[CompanyResponse]
    result_count: int


# Companies House specific schemas
class CompaniesHouseUpdate(BaseModel):
    """Schema for updating company from Companies House data."""

    company_number: str = Field(..., description="Companies House registration number")

    force_update: bool = Field(
        default=False, description="Force update even if data is recent"
    )


class CompaniesHouseResponse(BaseModel):
    """Schema for Companies House API integration responses."""

    success: bool
    message: str
    updated_fields: Optional[List[str]] = Field(default=None)
    last_updated: Optional[datetime] = Field(default=None)
