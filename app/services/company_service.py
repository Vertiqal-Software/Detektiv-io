# app/services/company_service.py
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, or_, and_

from app.models.company import Company
from app.core.database import get_db_session
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyFilter

logger = logging.getLogger(__name__)


class CompanyNotFoundError(Exception):
    """Raised when a company is not found."""
    pass


class CompanyExistsError(Exception):
    """Raised when trying to create a company that already exists."""
    pass


class CompanyService:
    """
    Service class for company-related business logic.
    Handles CRUD operations and business rules for companies.
    """
    
    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize the service with an optional database session.
        If no session provided, operations will create their own sessions.
        """
        self._db_session = db_session
    
    def _get_session(self) -> Session:
        """Get database session (provided or create new one)."""
        if self._db_session:
            return self._db_session
        else:
            # This will be used with context managers
            raise RuntimeError("No database session provided. Use with get_db_session().")
    
    def create_company(self, company_data: CompanyCreate) -> Company:
        """
        Create a new company.
        
        Args:
            company_data: Company creation data
            
        Returns:
            Created company instance
            
        Raises:
            CompanyExistsError: If company with same name already exists
        """
        session = self._get_session()
        
        try:
            # Check if company with same name already exists (case-insensitive)
            existing = session.execute(
                select(Company).where(
                    func.lower(Company.name) == func.lower(company_data.name)
                )
            ).scalar_one_or_none()
            
            if existing:
                raise CompanyExistsError(f"Company with name '{company_data.name}' already exists")
            
            # Create new company
            company = Company(**company_data.model_dump())
            company.data_source = "manual"  # Default for manually created companies
            
            session.add(company)
            session.flush()  # Get the ID without committing
            
            logger.info("Created company: %s (ID: %d)", company.name, company.id)
            return company
            
        except IntegrityError as e:
            logger.error("Database integrity error creating company: %s", e)
            raise CompanyExistsError("Company name already exists") from e
    
    def get_company_by_id(self, company_id: int) -> Company:
        """
        Get company by ID.
        
        Args:
            company_id: Company ID
            
        Returns:
            Company instance
            
        Raises:
            CompanyNotFoundError: If company not found
        """
        session = self._get_session()
        
        company = session.get(Company, company_id)
        if not company:
            raise CompanyNotFoundError(f"Company with ID {company_id} not found")
            
        return company
    
    def get_company_by_name(self, name: str) -> Optional[Company]:
        """
        Get company by name (case-insensitive).
        
        Args:
            name: Company name
            
        Returns:
            Company instance or None
        """
        session = self._get_session()
        
        return session.execute(
            select(Company).where(func.lower(Company.name) == func.lower(name))
        ).scalar_one_or_none()
    
    def get_company_by_companies_house_number(self, ch_number: str) -> Optional[Company]:
        """
        Get company by Companies House number.
        
        Args:
            ch_number: Companies House registration number
            
        Returns:
            Company instance or None
        """
        session = self._get_session()
        
        return session.execute(
            select(Company).where(Company.companies_house_number == ch_number)
        ).scalar_one_or_none()
    
    def update_company(self, company_id: int, company_data: CompanyUpdate) -> Company:
        """
        Update an existing company.
        
        Args:
            company_id: Company ID
            company_data: Company update data
            
        Returns:
            Updated company instance
            
        Raises:
            CompanyNotFoundError: If company not found
            CompanyExistsError: If name conflict with another company
        """
        session = self._get_session()
        
        company = self.get_company_by_id(company_id)
        
        # Check for name conflicts (if name is being changed)
        update_data = company_data.model_dump(exclude_unset=True)
        if 'name' in update_data and update_data['name'] != company.name:
            existing = session.execute(
                select(Company).where(
                    and_(
                        func.lower(Company.name) == func.lower(update_data['name']),
                        Company.id != company_id
                    )
                )
            ).scalar_one_or_none()
            
            if existing:
                raise CompanyExistsError(f"Company with name '{update_data['name']}' already exists")
        
        # Update the company
        company.update_from_dict(update_data)
        session.flush()
        
        logger.info("Updated company: %s (ID: %d)", company.name, company.id)
        return company
    
    def delete_company(self, company_id: int) -> None:
        """
        Delete a company.
        
        Args:
            company_id: Company ID
            
        Raises:
            CompanyNotFoundError: If company not found
        """
        session = self._get_session()
        
        company = self.get_company_by_id(company_id)
        session.delete(company)
        session.flush()
        
        logger.info("Deleted company: %s (ID: %d)", company.name, company.id)
    
    def list_companies(
        self,
        filters: Optional[CompanyFilter] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "id",
        order_desc: bool = False
    ) -> tuple[List[Company], int]:
        """
        List companies with filtering and pagination.
        
        Args:
            filters: Optional filtering criteria
            limit: Maximum number of results
            offset: Number of results to skip
            order_by: Field to order by
            order_desc: Whether to order in descending order
            
        Returns:
            Tuple of (companies list, total count)
        """
        session = self._get_session()
        
        # Build base query
        query = select(Company)
        count_query = select(func.count()).select_from(Company)
        
        # Apply filters
        if filters:
            filter_conditions = self._build_filter_conditions(filters)
            if filter_conditions:
                query = query.where(and_(*filter_conditions))
                count_query = count_query.where(and_(*filter_conditions))
        
        # Apply ordering
        order_column = getattr(Company, order_by, Company.id)
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column)
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        # Execute queries
        companies = session.execute(query).scalars().all()
        total_count = session.execute(count_query).scalar()
        
        return list(companies), total_count
    
    def search_companies(self, search_term: str, limit: int = 50) -> List[Company]:
        """
        Search companies by name or website.
        
        Args:
            search_term: Search term
            limit: Maximum number of results
            
        Returns:
            List of matching companies
        """
        session = self._get_session()
        
        search_pattern = f"%{search_term.lower()}%"
        
        query = select(Company).where(
            or_(
                func.lower(Company.name).contains(search_pattern),
                func.lower(Company.website).contains(search_pattern),
                func.lower(Company.email).contains(search_pattern)
            )
        ).limit(limit)
        
        companies = session.execute(query).scalars().all()
        return list(companies)
    
    def get_companies_by_postcode(self, postcode: str) -> List[Company]:
        """
        Get companies in a specific postcode area.
        
        Args:
            postcode: UK postcode or postcode prefix
            
        Returns:
            List of companies in that postcode area
        """
        session = self._get_session()
        
        # Handle both full postcodes and prefixes
        postcode_pattern = f"{postcode.upper()}%"
        
        query = select(Company).where(
            Company.postcode.ilike(postcode_pattern)
        ).order_by(Company.postcode, Company.name)
        
        companies = session.execute(query).scalars().all()
        return list(companies)
    
    def mark_as_prospect(self, company_id: int, stage: str = "lead") -> Company:
        """
        Mark company as a sales prospect.
        
        Args:
            company_id: Company ID
            stage: Prospect stage
            
        Returns:
            Updated company
        """
        company = self.get_company_by_id(company_id)
        company.is_prospect = True
        company.prospect_stage = stage
        
        session = self._get_session()
        session.flush()
        
        logger.info("Marked company as prospect: %s (stage: %s)", company.name, stage)
        return company
    
    def update_from_companies_house(self, company_id: int, ch_data: Dict[str, Any]) -> Company:
        """
        Update company with data from Companies House API.
        
        Args:
            company_id: Company ID
            ch_data: Companies House API response data
            
        Returns:
            Updated company
        """
        company = self.get_company_by_id(company_id)
        
        # Map Companies House data to our model
        if 'company_name' in ch_data:
            company.name = ch_data['company_name']
        
        if 'company_number' in ch_data:
            company.companies_house_number = ch_data['company_number']
        
        if 'company_status' in ch_data:
            company.companies_house_status = ch_data['company_status']
        
        if 'registered_office_address' in ch_data:
            address = ch_data['registered_office_address']
            company.address_line1 = address.get('address_line_1')
            company.address_line2 = address.get('address_line_2')
            company.city = address.get('locality')
            company.county = address.get('region')
            company.postcode = address.get('postal_code')
            company.country = address.get('country', 'GB')
        
        if 'sic_codes' in ch_data and ch_data['sic_codes']:
            company.sic_code = ch_data['sic_codes'][0]  # Take first SIC code
        
        company.data_source = "companies_house"
        company.last_updated_from_source = datetime.utcnow()
        
        session = self._get_session()
        session.flush()
        
        logger.info("Updated company from Companies House: %s", company.name)
        return company
    
    def _build_filter_conditions(self, filters: CompanyFilter) -> List:
        """Build SQLAlchemy filter conditions from filter object."""
        conditions = []
        
        if filters.name:
            conditions.append(func.lower(Company.name).contains(filters.name.lower()))
        
        if filters.country:
            conditions.append(Company.country == filters.country)
        
        if filters.industry:
            conditions.append(func.lower(Company.industry).contains(filters.industry.lower()))
        
        if filters.postcode:
            conditions.append(Company.postcode.ilike(f"{filters.postcode}%"))
        
        if filters.is_prospect is not None:
            conditions.append(Company.is_prospect == filters.is_prospect)
        
        if filters.has_companies_house_data is not None:
            if filters.has_companies_house_data:
                conditions.append(Company.companies_house_number.isnot(None))
            else:
                conditions.append(Company.companies_house_number.is_(None))
        
        if filters.data_source:
            conditions.append(Company.data_source == filters.data_source)
        
        return conditions


# Convenience functions for common operations
def create_company_with_session(company_data: CompanyCreate) -> Company:
    """Create a company using a managed session."""
    with get_db_session() as session:
        service = CompanyService(session)
        return service.create_company(company_data)


def get_company_with_session(company_id: int) -> Company:
    """Get a company using a managed session."""
    with get_db_session() as session:
        service = CompanyService(session)
        return service.get_company_by_id(company_id)


def list_companies_with_session(
    filters: Optional[CompanyFilter] = None,
    limit: int = 50,
    offset: int = 0
) -> tuple[List[Company], int]:
    """List companies using a managed session."""
    with get_db_session() as session:
        service = CompanyService(session)
        return service.list_companies(filters=filters, limit=limit, offset=offset)