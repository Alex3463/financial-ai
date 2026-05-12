from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from agents.composer_agent import run_composer_agent
from agents.context_slicer import split_context
from agents.financials_agent import run_financials_agent
from agents.holdings_agent import run_holdings_agent
from agents.etf_composer_agent import run_etf_composer_agent
from agents.gateway import configure_agents_sdk
from agents.growth_agent import run_growth_agent
from agents.mcp_servers import make_yfinance_server
from agents.postcheck import validate_etf_report_contract, validate_report_contract
from agents.risk_agent import run_risk_agent
from agents.schemas import ComposerInput, EtfComposerInput
from agents.valuation_agent import run_valuation_agent
from fio.storage import write_json

ETF_LIKE_ASSET_TYPES = {"ETF", "FUND", "MUTUALFUND", "ETN"}


def _is_etf_like(context: dict[str, Any]) -> bool:
    asset_type = str((context.get("metadata") or {}).get("asset_type") or "").strip().upper()
    return asset_type in ETF_LIKE_ASSET_TYPES


def _actual_per(context: dict[str, Any]) -> float | None:
    value = (context.get("valuation") or {}).get("PER")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _write_section_artifacts(
    artifacts_dir: Path,
    *,
    slices: dict[str, Any],
    domain_outputs: dict[str, Any],
    composer_input: Any,
    composer_output: Any,
) -> Path:
    section_dir = Path(artifacts_dir) / "sections"
    write_json(section_dir / "context_slices.json", _jsonable(slices))
    for name, output in domain_outputs.items():
        write_json(section_dir / f"{name}.json", _jsonable(output))
    write_json(section_dir / "composer_input.json", _jsonable(composer_input))
    write_json(section_dir / "composer_output.json", _jsonable(composer_output))
    return section_dir


async def _maybe_enter_server(
    exit_stack: AsyncExitStack,
    cfg: dict[str, Any],
    *,
    name: str,
):
    try:
        server = make_yfinance_server(cfg, name=name)
        if server is None:
            return None
        return await exit_stack.enter_async_context(server)
    except Exception as exc:
        print(f"[pipeline] [경고] {name} MCP 초기화 실패 - 도구 없이 계속: {exc}", flush=True)
        return None


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


async def _run_agent_report_async(
    cfg: dict[str, Any],
    context: dict[str, Any],
    *,
    artifacts_dir: Path | None = None,
) -> str:
    configure_agents_sdk(cfg)
    slices = split_context(context)

    if _is_etf_like(context):
        async with AsyncExitStack() as exit_stack:
            holdings_server = await _maybe_enter_server(exit_stack, cfg, name="yfinance-holdings")
            # Reuse risk agent for now; prompt specialization can be added later.
            risk_server = await _maybe_enter_server(exit_stack, cfg, name="yfinance-risk")

            holdings = await run_holdings_agent(cfg, slices["etf"], mcp_server=holdings_server)
            risk = await run_risk_agent(cfg, slices["risk"], mcp_server=risk_server)

        etf_input = EtfComposerInput(
            metadata=dict(context.get("metadata", {})),
            company_profile=dict(context.get("company_profile", {})),
            price_technicals=dict(context.get("price_technicals", {})),
            volume_summary=dict(context.get("volume_summary", {})),
            market_context=dict(context.get("market_context", {})),
            fund_profile=dict(context.get("fund_profile", {})),
            holdings=holdings,
            news_summary=dict(context.get("news_summary", {})),
        )
        etf_output = await run_etf_composer_agent(cfg, etf_input)
        report_md = etf_output.report_md.strip()

        if artifacts_dir is not None:
            section_dir = Path(artifacts_dir) / "sections"
            write_json(section_dir / "context_slices.json", _jsonable(slices))
            write_json(section_dir / "holdings.json", _jsonable(holdings))
            write_json(section_dir / "risk.json", _jsonable(risk))
            write_json(section_dir / "composer_input.json", _jsonable(etf_input))
            write_json(section_dir / "composer_output.json", _jsonable(etf_output))

        validate_etf_report_contract(report_md)
        return report_md + "\n"

    valuation, financials, growth, risk = await _run_domain_agents(cfg, slices)

    composer_input = ComposerInput(
        metadata=dict(context.get("metadata", {})),
        company_profile=dict(context.get("company_profile", {})),
        price_technicals=dict(context.get("price_technicals", {})),
        volume_summary=dict(context.get("volume_summary", {})),
        market_context=dict(context.get("market_context", {})),
        holder_summary=dict(context.get("holder_summary", {})),
        cashflow_summary=dict(context.get("cashflow_summary", {})),
        consensus_summary=dict(context.get("consensus_summary", {})),
        actual_per=_actual_per(context),
        valuation=valuation,
        financials=financials,
        growth=growth,
        risk=risk,
        news_summary=dict(context.get("news_summary", {})),
    )
    composer_output = await run_composer_agent(cfg, composer_input)
    report_md = composer_output.report_md.strip()
    if artifacts_dir is not None:
        _write_section_artifacts(
            Path(artifacts_dir),
            slices=slices,
            domain_outputs={
                "valuation": valuation,
                "financials": financials,
                "growth": growth,
                "risk": risk,
            },
            composer_input=composer_input,
            composer_output=composer_output,
        )
    validate_report_contract(
        report_md,
        actual_per=composer_input.actual_per,
        valuation_formula=composer_input.valuation.formula_text,
    )
    return report_md + "\n"


def run_agent_report(
    cfg: dict[str, Any],
    context: dict[str, Any],
    *,
    artifacts_dir: Path | None = None,
) -> str:
    return asyncio.run(_run_agent_report_async(cfg, context, artifacts_dir=artifacts_dir))
