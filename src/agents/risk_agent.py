from __future__ import annotations

from typing import Any

from agents.mcp import MCPServerStdio
from agents.gateway import dump_json, load_prompt_text, per_agent_max_tokens, run_structured_agent
from agents.schemas import RiskOutput

_PROMPT = load_prompt_text("risk.md")


def _build_input(context_slice: dict[str, Any]) -> str:
    return (
        "다음 risk 슬라이스만 사용해 RiskOutput JSON을 생성하세요.\n"
        "가능하면 경쟁/규제/금리/환율/멀티플/실적 카테고리를 넓게 커버하세요.\n"
        "news_summary.deep_read_articles 가 있으면 그 기사 요약과 URL 근거를 우선 사용하세요.\n"
        "회사 고유 뉴스가 없으면 price_technicals, cashflow_summary, valuation, financials.health 와 연결된 하방 메커니즘을 우선 쓰세요.\n"
        "필요할 때만 yfinance MCP 도구를 사용하세요.\n\n"
        f"{dump_json(context_slice)}"
    )


async def run_risk_agent(
    cfg: dict[str, Any],
    context_slice: dict[str, Any],
    *,
    mcp_server: MCPServerStdio | None = None,
) -> RiskOutput:
    return await run_structured_agent(
        cfg=cfg,
        name="RiskAgent",
        instructions=_PROMPT,
        input_text=_build_input(context_slice),
        output_type=RiskOutput,
        max_tokens=per_agent_max_tokens(cfg),
        mcp_servers=[mcp_server] if mcp_server else None,
    )
