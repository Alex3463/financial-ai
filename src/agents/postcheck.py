from __future__ import annotations

import re

# (섹션 번호, 제목 정규식) — Composer가 "###  2." 처럼 공백을 늘리거나 헤더 줄에 부제를 붙여도 매칭되게 함
_SECTION_SPECS: list[tuple[int, str]] = [
    (1, r"투자\s+요약"),
    (2, r"재무\s+현황"),
    (3, r"성장\s+동력"),
    (4, r"리스크\s+요인"),
    (5, r"밸류에이션"),
    (6, r"투자\s+결론"),
]

_HEADER_TO_SPEC: dict[str, tuple[int, str]] = {
    "### 1. 투자 요약": (1, r"투자\s+요약"),
    "### 2. 재무 현황": (2, r"재무\s+현황"),
    "### 3. 성장 동력": (3, r"성장\s+동력"),
    "### 4. 리스크 요인": (4, r"리스크\s+요인"),
    "### 5. 밸류에이션": (5, r"밸류에이션"),
    "### 6. 투자 결론": (6, r"투자\s+결론"),
}

INTERNAL_SOURCE_PATTERNS = [
    r"\bInput slice\b",
    r"입력\s*슬라이스",
    r"슬라이스\s*입력",
    r"\bprice_technicals\b",
    r"\bcashflow_summary\b",
    r"\bconsensus_summary\b",
    r"\bfinancials\.health\b",
    r"\bcontext\.",
    r"\[출처:\s*입력\s*:",
    r"\bformula_text\b",
]
SOURCE_CITATION = r"\[출처:[^\]]+\]"


_QUARTER_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_QUARTER_LABEL = re.compile(r"^\d{4}\s*[Qq]\s*[1-4]$")  # e.g. 2026Q1, 2026 Q1


def _is_acceptable_quarter_cell(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if v.upper() in {"N/A", "NA"}:
        return True
    if "데이터" in v and "미제공" in v:
        return True
    return bool(_QUARTER_DATE.match(v) or _QUARTER_LABEL.match(v))


def _section_header_line_re(num: int, title_re: str) -> re.Pattern[str]:
    # 제목 뒤 같은 줄에 "(요약)" 등 부제가 올 수 있음
    return re.compile(rf"^###\s*{num}\.\s*{title_re}(?:\s+[^\n]+)?\s*$", re.M)


def _section_body_re(num: int, title_re: str) -> re.Pattern[str]:
    return re.compile(
        rf"^###\s*{num}\.\s*{title_re}[^\n]*\n(.*?)(?=^###\s*\d+\.|\Z)",
        re.M | re.S,
    )


def _validate_required_headers(report_md: str) -> None:
    positions: list[int] = []
    for num, title_re in _SECTION_SPECS:
        m = _section_header_line_re(num, title_re).search(report_md)
        if not m:
            raise ValueError(f"Final report is missing required header for section {num}.")
        positions.append(m.start())
    if positions != sorted(positions):
        raise ValueError("Final report headers are not in the expected order.")


def _extract_section(report_md: str, header: str) -> str:
    spec = _HEADER_TO_SPEC.get(header)
    if not spec:
        return ""
    num, title_re = spec
    m = _section_body_re(num, title_re).search(report_md)
    return m.group(1) if m else ""


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_formula_for_match(text: str) -> str:
    """LLM이 ×/*, 전각 =, 공백만 바꾼 경우에도 부분 일치 검사가 되도록 정규화."""
    t = text.replace("＝", "=").replace("﹦", "=")
    for ch in ("×", "⋅", "·", "∗", "﹡"):
        t = t.replace(ch, "*")
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _valuation_formula_in_report(formula: str, report_md: str) -> bool:
    fn = _normalize_formula_for_match(formula)
    rn = _normalize_formula_for_match(report_md)
    if not fn:
        return False
    if fn in rn:
        return True
    fn_compact = re.sub(r"\s+", "", fn)
    rn_compact = re.sub(r"\s+", "", rn)
    return fn_compact in rn_compact


def validate_report_contract(
    report_md: str,
    *,
    actual_per: float | None = None,
    valuation_formula: str | None = None,
) -> None:
    if not re.search(r"^# .+ 투자 분석 리포트\s*$", report_md, re.M):
        raise ValueError("Final report is missing the required title line.")

    for pattern in INTERNAL_SOURCE_PATTERNS:
        if re.search(pattern, report_md, re.I):
            raise ValueError("Final report contains internal source leakage.")

    _validate_required_headers(report_md)

    sec2 = _section_body_re(2, r"재무\s+현황").search(report_md)
    if not sec2:
        raise ValueError("Section 2 could not be extracted for postcheck.")

    pipe_lines = [line for line in sec2.group(1).splitlines() if line.strip().startswith("|")]
    if not pipe_lines or not pipe_lines[0].strip().startswith("| 분기 |"):
        raise ValueError("Section 2 must begin with a quarter-row Markdown table.")
    data_rows = pipe_lines[2:]
    if len(data_rows) < 4:
        raise ValueError("Section 2 must start with a 4-row Markdown table.")
    for row in data_rows[:4]:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if not cells or not _is_acceptable_quarter_cell(cells[0]):
            raise ValueError("Section 2 data rows must use quarter dates in the first column.")

    _validate_extended_contract(report_md, actual_per=actual_per, valuation_formula=valuation_formula)


def _validate_extended_contract(
    report_md: str,
    *,
    actual_per: float | None,
    valuation_formula: str | None,
) -> None:
    if actual_per is not None:
        reported_per = _extract_reported_per(report_md)
        if reported_per is None:
            raise ValueError("Final report is missing a comparable trailing PER line.")
        if abs(float(reported_per) - float(actual_per)) > 2.0:
            raise ValueError(
                f"Final report PER mismatch: report={reported_per}, context={actual_per}."
            )

    if valuation_formula:
        if not re.search(r"\d", valuation_formula):
            raise ValueError("Valuation formula must include numeric inputs.")
        if not _valuation_formula_in_report(valuation_formula, report_md):
            raise ValueError("Final report is missing the required valuation formula text.")

    if not _has_labeled_number(report_md, "현재가"):
        raise ValueError("Final report is missing current price text.")
    if not re.search(r"목표가[^\n]{0,80}[\$₩￦]?\s*[\d,.]+", report_md):
        raise ValueError("Final report is missing target price text.")
    if not _has_labeled_number(report_md, "손절가"):
        raise ValueError("Final report is missing stop-loss price text.")
    if not re.search(r"\bVIX\b[^\n]{0,120}(?:\d|데이터\s*미제공)", report_md, re.I):
        raise ValueError("Final report is missing VIX market volatility text.")
    if not re.search(r"(1개월|3개월|6개월|12개월)", report_md):
        raise ValueError("Final report is missing investment horizon text.")

    growth = _extract_section(report_md, "### 3. 성장 동력")
    risk = _extract_section(report_md, "### 4. 리스크 요인")
    if not re.search(SOURCE_CITATION, growth):
        raise ValueError("Growth section is missing at least one citation.")
    if not re.search(SOURCE_CITATION, risk):
        raise ValueError("Risk section is missing at least one citation.")


def _extract_reported_per(report_md: str) -> float | None:
    section = _extract_section(report_md, "### 2. 재무 현황")
    patterns = [
        r"trailing\s+PER\s*약\s*(\d+(?:\.\d+)?)",
        r"PER\s*약\s*(\d+(?:\.\d+)?)",
        r"trailing\s+P/?E\s*[:：]?\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, section, re.I)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _has_labeled_number(report_md: str, label: str) -> bool:
    escaped = re.escape(label)
    label_then_number = rf"{escaped}[^\n]{{0,100}}[\$₩￦]?\s*[\d,.]+"
    number_then_label = rf"[\$₩￦]?\s*[\d,.]+[^\n]{{0,40}}{escaped}"
    return bool(
        re.search(label_then_number, report_md, re.I)
        or re.search(number_then_label, report_md, re.I)
    )
