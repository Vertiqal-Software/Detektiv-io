from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .base import Base


class CompanySize(enum.Enum):
    MICRO = "micro"  # <10 employees
    SMALL = "small"  # 10-49 employees  
    MEDIUM = "medium"  # 50-249 employees
    LARGE = "large"  # 250+ employees


class FinancialHealth(enum.Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class AlertPriority(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(enum.Enum):
    FINANCIAL_CHANGE = "financial_change"
    DIRECTORSHIP_CHANGE = "directorship_change"
    WEBSITE_UPDATE = "website_update"
    NEW_CONTRACT = "new_contract"
    PERSONNEL_CHANGE = "personnel_change"
    TENDER_OPPORTUNITY = "tender_opportunity"
    COMPETITIVE_INTELLIGENCE = "competitive_intelligence"


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    # Basic company information
    name = Column(String(255), nullable=False, index=True)
    companies_house_number = Column(String(20), unique=True, index=True)
    website = Column(String(500))
    description = Column(Text)
    industry = Column(String(255))
    sic_codes = Column(JSON)  # Standard Industrial Classification codes
    
    # Location data
    registered_address = Column(JSON)
    trading_addresses = Column(JSON)
    postcode = Column(String(20), index=True)
    
    # Company metrics
    employee_count = Column(Integer)
    company_size = Column(Enum(CompanySize))
    annual_revenue = Column(Float)
    
    # Financial health scoring
    financial_health_score = Column(Float)  # 0-100 score
    financial_health_status = Column(Enum(FinancialHealth))
    last_financial_analysis = Column(DateTime(timezone=True))
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_scraped = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="companies")
    financial_records = relationship("FinancialRecord", back_populates="company")
    directors = relationship("Director", back_populates="company")
    personnel = relationship("Personnel", back_populates="company")
    website_changes = relationship("WebsiteChange", back_populates="company")
    alerts = relationship("Alert", back_populates="company")
    sales_activities = relationship("SalesActivity", back_populates="company")
    competitive_intelligence = relationship("CompetitiveIntelligence", back_populates="company")


class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # Financial period
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    filing_date = Column(DateTime(timezone=True))
    
    # Key financial metrics (all in pence for precision)
    turnover = Column(Integer)  # Revenue
    gross_profit = Column(Integer)
    operating_profit = Column(Integer)
    net_profit = Column(Integer)
    total_assets = Column(Integer)
    current_assets = Column(Integer)
    cash_at_bank = Column(Integer)
    debtors = Column(Integer)
    creditors = Column(Integer)
    current_liabilities = Column(Integer)
    total_liabilities = Column(Integer)
    shareholders_equity = Column(Integer)
    
    # Calculated ratios
    current_ratio = Column(Float)
    debt_to_equity = Column(Float)
    profit_margin = Column(Float)
    roa = Column(Float)  # Return on Assets
    
    # Document metadata
    document_url = Column(String(500))
    document_type = Column(String(100))  # Annual Return, Confirmation Statement, etc.
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="financial_records")


class Director(Base):
    __tablename__ = "directors"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # Director information
    name = Column(String(255), nullable=False)
    date_of_birth = Column(DateTime(timezone=True))  # Month/Year only for privacy
    nationality = Column(String(100))
    occupation = Column(String(255))
    
    # Appointment details
    appointed_date = Column(DateTime(timezone=True))
    resigned_date = Column(DateTime(timezone=True))
    officer_role = Column(String(100))  # Director, Secretary, etc.
    
    # Address (usually service address)
    address = Column(JSON)
    
    # Control information
    significant_control = Column(Boolean, default=False)
    percentage_control = Column(Float)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="directors")


class Personnel(Base):
    __tablename__ = "personnel"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # Personal information
    name = Column(String(255), nullable=False)
    linkedin_profile = Column(String(500))
    email = Column(String(255))
    job_title = Column(String(255))
    department = Column(String(255))
    seniority_level = Column(String(100))  # C-Level, Senior, Manager, etc.
    
    # Employment details
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    is_current = Column(Boolean, default=True)
    
    # LinkedIn data
    connections = Column(Integer)
    skills = Column(JSON)
    certifications = Column(JSON)
    education = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_linkedin_sync = Column(DateTime(timezone=True))
    
    # Relationships
    company = relationship("Company", back_populates="personnel")


class WebsiteChange(Base):
    __tablename__ = "website_changes"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # Change details
    page_url = Column(String(1000), nullable=False)
    change_type = Column(String(100))  # content_added, content_removed, page_added, etc.
    change_summary = Column(Text)
    old_content = Column(Text)
    new_content = Column(Text)
    
    # Technology detection
    technologies_detected = Column(JSON)  # Software/hardware mentioned
    vendors_mentioned = Column(JSON)  # Competitor analysis
    certifications_found = Column(JSON)  # New industry certifications
    
    # Metadata
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    significance_score = Column(Float)  # 0-100 for prioritizing alerts
    
    # Relationships
    company = relationship("Company", back_populates="website_changes")


class TenderOpportunity(Base):
    __tablename__ = "tender_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    
    # Tender details
    title = Column(String(500), nullable=False)
    description = Column(Text)
    tender_id = Column(String(100), unique=True, index=True)
    source = Column(String(100))  # Contracts Finder, TED, etc.
    
    # Financial information
    estimated_value = Column(Integer)  # in pence
    currency = Column(String(10), default="GBP")
    
    # Dates
    publication_date = Column(DateTime(timezone=True))
    deadline_date = Column(DateTime(timezone=True))
    contract_start = Column(DateTime(timezone=True))
    contract_end = Column(DateTime(timezone=True))
    
    # Location and sector
    location = Column(String(255))
    sector = Column(String(255))
    keywords = Column(JSON)
    
    # Requirements
    requirements = Column(Text)
    technical_requirements = Column(JSON)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    matches = relationship("TenderMatch", back_populates="opportunity")


class TenderMatch(Base):
    __tablename__ = "tender_matches"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    opportunity_id = Column(Integer, ForeignKey("tender_opportunities.id"), nullable=False, index=True)
    
    # Match scoring
    match_score = Column(Float)  # 0-100 compatibility score
    match_reasons = Column(JSON)  # Why this company matches
    risk_factors = Column(JSON)  # Potential concerns
    
    # Opportunity analysis
    recommendation = Column(Text)
    estimated_win_probability = Column(Float)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_dismissed = Column(Boolean, default=False)
    
    # Relationships
    company = relationship("Company")
    opportunity = relationship("TenderOpportunity", back_populates="matches")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Alert details
    alert_type = Column(Enum(AlertType), nullable=False)
    priority = Column(Enum(AlertPriority), default=AlertPriority.MEDIUM)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Action suggestions
    suggested_actions = Column(JSON)
    call_script_points = Column(JSON)
    email_template = Column(Text)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_read = Column(Boolean, default=False)
    is_acted_upon = Column(Boolean, default=False)
    dismissed_at = Column(DateTime(timezone=True))
    
    # Relationships
    company = relationship("Company", back_populates="alerts")
    user = relationship("User")


class SalesActivity(Base):
    __tablename__ = "sales_activities"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Activity details
    activity_type = Column(String(100))  # call, email, meeting, note
    subject = Column(String(255))
    description = Column(Text)
    outcome = Column(String(255))
    next_steps = Column(Text)
    
    # Golden Circle methodology tracking
    why_notes = Column(Text)  # Purpose/belief notes
    how_notes = Column(Text)  # Process/differentiation notes  
    what_notes = Column(Text)  # Products/services notes
    
    # Metadata
    activity_date = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="sales_activities")
    user = relationship("User")


class CompetitiveIntelligence(Base):
    __tablename__ = "competitive_intelligence"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    
    # Vendor analysis
    vendors_used = Column(JSON)  # Current technology stack
    potential_opportunities = Column(JSON)  # Where we could compete
    competitive_threats = Column(JSON)  # Competing vendors present
    
    # Market intelligence
    market_position = Column(String(100))  # Leader, challenger, follower, niche
    growth_indicators = Column(JSON)
    investment_signals = Column(JSON)  # Funding, acquisitions, etc.
    
    # Relationship mapping
    key_contacts = Column(JSON)
    decision_makers = Column(JSON)
    influencers = Column(JSON)
    
    # Analysis metadata
    confidence_score = Column(Float)  # 0-100 confidence in analysis
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="competitive_intelligence")