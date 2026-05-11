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
    description: str
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
