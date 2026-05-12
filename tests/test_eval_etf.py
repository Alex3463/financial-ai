from __future__ import annotations

import unittest

from eval.rules import run_all_checks
from eval.rubric import aggregate


class EtfEvalRubricTests(unittest.TestCase):
    def test_etf_rubric_does_not_require_target_price(self) -> None:
        report = """# SPY (SPDR S&P 500 ETF Trust) ETF 분석 리포트

### 1. ETF 요약
| 항목 | 내용 |
|---|---|
| 투자 의견 | **매수** |
| 투자 기간 | 12개월 |
| 현재가/기준일 | 100 / 2026-05-12 |
| 핵심 테마 | 미국 대형주 |
| 데이터 가용성 | 보수/회전율/AUM 제공 |
| 지금 봐야 할 이벤트 | CPI |

### 2. 상위 보유종목/구성
- NVDA 7.85% [출처: yfinance.funds_data]

### 3. 운용 구조·비용
- 보수(Expense Ratio) 0.09%로 장기 보유 비용 부담이 낮습니다. [출처: yfinance.funds_data]
- 회전율(Turnover) 0.03으로 거래비용이 상대적으로 제한적일 수 있습니다. [출처: yfinance.funds_data]

### 4. 리스크(괴리·유동성·집중도)
- NAV 괴리/스프레드/유동성 언급. [출처: yfinance snapshot fields]

### 5. 시장/모멘텀(가격·거래량·VIX)
- RSI 55, VIX 16.2 [출처: yf.history, yf.history(^VIX)]
- 섹터 기반 전망(3~12개월): 기술 35.9%… 베이스/상방/하방 시나리오. [출처: yfinance.funds_data]

### 6. 투자 전략(투자자별)
| 투자자 | 제안 |
|---|---|
| 신규 진입자 | 분할매수 |
| 기존 보유자 | 홀드 |
| 단기/스윙 | 변동성 관리 |
| 중기/장기 | 장기보유 |
"""
        context = {
            "metadata": {"asset_type": "ETF"},
            "fund_profile": {
                "fund_operations": {
                    "expense_ratio": 0.0009,
                    "holdings_turnover": 0.03,
                    "total_net_assets": 100.0,
                },
                "sector_weightings": {"Technology": 0.3586},
            },
        }

        rs = run_all_checks(report, context)
        self.assertEqual(rs.get("_rubric_variant"), "ETF")
        self.assertNotIn("목표가 미기재", " | ".join(rs.get("flags", [])))

        agg = aggregate(rs, None)
        self.assertEqual(agg.get("rubric_mode"), "M0_etf_rules")
        self.assertIn("cost_structure", agg.get("breakdown", {}))


if __name__ == "__main__":
    unittest.main()

