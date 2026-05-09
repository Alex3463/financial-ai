"""리포트 내 '의미 있는 숫자' 개수 — 출처 비율 분모."""

from __future__ import annotations

import re


# 청사진 NUMBER_PATTERN 확장: 통화·소수·천단위 콤마까지 포함 (겹침은 스팬 병합으로 1회만 카운트)
_NUMBER_SUBPATTERNS = [
    r"\d+[\.,]?\d*\s*[%억조원달러$x배]",  # 10%, 3억 달러
    r"[\$₩￦]\s*\d+[\.,]?\d*\b",  # $200
    r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",  # 1,234,567
    r"\b\d+\.\d+\b",  # 35.47 (PER, EPS 등)
]


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    out: list[tuple[int, int]] = [spans[0]]
    for s, e in spans[1:]:
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def count_numeric_spans(report_text: str) -> tuple[int, list[tuple[int, int]]]:
    """겹치지 않게 병합한 숫자 스팬 개수와 스팬 목록."""
    spans: list[tuple[int, int]] = []
    for pat in _NUMBER_SUBPATTERNS:
        for m in re.finditer(pat, report_text):
            spans.append((m.start(), m.end()))
    merged = _merge_spans(spans)
    return len(merged), merged
