from __future__ import annotations

from agents.gateway import composer_max_tokens, dump_json, load_prompt_text, run_structured_agent
from agents.source_citations import polish_stock_report_markdown
from agents.schemas import ComposerInput, ComposerOutput

_PROMPT = load_prompt_text("composer.md")
_INTERNAL_SOURCE_TOKENS = (
    "Input slice",
    "입력 슬라이스",
    "슬라이스 입력",
    "price_technicals",
    "cashflow_summary",
    "consensus_summary",
    "financials.health",
    "market_context",
)


def _format_number(value: float | None) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(value)
    for threshold, suffix in ((1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M")):
        if abs_value >= threshold:
            return f"{value / threshold:.1f}{suffix}"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
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


def _sanitize_internal_sources(value: object, *, data_as_of: str) -> object:
    if isinstance(value, dict):
        return {
            key: _sanitize_internal_sources(item, data_as_of=data_as_of)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_internal_sources(item, data_as_of=data_as_of) for item in value]
    if isinstance(value, str) and any(token in value for token in _INTERNAL_SOURCE_TOKENS):
        return f"yfinance snapshot fields, {data_as_of}"
    return value


def _build_report_payload(composer_input: ComposerInput) -> dict[str, object]:
    raw = composer_input.model_dump(mode="json")
    return {
        "metadata": raw.get("metadata", {}),
        "business profile": raw.get("company_profile", {}),
        "price and momentum": raw.get("price_technicals", {}),
        "volume trading": raw.get("volume_summary", {}),
        "benchmark comparison": raw.get("market_context", {}),
        "VIX market volatility": (raw.get("market_context", {}) or {}).get("vix", {}),
        "ownership and holders": raw.get("holder_summary", {}),
        "cash-flow quality": raw.get("cashflow_summary", {}),
        "analyst view": raw.get("consensus_summary", {}),
        "actual trailing PER": raw.get("actual_per"),
        "valuation analysis": raw.get("valuation", {}),
        "financial statement analysis": raw.get("financials", {}),
        "growth catalyst analysis": raw.get("growth", {}),
        "risk analysis": raw.get("risk", {}),
        "company news and deep reads": raw.get("news_summary", {}),
    }


def _build_input(composer_input: ComposerInput) -> str:
    exact_table = _render_quarterly_table(composer_input)
    exact_per_line = _render_per_line(composer_input)
    raw_payload = _sanitize_internal_sources(
        composer_input.model_dump(mode="json"),
        data_as_of=str(composer_input.metadata.get("data_as_of", "")),
    )
    payload = _build_report_payload(ComposerInput.model_validate(raw_payload))
    return (
        "다음 구조화 입력만 사용해 ComposerOutput JSON을 생성하세요.\n"
        "report_md 는 완성된 Markdown 리포트 전문이어야 하며 code fence 를 포함하면 안 됩니다.\n\n"
        "Section 2 must begin with this exact 4-quarter table shape:\n"
        f"{exact_table}\n\n"
        "Immediately after that table, write this exact trailing PER line:\n"
        f"{exact_per_line}\n\n"
        "Use the supplemental fields for richer content:\n"
        "- business profile: 회사 설명 1줄\n"
        "- price and volume indicators: 이동평균, RSI, 52주 위치, 수익률, 거래량 변동\n"
        "- benchmark comparison: 벤치마크 대비 초과/부진 수익률\n"
        "- VIX market volatility: VIX 현재값, 1개월 변화, 시장 변동성 regime\n"
        "- stop-loss: valuation analysis의 stop_loss_price와 stop_loss_basis를 리스크 관리 기준으로 사용\n"
        "- ownership and holders: 기관/펀드 보유자 상위 목록\n"
        "- cash-flow and quality indicators: OCF, FCF, CapEx, current ratio, 순현금/순차입금\n"
        "- analyst consensus: buy/hold/sell 분포, 목표가 범위, 평균 목표가 업사이드\n"
        "- company news and deep reads: 회사 관련 기사 우선\n\n"
        "Citation policy:\n"
        "- 출처는 실제 URL, yfinance 필드명, 또는 사람이 읽을 수 있는 테이블/스냅샷 출처만 씁니다.\n"
        "- 내부 데이터 키나 입력 묶음명은 report_md에 출처로 쓰지 마세요.\n\n"
        f"{dump_json(payload)}"
    )


async def run_composer_agent(cfg: dict, composer_input: ComposerInput) -> ComposerOutput:
    output = await run_structured_agent(
        cfg=cfg,
        name="ComposerAgent",
        instructions=_PROMPT,
        input_text=_build_input(composer_input),
        output_type=ComposerOutput,
        max_tokens=composer_max_tokens(cfg),
    )
    return output.model_copy(
        update={
            "report_md": polish_stock_report_markdown(
                output.report_md,
                data_as_of=str(composer_input.metadata.get("data_as_of", "")),
            )
        }
    )
