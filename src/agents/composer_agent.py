from __future__ import annotations

from agents.gateway import composer_max_tokens, dump_json, load_prompt_text, run_structured_agent
from agents.schemas import ComposerInput, ComposerOutput

_PROMPT = load_prompt_text("composer.md")


def _format_number(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.0f}"


def _render_quarterly_table(composer_input: ComposerInput) -> str:
    lines = [
        "| 분기 | 매출 | 영업이익 | 순이익 |",
        "|---|---:|---:|---:|",
    ]
    for row in composer_input.financials.quarterly_table:
        lines.append(
            "| {quarter} | {revenue} | {op_income} | {net_income} |".format(
                quarter=row.quarter,
                revenue=_format_number(row.revenue),
                op_income=_format_number(row.op_income),
                net_income=_format_number(row.net_income),
            )
        )
    return "\n".join(lines)


def _render_per_line(composer_input: ComposerInput) -> str:
    rows = composer_input.financials.quarterly_table
    as_of = rows[0].as_of if rows else composer_input.metadata.get("data_as_of", "")
    per_value = composer_input.actual_per
    if per_value is None:
        per_value = composer_input.financials.per_trailing
    if per_value is None:
        return f"trailing PER 약 데이터 미제공 [출처: yf.info.trailingPE, {as_of}]"
    return f"trailing PER 약 {per_value:.2f} [출처: yf.info.trailingPE, {as_of}]"


def _build_input(composer_input: ComposerInput) -> str:
    exact_table = _render_quarterly_table(composer_input)
    exact_per_line = _render_per_line(composer_input)
    return (
        "다음 구조화 입력만 사용해 ComposerOutput JSON을 생성하세요.\n"
        "report_md 는 완성된 Markdown 리포트 전문이어야 하며 code fence 를 포함하면 안 됩니다.\n\n"
        "Section 2 must begin with this exact 4-quarter table shape:\n"
        f"{exact_table}\n\n"
        "Immediately after that table, write this exact trailing PER line:\n"
        f"{exact_per_line}\n\n"
        "Reuse the actual citation strings from the input data when you reference evidence.\n\n"
        f"{dump_json(composer_input.model_dump(mode='json'))}"
    )


async def run_composer_agent(cfg: dict, composer_input: ComposerInput) -> ComposerOutput:
    return await run_structured_agent(
        cfg=cfg,
        name="ComposerAgent",
        instructions=_PROMPT,
        input_text=_build_input(composer_input),
        output_type=ComposerOutput,
        max_tokens=composer_max_tokens(cfg),
    )
