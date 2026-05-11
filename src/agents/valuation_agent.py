from __future__ import annotations

from typing import Any

from agents.mcp import MCPServerStdio
from agents.gateway import dump_json, load_prompt_text, per_agent_max_tokens, run_structured_agent
from agents.schemas import ValuationOutput

_PROMPT = load_prompt_text("valuation.md")


def _build_input(context_slice: dict[str, Any]) -> str:
    return (
        "다음 valuation 슬라이스만 사용해 ValuationOutput JSON을 생성하세요.\n"
        "필요할 때만 yfinance MCP 도구를 사용하세요.\n\n"
        f"{dump_json(context_slice)}"
    )


async def run_valuation_agent(
    cfg: dict[str, Any],
    context_slice: dict[str, Any],
    *,
    mcp_server: MCPServerStdio | None = None,
) -> ValuationOutput:
    return await run_structured_agent(
        cfg=cfg,
        name="ValuationAgent",
        instructions=_PROMPT,
        input_text=_build_input(context_slice),
        output_type=ValuationOutput,
        max_tokens=per_agent_max_tokens(cfg),
        mcp_servers=[mcp_server] if mcp_server else None,
    )
