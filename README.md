# Sales Intelligence Platform

## Vision

A comprehensive sales intelligence platform for UK IT industry professionals to have a **single pane of glass view** into their customers. No more outdated data, no more guesswork - just comprehensive, actionable intelligence that makes you the hands-on account manager your customers deserve.

## What This Platform Does

### Core Intelligence Gathering
- **Companies House Integration**: Extract every piece of data including 5 years of financial documents
- **Financial Health Analysis**: Understand cash flow, debt ratios, and deal feasibility 
- **Website Monitoring**: Track blog posts, certifications, and content changes
- **LinkedIn Intelligence**: Monitor headcount, key personnel, and organizational changes
- **Tender Tracking**: Identify relevant government and public sector opportunities

### Sales Intelligence
- **Golden Circle Methodology**: Why/How/What approach for every interaction
- **Trigger Event Detection**: Get alerted when companies have significant changes
- **Account Management Alerts**: Know when to reach out proactively
- **Financial Story Crafting**: Understand their business journey for deeper conversations
- **Competitor Analysis**: Identify technology vendors and potential competitive threats

## Project Structure

```
sales-intelligence-platform/
├── src/
│   ├── backend/           # FastAPI application
│   ├── frontend/          # React application  
│   ├── intelligence/      # Core AI and analysis
│   │   ├── orchestrator.py      # Central coordination
│   │   ├── financial_analyzer.py  # Financial health analysis
│   │   └── sales_insights.py     # Golden Circle methodology
│   ├── scrapers/          # Data collection modules
│   │   ├── companies_house.py    # Companies House integration
│   │   ├── website_monitor.py    # Website change tracking
│   │   ├── linkedin_intelligence.py  # LinkedIn data
│   │   └── tender_monitor.py     # Government tender tracking
│   └── analytics/         # Reporting and dashboards
├── docker-compose.yml     # Complete platform deployment
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Quick Start

### 1. Environment Setup
```bash
# Clone and navigate to project
cd sales-intelligence-platform

# Copy environment template
cp .env.example .env

# Add your Companies House API key
echo "COMPANIES_HOUSE_API_KEY=your_key_here" >> .env
```

### 2. Launch Platform
```bash
# Start all services
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

### 3. Access Services
- **API**: http://localhost:8000
- **Frontend**: http://localhost:3000  
- **API Docs**: http://localhost:8000/docs

## Key Features

### 1. Comprehensive Company Intelligence
```bash
# Get complete intelligence report
curl http://localhost:8000/intelligence/COMPANY_NAME

# Returns:
# - Companies House data (5 years)
# - Financial health analysis
# - Director changes
# - Website activity
# - LinkedIn insights
# - Tender opportunities
# - Sales recommendations
```

### 2. Financial Health Analysis
```bash
# Analyze company finances
curl http://localhost:8000/financial/12345678

# Perfect for understanding:
# - Can they afford the deals they discuss?
# - Cash vs debtors analysis
# - Financial red flags
# - Growth trajectory
```

### 3. Sales Intelligence & Golden Circle
```bash
# Get sales approach recommendations
curl http://localhost:8000/sales/COMPANY_NAME

# Returns:
# - Why: Purpose-driven conversation starters
# - How: Process and approach recommendations  
# - What: Specific value propositions
# - Call talking points
# - Email templates
```

### 4. Trigger Event Detection
```bash
# Identify sales opportunities
curl http://localhost:8000/triggers/COMPANY_NAME

# Alerts on:
# - Director changes
# - New certifications
# - Website updates
# - Financial milestones
# - Tender applications
```

## The "Hands-On Account Manager" Approach

This platform enables you to:

1. **Understand Their Business**: Deep dive into financial health, growth patterns, and organizational changes
2. **Time Your Outreach**: Get alerts when companies have significant changes worth discussing
3. **Speak Their Language**: Reference specific achievements, challenges, and industry context
4. **Add Real Value**: Identify tender opportunities and frameworks that match their capabilities
5. **Build Relationships**: Show you understand their journey, not just their orders

## API Examples

### Get Intelligence Report
```python
import httpx

async def get_customer_intelligence(company_name):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8000/intelligence/{company_name}")
        return response.json()

# Usage
intelligence = await get_customer_intelligence("TechCorp Ltd")
print(f"Financial Health: {intelligence['financial_analysis']['health_score']}")
print(f"Recent Changes: {intelligence['trigger_events']}")
```

### Monitor Account Alerts
```python
async def check_account_alerts(company_list):
    params = {"companies": company_list}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/alerts", params=params)
        return response.json()

# Get alerts for your accounts
alerts = await check_account_alerts(["Company A", "Company B", "Company C"])
for alert in alerts['alerts']:
    print(f"Action required for {alert['company']}: {alert['reason']}")
```

## Configuration

### Environment Variables
```bash
# Companies House API
COMPANIES_HOUSE_API_KEY=your_api_key_here

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sales_intelligence
POSTGRES_USER=sales_user
POSTGRES_PASSWORD=your_secure_password

# Optional: LinkedIn API (requires special permissions)
LINKEDIN_API_KEY=your_linkedin_key

# Monitoring
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### Companies House API Key
Get your free API key from: https://developer.company-information.service.gov.uk/

## Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run API locally
cd src/backend
python -m app.main_sales_intelligence

# Run frontend locally  
cd src/frontend
npm install
npm start
```

### Testing
```bash
# Run API tests
pytest src/backend/tests/

# Test specific intelligence features
pytest src/intelligence/tests/

# Test scrapers
pytest src/scrapers/tests/
```

## Deployment

### Production Deployment
```bash
# Production environment
export ENVIRONMENT=production
export COMPANIES_HOUSE_API_KEY=your_production_key

# Deploy with Docker Compose
docker-compose -f docker-compose.prod.yml up -d
```

### Security Considerations
- Store API keys securely (use environment variables or secrets management)
- Respect rate limits for external APIs
- Implement proper authentication for multi-user deployment
- Regular data retention and privacy compliance reviews

## Roadmap

### Phase 1: Core Intelligence ✅
- [x] Companies House integration
- [x] Financial analysis engine
- [x] Basic website monitoring
- [x] Sales insight generation

### Phase 2: Enhanced Data Collection
- [ ] Advanced LinkedIn integration (requires API access)
- [ ] Comprehensive tender monitoring
- [ ] News and press release tracking
- [ ] Industry certification monitoring

### Phase 3: AI-Powered Insights  
- [ ] Predictive analytics for deal timing
- [ ] Automated competitor analysis
- [ ] Natural language processing for content analysis
- [ ] Machine learning for opportunity scoring

### Phase 4: Team Collaboration
- [ ] Multi-user accounts and permissions
- [ ] CRM integration (Salesforce, HubSpot)
- [ ] Team alerts and notifications
- [ ] Performance analytics and reporting

## Contributing

This is a focused platform for sales professionals in the UK IT industry. Contributions should align with the core vision of providing comprehensive, actionable customer intelligence.

## License

Private commercial software for UK IT sales professionals.

---

**Remember**: The goal is to be the account manager who truly understands their customers' businesses, not just someone who asks for orders. This platform gives you the intelligence to have those meaningful conversations that build lasting business relationships.