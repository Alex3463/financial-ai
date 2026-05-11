from __future__ import annotations

import re

REQUIRED_HEADERS = [
    "### 1. 투자 요약",
    "### 2. 재무 현황",
    "### 3. 성장 동력",
    "### 4. 리스크 요인",
    "### 5. 밸류에이션",
    "### 6. 투자 결론",
]
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

    positions: list[int] = []
    for header in REQUIRED_HEADERS:
        pos = report_md.find(header)
        if pos < 0:
            raise ValueError(f"Final report is missing required header: {header}")
        positions.append(pos)
    if positions != sorted(positions):
        raise ValueError("Final report headers are not in the expected order.")

    sec2 = re.search(
        r"^### 2\. 재무 현황\s*\n(.*?)(?=^### \d\.|\Z)",
        report_md,
        re.M | re.S,
    )
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
        if not cells or not re.match(r"^\d{4}-\d{2}-\d{2}$", cells[0]):
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
        formula_norm = _normalize_text(valuation_formula)
        report_norm = _normalize_text(report_md)
        if formula_norm not in report_norm:
            raise ValueError("Final report is missing the required valuation formula text.")

    if not re.search(r"목표가[^\n]{0,80}[\$₩￦]?\s*[\d,.]+", report_md):
        raise ValueError("Final report is missing target price text.")
    if not re.search(r"(1개월|3개월|6개월|12개월)", report_md):
        raise ValueError("Final report is missing investment horizon text.")

    growth = _extract_section(report_md, "### 3. 성장 동력")
    risk = _extract_section(report_md, "### 4. 리스크 요인")
    if not re.search(SOURCE_CITATION, growth):
        raise ValueError("Growth section is missing at least one citation.")
    if not re.search(SOURCE_CITATION, risk):
        raise ValueError("Risk section is missing at least one citation.")


def _extract_section(report_md: str, header: str) -> str:
    escaped = re.escape(header)
    match = re.search(rf"^{escaped}\s*\n(.*?)(?=^### \d\.|\Z)", report_md, re.M | re.S)
    return match.group(1) if match else ""


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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
