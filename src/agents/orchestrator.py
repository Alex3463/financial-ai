from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

from agents.composer_agent import run_composer_agent
from agents.context_slicer import split_context
from agents.financials_agent import run_financials_agent
from agents.gateway import configure_agents_sdk
from agents.growth_agent import run_growth_agent
from agents.mcp_servers import make_yfinance_server
from agents.postcheck import validate_report_contract
from agents.risk_agent import run_risk_agent
from agents.schemas import ComposerInput
from agents.valuation_agent import run_valuation_agent


def _actual_per(context: dict[str, Any]) -> float | None:
    value = (context.get("valuation") or {}).get("PER")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _maybe_enter_server(
    exit_stack: AsyncExitStack,
    cfg: dict[str, Any],
    *,
    name: str,
):
    server = make_yfinance_server(cfg, name=name)
    if server is None:
        return None
    return await exit_stack.enter_async_context(server)


async def _run_domain_agents(
    cfg: dict[str, Any],
    slices: dict[str, dict[str, Any]],
) -> tuple[Any, Any, Any, Any]:
    async with AsyncExitStack() as exit_stack:
        valuation_server = await _maybe_enter_server(exit_stack, cfg, name="yfinance-valuation")
        financials_server = await _maybe_enter_server(exit_stack, cfg, name="yfinance-financials")
        growth_server = await _maybe_enter_server(exit_stack, cfg, name="yfinance-growth")
        risk_server = await _maybe_enter_server(exit_stack, cfg, name="yfinance-risk")

        if bool(cfg.get("agents", {}).get("parallel", True)):
            return await asyncio.gather(
                run_valuation_agent(cfg, slices["valuation"], mcp_server=valuation_server),
                run_financials_agent(cfg, slices["financials"], mcp_server=financials_server),
                run_growth_agent(cfg, slices["growth"], mcp_server=growth_server),
                run_risk_agent(cfg, slices["risk"], mcp_server=risk_server),
            )

        valuation = await run_valuation_agent(cfg, slices["valuation"], mcp_server=valuation_server)
        financials = await run_financials_agent(
            cfg, slices["financials"], mcp_server=financials_server
        )
        growth = await run_growth_agent(cfg, slices["growth"], mcp_server=growth_server)
        risk = await run_risk_agent(cfg, slices["risk"], mcp_server=risk_server)
        return valuation, financials, growth, risk


async def _run_agent_report_async(cfg: dict[str, Any], context: dict[str, Any]) -> str:
    configure_agents_sdk(cfg)
    slices = split_context(context)
    valuation, financials, growth, risk = await _run_domain_agents(cfg, slices)

    composer_input = ComposerInput(
        metadata=dict(context.get("metadata", {})),
        actual_per=_actual_per(context),
        valuation=valuation,
        financials=financials,
        growth=growth,
        risk=risk,
    )
    composer_output = await run_composer_agent(cfg, composer_input)
    report_md = composer_output.report_md.strip()
    validate_report_contract(report_md)
    return report_md + "\n"


def run_agent_report(cfg: dict[str, Any], context: dict[str, Any]) -> str:
    return asyncio.run(_run_agent_report_async(cfg, context))
