import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.intelligence import (
    Company,
    FinancialRecord,
    FinancialHealth,
    CompanySize,
)
from app.core.session import SessionLocal

logger = logging.getLogger(__name__)


class FinancialAnalyzer:
    """
    Comprehensive financial analysis engine for UK companies.

    Analyzes financial health, calculates risk scores, identifies trends,
    and provides insights for sales intelligence.
    """

    def __init__(self):
        self.industry_benchmarks = self._load_industry_benchmarks()
        self.scoring_weights = {
            "liquidity": 0.25,  # Current ratio, cash position
            "profitability": 0.30,  # Profit margins, ROA
            "leverage": 0.20,  # Debt ratios
            "growth": 0.15,  # Revenue/profit growth
            "stability": 0.10,  # Consistency of performance
        }

    def analyze_company_financials(self, company_id: int) -> Dict[str, any]:
        """
        Comprehensive financial analysis of a company.
        Returns scoring, health assessment, and actionable insights.
        """
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise ValueError(f"Company {company_id} not found")

            # Get financial records for analysis
            financial_records = (
                db.query(FinancialRecord)
                .filter(FinancialRecord.company_id == company_id)
                .order_by(FinancialRecord.period_end.desc())
                .limit(5)
                .all()
            )

            if not financial_records:
                logger.warning(f"No financial records found for company {company_id}")
                return self._default_analysis()

            # Perform comprehensive analysis
            analysis = {
                "company_id": company_id,
                "company_name": company.name,
                "analysis_date": datetime.utcnow(),
                "financial_health_score": 0,
                "financial_health_status": FinancialHealth.FAIR,
                "key_metrics": {},
                "trends": {},
                "risk_factors": [],
                "opportunities": [],
                "sales_insights": {},
                "benchmark_comparison": {},
            }

            # Calculate key financial metrics
            latest_record = financial_records[0]
            analysis["key_metrics"] = self._calculate_key_metrics(latest_record)

            # Analyze trends if we have multiple periods
            if len(financial_records) > 1:
                analysis["trends"] = self._analyze_trends(financial_records)

            # Calculate financial health score
            analysis["financial_health_score"] = self._calculate_health_score(
                analysis["key_metrics"], analysis["trends"], company.industry
            )

            # Determine health status
            analysis["financial_health_status"] = self._determine_health_status(
                analysis["financial_health_score"]
            )

            # Generate risk factors and opportunities
            analysis["risk_factors"] = self._identify_risk_factors(
                analysis["key_metrics"], analysis["trends"]
            )
            analysis["opportunities"] = self._identify_opportunities(
                analysis["key_metrics"], analysis["trends"]
            )

            # Generate sales-specific insights
            analysis["sales_insights"] = self._generate_sales_insights(
                analysis["key_metrics"],
                analysis["trends"],
                analysis["financial_health_score"],
                company,
            )

            # Industry benchmark comparison
            if company.industry:
                analysis["benchmark_comparison"] = self._compare_to_benchmarks(
                    analysis["key_metrics"], company.industry
                )

            # Update company record
            company.financial_health_score = analysis["financial_health_score"]
            company.financial_health_status = analysis["financial_health_status"]
            company.last_financial_analysis = datetime.utcnow()

            db.commit()

            return analysis

        except Exception as e:
            db.rollback()
            logger.error(f"Error analyzing company {company_id}: {e}")
            raise
        finally:
            db.close()

    def _calculate_key_metrics(
        self, financial_record: FinancialRecord
    ) -> Dict[str, float]:
        """Calculate key financial ratios and metrics"""
        metrics = {}

        try:
            # Convert from pence to pounds for calculations
            turnover = (financial_record.turnover or 0) / 100
            total_assets = (financial_record.total_assets or 0) / 100
            current_assets = (financial_record.current_assets or 0) / 100
            current_liabilities = (financial_record.current_liabilities or 0) / 100
            total_liabilities = (financial_record.total_liabilities or 0) / 100
            cash_at_bank = (financial_record.cash_at_bank or 0) / 100
            net_profit = (financial_record.net_profit or 0) / 100

            # Liquidity ratios
            if current_liabilities > 0:
                metrics["current_ratio"] = current_assets / current_liabilities
            else:
                metrics["current_ratio"] = float("inf") if current_assets > 0 else 0

            metrics["cash_ratio"] = (
                cash_at_bank / current_liabilities if current_liabilities > 0 else 0
            )

            # Profitability ratios
            if turnover > 0:
                metrics["net_profit_margin"] = (net_profit / turnover) * 100
                metrics["revenue"] = turnover
            else:
                metrics["net_profit_margin"] = 0
                metrics["revenue"] = 0

            if total_assets > 0:
                metrics["return_on_assets"] = (net_profit / total_assets) * 100
            else:
                metrics["return_on_assets"] = 0

            # Leverage ratios
            if total_assets > 0:
                metrics["debt_to_assets"] = (total_liabilities / total_assets) * 100
            else:
                metrics["debt_to_assets"] = 0

            equity = total_assets - total_liabilities
            if equity > 0:
                metrics["debt_to_equity"] = (total_liabilities / equity) * 100
            else:
                metrics["debt_to_equity"] = float("inf") if total_liabilities > 0 else 0

            # Absolute values for context
            metrics["total_assets"] = total_assets
            metrics["cash_position"] = cash_at_bank
            metrics["net_profit"] = net_profit

            return metrics

        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return {}

    def _analyze_trends(
        self, financial_records: List[FinancialRecord]
    ) -> Dict[str, any]:
        """Analyze financial trends over multiple periods"""
        trends = {}

        try:
            # Sort by period end date
            records = sorted(
                financial_records, key=lambda x: x.period_end or datetime.min
            )

            if len(records) < 2:
                return trends

            # Calculate revenue trend
            revenues = []
            profits = []

            for record in records:
                revenues.append((record.turnover or 0) / 100)
                profits.append((record.net_profit or 0) / 100)

            # Revenue growth analysis
            if len(revenues) >= 2:
                recent_revenue = revenues[-1]
                previous_revenue = revenues[-2]

                if previous_revenue > 0:
                    revenue_growth = (
                        (recent_revenue - previous_revenue) / previous_revenue
                    ) * 100
                else:
                    revenue_growth = 0

                trends["revenue_growth_latest"] = revenue_growth

                # Calculate compound annual growth rate (CAGR) if we have enough data
                if len(revenues) >= 3:
                    years = len(revenues) - 1
                    if revenues[0] > 0:
                        cagr = (pow(recent_revenue / revenues[0], 1 / years) - 1) * 100
                        trends["revenue_cagr"] = cagr

            # Profit trend analysis
            if len(profits) >= 2:
                recent_profit = profits[-1]
                previous_profit = profits[-2]

                if previous_profit != 0:
                    profit_growth = (
                        (recent_profit - previous_profit) / abs(previous_profit)
                    ) * 100
                else:
                    profit_growth = 100 if recent_profit > 0 else 0

                trends["profit_growth_latest"] = profit_growth

            # Stability analysis (coefficient of variation)
            if len(revenues) >= 3:
                rev_mean = np.mean(revenues)
                rev_std = np.std(revenues)
                trends["revenue_stability"] = (
                    1 - (rev_std / rev_mean) if rev_mean > 0 else 0
                )

            return trends

        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return {}

    def _calculate_health_score(
        self, metrics: Dict[str, float], trends: Dict[str, any], industry: str
    ) -> float:
        """Calculate overall financial health score (0-100)"""
        try:
            score_components = {}

            # Liquidity scoring (25%)
            current_ratio = metrics.get("current_ratio", 0)
            if current_ratio >= 2.0:
                liquidity_score = 100
            elif current_ratio >= 1.5:
                liquidity_score = 80
            elif current_ratio >= 1.0:
                liquidity_score = 60
            elif current_ratio >= 0.5:
                liquidity_score = 40
            else:
                liquidity_score = 20

            score_components["liquidity"] = liquidity_score

            # Profitability scoring (30%)
            profit_margin = metrics.get("net_profit_margin", 0)
            roa = metrics.get("return_on_assets", 0)

            if profit_margin >= 10 and roa >= 10:
                profitability_score = 100
            elif profit_margin >= 5 and roa >= 5:
                profitability_score = 80
            elif profit_margin >= 0 and roa >= 0:
                profitability_score = 60
            elif profit_margin >= -5:
                profitability_score = 40
            else:
                profitability_score = 20

            score_components["profitability"] = profitability_score

            # Leverage scoring (20%)
            debt_to_assets = metrics.get("debt_to_assets", 0)
            if debt_to_assets <= 30:
                leverage_score = 100
            elif debt_to_assets <= 50:
                leverage_score = 80
            elif debt_to_assets <= 70:
                leverage_score = 60
            elif debt_to_assets <= 85:
                leverage_score = 40
            else:
                leverage_score = 20

            score_components["leverage"] = leverage_score

            # Growth scoring (15%)
            revenue_growth = trends.get("revenue_growth_latest", 0)
            if revenue_growth >= 20:
                growth_score = 100
            elif revenue_growth >= 10:
                growth_score = 80
            elif revenue_growth >= 0:
                growth_score = 60
            elif revenue_growth >= -10:
                growth_score = 40
            else:
                growth_score = 20

            score_components["growth"] = growth_score

            # Stability scoring (10%)
            stability = trends.get("revenue_stability", 0.5)
            stability_score = min(100, max(0, stability * 100))
            score_components["stability"] = stability_score

            # Calculate weighted score
            total_score = sum(
                score_components[component] * self.scoring_weights[component]
                for component in score_components
            )

            return min(100, max(0, total_score))

        except Exception as e:
            logger.error(f"Error calculating health score: {e}")
            return 50  # Default neutral score

    def _determine_health_status(self, score: float) -> FinancialHealth:
        """Convert numerical score to health status enum"""
        if score >= 80:
            return FinancialHealth.EXCELLENT
        elif score >= 65:
            return FinancialHealth.GOOD
        elif score >= 45:
            return FinancialHealth.FAIR
        elif score >= 25:
            return FinancialHealth.POOR
        else:
            return FinancialHealth.CRITICAL

    def _identify_risk_factors(
        self, metrics: Dict[str, float], trends: Dict[str, any]
    ) -> List[str]:
        """Identify potential financial risk factors"""
        risks = []

        # Liquidity risks
        current_ratio = metrics.get("current_ratio", 0)
        if current_ratio < 1.0:
            risks.append("Low current ratio indicates potential cash flow problems")

        cash_ratio = metrics.get("cash_ratio", 0)
        if cash_ratio < 0.1:
            risks.append("Low cash reserves relative to current liabilities")

        # Profitability risks
        profit_margin = metrics.get("net_profit_margin", 0)
        if profit_margin < 0:
            risks.append("Operating at a loss - negative profit margin")
        elif profit_margin < 2:
            risks.append("Very thin profit margins - vulnerable to cost increases")

        # Growth risks
        revenue_growth = trends.get("revenue_growth_latest")
        if revenue_growth is not None and revenue_growth < -10:
            risks.append("Significant revenue decline in latest period")

        # Leverage risks
        debt_to_assets = metrics.get("debt_to_assets", 0)
        if debt_to_assets > 80:
            risks.append("High debt levels relative to assets")

        return risks

    def _identify_opportunities(
        self, metrics: Dict[str, float], trends: Dict[str, any]
    ) -> List[str]:
        """Identify potential business opportunities based on financial position"""
        opportunities = []

        # Strong cash position
        cash_position = metrics.get("cash_position", 0)
        current_ratio = metrics.get("current_ratio", 0)
        if cash_position > 100000 and current_ratio > 2.0:
            opportunities.append(
                "Strong cash position - good candidate for expansion projects"
            )

        # Growth trajectory
        revenue_growth = trends.get("revenue_growth_latest")
        if revenue_growth is not None and revenue_growth > 15:
            opportunities.append(
                "Strong growth trajectory - may need additional infrastructure/services"
            )

        # Profitable operations
        profit_margin = metrics.get("net_profit_margin", 0)
        if profit_margin > 10:
            opportunities.append(
                "High profitability - likely to invest in growth initiatives"
            )

        # Low leverage
        debt_to_assets = metrics.get("debt_to_assets", 0)
        if debt_to_assets < 30:
            opportunities.append(
                "Conservative debt levels - capacity for strategic investments"
            )

        return opportunities

    def _generate_sales_insights(
        self,
        metrics: Dict[str, float],
        trends: Dict[str, any],
        health_score: float,
        company: Company,
    ) -> Dict[str, any]:
        """Generate sales-specific insights and recommendations"""
        insights = {
            "deal_size_potential": "medium",
            "payment_risk": "medium",
            "decision_making_speed": "medium",
            "budget_availability": "medium",
            "talking_points": [],
            "approach_strategy": "",
            "urgency_indicators": [],
        }

        # Deal size potential based on revenue and cash
        revenue = metrics.get("revenue", 0)
        cash_position = metrics.get("cash_position", 0)

        if revenue > 10000000 or cash_position > 1000000:  # £10M+ revenue or £1M+ cash
            insights["deal_size_potential"] = "high"
            insights["talking_points"].append(
                "Large organization with substantial revenue - discuss enterprise solutions"
            )
        elif revenue > 1000000:  # £1M+ revenue
            insights["deal_size_potential"] = "medium"
            insights["talking_points"].append(
                "Growing business - focus on scalable solutions"
            )
        else:
            insights["deal_size_potential"] = "low"
            insights["talking_points"].append(
                "SME focused - emphasize cost-effective solutions"
            )

        # Payment risk assessment
        current_ratio = metrics.get("current_ratio", 0)
        if health_score >= 70 and current_ratio >= 1.5:
            insights["payment_risk"] = "low"
            insights["talking_points"].append(
                "Strong financial position - reliable payment capability"
            )
        elif health_score >= 45:
            insights["payment_risk"] = "medium"
        else:
            insights["payment_risk"] = "high"
            insights["talking_points"].append(
                "Consider payment terms carefully - may need flexible arrangements"
            )

        # Decision making speed based on growth and health
        revenue_growth = trends.get("revenue_growth_latest", 0)
        if revenue_growth > 20 and health_score > 60:
            insights["decision_making_speed"] = "fast"
            insights["talking_points"].append(
                "Rapid growth phase - likely to make quick decisions on growth-enabling technology"
            )
            insights["urgency_indicators"].append(
                "Fast-growing company needs to act quickly to maintain momentum"
            )
        elif health_score < 40:
            insights["decision_making_speed"] = "slow"
            insights["talking_points"].append(
                "Conservative approach likely - focus on ROI and cost savings"
            )

        # Budget availability
        profit_margin = metrics.get("net_profit_margin", 0)
        if profit_margin > 10 and cash_position > 500000:
            insights["budget_availability"] = "high"
            insights["talking_points"].append(
                "Healthy margins and cash reserves - budget available for strategic investments"
            )
        elif profit_margin > 5:
            insights["budget_availability"] = "medium"
        else:
            insights["budget_availability"] = "low"
            insights["talking_points"].append(
                "Tight margins - focus on solutions that directly impact profitability"
            )

        # Approach strategy
        if health_score >= 70:
            insights["approach_strategy"] = (
                "Growth-focused: Emphasize expansion, efficiency gains, and competitive advantages"
            )
        elif health_score >= 45:
            insights["approach_strategy"] = (
                "Balanced: Mix of growth and efficiency, emphasize ROI"
            )
        else:
            insights["approach_strategy"] = (
                "Conservative: Focus on cost reduction, efficiency, and essential systems only"
            )

        return insights

    def _compare_to_benchmarks(
        self, metrics: Dict[str, float], industry: str
    ) -> Dict[str, any]:
        """Compare company metrics to industry benchmarks"""
        benchmarks = self.industry_benchmarks.get(
            industry, self.industry_benchmarks.get("default", {})
        )

        comparison = {}

        for metric, value in metrics.items():
            if metric in benchmarks:
                benchmark_value = benchmarks[metric]
                if benchmark_value > 0:
                    ratio = value / benchmark_value
                    if ratio >= 1.2:
                        comparison[metric] = {"status": "above", "ratio": ratio}
                    elif ratio <= 0.8:
                        comparison[metric] = {"status": "below", "ratio": ratio}
                    else:
                        comparison[metric] = {"status": "average", "ratio": ratio}

        return comparison

    def _load_industry_benchmarks(self) -> Dict[str, Dict[str, float]]:
        """Load industry benchmark data"""
        return {
            "Information Technology": {
                "current_ratio": 2.5,
                "net_profit_margin": 15.0,
                "return_on_assets": 12.0,
                "debt_to_assets": 25.0,
            },
            "Professional Services": {
                "current_ratio": 1.8,
                "net_profit_margin": 12.0,
                "return_on_assets": 15.0,
                "debt_to_assets": 35.0,
            },
            "default": {
                "current_ratio": 2.0,
                "net_profit_margin": 8.0,
                "return_on_assets": 8.0,
                "debt_to_assets": 40.0,
            },
        }

    def _default_analysis(self) -> Dict[str, any]:
        """Return default analysis when no financial data is available"""
        return {
            "financial_health_score": 50,
            "financial_health_status": FinancialHealth.FAIR,
            "key_metrics": {},
            "trends": {},
            "risk_factors": ["No financial data available for analysis"],
            "opportunities": [],
            "sales_insights": {
                "deal_size_potential": "unknown",
                "payment_risk": "unknown",
                "decision_making_speed": "unknown",
                "budget_availability": "unknown",
                "talking_points": [
                    "Research company background before initial contact"
                ],
                "approach_strategy": "Exploratory: Gather more information about company's financial position",
                "urgency_indicators": [],
            },
            "benchmark_comparison": {},
        }


def analyze_company_batch(company_ids: List[int]) -> Dict[int, Dict[str, any]]:
    """Batch analyze multiple companies for efficiency"""
    analyzer = FinancialAnalyzer()
    results = {}

    for company_id in company_ids:
        try:
            analysis = analyzer.analyze_company_financials(company_id)
            results[company_id] = analysis
        except Exception as e:
            logger.error(f"Error analyzing company {company_id}: {e}")
            results[company_id] = analyzer._default_analysis()

    return results
