from __future__ import annotations

from typing import Any


def split_context(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = dict(context.get("metadata", {}))
    company_profile = dict(context.get("company_profile", {}))
    price_summary = dict(context.get("price_summary", {}))
    price_technicals = dict(context.get("price_technicals", {}))
    volume_summary = dict(context.get("volume_summary", {}))
    market_context = dict(context.get("market_context", {}))
    holder_summary = dict(context.get("holder_summary", {}))
    valuation = dict(context.get("valuation", {}))
    financials = dict(context.get("financials", {}))
    cashflow_summary = dict(context.get("cashflow_summary", {}))
    news_summary = dict(context.get("news_summary", {}))
    analyst_consensus = dict(context.get("analyst_consensus", {}))
    consensus_summary = dict(context.get("consensus_summary", {}))

    return {
        "valuation": {
            "metadata": metadata,
            "company_profile": company_profile,
            "price_summary": {
                "current_price": price_summary.get("current_price"),
                "market_reference_date": price_summary.get("market_reference_date"),
                "returns": dict(price_summary.get("returns", {})),
            },
            "price_technicals": price_technicals,
            "volume_summary": volume_summary,
            "market_context": market_context,
            "valuation": valuation,
            "analyst_consensus": analyst_consensus,
            "consensus_summary": consensus_summary,
        },
        "financials": {
            "metadata": metadata,
            "company_profile": company_profile,
            "financials": {
                "quarterly_trend": list(financials.get("quarterly_trend", [])),
                "growth_rates": dict(financials.get("growth_rates", {})),
                "health": dict(financials.get("health", {})),
            },
            "cashflow_summary": cashflow_summary,
            "valuation": {"PER": valuation.get("PER")},
        },
        "growth": {
            "metadata": metadata,
            "company_profile": company_profile,
            "price_technicals": price_technicals,
            "volume_summary": volume_summary,
            "market_context": market_context,
            "holder_summary": holder_summary,
            "financials": {
                "growth_rates": dict(financials.get("growth_rates", {})),
            },
            "cashflow_summary": cashflow_summary,
            "news_summary": news_summary,
            "analyst_consensus": analyst_consensus,
            "consensus_summary": consensus_summary,
        },
        "risk": {
            "metadata": metadata,
            "company_profile": company_profile,
            "price_summary": price_summary,
            "price_technicals": price_technicals,
            "volume_summary": volume_summary,
            "market_context": market_context,
            "holder_summary": holder_summary,
            "valuation": valuation,
            "financials": {"health": dict(financials.get("health", {}))},
            "cashflow_summary": cashflow_summary,
            "news_summary": news_summary,
            "consensus_summary": consensus_summary,
        },
    }
