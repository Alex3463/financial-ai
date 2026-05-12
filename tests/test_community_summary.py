from __future__ import annotations

import unittest

from report.composer import ContextBuilder


class CommunitySummaryTests(unittest.TestCase):
    def test_community_summary_basic_sentiment(self) -> None:
        cb = ContextBuilder()
        out = cb._community_summary(  # type: ignore[attr-defined]
            {
                "status": "ok",
                "conversations": [
                    {"text": "매수 각! strong breakout soon"},
                    {"text": "dump incoming... 매도 해야 하나"},
                    {"text": "bullish long term good"},
                ],
                "source_url": "https://finance.yahoo.com/quote/SPY/community/",
            }
        )
        self.assertEqual(out.get("status"), "ok")
        self.assertEqual(out.get("n"), 3)
        self.assertIn("sentiment_score", out)
        self.assertTrue(-1.0 <= float(out.get("sentiment_score")) <= 1.0)


if __name__ == "__main__":
    unittest.main()

