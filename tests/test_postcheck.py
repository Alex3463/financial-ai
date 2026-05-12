from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.postcheck import validate_report_contract  # noqa: E402


VALID_REPORT = """# AAPL (Apple Inc.) 투자 분석 리포트

### 1. 투자 요약
| 항목 | 내용 |
|---|---|
| 투자 의견 | **투자 의견**: 중립 |
| 현재가/기준일 | 현재가 200달러 / 2026-05-11 |
| 목표가 | 목표가 210달러 |
| 손절가 | 손절가 180달러 |
| 기간 | 12개월 |
| VIX/시장 변동성 | VIX 18.5, 보통 [출처: yf.history(^VIX).Close, 2026-05-11] |
- 핵심 쟁점: 성장성과 밸류에이션 균형.
- 지금 봐야 할 이벤트: 다음 실적 발표.

### 2. 재무 현황
| 분기 | 매출 | 영업이익 | 순이익 |
|---|---:|---:|---:|
| 2026-03-31 | 111.2B | 35.9B | 29.6B |
| 2025-12-31 | 143.8B | 50.9B | 42.1B |
| 2025-09-30 | 102.5B | 32.4B | 27.5B |
| 2025-06-30 | 94.0B | 28.2B | 23.4B |
trailing PER 약 35.32 [출처: yf.info.trailingPE, 2026-05-11T14:14:19Z]

| 품질 지표 | 해석 |
|---|---|
| FCF | 26.7B [출처: yf.cashflow.Free Cash Flow, 2026-03-31] |

### 3. 성장 동력
- Services: 고마진 서비스 성장이 마진 방어에 기여 [출처: https://example.com/growth]

### 4. 리스크 요인
| 리스크 | 하방 메커니즘 | 관찰 트리거 |
|---|---|---|
| 멀티플 | PER 축소 시 목표가 하향 | 실적 둔화 [출처: https://example.com/risk] |
- 금리: 할인율 상승 시 멀티플 압박 [출처: https://example.com/rates]

### 5. 밸류에이션
- 목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러
- 현재가 200달러, 목표가 210달러, 하방 시나리오 180달러 [출처: yf.info.trailingPE, yf.info.trailingEps]
- 손절가 180달러는 장기 가치판단이 아니라 리스크 관리 기준입니다 [출처: yf.history.High/Low/Close, 2026-05-11].
- VIX 18.5는 시장 변동성이 보통 국면임을 시사합니다 [출처: yf.history(^VIX).Close, 2026-05-11].

### 6. 투자 결론
| 투자자 | 전략 |
|---|---|
| 신규 진입자 | 분할 접근 |
| 기존 보유자 | 보유 |
- 12개월 관점 중립입니다.
"""


class PostcheckTests(unittest.TestCase):
    def test_validate_report_contract_accepts_extended_contract(self) -> None:
        validate_report_contract(
            VALID_REPORT,
            actual_per=35.32,
            valuation_formula="목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러",
        )

    def test_validate_report_contract_rejects_internal_source_leakage(self) -> None:
        leaked = VALID_REPORT.replace(
            "고마진 서비스 성장이 마진 방어에 기여",
            "price_technicals 내부 입력을 보면 고마진 서비스 성장이 마진 방어에 기여",
        )

        with self.assertRaisesRegex(ValueError, "internal"):
            validate_report_contract(leaked, actual_per=35.32, valuation_formula="목표가 =")

    def test_validate_report_contract_rejects_input_style_source_labels(self) -> None:
        leaked = VALID_REPORT.replace(
            "[출처: https://example.com/growth]",
            "[출처: 입력: analyst view]",
        )

        with self.assertRaisesRegex(ValueError, "internal"):
            validate_report_contract(leaked, actual_per=35.32, valuation_formula="목표가 =")

    def test_validate_report_contract_rejects_schema_token_leakage(self) -> None:
        leaked = VALID_REPORT.replace(
            "목표가 = (기준 PER 35.32)",
            "formula_text: 목표가 = (기준 PER 35.32)",
        )

        with self.assertRaisesRegex(ValueError, "internal"):
            validate_report_contract(leaked, actual_per=35.32, valuation_formula="목표가 =")

    def test_validate_report_contract_rejects_per_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "PER"):
            validate_report_contract(
                VALID_REPORT,
                actual_per=28.0,
                valuation_formula="목표가 =",
            )

    def test_validate_report_contract_rejects_missing_formula(self) -> None:
        with self.assertRaisesRegex(ValueError, "formula"):
            validate_report_contract(
                VALID_REPORT,
                actual_per=35.32,
                valuation_formula="목표가 = 존재하지 않는 산식",
            )

    def test_validate_report_contract_rejects_missing_growth_or_risk_citation(self) -> None:
        no_growth_citation = VALID_REPORT.replace(
            " [출처: https://example.com/growth]",
            "",
        )

        with self.assertRaisesRegex(ValueError, "citation"):
            validate_report_contract(
                no_growth_citation,
                actual_per=35.32,
                valuation_formula="목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러",
            )

    def test_validate_report_contract_rejects_missing_stop_loss_or_vix(self) -> None:
        no_stop_loss = VALID_REPORT.replace("손절가", "리스크 기준")

        with self.assertRaisesRegex(ValueError, "stop-loss"):
            validate_report_contract(
                no_stop_loss,
                actual_per=35.32,
                valuation_formula="목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러",
            )

        no_vix = VALID_REPORT.replace("VIX", "변동성지수")

        with self.assertRaisesRegex(ValueError, "VIX"):
            validate_report_contract(
                no_vix,
                actual_per=35.32,
                valuation_formula="목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러",
            )

    def test_section2_postcheck_when_header_has_inline_suffix(self) -> None:
        relaxed = VALID_REPORT.replace("### 2. 재무 현황\n", "### 2. 재무 현황 (분기 추이)\n", 1)
        validate_report_contract(
            relaxed,
            actual_per=35.32,
            valuation_formula="목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러",
        )

    def test_valuation_formula_matches_when_report_uses_ascii_multiply(self) -> None:
        formula = "목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러"
        swapped = VALID_REPORT.replace(
            "목표가 = (기준 PER 35.32) × (TTM EPS 5.95) = 210달러",
            "목표가 = (기준 PER 35.32) * (TTM EPS 5.95) = 210달러",
        )
        validate_report_contract(swapped, actual_per=35.32, valuation_formula=formula)


if __name__ == "__main__":
    unittest.main()
