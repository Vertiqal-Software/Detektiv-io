# Getting Started with Sales Intelligence Platform

## Overview

This guide will help you set up and start using the Sales Intelligence Platform to transform how you research and engage with customers in the UK IT industry.

## Prerequisites

### Required
- Docker and Docker Compose
- Companies House API Key (free from [developer.company-information.service.gov.uk](https://developer.company-information.service.gov.uk/))
- Basic understanding of sales processes

### Optional
- LinkedIn API access (for enhanced personnel insights)
- Government tender API keys (for comprehensive tender tracking)

## 1. Initial Setup

### Get Your Companies House API Key
1. Visit [Companies House Developer Hub](https://developer.company-information.service.gov.uk/)
2. Register for a free account
3. Create an API key
4. Note: Free tier allows 600 requests per 5 minutes

### Environment Configuration
```bash
# Copy the environment template
cp .env.example .env

# Edit .env file with your settings
COMPANIES_HOUSE_API_KEY=your_key_here
POSTGRES_PASSWORD=choose_secure_password
```

## 2. Launch the Platform

### Using Docker (Recommended)
```bash
# Start all services
docker-compose up -d

# Check all services are healthy
docker-compose ps

# View logs if needed
docker-compose logs -f api
```

### Verify Installation
```bash
# Test API health
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "service": "Sales Intelligence Platform",
  "components": {
    "companies_house": true,
    "orchestrator": true,
    "financial_analyzer": true,
    "sales_engine": true
  }
}
```

## 3. Your First Intelligence Report

### Test with Demo Company
```bash
# Get comprehensive intelligence
curl http://localhost:8000/intelligence/ExampleTech

# Or use the demo endpoint
curl -X POST http://localhost:8000/demo/analyze \
  -H "Content-Type: application/json" \
  -d '{"company_name": "TechCorp Ltd"}'
```

### Understanding the Response
The intelligence report includes:
- **Companies House Data**: Official business information
- **Financial Analysis**: Health indicators and cash flow insights
- **Trigger Events**: Recent changes worth discussing
- **Sales Recommendations**: Golden Circle approach suggestions

## 4. Core Workflows

### Workflow 1: Researching a New Prospect
```bash
# 1. Get comprehensive intelligence
curl http://localhost:8000/intelligence/[COMPANY_NAME]

# 2. Analyze their financial health
curl http://localhost:8000/financial/[COMPANIES_HOUSE_NUMBER]

# 3. Get sales approach recommendations
curl http://localhost:8000/sales/[COMPANY_NAME]

# 4. Identify recent trigger events
curl http://localhost:8000/triggers/[COMPANY_NAME]
```

### Workflow 2: Monitoring Existing Accounts
```bash
# Set up monitoring for multiple accounts
curl "http://localhost:8000/alerts?companies=CompanyA&companies=CompanyB&companies=CompanyC"

# Review alerts daily for proactive outreach opportunities
```

### Workflow 3: Preparing for a Sales Call
1. **Run Intelligence Report**: Get complete picture
2. **Review Financial Story**: Understand their business journey  
3. **Check Trigger Events**: Find recent conversation starters
4. **Generate Talking Points**: Use Golden Circle methodology

## 5. Using the Web Interface

### Access the Dashboard
- Open http://localhost:3000 in your browser
- Dashboard provides visual interface for all intelligence features
- Export reports for offline review or team sharing

### Key Dashboard Features
- **Intelligence Search**: Look up any UK company
- **Account Monitoring**: Track changes across your customer base
- **Financial Health Dashboard**: Visual financial analysis
- **Trigger Event Feed**: Recent changes across monitored companies

## 6. Integration with Your Sales Process

### CRM Integration Preparation
```python
# Example: Export intelligence data for CRM import
import json
import httpx

async def export_customer_intelligence(company_name):
    async with httpx.AsyncClient() as client:
        intelligence = await client.get(f"http://localhost:8000/intelligence/{company_name}")
        
        # Format for your CRM
        crm_data = {
            "company": company_name,
            "financial_health": intelligence["financial_analysis"]["health_score"],
            "last_updated": intelligence["generated_at"],
            "trigger_events": intelligence["trigger_events"][:3],  # Top 3 events
            "recommended_approach": intelligence["sales_insights"]["golden_circle_approach"]
        }
        
        return crm_data
```

### Email Template Generation
```bash
# Get personalized email template
curl http://localhost:8000/sales/[COMPANY_NAME]

# Response includes:
# - Personalized subject line
# - Opening paragraph referencing recent company news
# - Value proposition aligned with their business
# - Call-to-action
```

## 7. Daily Operations

### Morning Routine (5 minutes)
1. **Check Account Alerts**: Review overnight changes
2. **Review Trigger Events**: Identify outreach opportunities  
3. **Plan Your Day**: Prioritize calls based on intelligence

### Before Each Sales Call
1. **Refresh Intelligence**: Get latest data
2. **Review Financial Story**: Understand their context
3. **Prepare Talking Points**: Reference specific insights

### Weekly Review
1. **Analyze Platform Usage**: Which features provide most value?
2. **Update Monitored Companies**: Add new prospects
3. **Review Success Stories**: What intelligence led to wins?

## 8. Advanced Features

### Batch Analysis for Territory Planning
```bash
# Analyze multiple companies for market research
for company in CompanyA CompanyB CompanyC; do
  curl http://localhost:8000/intelligence/$company > ${company}_intelligence.json
done
```

### Tender Opportunity Matching
```bash
# Find relevant tender opportunities
curl http://localhost:8000/triggers/[COMPANY_NAME] | jq '.trigger_events[] | select(.type == "tender")'
```

### Competitive Intelligence
```bash
# Identify technology vendors mentioned on company websites
curl http://localhost:8000/intelligence/[COMPANY_NAME] | jq '.website_changes.tech_stack'
```

## 9. Best Practices

### Data Privacy and Compliance
- All data comes from public sources (Companies House, websites, etc.)
- Respect website terms of service and robots.txt
- Store intelligence data securely
- Regular data retention reviews

### Effective Usage
- **Quality over Quantity**: Deep research on fewer prospects beats shallow research on many
- **Regular Updates**: Intelligence becomes stale - refresh before important interactions
- **Context is Key**: Use intelligence to start conversations, not replace relationship building
- **Follow Through**: Act on trigger events quickly while they're still relevant

### Team Adoption
- **Start Small**: Begin with a few key accounts
- **Share Success Stories**: Show how intelligence led to better conversations
- **Regular Training**: Keep team updated on new features
- **Measure Impact**: Track conversion rates and relationship quality improvements

## 10. Troubleshooting

### Common Issues

#### API Key Issues
```bash
# Test your Companies House API key
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://api.company-information.service.gov.uk/company/00000006
```

#### Service Not Starting
```bash
# Check service logs
docker-compose logs api
docker-compose logs database

# Restart specific service
docker-compose restart api
```

#### Slow Performance
- Check your internet connection for API calls
- Review Companies House API rate limits
- Consider upgrading to paid API tier for higher limits

### Getting Help
- Check API documentation: http://localhost:8000/docs
- Review service logs: `docker-compose logs -f`
- Ensure all environment variables are set correctly

## Next Steps

### Immediate Actions
1. Set up monitoring for your top 10 accounts
2. Run intelligence reports on your next 3 sales calls
3. Set up daily alert checking routine

### This Week
1. Integrate intelligence gathering into your sales process
2. Train team members on platform usage
3. Begin measuring impact on conversation quality

### This Month
1. Expand to monitor entire territory
2. Set up automated reporting
3. Explore advanced features like tender tracking

---

**Remember**: This platform makes you smarter about your customers' businesses, but relationships are still built through genuine conversations and valuable service. Use intelligence as the foundation for better interactions, not as a replacement for authentic relationship building.