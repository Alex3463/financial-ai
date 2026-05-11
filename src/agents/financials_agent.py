from __future__ import annotations

from typing import Any

from agents.mcp import MCPServerStdio
from agents.gateway import dump_json, load_prompt_text, per_agent_max_tokens, run_structured_agent
from agents.schemas import FinancialsHealthOutput

_PROMPT = load_prompt_text("financials.md")


def _build_input(context_slice: dict[str, Any]) -> str:
    return (
        "다음 financials 슬라이스만 사용해 FinancialsHealthOutput JSON을 생성하세요.\n"
        "quarterly_table 은 최신 분기부터 정확히 4행이어야 합니다.\n"
        "필요할 때만 yfinance MCP 도구를 사용하세요.\n\n"
        f"{dump_json(context_slice)}"
    )


async def run_financials_agent(
    cfg: dict[str, Any],
    context_slice: dict[str, Any],
    *,
    mcp_server: MCPServerStdio | None = None,
) -> FinancialsHealthOutput:
    return await run_structured_agent(
        cfg=cfg,
        name="FinancialsHealthAgent",
        instructions=_PROMPT,
        input_text=_build_input(context_slice),
        output_type=FinancialsHealthOutput,
        max_tokens=per_agent_max_tokens(cfg),
        mcp_servers=[mcp_server] if mcp_server else None,
    )
