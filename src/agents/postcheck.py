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


def validate_report_contract(report_md: str) -> None:
    if not re.search(r"^# .+ 투자 분석 리포트\s*$", report_md, re.M):
        raise ValueError("Final report is missing the required title line.")

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
