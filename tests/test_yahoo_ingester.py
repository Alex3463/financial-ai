from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ingest.yahoo import YahooIngester, _normalize_news_item  # noqa: E402


class YahooIngesterTests(unittest.TestCase):
    def test_normalize_news_item_supports_nested_content(self) -> None:
        raw_item = {
            "id": "123",
            "content": {
                "title": "Tech stocks today: AI chipmaker surges",
                "summary": "The artificial intelligence boom broadened.",
                "pubDate": "2026-05-11T10:00:00Z",
                "provider": {"displayName": "Yahoo Finance"},
                "canonicalUrl": {"url": "https://finance.yahoo.com/example"},
            },
        }

        normalized = _normalize_news_item(raw_item)

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["title"], raw_item["content"]["title"])
        self.assertEqual(normalized["publisher"], "Yahoo Finance")
        self.assertEqual(normalized["published"], "2026-05-11")
        self.assertEqual(normalized["link"], "https://finance.yahoo.com/example")
        self.assertIn("artificial intelligence", normalized["summary"])

    def test_build_snapshot_includes_volume_market_reference_and_holders(self) -> None:
        idx = pd.to_datetime(["2026-05-07", "2026-05-08"])
        price_daily = pd.DataFrame(
            {
                "Close": [99.0, 101.0],
                "High": [100.0, 102.0],
                "Low": [98.0, 100.0],
                "Volume": [1_000_000, 1_500_000],
            },
            index=idx,
        )
        price_monthly = pd.Series([101.0], index=pd.to_datetime(["2026-05-31"]))
        institutional_holders = pd.DataFrame(
            [
                {
                    "Holder": "Example Capital",
                    "Shares": 123456,
                    "Value": 9876543,
                    "% Out": 0.01,
                }
            ]
        )

        snapshot = YahooIngester()._build_snapshot(
            "AAPL",
            price_monthly,
            price_daily,
            {"longName": "Apple Inc.", "trailingPE": 20.0},
            None,
            None,
            None,
            [],
            None,
            benchmark_ticker="^GSPC",
            benchmark_daily_close={"2026-05-07": 5000.0, "2026-05-08": 5050.0},
            vix_ticker="^VIX",
            vix_daily_close={"2026-05-07": 18.0, "2026-05-08": 19.5},
            institutional_holders=institutional_holders,
            mutualfund_holders=None,
            major_holders=None,
        )

        self.assertEqual(snapshot["price"]["market_reference_date"], "2026-05-08")
        self.assertEqual(snapshot["price"]["daily_volume"]["2026-05-08"], 1_500_000.0)
        self.assertEqual(snapshot["price"]["daily_high"]["2026-05-08"], 102.0)
        self.assertEqual(snapshot["price"]["daily_low"]["2026-05-08"], 100.0)
        self.assertEqual(snapshot["price"]["benchmark_ticker"], "^GSPC")
        self.assertEqual(snapshot["price"]["benchmark_daily_close"]["2026-05-08"], 5050.0)
        self.assertEqual(snapshot["price"]["vix_ticker"], "^VIX")
        self.assertEqual(snapshot["price"]["vix_daily_close"]["2026-05-08"], 19.5)
        self.assertEqual(
            snapshot["holders"]["institutional_holders"][0]["holder"],
            "Example Capital",
        )


if __name__ == "__main__":
    unittest.main()
