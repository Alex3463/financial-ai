"""티커 자산 유형(ETF/펀드 vs 주식) 판별 — 파이프라인 분기 단일 진실 공급원."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ETF_LIKE_ASSET_TYPES = frozenset({"ETF", "FUND", "MUTUALFUND", "ETN"})
EQUITY_LIKE_ASSET_TYPES = frozenset({"EQUITY", "STOCK"})

_NAME_ETF_HINTS = (" etf", " etn", " fund", " trust", " index", "portfolio", "income")


@dataclass(frozen=True)
class AssetClassification:
    asset_type: str
    branch: str  # "etf" | "equity"
    signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_etf_like(self) -> bool:
        return self.branch == "etf"

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "branch": self.branch,
            "signals": list(self.signals),
        }


def is_etf_asset_type(asset_type: str | None) -> bool:
    return str(asset_type or "").strip().upper() in ETF_LIKE_ASSET_TYPES


def is_etf_like(data: dict[str, Any]) -> bool:
    """context 또는 snapshot dict에서 ETF/펀드 계열 여부."""
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    declared = meta.get("asset_type")
    if declared:
        return is_etf_asset_type(str(declared))

    if "info" in data or "fund" in data or data.get("ticker"):
        return classify_snapshot(data).is_etf_like

    fund_profile = data.get("fund_profile")
    if isinstance(fund_profile, dict) and (
        fund_profile.get("top_holdings") or fund_profile.get("fund_operations")
    ):
        return True
    return False


def pipeline_branch_label(data: dict[str, Any]) -> str:
    return "etf" if is_etf_like(data) else "equity"


def _fund_block(snapshot: dict[str, Any]) -> dict[str, Any]:
    fund = snapshot.get("fund")
    if isinstance(fund, dict):
        return fund
    return {}


def _has_fund_holdings(fund: dict[str, Any]) -> bool:
    holdings = fund.get("top_holdings")
    return isinstance(holdings, list) and len(holdings) > 0


def _has_fund_operations(fund: dict[str, Any]) -> bool:
    ops = fund.get("fund_operations")
    if not isinstance(ops, dict):
        return False
    return any(ops.get(k) not in (None, "", "데이터 미제공") for k in ("expense_ratio", "holdings_turnover", "total_net_assets"))


def _empty_corporate_financials(snapshot: dict[str, Any]) -> bool:
    fin = snapshot.get("financials") or {}
    for key in ("income_stmt", "balance_sheet", "cashflow"):
        block = fin.get(key)
        if isinstance(block, dict) and block:
            return False
    return True


def classify_snapshot(snapshot: dict[str, Any]) -> AssetClassification:
    """yfinance snapshot 기준 자산 유형·파이프라인 분기."""
    info = dict(snapshot.get("info") or {})
    fund = _fund_block(snapshot)
    signals: list[str] = []

    quote_type = str(info.get("quoteType") or "").strip().upper()
    if quote_type:
        signals.append(f"quoteType={quote_type}")
        if quote_type in ETF_LIKE_ASSET_TYPES:
            return AssetClassification(asset_type=quote_type, branch="etf", signals=tuple(signals))
        if quote_type in EQUITY_LIKE_ASSET_TYPES:
            return AssetClassification(asset_type="EQUITY", branch="equity", signals=tuple(signals))

    overview = fund.get("fund_overview") if isinstance(fund.get("fund_overview"), dict) else {}
    legal_type = str(overview.get("legalType") or "").strip()
    if legal_type:
        signals.append(f"legalType={legal_type}")
        if "EXCHANGE TRADED" in legal_type.upper():
            return AssetClassification(asset_type="ETF", branch="etf", signals=tuple(signals))

    if _has_fund_holdings(fund):
        signals.append("fund.top_holdings")
        asset_type = "ETF" if "etf" in str(info.get("longName") or "").lower() else "FUND"
        return AssetClassification(asset_type=asset_type, branch="etf", signals=tuple(signals))

    if _has_fund_operations(fund):
        signals.append("fund.fund_operations")
        return AssetClassification(asset_type="FUND", branch="etf", signals=tuple(signals))

    if fund.get("sector_weightings") or fund.get("asset_classes"):
        signals.append("fund.sector_or_asset_classes")
        return AssetClassification(asset_type="FUND", branch="etf", signals=tuple(signals))

    name = str(info.get("longName") or info.get("shortName") or snapshot.get("ticker") or "")
    name_l = name.lower()
    if any(hint in name_l for hint in _NAME_ETF_HINTS):
        signals.append("name_hint")
        return AssetClassification(
            asset_type="ETF" if " etf" in name_l or " etn" in name_l else "FUND",
            branch="etf",
            signals=tuple(signals),
        )

    if _empty_corporate_financials(snapshot) and not info.get("trailingPE"):
        signals.append("no_corporate_financials")
        return AssetClassification(asset_type="FUND", branch="etf", signals=tuple(signals))

    signals.append("default_equity")
    return AssetClassification(asset_type="EQUITY", branch="equity", signals=tuple(signals))


def classify_context(context: dict[str, Any]) -> AssetClassification:
    meta = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
    declared = str(meta.get("asset_type") or "").strip().upper()
    if declared:
        branch = "etf" if declared in ETF_LIKE_ASSET_TYPES else "equity"
        return AssetClassification(asset_type=declared, branch=branch, signals=("metadata.asset_type",))
    snapshot_like = {
        "ticker": meta.get("ticker"),
        "info": {},
        "fund": dict(context.get("fund_profile") or {}),
        "financials": dict(context.get("financials") or {}),
    }
    return classify_snapshot(snapshot_like)
