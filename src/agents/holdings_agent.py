from __future__ import annotations

from typing import Any

from agents.mcp import MCPServerStdio
from agents.gateway import dump_json, load_prompt_text, per_agent_max_tokens, run_structured_agent
from agents.schemas import EtfHoldingsOutput

_PROMPT = load_prompt_text("holdings.md")


def _build_input(context_slice: dict[str, Any]) -> str:
    return (
        "다음 ETF/펀드 슬라이스만 사용해 EtfHoldingsOutput JSON을 생성하세요.\n"
        "가능하면 yfinance MCP 도구로 상위 보유종목(티커/이름/비중%)을 조회해 보강하세요.\n"
        "보유종목을 못 가져오면 data_availability='missing'으로 두고, 이유를 concentration_note에 짧게 적고, "
        "top_holdings는 비워도 됩니다.\n\n"
        f"{dump_json(context_slice)}"
    )


async def run_holdings_agent(
    cfg: dict[str, Any],
    context_slice: dict[str, Any],
    *,
    mcp_server: MCPServerStdio | None = None,
) -> EtfHoldingsOutput:
    return await run_structured_agent(
        cfg=cfg,
        name="HoldingsAgent",
        instructions=_PROMPT,
        input_text=_build_input(context_slice),
        output_type=EtfHoldingsOutput,
        max_tokens=per_agent_max_tokens(cfg),
        mcp_servers=[mcp_server] if mcp_server else None,
    )

