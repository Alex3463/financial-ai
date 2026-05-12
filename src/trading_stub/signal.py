from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass
class TradingSignal:
    ticker: str
    signal: Literal["buy", "hold", "sell"]
    confidence: float
    time_horizon: Literal["1m", "3m", "12m"]
    thesis_bullets: list[str]
    risk_triggers: list[str]
    source_report: str
    date: str


def today_str() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _extract_section_bullets(report_text: str, section_keyword: str) -> list[str]:
    # 정규식 블록 캡처는 환경/문서 편차에 취약할 수 있어,
    # 라인 단위로 섹션을 스캔하며 다음 헤딩까지를 블록으로 간주합니다.
    in_section = False
    bullets: list[str] = []
    for raw in report_text.splitlines():
        line = raw.strip()
        if re.match(r"^#{1,6}\s+", line):
            # 섹션 시작/종료 판정
            if in_section:
                break
            if section_keyword.lower() in line.lower():
                in_section = True
            continue
        if not in_section:
            continue

        # 일반 불릿/번호 목록을 최대한 넓게 수용 (리포트 포맷 편차 대응)
        item: str | None = None
        if len(line) >= 2 and line[0] in ("-", "*", "•") and line[1].isspace():
            item = line[2:].strip()
        else:
            mnum = re.match(r"^(\d+)\.\s+(.*)$", line)
            if mnum:
                item = (mnum.group(2) or "").strip()
        if not item:
            continue

        # 마크다운 강조 제거(가독성/후처리 용이)
        item = re.sub(r"\*\*(.*?)\*\*", r"\1", item).strip()
        item = re.sub(r"\*(.*?)\*", r"\1", item).strip()
        if item:
            bullets.append(item)

    # 너무 긴 항목은 신호 아티팩트에 부담이므로 적당히 컷
    trimmed = [b[:280].rstrip() for b in bullets if b]
    return trimmed[:5]


def extract_signal_from_report(
    report_text: str,
    eval_result: dict[str, Any],
    ticker: str,
    report_path: str,
    report_date: str,
) -> TradingSignal:
    m = re.search(r"투자\s*의견[^\n]*?(매수|중립|매도)", report_text)
    opinion_map = {"매수": "buy", "중립": "hold", "매도": "sell"}
    signal: Literal["buy", "hold", "sell"] = (
        opinion_map.get(m.group(1), "hold") if m else "hold"
    )
    if not m:
        # ETF 리포트는 표 형태로 투자 의견을 쓰는 경우가 많아, 간단한 폴백을 둡니다.
        m2 = re.search(r"\|\s*투자\s*의견\s*\|\s*\*\*(매수|중립|매도)\*\*", report_text)
        if m2:
            signal = opinion_map.get(m2.group(1), "hold")

    basis = eval_result.get("score_normalized_100")
    if basis is not None:
        confidence = min(float(basis) / 100.0, 1.0)
    else:
        confidence = min(float(eval_result.get("total_score", 0)) / 100.0, 1.0)

    hm = re.search(r"(12개월|6개월|3개월|1개월)", report_text)
    horizon_map = {"12개월": "12m", "6개월": "3m", "3개월": "3m", "1개월": "1m"}
    raw_h = horizon_map.get(hm.group(1), "12m") if hm else "12m"
    horizon = raw_h

    # ETF/주식 모두에서 최대한 작동하도록 키워드 폭을 넓힙니다.
    bullets = _extract_section_bullets(report_text, "성장 동력")
    if not bullets:
        bullets = _extract_section_bullets(report_text, "투자 전략")
    risks = _extract_section_bullets(report_text, "리스크 요인")
    if not risks:
        risks = _extract_section_bullets(report_text, "리스크")

    return TradingSignal(
        ticker=ticker,
        signal=signal,
        confidence=round(confidence, 4),
        time_horizon=horizon,
        thesis_bullets=bullets[:5],
        risk_triggers=risks[:5],
        source_report=report_path,
        date=report_date,
    )


def to_backtest_input(signal: TradingSignal) -> dict[str, Any]:
    horizon_days = {"1m": 30, "3m": 90, "12m": 365}
    return {
        "date": signal.date,
        "ticker": signal.ticker,
        "direction": signal.signal,
        "weight": signal.confidence,
        "horizon_days": horizon_days.get(signal.time_horizon, 365),
        "thesis": signal.thesis_bullets,
        "risk_triggers": signal.risk_triggers,
    }


def trading_signal_to_json(sig: TradingSignal) -> dict[str, Any]:
    return asdict(sig)
