from __future__ import annotations

import re
from typing import Any

from eval.number_scan import count_numeric_spans

OVERCONFIDENCE = [
    r"(무조건|확실히|반드시|절대로)\s*(오른|상승|매수|이익)",
    r"(놓치면\s*안|손실\s*없|무리\s*없)",
    r"(100%\s*(확실|보장|수익))",
]
SOURCE_CITATION = r"\[출처:[^\]]+\]"
RISK_KEYWORDS = ["경쟁", "규제", "금리", "환율", "멀티플", "실적", "부진", "하락", "감소"]
TARGET_PRICE = r"목표가.{0,40}[\$₩￦]?\s*[\d,.]+"
FORMULA_KEYWORDS = r"(PER|DCF|EPS|PBR|배수|할인율|성장률).{0,80}(목표가|산출|×|=|\*)"


def _try_per_from_text(chunk: str) -> float | None:
    """재무·밸류 문맥을 구분해 trailing/실적 PER 후보만 추출."""
    patterns = [
        r"PER\s*약\s*(\d+\.?\d*)",
        r"trailing\s+P/?E?R?\s*[^\d\n]{0,20}(\d+\.?\d*)",
        r"(?:trailing\s*)?(?:P/?E|PER)\s*[:：]\s*(\d+\.?\d*)",
        r"(?:P/?E|PER)\s+(\d+\.?\d*)\s*[x×]",
    ]
    for p in patterns:
        m = re.search(p, chunk, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _extract_reported_per(text: str) -> float | None:
    """
    리포트에 기재된 '실제/트레일링 PER'만 대조합니다.
    밸류에이션의 '목표가 = EPS × PER 26' 처럼 적용 배수로 쓰인 숫자는 제외합니다.
    """
    sec2 = re.search(
        r"(?:^|\n)#{1,6}\s*[^\n]*2\.[^\n]*재무[^\n]*\n(.*?)(?=\n#{1,6}\s|\Z)",
        text,
        re.S | re.I,
    )
    if sec2:
        v = _try_per_from_text(sec2.group(1))
        if v is not None:
            return v

    for line in text.splitlines():
        if re.search(
            r"목표가|EPS\s*[×x*]\s*PER|PER\s*\d+\s*\[출처|적용\s*배수|밸류에이션\s*방법",
            line,
            re.I,
        ):
            continue
        v = _try_per_from_text(line)
        if v is not None:
            return v
    return None


def run_all_checks(report_text: str, context: dict[str, Any]) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    flags: list[str] = []

    n_numbers, _ = count_numeric_spans(report_text)
    n_cited = len(re.findall(SOURCE_CITATION, report_text))
    cite_rate = n_cited / max(n_numbers, 1)
    scores["source_transparency"] = min(10, round(cite_rate * 10))
    if cite_rate < 0.5:
        flags.append(f"출처 누락: 숫자 {n_numbers}개 중 {n_cited}개만 출처 표기 ({cite_rate:.0%})")

    found_overconf = [p for p in OVERCONFIDENCE if re.search(p, report_text)]
    if found_overconf:
        scores["bias_penalty"] = -3
        flags.append(f"과도한 확신 표현 {len(found_overconf)}건 감지 → -3점")

    covered = [kw for kw in RISK_KEYWORDS if kw in report_text]
    risk_score = round(len(covered) / len(RISK_KEYWORDS) * 10)
    scores["risk_coverage"] = risk_score
    missing = set(RISK_KEYWORDS) - set(covered)
    if risk_score < 6:
        flags.append(f"리스크 미흡: 미커버 키워드 → {list(missing)}")

    has_target = bool(re.search(TARGET_PRICE, report_text))
    has_formula = bool(re.search(FORMULA_KEYWORDS, report_text, re.I))
    if has_target and has_formula:
        scores["forecast_verifiability"] = 5
    elif has_target:
        scores["forecast_verifiability"] = 3
        flags.append("목표가는 있으나 산식 미제시: 재현 불가")
    else:
        scores["forecast_verifiability"] = 0
        flags.append("목표가 미기재")

    reported_pe = _extract_reported_per(report_text)
    actual_pe = None
    val = context.get("valuation") or {}
    if isinstance(val, dict):
        actual_pe = val.get("PER")
    try:
        actual_pe_f = float(actual_pe) if actual_pe is not None else None
    except (TypeError, ValueError):
        actual_pe_f = None

    if reported_pe is not None and actual_pe_f is not None:
        if abs(reported_pe - actual_pe_f) > 2.0:
            scores["data_accuracy_penalty"] = -5
            flags.append(
                f"PER 불일치: 리포트={reported_pe}, 원자료={actual_pe_f} → -5점"
            )

    scores["flags"] = flags
    return scores
