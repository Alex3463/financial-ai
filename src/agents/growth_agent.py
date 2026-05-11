from __future__ import annotations

from typing import Any

from agents.mcp import MCPServerStdio
from agents.gateway import dump_json, load_prompt_text, per_agent_max_tokens, run_structured_agent
from agents.schemas import GrowthNewsOutput

_PROMPT = load_prompt_text("growth.md")


def _build_input(context_slice: dict[str, Any]) -> str:
    return (
        "다음 growth 슬라이스만 사용해 GrowthNewsOutput JSON을 생성하세요.\n"
        "drivers 는 2~3개여야 하며, 각 숫자나 사실 판단에는 citations 를 붙이세요.\n"
        "news_summary.deep_read_articles 가 있으면 그 기사 요약과 URL 근거를 우선 사용하세요.\n"
        "회사 고유 뉴스가 없으면 company_profile, cashflow_summary, consensus_summary 를 활용해 회사 맞춤형 성장 근거를 만드세요.\n"
        "필요할 때만 yfinance MCP 도구를 사용하세요.\n\n"
        f"{dump_json(context_slice)}"
    )


async def run_growth_agent(
    cfg: dict[str, Any],
    context_slice: dict[str, Any],
    *,
    mcp_server: MCPServerStdio | None = None,
) -> GrowthNewsOutput:
    return await run_structured_agent(
        cfg=cfg,
        name="GrowthNewsAgent",
        instructions=_PROMPT,
        input_text=_build_input(context_slice),
        output_type=GrowthNewsOutput,
        max_tokens=per_agent_max_tokens(cfg),
        mcp_servers=[mcp_server] if mcp_server else None,
    )
