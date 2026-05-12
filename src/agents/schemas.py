from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuarterRow(StrictModel):
    quarter: str
    revenue: float | None = None
    op_income: float | None = None
    net_income: float | None = None
    source: str
    as_of: str


class ValuationOutput(StrictModel):
    method: Literal["PER", "DCF", "PBR", "mixed"]
    per_trailing: float | None = None
    per_applied: float | None = None
    eps: float | None = None
    target_price: float
    target_price_downside: float | None = None
    stop_loss_price: float
    target_upside_pct: float | None = None
    stop_loss_downside_pct: float | None = None
    target_price_basis: str
    stop_loss_basis: str
    formula_text: str
    horizon: Literal["1개월", "3개월", "6개월", "12개월"]
    rationale_bullets: list[str] = Field(min_length=3, max_length=5)
    citations: list[str] = Field(min_length=1)


class FinancialsHealthOutput(StrictModel):
    quarterly_table: list[QuarterRow] = Field(min_length=4, max_length=4)
    per_trailing: float | None = None
    health_notes: list[str] = Field(min_length=2, max_length=5)
    citations: list[str] = Field(min_length=1)


class GrowthDriver(StrictModel):
    headline: str
    evidence: str
    citations: list[str] = Field(min_length=1)


class GrowthNewsOutput(StrictModel):
    drivers: list[GrowthDriver] = Field(min_length=2, max_length=3)
    sentiment_summary: str


class RiskItem(StrictModel):
    category: Literal["경쟁", "규제", "금리", "환율", "멀티플", "실적", "기타"]
    description: str = Field(max_length=320)
    citations: list[str] = Field(min_length=1)


class RiskOutput(StrictModel):
    risks: list[RiskItem] = Field(min_length=3, max_length=6)


class InvestmentOpinion(StrictModel):
    opinion: Literal["매수", "중립", "매도"]
    confidence_basis: str


class ComposerInput(StrictModel):
    metadata: dict[str, Any]
    company_profile: dict[str, Any] = Field(default_factory=dict)
    price_technicals: dict[str, Any] = Field(default_factory=dict)
    volume_summary: dict[str, Any] = Field(default_factory=dict)
    market_context: dict[str, Any] = Field(default_factory=dict)
    holder_summary: dict[str, Any] = Field(default_factory=dict)
    cashflow_summary: dict[str, Any] = Field(default_factory=dict)
    consensus_summary: dict[str, Any] = Field(default_factory=dict)
    actual_per: float | None = None
    valuation: ValuationOutput
    financials: FinancialsHealthOutput
    growth: GrowthNewsOutput
    risk: RiskOutput
    news_summary: dict[str, Any] = Field(default_factory=dict)


class ComposerOutput(StrictModel):
    opinion: InvestmentOpinion
    report_md: str


# ---------------------------
# ETF / fund-like assets
# ---------------------------


class EtfHolding(StrictModel):
    name: str | None = None
    ticker: str | None = None
    weight_pct: float | None = None
    notes: str | None = None
    citations: list[str] = Field(min_length=1)


class EtfHoldingsOutput(StrictModel):
    asset_type: Literal["ETF", "FUND", "ETN", "MUTUALFUND", "UNKNOWN"]
    holdings_as_of: str | None = None
    top_holdings: list[EtfHolding] = Field(min_length=0, max_length=15)
    concentration_note: str
    data_availability: Literal["ok", "partial", "missing"]
    citations: list[str] = Field(min_length=1)


class EtfComposerInput(StrictModel):
    metadata: dict[str, Any]
    company_profile: dict[str, Any] = Field(default_factory=dict)
    price_technicals: dict[str, Any] = Field(default_factory=dict)
    volume_summary: dict[str, Any] = Field(default_factory=dict)
    market_context: dict[str, Any] = Field(default_factory=dict)
    holdings: EtfHoldingsOutput
    news_summary: dict[str, Any] = Field(default_factory=dict)


class EtfComposerOutput(StrictModel):
    report_md: str
