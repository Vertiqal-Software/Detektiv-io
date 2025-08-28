# app/models/company.py
from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional, Dict, Any, Set
from urllib.parse import urlparse

from sqlalchemy import (
    String,
    Text,
    Integer,
    BigInteger,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    func,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, validates, synonym

from .base import Base


class Company(Base):
    """
    Company model for storing business information.

    Combines the original project's fields (multi-tenant, Companies House support,
    last_accounts) with validation and extra metadata (contacts, address, etc.).
    """

    __tablename__ = "companies"

    # Primary key (use Integer if you already created this table and want to avoid a type migration)
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Unique company identifier",
    )

    # Multi-tenant association (kept from original)
    # NOTE: We don't force nullable=False here to avoid migration friction if older data had NULLs.
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"), index=True, comment="Owning tenant ID"
    )

    # Core identity
    name: Mapped[str] = mapped_column(
        Text, nullable=False, index=True, comment="Company legal/trading name"
    )

    # Website & contacts
    website: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Primary company website URL"
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Primary contact email address"
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Primary contact phone number"
    )

    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postcode: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True, comment="UK postcode"
    )
    country: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="GB",
        server_default="GB",
        comment="ISO country code",
    )

    # Companies House (original names preserved for DB compatibility)
    company_number: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Companies House registration number",
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Company status (e.g. active, dissolved)"
    )
    incorporated_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="Date of incorporation"
    )
    jurisdiction: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Jurisdiction"
    )

    # Financial snapshot (kept from original)
    last_accounts: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Latest accounts snapshot"
    )

    # Business classification
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sic_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    employee_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    annual_revenue: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Sales intelligence metadata
    data_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="manual, companies_house, scraped, api, import",
    )
    last_updated_from_source: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_prospect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    prospect_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Constraints & indexes (kept conservative to avoid unique-constraint breakage)
    __table_args__ = (
        CheckConstraint(
            "employee_count IS NULL OR employee_count >= 0",
            name="ck_companies_employee_count_positive",
        ),
        CheckConstraint(
            "annual_revenue IS NULL OR annual_revenue >= 0",
            name="ck_companies_annual_revenue_positive",
        ),
        CheckConstraint(
            "country IS NULL OR country IN ('GB','IE','US','CA','AU','NZ')",
            name="ck_companies_supported_countries",
        ),
        CheckConstraint(
            "data_source IN ('manual','companies_house','scraped','api','import')",
            name="ck_companies_valid_data_source",
        ),
        Index("ix_companies_name", "name"),
    )

    # Aliases for forward/backward compatibility with code calling new names
    # (no DB rename: both refer to the same underlying columns)
    companies_house_number = synonym("company_number")
    companies_house_status = synonym("status")

    # ---------------------------- Validators ---------------------------------

    @validates("website")
    def _validate_website(self, key: str, website: Optional[str]) -> Optional[str]:
        if not website:
            return None
        website = website.strip()
        if not website:
            return None
        if not website.startswith(("http://", "https://")):
            website = f"https://{website}"
        parsed = urlparse(website)
        if not parsed.netloc:
            raise ValueError("Invalid website URL format")
        return website

    @validates("email")
    def _validate_email(self, key: str, email: Optional[str]) -> Optional[str]:
        if not email:
            return None
        email = email.strip().lower()
        if not email:
            return None
        if "@" not in email or "." not in email.split("@")[-1]:
            raise ValueError("Invalid email format")
        return email

    @validates("postcode")
    def _validate_postcode(self, key: str, postcode: Optional[str]) -> Optional[str]:
        if not postcode:
            return None
        postcode = postcode.strip().upper()
        if not postcode:
            return None
        uk_postcode_pattern = r"^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$"
        # Soft-check: allow non-UK postcodes by not raising
        # (keeps international records possible)
        _ = re.match(uk_postcode_pattern, postcode)
        return postcode

    # --------------------------- Convenience ---------------------------------

    def get_full_address(self) -> Optional[str]:
        parts = [
            p
            for p in [
                self.address_line1,
                self.address_line2,
                self.city,
                self.county,
                self.postcode,
            ]
            if p
        ]
        return ", ".join(parts) if parts else None

    def is_uk_company(self) -> bool:
        return (self.country or "").upper() == "GB"

    def has_companies_house_data(self) -> bool:
        return bool(self.company_number)

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        exclude: Set[str] = set()
        if not include_sensitive:
            exclude.update(
                {
                    "notes",
                    "prospect_stage",
                    "is_prospect",
                    "last_updated_from_source",
                    "data_source",
                }
            )
        return super().to_dict(exclude=exclude)

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name={self.name!r})>"


class SourceEvent(Base):
    """
    Event log for where a piece of company data came from (CH filing, website scan, etc.)
    Kept from original model; now benefits from Base's created_at/updated_at fields.
    """

    __tablename__ = "source_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)

    source: Mapped[str] = mapped_column(
        String(64), nullable=False, comment='e.g. "companies_house", "website_head"'
    )
    kind: Mapped[str] = mapped_column(
        String(64), nullable=False, comment='e.g. "filing", "officer_change"'
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_source_events_company", "company_id"),
        Index("ix_source_events_tenant_company", "tenant_id", "company_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SourceEvent(id={self.id}, company_id={self.company_id}, "
            f"source={self.source!r}, kind={self.kind!r})>"
        )
