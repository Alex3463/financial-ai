from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.source_citations import (  # noqa: E402
    normalize_citation_source,
    normalize_report_citations,
    polish_etf_report_markdown,
    polish_stock_report_markdown,
)


class SourceCitationTests(unittest.TestCase):
    def test_normalize_fund_operations_leak(self) -> None:
        src = "yfinance.funds_data fund_operations.expense_ratio/ provided input"
        out = normalize_citation_source(src, data_as_of="2026-06-08")
        self.assertIn("Yahoo Finance ETF profile", out)
        self.assertNotIn("provided input", out)
        self.assertNotIn("fund_operations", out)

    def test_normalize_holdings_leak(self) -> None:
        src = "holdings table provided in input"
        out = normalize_citation_source(src, data_as_of="2026-06-08")
        self.assertIn("Yahoo Finance ETF holdings", out)

    def test_keep_public_url(self) -> None:
        url = "https://finance.yahoo.com/quote/SPY/community/"
        self.assertEqual(normalize_citation_source(url), url)

    def test_polish_etf_report_strips_metadata_in_body(self) -> None:
        raw = (
            "ETF 성격 | `metadata.asset_type=ETF`에 기반하며 패시브 ETF [출처: metadata.asset_type / provided input]\n"
            "- 보수 0.09% [출처: yfinance.funds_data fund_operations.expense_ratio/ provided input]"
        )
        polished = polish_etf_report_markdown(raw, data_as_of="2026-06-08")
        self.assertNotIn("metadata.asset_type", polished)
        self.assertNotIn("provided input", polished)
        self.assertIn("Yahoo Finance ETF profile", polished)

    def test_polish_stock_report_formula_and_input(self) -> None:
        report = (
            "### 5. 밸류에이션\n"
            "- `formula_text`: 목표가 = EPS × PER [출처: 입력: analyst view; valuation analysis formula_text]\n"
            "- 목표가 [출처: AAPL valuation: trailing PER 35]"
        )
        polished = polish_stock_report_markdown(report, data_as_of="2026-05-11T00:00:00Z")
        self.assertIn("산식: 목표가 = EPS × PER", polished)
        self.assertIn("Yahoo Finance analyst consensus", polished)
        self.assertIn("Yahoo Finance valuation", polished)
        self.assertNotIn("formula_text", polished)
        self.assertNotIn("입력:", polished)

    def test_normalize_report_citations_block(self) -> None:
        md = "RSI 53 [출처: yfinance snapshot fields, 2026-06-08T14:38:04Z]"
        out = normalize_report_citations(md, data_as_of="2026-06-08")
        self.assertIn("Yahoo Finance price history", out)

    def test_polish_preserves_markdown_newlines(self) -> None:
        md = "# SPY ETF 분석 리포트\n\n### 1. ETF 요약\n\n| 항목 | 내용 |\n|---|---|\n| ETF 성격 | 패시브 [출처: provided input]\n"
        polished = polish_etf_report_markdown(md, data_as_of="2026-06-08")
        self.assertIn("\n\n### 1.", polished)
        self.assertIn("\n|---|---|\n", polished)
        self.assertNotIn("리포트 ### 1.", polished)


if __name__ == "__main__":
    unittest.main()
