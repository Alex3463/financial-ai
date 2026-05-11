from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.composer_agent import _render_quarterly_table  # noqa: E402
from agents.schemas import (  # noqa: E402
    ComposerInput,
    FinancialsHealthOutput,
    GrowthNewsOutput,
    GrowthDriver,
    QuarterRow,
    RiskItem,
    RiskOutput,
    ValuationOutput,
)


class ComposerAgentFormattingTests(unittest.TestCase):
    def test_quarterly_table_uses_compact_units(self) -> None:
        composer_input = ComposerInput(
            metadata={"ticker": "AAPL", "company_name": "Apple Inc.", "data_as_of": "2026-05-11"},
            actual_per=35.46,
            valuation=ValuationOutput(
                method="PER",
                per_trailing=35.46,
                per_applied=35.46,
                eps=8.27,
                target_price=293.33,
                target_price_downside=253.0,
                formula_text="목표가 = (적용 PER 35.46) × (TTM EPS 8.27) = 293.33달러",
                horizon="12개월",
                rationale_bullets=["a", "b", "c"],
                citations=["yf.info.trailingPE"],
            ),
            financials=FinancialsHealthOutput(
                quarterly_table=[
                    QuarterRow(
                        quarter="2026-03-31",
                        revenue=111_184_000_000,
                        op_income=35_885_000_000,
                        net_income=29_578_000_000,
                        source="financials.quarterly_trend",
                        as_of="2026-05-11T12:04:00Z",
                    ),
                    QuarterRow(
                        quarter="2025-12-31",
                        revenue=143_756_000_000,
                        op_income=50_852_000_000,
                        net_income=42_097_000_000,
                        source="financials.quarterly_trend",
                        as_of="2026-05-11T12:04:00Z",
                    ),
                    QuarterRow(
                        quarter="2025-09-30",
                        revenue=102_466_000_000,
                        op_income=32_427_000_000,
                        net_income=27_466_000_000,
                        source="financials.quarterly_trend",
                        as_of="2026-05-11T12:04:00Z",
                    ),
                    QuarterRow(
                        quarter="2025-06-30",
                        revenue=94_036_000_000,
                        op_income=28_202_000_000,
                        net_income=23_434_000_000,
                        source="financials.quarterly_trend",
                        as_of="2026-05-11T12:04:00Z",
                    ),
                ],
                per_trailing=35.46,
                health_notes=["note 1", "note 2"],
                citations=["financials.quarterly_trend"],
            ),
            growth=GrowthNewsOutput(
                drivers=[
                    GrowthDriver(
                        headline="driver 1",
                        evidence="evidence 1",
                        citations=["https://example.com/1"],
                    ),
                    GrowthDriver(
                        headline="driver 2",
                        evidence="evidence 2",
                        citations=["https://example.com/2"],
                    ),
                ],
                sentiment_summary="neutral",
            ),
            risk=RiskOutput(
                risks=[
                    RiskItem(category="경쟁", description="risk 1", citations=["c1"]),
                    RiskItem(category="규제", description="risk 2", citations=["c2"]),
                    RiskItem(category="금리", description="risk 3", citations=["c3"]),
                ]
            ),
            news_summary={},
        )

        table = _render_quarterly_table(composer_input)

        self.assertIn("111.2B", table)
        self.assertIn("35.9B", table)
        self.assertNotIn("111,184,000,000", table)


if __name__ == "__main__":
    unittest.main()
