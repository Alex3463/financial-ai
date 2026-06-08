from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.composer_agent import (  # noqa: E402
    _build_input,
    _render_quarterly_table,
)
from agents.source_citations import polish_stock_report_markdown  # noqa: E402
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
    def _composer_input(self) -> ComposerInput:
        return ComposerInput(
            metadata={"ticker": "AAPL", "company_name": "Apple Inc.", "data_as_of": "2026-05-11"},
            actual_per=35.46,
            valuation=ValuationOutput(
                method="PER",
                per_trailing=35.46,
                per_applied=35.46,
                eps=8.27,
                target_price=293.33,
                target_price_downside=253.0,
                stop_loss_price=270.0,
                target_upside_pct=8.6,
                stop_loss_downside_pct=-8.0,
                target_price_basis="LLM 판단: PER와 컨센서스 평균을 함께 참고",
                stop_loss_basis="리스크 관리 기준: 20일 지지선과 ATR 하단 참고",
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

    def test_quarterly_table_uses_compact_units(self) -> None:
        composer_input = self._composer_input()

        table = _render_quarterly_table(composer_input)

        self.assertIn("111.2B", table)
        self.assertIn("35.9B", table)
        self.assertNotIn("111,184,000,000", table)

    def test_composer_input_hides_internal_field_names_from_llm_prompt(self) -> None:
        composer_input = self._composer_input().model_copy(
            update={
                "price_technicals": {"rsi_14": 55.0},
                "cashflow_summary": {"free_cash_flow": 10.0},
                "consensus_summary": {"target_mean_price": 210.0},
                "market_context": {
                    "vix": {
                        "ticker": "^VIX",
                        "current": 18.5,
                        "reference_date": "2026-05-11",
                        "return_1m": 7.2,
                        "regime": "보통",
                    }
                },
            }
        )

        prompt_input = _build_input(composer_input)

        self.assertNotIn("price_technicals", prompt_input)
        self.assertNotIn("cashflow_summary", prompt_input)
        self.assertNotIn("consensus_summary", prompt_input)
        self.assertIn("price and momentum", prompt_input)
        self.assertIn("cash-flow quality", prompt_input)
        self.assertIn("analyst view", prompt_input)
        self.assertIn("VIX market volatility", prompt_input)
        self.assertIn("stop-loss", prompt_input)

    def test_polish_report_markdown_replaces_schema_label_with_human_label(self) -> None:
        report = (
            "### 5. 밸류에이션\n"
            "- `formula_text`: 목표가 = EPS × PER [출처: 입력: analyst view; valuation analysis formula_text]\n"
            "- 목표가 [출처: AAPL valuation: trailing PER 35]"
        )

        polished = polish_stock_report_markdown(report, data_as_of="2026-05-11T00:00:00Z")

        self.assertIn("산식: 목표가 = EPS × PER", polished)
        self.assertIn("Yahoo Finance analyst consensus, 2026-05-11T00:00:00Z", polished)
        self.assertIn("Yahoo Finance valuation, 2026-05-11T00:00:00Z", polished)
        self.assertNotIn("formula_text", polished)
        self.assertNotIn("입력:", polished)


if __name__ == "__main__":
    unittest.main()
