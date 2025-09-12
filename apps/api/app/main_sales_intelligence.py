# Sales Intelligence Platform API
# Clean, focused FastAPI application for UK IT sales intelligence

import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import our sales intelligence modules
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))

from app.intelligence.orchestrator import SalesIntelligenceOrchestrator
from app.intelligence.financial_analyzer import FinancialAnalyzer
from app.intelligence.sales_insights import SalesInsightEngine


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sales-intelligence-api")

# Initialize the intelligence system
orchestrator = SalesIntelligenceOrchestrator(
    companies_house_api_key=os.getenv("COMPANIES_HOUSE_API_KEY", "")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Sales Intelligence Platform starting...")
    yield
    logger.info("Sales Intelligence Platform shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Sales Intelligence Platform",
    description="UK IT Sales Intelligence Platform - Single pane of glass for customer insights",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Root endpoint with API overview"""
    return {
        "name": "Sales Intelligence Platform",
        "description": "UK IT Sales Intelligence - Single pane of glass for customer insights",
        "version": "1.0.0",
        "features": [
            "Companies House integration (5 years of data)",
            "Financial health analysis",
            "Website monitoring",
            "LinkedIn intelligence",
            "Tender opportunity tracking",
            "Golden Circle sales methodology",
            "Trigger event detection",
            "Account management alerts",
        ],
        "endpoints": {
            "intelligence": "/intelligence/{company_identifier}",
            "financial_analysis": "/financial/{company_number}",
            "sales_insights": "/sales/{company_identifier}",
            "trigger_events": "/triggers/{company_identifier}",
            "account_alerts": "/alerts",
            "health": "/health",
        },
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Sales Intelligence Platform",
        "components": {
            "companies_house": bool(os.getenv("COMPANIES_HOUSE_API_KEY")),
            "orchestrator": True,
            "financial_analyzer": True,
            "sales_engine": True,
        },
    }


@app.get("/intelligence/{company_identifier}")
async def get_comprehensive_intelligence(company_identifier: str):
    """
    Get comprehensive intelligence report for a company.
    This is your 'single pane of glass' view.

    Returns:
    - Companies House data (5 years)
    - Financial health analysis
    - Director changes
    - Website activity
    - LinkedIn insights
    - Tender opportunities
    - Sales approach recommendations
    """
    try:
        report = await orchestrator.generate_complete_intelligence_report(
            company_identifier
        )
        return report
    except Exception as e:
        logger.error(
            f"Failed to generate intelligence report for {company_identifier}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Intelligence gathering failed: {str(e)}"
        )


@app.get("/financial/{company_number}")
async def get_financial_analysis(company_number: str):
    """
    Get detailed financial health analysis for a company.

    Perfect for understanding if they can afford the deals they're discussing.
    """
    try:
        # Get financial documents from Companies House
        financial_docs = await orchestrator.companies_house.get_financial_history(
            company_number, years=5
        )

        # Analyze financial health
        analysis = orchestrator.financial_analyzer.analyze_financial_health(
            financial_docs
        )

        return {
            "company_number": company_number,
            "financial_health": analysis,
            "story": orchestrator.financial_analyzer.generate_financial_story(
                company_number
            ),
            "documents_analyzed": len(financial_docs),
        }

    except Exception as e:
        logger.error(f"Financial analysis failed for {company_number}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Financial analysis failed: {str(e)}"
        )


@app.get("/sales/{company_identifier}")
async def get_sales_insights(company_identifier: str):
    """
    Generate sales insights and approach recommendations using Golden Circle methodology.

    Returns:
    - Initial contact strategy
    - Call talking points
    - Email templates
    - Follow-up recommendations
    """
    try:
        # Get basic company profile first
        company_data = (
            await orchestrator.companies_house.get_comprehensive_company_data(
                company_identifier
            )
        )

        # Generate Golden Circle approach
        golden_circle = orchestrator.sales_engine.generate_golden_circle_approach(
            company_data
        )

        # Get talking points and templates
        talking_points = orchestrator.sales_engine.generate_call_talking_points(
            company_data
        )
        initial_email = orchestrator.sales_engine.craft_initial_email(company_data, [])

        return {
            "company_identifier": company_identifier,
            "golden_circle_approach": golden_circle,
            "talking_points": talking_points,
            "initial_email_template": initial_email,
            "methodology": "Golden Circle (Why/How/What)",
        }

    except Exception as e:
        logger.error(f"Sales insights failed for {company_identifier}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sales insights failed: {str(e)}")


@app.get("/triggers/{company_identifier}")
async def get_trigger_events(company_identifier: str):
    """
    Identify trigger events that create sales opportunities.

    Examples:
    - Director changes
    - New certifications
    - Website updates
    - Financial milestones
    - Tender applications
    """
    try:
        # Get company data
        company_data = (
            await orchestrator.companies_house.get_comprehensive_company_data(
                company_identifier
            )
        )

        # Identify trigger events
        triggers = orchestrator.sales_engine.identify_trigger_events(company_data)

        return {
            "company_identifier": company_identifier,
            "trigger_events": triggers,
            "alert_worthy": [t for t in triggers if t.get("priority") == "high"],
            "recommendations": [
                "Call within 24 hours of high priority triggers",
                "Reference specific trigger in conversation",
                "Position as helpful partner, not opportunistic vendor",
            ],
        }

    except Exception as e:
        logger.error(
            f"Trigger event detection failed for {company_identifier}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Trigger detection failed: {str(e)}"
        )


@app.get("/alerts")
async def get_account_alerts(companies: List[str] = Query(...)):
    """
    Get alerts for account managers about significant company changes.

    Enables the 'hands-on account manager' approach by surfacing
    opportunities to reach out proactively.
    """
    try:
        alerts = []

        for company in companies:
            try:
                # Check for changes
                changes = await orchestrator.monitor_for_changes([company])

                # Generate alert if significant changes detected
                if changes.get("significant_changes"):
                    alert = orchestrator.generate_account_update_alert(changes)
                    if alert:
                        alerts.append(alert)

            except Exception as e:
                logger.warning(f"Failed to check alerts for {company}: {str(e)}")
                continue

        return {
            "alerts": alerts,
            "monitoring": len(companies),
            "active_alerts": len(alerts),
            "recommendations": [
                "Review alerts daily at start of business",
                "Act on high priority alerts within 24 hours",
                "Document all alert-driven outreach in CRM",
            ],
        }

    except Exception as e:
        logger.error(f"Alert generation failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Alert generation failed: {str(e)}"
        )


@app.post("/demo/analyze")
async def demo_analyze_company(request: Dict):
    """
    Demo endpoint to analyze a company for demonstration purposes.
    Shows how the platform would work with real data.
    """
    company_name = request.get("company_name", "")
    if not company_name:
        raise HTTPException(status_code=400, detail="company_name is required")

    # Return demo data showing the platform's capabilities
    return {
        "company_name": company_name,
        "analysis_complete": True,
        "intelligence_gathered": {
            "companies_house_data": "✓ 5 years of financial documents retrieved",
            "website_monitoring": "✓ Recent blog post about new certification found",
            "linkedin_analysis": "✓ 15% headcount growth in last 6 months",
            "tender_opportunities": "✓ 3 relevant framework opportunities identified",
            "financial_health": "✓ Strong cash position, low debt ratio",
            "director_changes": "✓ New CTO appointed 2 months ago",
        },
        "sales_recommendations": {
            "approach": "Golden Circle methodology",
            "why": "Help them scale their growing team efficiently",
            "how": "IT infrastructure solutions for rapid growth",
            "what": "Specific products matching their tech stack",
            "timing": "Optimal - new CTO likely evaluating suppliers",
            "urgency": "High - growth phase creates immediate needs",
        },
        "suggested_actions": [
            "Contact new CTO within 48 hours",
            "Reference their recent certification achievement",
            "Mention relevant government framework opportunities",
            "Prepare proposal for scaling infrastructure needs",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main_sales_intelligence:app", host="0.0.0.0", port=8000, reload=True)
