from __future__ import annotations

from typing import Any

# M0: rules.py 가 채우는 3항목(출처·리스크·예측) 양수 합 상한. 나머지 6항목은 Judge(M2).
M0_AUTO_SCORE_CAP = 10 + 10 + 5

RUBRIC_MAX = {
    "data_accuracy": 20,
    "source_transparency": 10,
    "financial_quality": 15,
    "valuation_soundness": 20,
    "logic_consistency": 10,
    "risk_coverage": 10,
    "bias_check": 5,
    "forecast_verifiability": 5,
    "readability": 5,
}


def aggregate(rule_scores: dict[str, Any], llm_judge_scores: dict[str, Any] | None = None) -> dict[str, Any]:
    rs = dict(rule_scores)
    flags = list(rs.pop("flags", []))

    breakdown: dict[str, Any] = {}

    for k in ["source_transparency", "risk_coverage", "forecast_verifiability"]:
        breakdown[k] = rs.get(k, 0)

    if llm_judge_scores:
        breakdown.update(llm_judge_scores)
    else:
        for k in [
            "data_accuracy",
            "financial_quality",
            "valuation_soundness",
            "logic_consistency",
            "bias_check",
            "readability",
        ]:
            breakdown[k] = None

    penalty = sum(
        v
        for k, v in rs.items()
        if ("penalty" in k or "deduction" in k) and isinstance(v, (int, float))
    )

    computable = {k: v for k, v in breakdown.items() if v is not None}
    total = sum(computable.values()) + penalty

    if llm_judge_scores:
        rubric_mode = "M2_full"
        normalized_100 = float(max(0.0, min(100.0, total)))
        grade = _interpret(normalized_100)
        grade_note = (
            "M2: 규칙(출처·리스크·목표가·페널티) + LLM Judge 6항목 합산. "
            f"이론 만점 100 + 페널티. total_score={total}."
        )
    else:
        rubric_mode = "M0_rules_only"
        cap = float(M0_AUTO_SCORE_CAP)
        raw_for_scale = max(0.0, float(total))
        normalized_100 = max(0.0, min(100.0, (raw_for_scale / cap) * 100.0))
        grade = _interpret(normalized_100)
        grade_note = (
            f"M0 규칙만 적용: 양수 항목 합 상한 약 {int(cap)}점(3/9 항목). "
            f"원점수 total_score={total} → 100점 환산 약 {normalized_100:.1f}로 등급 산정. "
            f"config eval.use_llm_judge 로 M2 전체 루브릭을 쓸 수 있습니다."
        )

    return {
        "total_score": round(float(total), 2),
        "score_normalized_100": round(normalized_100, 2),
        "breakdown": breakdown,
        "penalty": penalty,
        "flags": flags,
        "grade": grade,
        "grade_note": grade_note,
        "rubric_mode": rubric_mode,
        "auto_coverage": f"{len(computable)}/{len(RUBRIC_MAX)} 항목 자동 채점 ({rubric_mode})",
    }


def _interpret(score: float) -> str:
    if score >= 85:
        return "A: 의사결정 보조 가능 (원자료 검증은 여전히 필요)"
    if score >= 70:
        return "B: 참고 가능, 핵심 숫자·가정 재검증 필요"
    if score >= 50:
        return "C: 투자 판단 부족, 논리·데이터 보강 필요"
    return "D: 폐기 또는 전면 재작성 권장"
