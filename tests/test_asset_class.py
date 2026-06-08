from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fio.asset_class import (  # noqa: E402
    classify_snapshot,
    is_etf_like,
    pipeline_branch_label,
)


class AssetClassTests(unittest.TestCase):
    def test_spy_classified_as_etf(self) -> None:
        snap = {
            "ticker": "SPY",
            "info": {"quoteType": "ETF", "longName": "SPDR S&P 500 ETF Trust"},
            "fund": {"top_holdings": [{"symbol": "NVDA", "weight_pct": 7.0}]},
            "financials": {"income_stmt": {}},
        }
        c = classify_snapshot(snap)
        self.assertEqual(c.asset_type, "ETF")
        self.assertEqual(c.branch, "etf")
        self.assertTrue(is_etf_like(snap))

    def test_aapl_classified_as_equity(self) -> None:
        snap = {
            "ticker": "AAPL",
            "info": {"quoteType": "EQUITY", "longName": "Apple Inc", "trailingPE": 28.0},
            "fund": {},
            "financials": {"income_stmt": {"2024-09-30": {"Total Revenue": 100}}},
        }
        c = classify_snapshot(snap)
        self.assertEqual(c.asset_type, "EQUITY")
        self.assertEqual(c.branch, "equity")
        self.assertFalse(is_etf_like(snap))

    def test_jepi_via_fund_holdings(self) -> None:
        snap = {
            "ticker": "JEPI",
            "info": {"longName": "JPMorgan Equity Premium Income ETF"},
            "fund": {
                "top_holdings": [{"symbol": "AVGO", "weight_pct": 1.7}],
                "fund_operations": {"expense_ratio": 0.0035},
                "fund_overview": {"legalType": "Exchange Traded Fund"},
            },
            "financials": {"income_stmt": {}},
        }
        c = classify_snapshot(snap)
        self.assertEqual(c.branch, "etf")
        self.assertIn(c.asset_type, {"ETF", "FUND"})

    def test_context_metadata_short_circuit(self) -> None:
        ctx = {"metadata": {"asset_type": "ETF"}}
        self.assertEqual(pipeline_branch_label(ctx), "etf")
        self.assertTrue(is_etf_like(ctx))

    def test_stub_report_branches_etf(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        from run_pipeline import _stub_report  # noqa: E402

        etf_ctx = {
            "metadata": {
                "asset_type": "ETF",
                "company_name": "JPMorgan Equity Premium Income ETF",
                "market_reference_date": "2026-06-08",
                "data_as_of": "2026-06-08",
            },
            "fund_profile": {
                "top_holdings": [{"symbol": "AVGO", "name": "Broadcom", "weight_pct": 1.7}],
                "fund_operations": {"expense_ratio": 0.0035},
            },
            "price_summary": {"current_price": 55.63},
            "price_technicals": {},
            "market_context": {"vix": {"current": 18.9, "regime": "보통"}},
        }
        equity_ctx = {
            "metadata": {"asset_type": "EQUITY", "company_name": "Apple Inc"},
            "price_summary": {"current_price": 200},
            "valuation": {"PER": 28},
            "price_technicals": {},
            "consensus_summary": {},
            "market_context": {},
        }
        etf_md = _stub_report("JEPI", etf_ctx)
        eq_md = _stub_report("AAPL", equity_ctx)
        self.assertIn("ETF 분석 리포트", etf_md)
        self.assertIn("### 2. 상위 보유종목/구성", etf_md)
        self.assertIn("투자 분석 리포트", eq_md)
        self.assertIn("### 2. 재무 현황", eq_md)
        self.assertNotIn("목표가", etf_md.split("### 6.")[0])  # ETF 요약엔 목표가 없음


if __name__ == "__main__":
    unittest.main()
