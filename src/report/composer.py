from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tiktoken
from jinja2 import Environment, FileSystemLoader, select_autoescape

from fio.asset_class import classify_snapshot


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class ContextBuilder:
    TOKEN_LIMIT = 5000

    def build(
        self,
        snapshot: dict[str, Any],
        features: dict[str, Any],
        news_enrichment: dict[str, Any] | None = None,
        *,
        artifact_date: str | None = None,
    ) -> dict[str, Any]:
        info = snapshot["info"]
        price = snapshot.get("price", {})
        deep_read_articles = list((news_enrichment or {}).get("deep_read_articles", []))
        deep_read_status = dict((news_enrichment or {}).get("status", {}))
        company_relevant_articles = list((news_enrichment or {}).get("company_relevant_articles", []))
        market_reference_date = price.get("market_reference_date") or "데이터 미제공"
        asset_type = classify_snapshot(snapshot).asset_type
        community_summary = self._community_summary(snapshot.get("community") or {})
        return {
            "metadata": {
                "ticker": snapshot["ticker"],
                "company_name": info.get("longName") or snapshot["ticker"],
                "sector": info.get("sector") or "N/A",
                "industry": info.get("industry") or "N/A",
                "asset_type": asset_type,
                "report_date": today_str(),
                "artifact_date": artifact_date or today_str(),
                "market_reference_date": market_reference_date,
                "timezone_basis": "UTC artifact date; market_reference_date from latest yfinance price row",
                "data_as_of": snapshot["fetched_at"],
            },
            "company_profile": self._company_profile(info),
            "fund_profile": dict(snapshot.get("fund") or {}),
            "price_summary": {
                "current_price": price["current"],
                "52w_high": price["52w_high"],
                "52w_low": price["52w_low"],
                "market_reference_date": market_reference_date,
                "returns": {k: v for k, v in features.items() if str(k).startswith("return_")},
                "vol_annual": features.get("vol_annual"),
            },
            "price_technicals": self._price_technicals(snapshot, features),
            "volume_summary": self._volume_summary(features),
            "market_context": self._market_context(features),
            "holder_summary": self._holder_summary(snapshot),
            "valuation": features["valuation"],
            "financials": {
                "quarterly_trend": self._last_4q_summary(snapshot["financials"]["income_stmt"]),
                "growth_rates": features["growth"],
                "health": features["health"],
            },
            "cashflow_summary": self._cashflow_summary(snapshot, features),
            "news_summary": {
                "recent_headlines": [n.get("title", "") for n in snapshot["news"][:5]],
                "sentiment": features["sentiment"],
                "deep_read_articles": deep_read_articles,
                "deep_read_status": deep_read_status,
                "company_relevant_articles": company_relevant_articles,
                "community": community_summary,
            },
            "analyst_consensus": snapshot["analyst_recs"],
            "consensus_summary": self._consensus_summary(snapshot, current_price=price.get("current")),
        }

    def check_token_budget(self, context: dict[str, Any], model: str = "gpt-4o") -> dict[str, Any]:
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        tokens = len(enc.encode(json.dumps(context, ensure_ascii=False)))
        return {
            "context_tokens": tokens,
            "within_budget": tokens <= self.TOKEN_LIMIT,
            "warning": None if tokens <= self.TOKEN_LIMIT else f"컨텍스트 {tokens} tokens → 요약 필요",
        }

    def _last_4q_summary(self, income: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(income, dict):
            return []
        rev = income.get("Total Revenue") or {}
        op = income.get("Operating Income") or {}
        net = income.get("Net Income") or {}
        if not isinstance(rev, dict):
            return []
        dates = sorted(rev.keys(), reverse=True)[:4]
        rows: list[dict[str, Any]] = []
        for d in dates:
            rows.append(
                {
                    "quarter": d,
                    "revenue": rev.get(d),
                    "op_income": op.get(d) if isinstance(op, dict) else None,
                    "net_income": net.get(d) if isinstance(net, dict) else None,
                }
            )
        return rows

    def _company_profile(self, info: dict[str, Any]) -> dict[str, Any]:
        company_name = info.get("longName")
        sector = info.get("sector")
        industry = info.get("industry")
        long_summary = str(info.get("longBusinessSummary") or "").strip()

        summary_line = self._first_sentence(long_summary)
        if company_name and long_summary and summary_line.rstrip(".") == str(company_name).rstrip("."):
            summary_line = re.sub(r"\s+", " ", long_summary).strip()[:220].rstrip() + "…"
        if not summary_line:
            bits = [bit for bit in (sector, industry) if bit]
            if company_name and bits:
                summary_line = f"{company_name} is a {bits[-1]} company in the {bits[0]} sector."
            elif company_name:
                summary_line = f"{company_name} business summary: 데이터 미제공."
            else:
                summary_line = "데이터 미제공"

        return {
            "summary_line": summary_line,
            "website": info.get("website"),
            "sector": sector,
            "industry": industry,
            "source": "yf.info.longBusinessSummary"
            if long_summary
            else "yf.info.sector/industry (fallback)",
        }

    def _price_technicals(self, snapshot: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
        price = snapshot.get("price", {})
        technicals = dict(features.get("technicals", {}))
        return {
            "current_price": price.get("current"),
            "ma_20": technicals.get("ma_20"),
            "ma_50": technicals.get("ma_50"),
            "ma_200": technicals.get("ma_200"),
            "rsi_14": technicals.get("rsi_14"),
            "atr_14": technicals.get("atr_14"),
            "atr_stop_loss_candidate": technicals.get("atr_stop_loss_candidate"),
            "support_stop_loss_candidate": technicals.get("support_stop_loss_candidate"),
            "pct_from_52w_high": technicals.get("pct_from_52w_high"),
            "pct_above_52w_low": technicals.get("pct_above_52w_low"),
            "range_position_pct": technicals.get("range_position_pct"),
            "distance_to_ma_20_pct": technicals.get("distance_to_ma_20_pct"),
            "distance_to_ma_50_pct": technicals.get("distance_to_ma_50_pct"),
            "distance_to_ma_200_pct": technicals.get("distance_to_ma_200_pct"),
            "returns": dict(technicals.get("returns", {})),
            "vol_annual": features.get("vol_annual"),
        }

    def _cashflow_summary(self, snapshot: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
        balance_sheet = snapshot.get("financials", {}).get("balance_sheet", {})
        cashflow = snapshot.get("financials", {}).get("cashflow", {})
        health = dict(features.get("health", {}))
        latest_quarter = self._latest_statement_date(
            balance_sheet.get("Current Assets"),
            cashflow.get("Operating Cash Flow"),
            cashflow.get("Free Cash Flow"),
        )

        current_assets = self._statement_value(balance_sheet, "Current Assets", latest_quarter)
        current_liabilities = self._statement_value(
            balance_sheet,
            "Current Liabilities",
            latest_quarter,
        )
        current_ratio = None
        if current_assets is not None and current_liabilities not in (None, 0):
            current_ratio = round(current_assets / current_liabilities, 2)

        return {
            "latest_quarter": latest_quarter,
            "operating_cash_flow": self._statement_value(
                cashflow,
                "Operating Cash Flow",
                latest_quarter,
            ),
            "free_cash_flow": self._statement_value(cashflow, "Free Cash Flow", latest_quarter),
            "capital_expenditure": self._statement_value(
                cashflow,
                "Capital Expenditure",
                latest_quarter,
            ),
            "cash": snapshot.get("info", {}).get("totalCash"),
            "debt": snapshot.get("info", {}).get("totalDebt"),
            "net_debt": health.get("net_debt"),
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "current_ratio": current_ratio,
            "operating_margin": health.get("operating_margin"),
            "profit_margin": health.get("profit_margin"),
        }

    def _volume_summary(self, features: dict[str, Any]) -> dict[str, Any]:
        summary = dict(features.get("volume_summary", {}))
        return {
            "latest_volume": summary.get("latest_volume"),
            "avg_volume_20d": summary.get("avg_volume_20d"),
            "avg_volume_60d": summary.get("avg_volume_60d"),
            "volume_vs_20d_pct": summary.get("volume_vs_20d_pct"),
            "volume_vs_60d_pct": summary.get("volume_vs_60d_pct"),
            "source": "yf.history.Volume",
        }

    def _market_context(self, features: dict[str, Any]) -> dict[str, Any]:
        market = dict(features.get("market_context", {}))
        market.setdefault("benchmark_ticker", None)
        vix = market.get("vix")
        if not isinstance(vix, dict):
            vix = {}
        market["vix"] = {
            "ticker": vix.get("ticker"),
            "current": vix.get("current"),
            "reference_date": vix.get("reference_date"),
            "return_1m": vix.get("return_1m"),
            "regime": vix.get("regime") or "데이터 미제공",
            "source": vix.get("source") or "yf.history(^VIX).Close",
        }
        market["source"] = "yf.history.Close benchmark comparison"
        return market

    def _holder_summary(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        holders = dict(snapshot.get("holders") or {})
        return {
            "institutional_holders": list(holders.get("institutional_holders") or []),
            "mutualfund_holders": list(holders.get("mutualfund_holders") or []),
            "major_holders": list(holders.get("major_holders") or []),
            "source": "yfinance holders",
        }

    def _consensus_summary(
        self,
        snapshot: dict[str, Any],
        *,
        current_price: float | None,
    ) -> dict[str, Any]:
        info = snapshot.get("info", {})
        recs = snapshot.get("analyst_recs", {})
        strong_buy = self._int_or_none(recs.get("strongBuy"))
        buy = self._int_or_none(recs.get("buy"))
        hold = self._int_or_none(recs.get("hold"))
        sell = self._int_or_none(recs.get("sell"))
        strong_sell = self._int_or_none(recs.get("strongSell"))

        buy_count = self._sum_known(strong_buy, buy)
        hold_count = hold
        sell_count = self._sum_known(sell, strong_sell)

        total_count = self._int_or_none(info.get("numberOfAnalystOpinions"))
        if total_count is None:
            total_count = self._sum_known(buy_count, hold_count, sell_count)

        buy_ratio_pct = None
        if total_count not in (None, 0) and buy_count is not None:
            buy_ratio_pct = round(buy_count / total_count * 100, 1)

        target_mean = info.get("targetMeanPrice")
        target_upside_pct = None
        if target_mean not in (None, 0) and current_price not in (None, 0):
            try:
                target_upside_pct = round((float(target_mean) / float(current_price) - 1) * 100, 1)
            except (TypeError, ValueError, ZeroDivisionError):
                target_upside_pct = None

        recommendation = info.get("recommendationKey")
        stance_summary = self._consensus_stance(
            recommendation=recommendation,
            buy_ratio_pct=buy_ratio_pct,
            total_count=total_count,
            target_upside_pct=target_upside_pct,
        )

        return {
            "buy_count": buy_count,
            "hold_count": hold_count,
            "sell_count": sell_count,
            "total_count": total_count,
            "buy_ratio_pct": buy_ratio_pct,
            "target_mean_price": target_mean,
            "target_low_price": info.get("targetLowPrice"),
            "target_high_price": info.get("targetHighPrice"),
            "target_upside_pct": target_upside_pct,
            "number_of_analyst_opinions": self._int_or_none(info.get("numberOfAnalystOpinions")),
            "recommendation_key": recommendation,
            "stance_summary": stance_summary,
        }

    def _consensus_stance(
        self,
        *,
        recommendation: Any,
        buy_ratio_pct: float | None,
        total_count: int | None,
        target_upside_pct: float | None,
    ) -> str:
        rec = str(recommendation or "").strip().lower()
        rec_label = {
            "strong_buy": "강한 매수",
            "buy": "매수",
            "hold": "중립",
            "sell": "매도",
            "strong_sell": "강한 매도",
        }.get(rec, "데이터 미제공")

        parts = [f"컨센서스 의견: {rec_label}"]
        if total_count:
            parts.append(f"참여 애널리스트 {total_count}명")
        if buy_ratio_pct is not None:
            parts.append(f"매수 비중 {buy_ratio_pct}%")
        if target_upside_pct is not None:
            parts.append(f"평균 목표가 기준 업사이드 {target_upside_pct}%")
        return " / ".join(parts)

    def _community_summary(self, community: dict[str, Any]) -> dict[str, Any]:
        """
        Lightweight sentiment summary over Yahoo Finance community conversations.
        NOTE: 참고 지표이며, 표본/편향/조작/차단 가능성을 전제로 합니다.
        """
        if not isinstance(community, dict) or not community:
            return {"status": "missing", "note": "community 데이터 미제공"}
        status = str(community.get("status") or "")
        convs = community.get("conversations")
        if status != "ok" or not isinstance(convs, list) or not convs:
            return {"status": status or "missing", "note": "community 대화 데이터가 비어 있거나 수집 실패"}

        pos_kw = [
            "buy",
            "bull",
            "up",
            "rally",
            "breakout",
            "strong",
            "good",
            "long",
            "moon",
            "매수",
            "상승",
            "호재",
            "강세",
            "돌파",
            "우상향",
            "좋다",
        ]
        neg_kw = [
            "sell",
            "bear",
            "down",
            "dump",
            "crash",
            "weak",
            "bad",
            "short",
            "매도",
            "하락",
            "악재",
            "약세",
            "폭락",
            "거품",
            "리스크",
        ]

        pos = 0
        neg = 0
        tokens: dict[str, int] = {}
        texts: list[str] = []
        for item in convs[:20]:
            t = str((item or {}).get("text") or "")
            if not t:
                continue
            tl = t.lower()
            texts.append(t[:240])
            if any(k in tl for k in pos_kw):
                pos += 1
            if any(k in tl for k in neg_kw):
                neg += 1
            for w in re.findall(r"[A-Za-z]{3,}|[가-힣]{2,}", t):
                wl = w.lower()
                if wl in {"the", "and", "for", "with", "this", "that", "you", "are", "was", "have"}:
                    continue
                if wl in {"매수", "매도", "상승", "하락"}:
                    continue
                tokens[wl] = tokens.get(wl, 0) + 1

        n = len(texts)
        if n == 0:
            return {"status": "empty", "note": "community 대화 텍스트가 비어 있음"}
        top_terms = [k for k, _ in sorted(tokens.items(), key=lambda kv: kv[1], reverse=True)[:8]]
        score = (pos - neg) / max(n, 1)
        return {
            "status": "ok",
            "n": n,
            "pos_ratio": round(pos / max(n, 1), 3),
            "neg_ratio": round(neg / max(n, 1), 3),
            "sentiment_score": round(score, 3),
            "top_terms": top_terms,
            "sample": texts[:6],
            "source_url": community.get("source_url", ""),
            "note": "리테일 커뮤니티 여론(참고). 표본/편향/조작 가능성을 감안하세요.",
        }

    def _first_sentence(self, text: str, limit: int = 220) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        sentence = parts[0].strip()
        if len(parts) > 1 and re.search(r"\b(?:inc|corp|corporation|ltd|plc|co)\.$", sentence.lower()):
            sentence = f"{sentence} {parts[1].strip()}".strip()
        if len(sentence) <= limit:
            return sentence
        return sentence[: limit - 1].rstrip() + "…"

    def _latest_statement_date(self, *series_candidates: Any) -> str | None:
        for candidate in series_candidates:
            if isinstance(candidate, dict) and candidate:
                return sorted(candidate.keys(), reverse=True)[0]
        return None

    def _statement_value(
        self,
        statement: dict[str, Any],
        row_name: str,
        quarter: str | None,
    ) -> float | None:
        row = statement.get(row_name)
        if not isinstance(row, dict) or not row:
            return None
        if quarter and row.get(quarter) is not None:
            return row.get(quarter)
        latest_quarter = sorted(row.keys(), reverse=True)[0]
        return row.get(latest_quarter)

    def _int_or_none(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _sum_known(self, *values: int | None) -> int | None:
        known = [value for value in values if value is not None]
        if not known:
            return None
        return sum(known)


def render_report_prompt(
    prompts_dir: Path,
    context: dict[str, Any],
    template_name: str = "report.j2",
) -> tuple[str, str]:
    env = Environment(
        loader=FileSystemLoader(str(prompts_dir)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template(template_name)
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    rendered = tmpl.render(context=context, context_json=context_json, metadata=context["metadata"])
    sep = "---SYSTEM---"
    if sep in rendered:
        system_part, user_part = rendered.split(sep, 1)
        return system_part.strip(), user_part.strip()
    return "", rendered.strip()


def compose_markdown_report(
    llm: Any,
    prompts_dir: Path,
    context: dict[str, Any],
) -> str:
    system_msg, user_msg = render_report_prompt(prompts_dir, context)
    if not system_msg:
        system_msg = (
            "당신은 CFA 자격증을 보유한 금융 애널리스트입니다. "
            "제공된 데이터만 사용하고, 숫자에는 반드시 출처 태그를 붙이세요."
        )
    return llm.generate(system_msg, user_msg)
