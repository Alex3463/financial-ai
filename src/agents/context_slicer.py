from __future__ import annotations

from typing import Any


def split_context(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = dict(context.get("metadata", {}))
    price_summary = dict(context.get("price_summary", {}))
    valuation = dict(context.get("valuation", {}))
    financials = dict(context.get("financials", {}))
    news_summary = dict(context.get("news_summary", {}))
    analyst_consensus = dict(context.get("analyst_consensus", {}))

    return {
        "valuation": {
            "metadata": metadata,
            "price_summary": {
                "current_price": price_summary.get("current_price"),
                "returns": dict(price_summary.get("returns", {})),
            },
            "valuation": valuation,
            "analyst_consensus": analyst_consensus,
        },
        "financials": {
            "metadata": metadata,
            "financials": {
                "quarterly_trend": list(financials.get("quarterly_trend", [])),
                "growth_rates": dict(financials.get("growth_rates", {})),
                "health": dict(financials.get("health", {})),
            },
            "valuation": {"PER": valuation.get("PER")},
        },
        "growth": {
            "metadata": metadata,
            "financials": {
                "growth_rates": dict(financials.get("growth_rates", {})),
            },
            "news_summary": news_summary,
            "analyst_consensus": analyst_consensus,
        },
        "risk": {
            "metadata": metadata,
            "price_summary": price_summary,
            "valuation": valuation,
            "financials": {"health": dict(financials.get("health", {}))},
            "news_summary": news_summary,
        },
    }
