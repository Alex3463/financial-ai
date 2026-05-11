from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from features.builder import FeatureBuilder  # noqa: E402


class FeatureBuilderTests(unittest.TestCase):
    def test_build_includes_volume_and_benchmark_context(self) -> None:
        daily_close = {f"2026-04-{day:02d}": float(100 + day) for day in range(1, 23)}
        daily_high = {date: value + 2.0 for date, value in daily_close.items()}
        daily_low = {date: value - 2.0 for date, value in daily_close.items()}
        daily_volume = {f"2026-04-{day:02d}": float(1_000 + day * 10) for day in range(1, 23)}
        benchmark_daily_close = {f"2026-04-{day:02d}": float(500 + day) for day in range(1, 23)}
        vix_daily_close = {f"2026-04-{day:02d}": float(14 + day / 10) for day in range(1, 23)}
        snapshot = {
            "ticker": "AAPL",
            "price": {
                "current": 122.0,
                "52w_high": 130.0,
                "52w_low": 90.0,
                "monthly_close": {"2026-03-31": 100.0, "2026-04-30": 122.0},
                "daily_close": daily_close,
                "daily_high": daily_high,
                "daily_low": daily_low,
                "daily_volume": daily_volume,
                "benchmark_ticker": "^GSPC",
                "benchmark_daily_close": benchmark_daily_close,
                "vix_ticker": "^VIX",
                "vix_daily_close": vix_daily_close,
            },
            "info": {},
            "financials": {"income_stmt": {}},
            "news": [],
        }

        features = FeatureBuilder().build(snapshot)

        self.assertEqual(features["volume_summary"]["latest_volume"], 1220.0)
        self.assertGreater(features["volume_summary"]["avg_volume_20d"], 0)
        self.assertEqual(features["market_context"]["benchmark_ticker"], "^GSPC")
        self.assertIsNotNone(features["market_context"]["stock_return_1m"])
        self.assertIsNotNone(features["market_context"]["benchmark_return_1m"])
        self.assertIsNotNone(features["market_context"]["excess_return_1m"])
        self.assertEqual(features["technicals"]["atr_14"], 4.0)
        self.assertEqual(features["technicals"]["atr_stop_loss_candidate"], 114.0)
        self.assertLess(features["technicals"]["support_stop_loss_candidate"], 122.0)
        self.assertEqual(features["market_context"]["vix"]["ticker"], "^VIX")
        self.assertEqual(features["market_context"]["vix"]["current"], 16.2)
        self.assertEqual(features["market_context"]["vix"]["reference_date"], "2026-04-22")
        self.assertEqual(features["market_context"]["vix"]["regime"], "보통")


if __name__ == "__main__":
    unittest.main()
