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
    def test_context_builder_includes_deep_read_news(self) -> None:
        snapshot = {
            "ticker": "AAPL",
            "fetched_at": "2026-05-11T11:31:03Z",
            "info": {
                "longName": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
            },
            "price": {
                "current": 100.0,
                "52w_high": 110.0,
                "52w_low": 90.0,
            },
            "financials": {"income_stmt": {}},
            "news": [{"title": "Apple launches new AI feature"}],
            "analyst_recs": {},
        }
        features = {
            "return_1m": 1.0,
            "vol_annual": 0.2,
            "valuation": {"PER": 20.0},
            "growth": {"revenue_yoy_pct": 5.0},
            "health": {"net_debt": 10.0},
            "sentiment": {"positive": 1, "negative": 0, "neutral": 0, "keywords": ["ai"]},
        }
        enrichment = {
            "status": {"selected_count": 1, "deep_read_count": 1, "failed_count": 0},
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


if __name__ == "__main__":
    unittest.main()
