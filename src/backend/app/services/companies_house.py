import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from app.models.intelligence import Company, FinancialRecord, Director
from app.core.session import SessionLocal

logger = logging.getLogger(__name__)


class CompaniesHouseClient:
    """
    Companies House API client for comprehensive company data extraction.
    
    Handles all aspects of company intelligence gathering including:
    - Company profile data
    - Officer (director) information  
    - Financial filings and accounts
    - Document filing history
    - Significant control persons
    """
    
    BASE_URL = "https://api.company-information.service.gov.uk"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self.api_key, ''),
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'Detecktiv.io Intelligence Platform/1.0',
                'Accept': 'application/json'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_company_profile(self, company_number: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive company profile data"""
        try:
            url = f"{self.BASE_URL}/company/{company_number}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    logger.warning(f"Company {company_number} not found")
                    return None
                else:
                    logger.error(f"API error {response.status} for company {company_number}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching company profile {company_number}: {e}")
            return None
    
    async def get_officers(self, company_number: str) -> List[Dict[str, Any]]:
        """Get all officers (directors, secretaries) for a company"""
        officers = []
        items_per_page = 35
        start_index = 0
        
        try:
            while True:
                url = f"{self.BASE_URL}/company/{company_number}/officers"
                params = {
                    'items_per_page': items_per_page,
                    'start_index': start_index
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        officers.extend(data.get('items', []))
                        
                        # Check if there are more pages
                        if len(data.get('items', [])) < items_per_page:
                            break
                        start_index += items_per_page
                    else:
                        logger.error(f"Error fetching officers for {company_number}: {response.status}")
                        break
                        
        except Exception as e:
            logger.error(f"Error fetching officers for {company_number}: {e}")
            
        return officers
    
    async def get_filing_history(self, company_number: str, years: int = 5) -> List[Dict[str, Any]]:
        """Get filing history for the specified number of years"""
        filings = []
        items_per_page = 100
        start_index = 0
        cutoff_date = datetime.now() - timedelta(days=years * 365)
        
        try:
            while True:
                url = f"{self.BASE_URL}/company/{company_number}/filing-history"
                params = {
                    'items_per_page': items_per_page,
                    'start_index': start_index
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('items', [])
                        
                        for item in items:
                            # Check if filing is within our date range
                            date_str = item.get('date')
                            if date_str:
                                filing_date = datetime.strptime(date_str, '%Y-%m-%d')
                                if filing_date >= cutoff_date:
                                    filings.append(item)
                                else:
                                    # Files are in reverse chronological order
                                    # So we can stop once we hit the cutoff
                                    return filings
                        
                        # Check if there are more pages
                        if len(items) < items_per_page:
                            break
                        start_index += items_per_page
                    else:
                        logger.error(f"Error fetching filing history for {company_number}: {response.status}")
                        break
                        
        except Exception as e:
            logger.error(f"Error fetching filing history for {company_number}: {e}")
            
        return filings
    
    async def get_significant_control(self, company_number: str) -> List[Dict[str, Any]]:
        """Get persons with significant control (PSCs)"""
        try:
            url = f"{self.BASE_URL}/company/{company_number}/persons-with-significant-control"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('items', [])
                elif response.status == 404:
                    return []  # No PSCs found
                else:
                    logger.error(f"Error fetching PSCs for {company_number}: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching PSCs for {company_number}: {e}")
            return []
    
    async def get_company_accounts(self, company_number: str) -> Optional[Dict[str, Any]]:
        """Get the latest company accounts information"""
        try:
            # First get the filing history to find the latest accounts
            filings = await self.get_filing_history(company_number, years=2)
            
            # Look for annual accounts in the filings
            for filing in filings:
                if filing.get('category') == 'accounts':
                    # Get the document if available
                    document_id = filing.get('transaction_id')
                    if document_id:
                        doc_url = f"{self.BASE_URL}/company/{company_number}/filing-history/{document_id}/document"
                        # Note: Actual document download would require additional handling
                        # For now, we return the filing metadata
                        return filing
            
            return None
        except Exception as e:
            logger.error(f"Error fetching accounts for {company_number}: {e}")
            return None


class CompaniesHouseProcessor:
    """
    Processes Companies House data and stores it in our intelligence database
    """
    
    def __init__(self, api_key: str):
        self.client = CompaniesHouseClient(api_key)
    
    async def process_company(self, company_number: str, tenant_id: int) -> Optional[Company]:
        """
        Comprehensive processing of a single company.
        Gathers all available data from Companies House API.
        """
        async with self.client:
            # Get company profile
            profile = await self.client.get_company_profile(company_number)
            if not profile:
                logger.warning(f"No profile found for company {company_number}")
                return None
            
            db = SessionLocal()
            try:
                # Create or update company record
                company = db.query(Company).filter(
                    Company.companies_house_number == company_number
                ).first()
                
                if not company:
                    company = Company(
                        tenant_id=tenant_id,
                        companies_house_number=company_number
                    )
                    db.add(company)
                
                # Update company data from profile
                await self._update_company_from_profile(company, profile)
                
                # Process officers/directors
                officers = await self.client.get_officers(company_number)
                await self._process_officers(db, company, officers)
                
                # Process significant control persons
                pscs = await self.client.get_significant_control(company_number)
                await self._process_significant_control(db, company, pscs)
                
                # Process filing history and extract financial data
                filings = await self.client.get_filing_history(company_number)
                await self._process_filings(db, company, filings)
                
                # Update metadata
                company.last_scraped = datetime.utcnow()
                
                db.commit()
                db.refresh(company)
                
                logger.info(f"Successfully processed company {company_number}: {company.name}")
                return company
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error processing company {company_number}: {e}")
                return None
            finally:
                db.close()
    
    async def _update_company_from_profile(self, company: Company, profile: Dict[str, Any]):
        """Update company record with profile data"""
        company.name = profile.get('company_name', '')
        company.company_status = profile.get('company_status')
        company.company_type = profile.get('type')
        
        # SIC codes for industry classification
        sic_codes = profile.get('sic_codes', [])
        if sic_codes:
            company.sic_codes = sic_codes
            # Map SIC codes to industry (simplified mapping)
            company.industry = self._map_sic_to_industry(sic_codes[0])
        
        # Address information
        registered_office = profile.get('registered_office_address', {})
        if registered_office:
            company.registered_address = registered_office
            company.postcode = registered_office.get('postal_code')
        
        # Company dates
        incorporation_date = profile.get('date_of_creation')
        if incorporation_date:
            company.incorporation_date = datetime.strptime(incorporation_date, '%Y-%m-%d')
        
        # Accounts information
        accounts = profile.get('accounts', {})
        if accounts:
            next_due = accounts.get('next_due')
            if next_due:
                company.next_accounts_due = datetime.strptime(next_due, '%Y-%m-%d')
    
    async def _process_officers(self, db: Session, company: Company, officers: List[Dict[str, Any]]):
        """Process and store officer information"""
        # Mark existing directors as potentially inactive
        existing_directors = db.query(Director).filter(
            Director.company_id == company.id,
            Director.is_active == True
        ).all()
        
        active_officer_names = set()
        
        for officer_data in officers:
            # Extract officer information
            name = officer_data.get('name', '')
            if not name:
                continue
                
            active_officer_names.add(name)
            
            # Find or create director record
            director = db.query(Director).filter(
                Director.company_id == company.id,
                Director.name == name
            ).first()
            
            if not director:
                director = Director(company_id=company.id, name=name)
                db.add(director)
            
            # Update director information
            director.officer_role = officer_data.get('officer_role')
            director.nationality = officer_data.get('nationality')
            director.occupation = officer_data.get('occupation')
            
            # Appointment dates
            appointed_on = officer_data.get('appointed_on')
            if appointed_on:
                director.appointed_date = datetime.strptime(appointed_on, '%Y-%m-%d')
            
            resigned_on = officer_data.get('resigned_on')
            if resigned_on:
                director.resigned_date = datetime.strptime(resigned_on, '%Y-%m-%d')
                director.is_active = False
            else:
                director.is_active = True
            
            # Address information
            address = officer_data.get('address', {})
            if address:
                director.address = address
        
        # Mark directors no longer listed as inactive
        for existing in existing_directors:
            if existing.name not in active_officer_names:
                existing.is_active = False
    
    async def _process_significant_control(self, db: Session, company: Company, pscs: List[Dict[str, Any]]):
        """Process persons with significant control"""
        for psc in pscs:
            name = psc.get('name')
            if not name:
                continue
            
            # Find corresponding director record
            director = db.query(Director).filter(
                Director.company_id == company.id,
                Director.name == name
            ).first()
            
            if director:
                director.significant_control = True
                # Extract control percentage if available
                natures = psc.get('natures_of_control', [])
                for nature in natures:
                    if 'percent' in nature.lower():
                        # Extract percentage from control nature
                        # This is simplified - actual extraction would be more complex
                        director.percentage_control = 25.0  # Default for significant control
    
    async def _process_filings(self, db: Session, company: Company, filings: List[Dict[str, Any]]):
        """Process filing history and extract financial information"""
        for filing in filings:
            category = filing.get('category')
            subcategory = filing.get('subcategory')
            
            # Look for annual accounts
            if category == 'accounts' and 'annual' in subcategory.lower():
                await self._extract_financial_data(db, company, filing)
    
    async def _extract_financial_data(self, db: Session, company: Company, filing: Dict[str, Any]):
        """Extract financial data from accounts filing"""
        # In a real implementation, this would:
        # 1. Download the actual PDF/iXBRL document
        # 2. Parse the financial statements
        # 3. Extract key financial metrics
        # 4. Store in FinancialRecord table
        
        # For now, we create a basic record with filing metadata
        filing_date_str = filing.get('date')
        if not filing_date_str:
            return
        
        filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d')
        
        # Check if we already have this filing
        existing = db.query(FinancialRecord).filter(
            FinancialRecord.company_id == company.id,
            FinancialRecord.filing_date == filing_date
        ).first()
        
        if not existing:
            financial_record = FinancialRecord(
                company_id=company.id,
                filing_date=filing_date,
                document_type=filing.get('description', ''),
                document_url=f"https://find-and-update.company-information.service.gov.uk/company/{company.companies_house_number}/filing-history/{filing.get('transaction_id')}"
            )
            
            # Extract period information if available
            # This would typically come from parsing the actual document
            # For now, we estimate based on filing date
            financial_record.period_end = filing_date
            financial_record.period_start = filing_date - timedelta(days=365)
            
            db.add(financial_record)
    
    def _map_sic_to_industry(self, sic_code: str) -> str:
        """Map SIC code to industry category (simplified)"""
        sic_mapping = {
            '62': 'Information Technology',
            '63': 'Information Services',
            '58': 'Software Publishing',
            '46': 'Wholesale Trade',
            '47': 'Retail Trade',
            '68': 'Real Estate',
            '70': 'Professional Services',
            '71': 'Technical Services',
            '72': 'Scientific Research',
            '73': 'Advertising and Market Research',
            '74': 'Other Professional Activities',
            '82': 'Office Administrative Services'
        }
        
        # Extract first 2 digits of SIC code
        sic_prefix = sic_code[:2] if len(sic_code) >= 2 else sic_code
        return sic_mapping.get(sic_prefix, 'Other')


async def bulk_process_companies(api_key: str, company_numbers: List[str], tenant_id: int) -> List[Company]:
    """
    Bulk process multiple companies with rate limiting and error handling
    """
    processor = CompaniesHouseProcessor(api_key)
    results = []
    
    # Process companies with rate limiting (Companies House allows 600 requests per 5 minutes)
    semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
    
    async def process_with_semaphore(company_number: str):
        async with semaphore:
            try:
                result = await processor.process_company(company_number, tenant_id)
                if result:
                    results.append(result)
                # Rate limiting delay
                await asyncio.sleep(0.5)  # 0.5 seconds between requests
            except Exception as e:
                logger.error(f"Error processing company {company_number}: {e}")
    
    # Create tasks for all companies
    tasks = [process_with_semaphore(cn) for cn in company_numbers]
    
    # Execute all tasks
    await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info(f"Bulk processed {len(results)} companies out of {len(company_numbers)} attempted")
    return results