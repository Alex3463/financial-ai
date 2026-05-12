from __future__ import annotations

import re
from typing import Any

from agents.gateway import composer_max_tokens, dump_json, load_prompt_text, run_structured_agent
from agents.schemas import EtfComposerInput, EtfComposerOutput, EtfHoldingsOutput

_PROMPT = load_prompt_text("composer_etf.md")
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


def _format_weight(value: float | None) -> str:
    if value is None:
        return "데이터 미제공"
    return f"{value:.2f}%"


def _render_holdings_table(holdings: EtfHoldingsOutput) -> str:
    lines = [
        "| 순위 | 종목 | 티커 | 비중 | 비고 |",
        "|---:|---|---|---:|---|",
    ]
    for i, h in enumerate(holdings.top_holdings[:10], start=1):
        name = (h.name or "").strip() or "N/A"
        ticker = (h.ticker or "").strip() or "N/A"
        lines.append(
            "| {i} | {name} | {ticker} | {w} | {notes} |".format(
                i=i,
                name=name,
                ticker=ticker,
                w=_format_weight(h.weight_pct),
                notes=(h.notes or "").strip(),
            )
        )
    if len(lines) == 2:
        lines.append("| 1 | 데이터 미제공 | N/A | 데이터 미제공 | 보유종목 데이터를 확보하지 못했습니다. |")
    return "\n".join(lines)


def _build_payload(etf_input: EtfComposerInput) -> dict[str, Any]:
    raw = etf_input.model_dump(mode="json")
    holdings_table = _render_holdings_table(etf_input.holdings)
    return {
        "metadata": raw.get("metadata", {}),
        "business profile": raw.get("company_profile", {}),
        "price and momentum": raw.get("price_technicals", {}),
        "volume trading": raw.get("volume_summary", {}),
        "VIX market volatility": (raw.get("market_context", {}) or {}).get("vix", {}),
        "fund profile": raw.get("fund_profile", {}),
        "holdings summary": raw.get("holdings", {}),
        "holdings table (markdown)": holdings_table,
        "ops hints": "If fund profile includes expense_ratio/holdings_turnover/total_net_assets or sector/asset class weights, summarize them in section 3 with plain language and decision guidance.",
        "company news and deep reads": raw.get("news_summary", {}),
    }


def _build_input(etf_input: EtfComposerInput) -> str:
    payload = _build_payload(etf_input)
    return (
        "다음 구조화 입력만 사용해 EtfComposerOutput JSON을 생성하세요.\n"
        "report_md 는 완성된 Markdown 리포트 전문이어야 하며 code fence 를 포함하면 안 됩니다.\n\n"
        "Use this pre-rendered holdings table for section 2:\n"
        f"{payload['holdings table (markdown)']}\n\n"
        "Use fund profile/operations fields for section 3 when available.\n\n"
        f"{dump_json(payload)}"
    )


def _polish_report_markdown(report_md: str, *, data_as_of: str = "") -> str:
    """
    Replace internal/source-leaking tokens inside citations.

    ETF composer output should never mention internal keys like `price_technicals`,
    but models can still do it; we normalize citations to safe, human-readable sources.
    """
    source_suffix = f", {data_as_of}" if data_as_of else ""

    def rewrite_source(match: re.Match[str]) -> str:
        source = match.group(1)
        if any(token in source for token in _INTERNAL_SOURCE_TOKENS) or "제공 입력" in source:
            source = f"yfinance snapshot fields{source_suffix}"
        source = re.sub(r"제공\s*입력[^;\]]*", f"yfinance snapshot fields{source_suffix}", source)
        return f"[출처: {source}]"

    return re.sub(r"\[출처:\s*([^\]]+)\]", rewrite_source, report_md)


async def run_etf_composer_agent(cfg: dict[str, Any], etf_input: EtfComposerInput) -> EtfComposerOutput:
    output = await run_structured_agent(
        cfg=cfg,
        name="EtfComposerAgent",
        instructions=_PROMPT,
        input_text=_build_input(etf_input),
        output_type=EtfComposerOutput,
        max_tokens=composer_max_tokens(cfg),
    )
    return output.model_copy(
        update={
            "report_md": _polish_report_markdown(
                output.report_md,
                data_as_of=str(etf_input.metadata.get("data_as_of", "")),
            )
        }
    )

