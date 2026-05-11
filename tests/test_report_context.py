from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from report.composer import ContextBuilder  # noqa: E402


class ReportContextTests(unittest.TestCase):
    def test_context_builder_includes_deep_read_news_and_supporting_fields(self) -> None:
        snapshot = {
            "ticker": "AAPL",
            "fetched_at": "2026-05-11T11:31:03Z",
            "info": {
                "longName": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "longBusinessSummary": "Apple designs consumer electronics, software, and services.",
                "website": "https://apple.com",
                "targetMeanPrice": 210.0,
                "targetLowPrice": 180.0,
                "targetHighPrice": 240.0,
                "numberOfAnalystOpinions": 42,
                "recommendationKey": "buy",
                "totalCash": 50.0,
                "totalDebt": 70.0,
            },
            "price": {
                "current": 100.0,
                "52w_high": 110.0,
                "52w_low": 90.0,
            },
            "financials": {
                "income_stmt": {},
                "balance_sheet": {
                    "Current Assets": {"2026-03-31": 120.0},
                    "Current Liabilities": {"2026-03-31": 60.0},
                },
                "cashflow": {
                    "Operating Cash Flow": {"2026-03-31": 40.0},
                    "Free Cash Flow": {"2026-03-31": 30.0},
                    "Capital Expenditure": {"2026-03-31": -10.0},
                },
            },
            "news": [{"title": "Apple launches new AI feature"}],
            "analyst_recs": {
                "strongBuy": 5,
                "buy": 10,
                "hold": 2,
                "sell": 1,
                "strongSell": 0,
            },
        }
        features = {
            "return_1m": 1.0,
            "vol_annual": 0.2,
            "valuation": {"PER": 20.0},
            "growth": {"revenue_yoy_pct": 5.0},
            "health": {
                "net_debt": 10.0,
                "FCF_yield_pct": 2.5,
                "profit_margin": 0.25,
                "operating_margin": 0.3,
            },
            "sentiment": {"positive": 1, "negative": 0, "neutral": 0, "keywords": ["ai"]},
            "technicals": {
                "ma_20": 98.0,
                "ma_50": 96.0,
                "ma_200": 90.0,
                "rsi_14": 58.2,
                "pct_from_52w_high": -9.09,
                "pct_above_52w_low": 11.11,
                "range_position_pct": 50.0,
                "distance_to_ma_20_pct": 2.04,
                "distance_to_ma_50_pct": 4.17,
                "distance_to_ma_200_pct": 11.11,
                "returns": {"return_1m": 1.0},
            },
        }
        enrichment = {
            "status": {"selected_count": 1, "deep_read_count": 1, "failed_count": 0},
            "company_relevant_articles": [
                {
                    "title": "Apple launches new AI feature",
                    "url": "https://example.com/ai-feature",
                    "selection_reason": "제목에 회사명/티커 직접 언급",
                    "company_relevance_score": 100,
                }
            ],
            "deep_read_articles": [
                {
                    "title": "Apple launches new AI feature",
                    "url": "https://example.com/ai-feature",
                    "selection_reason": "영향 키워드: AI",
                    "markdown_path": "/tmp/article.md",
                    "summary_bullets": ["AI feature may support upgrade demand."],
                }
            ],
        }

        context = ContextBuilder().build(snapshot, features, enrichment)

        self.assertEqual(context["news_summary"]["recent_headlines"], ["Apple launches new AI feature"])
        self.assertEqual(len(context["news_summary"]["deep_read_articles"]), 1)
        self.assertEqual(context["news_summary"]["deep_read_status"]["deep_read_count"], 1)
        self.assertEqual(context["company_profile"]["website"], "https://apple.com")
        self.assertEqual(context["price_technicals"]["ma_20"], 98.0)
        self.assertEqual(context["cashflow_summary"]["current_ratio"], 2.0)
        self.assertEqual(context["consensus_summary"]["buy_count"], 15)
        self.assertEqual(len(context["news_summary"]["company_relevant_articles"]), 1)

    def test_context_builder_handles_missing_supporting_data(self) -> None:
        snapshot = {
            "ticker": "MSFT",
            "fetched_at": "2026-05-11T11:31:03Z",
            "info": {
                "longName": "Microsoft Corporation",
                "sector": "Technology",
                "industry": "Software",
            },
            "price": {
                "current": 100.0,
                "52w_high": 110.0,
                "52w_low": 90.0,
            },
            "financials": {"income_stmt": {}, "balance_sheet": {}, "cashflow": {}},
            "news": [],
            "analyst_recs": {},
        }
        features = {
            "valuation": {"PER": 20.0},
            "growth": {"revenue_yoy_pct": None},
            "health": {"net_debt": None},
            "sentiment": {"positive": 0, "negative": 0, "neutral": 0, "keywords": []},
        }

        context = ContextBuilder().build(snapshot, features, None)

        self.assertEqual(context["news_summary"]["company_relevant_articles"], [])
        self.assertIsNone(context["cashflow_summary"]["current_ratio"])
        self.assertEqual(context["company_profile"]["industry"], "Software")


if __name__ == "__main__":
    unittest.main()
