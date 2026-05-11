from __future__ import annotations

import math
from typing import Any

import numpy as np


class FeatureBuilder:
    def build(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        monthly = snapshot["price"]["monthly_close"]
        daily = snapshot["price"]["daily_close"]
        info = snapshot["info"]
        income = snapshot["financials"]["income_stmt"]
        price = snapshot["price"]

        returns = self._compute_returns(monthly)
        valuation = self._compute_valuation(info)
        health = self._compute_health(info)
        growth = self._compute_yoy_growth(income)
        sentiment = self._simple_news_sentiment(snapshot["news"])
        vol = self._annualized_vol(daily)
        technicals = self._compute_price_technicals(
            daily,
            current_price=price.get("current"),
            high_52w=price.get("52w_high"),
            low_52w=price.get("52w_low"),
            returns=returns,
        )

        out = {
            **returns,
            "valuation": valuation,
            "health": health,
            "growth": growth,
            "sentiment": sentiment,
            "vol_annual": vol,
            "technicals": technicals,
        }
        return out

    def _compute_returns(self, monthly: dict[str, float]) -> dict[str, Any]:
        prices = sorted(monthly.items(), key=lambda x: x[0])
        vals = [v for _, v in prices]
        if len(vals) < 2:
            return {}

        def ret(n: int) -> float | None:
            if len(vals) < n:
                return None
            prev = vals[-n]
            if prev == 0:
                return None
            return round((vals[-1] / prev - 1) * 100, 2)

        return {
            "return_1m": ret(2),
            "return_3m": ret(4),
            "return_6m": ret(7),
            "return_12m": ret(13),
        }

    def _annualized_vol(self, daily: dict[str, float]) -> float | None:
        if len(daily) < 5:
            return None
        sorted_items = sorted(daily.items(), key=lambda x: x[0])
        closes = [v for _, v in sorted_items]
        if any(c <= 0 for c in closes):
            return None
        log_ret = np.diff(np.log(np.array(closes, dtype=float)))
        if len(log_ret) < 2:
            return None
        return round(float(np.std(log_ret) * np.sqrt(252)), 4)

    def _compute_valuation(self, info: dict[str, Any]) -> dict[str, Any]:
        ev = info.get("enterpriseValue") or 0
        ebitda = info.get("ebitda") or 0
        ev_ebitda = None
        if ebitda not in (0, None):
            try:
                ev_ebitda = round(float(ev) / float(ebitda), 2)
            except (TypeError, ValueError):
                ev_ebitda = None
        return {
            "PER": info.get("trailingPE"),
            "Forward_PER": info.get("forwardPE"),
            "PBR": info.get("priceToBook"),
            "EV_EBITDA": ev_ebitda,
        }

    def _compute_health(self, info: dict[str, Any]) -> dict[str, Any]:
        debt = info.get("totalDebt") or 0
        cash = info.get("totalCash") or 0
        mktcap = info.get("marketCap") or 0
        fcf = info.get("freeCashflow") or 0
        try:
            net_debt = float(debt) - float(cash)
        except (TypeError, ValueError):
            net_debt = None
        fcf_yield = None
        if mktcap:
            try:
                fcf_yield = round(float(fcf) / float(mktcap) * 100, 2)
            except (TypeError, ValueError):
                fcf_yield = None
        return {
            "net_debt": net_debt,
            "FCF_yield_pct": fcf_yield,
            "profit_margin": info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "ROE": info.get("returnOnEquity"),
        }

    def _compute_yoy_growth(self, income: dict[str, Any]) -> dict[str, Any]:
        rev = income.get("Total Revenue") if isinstance(income, dict) else None
        if not rev or not isinstance(rev, dict):
            return {"revenue_yoy_pct": None}
        dates = sorted(rev.keys())
        values = [rev[d] for d in dates]
        if len(values) < 8:
            return {"revenue_yoy_pct": None}
        ttm_now = sum(values[-4:])
        ttm_prev = sum(values[-8:-4])
        if not ttm_prev or math.isclose(ttm_prev, 0):
            return {"revenue_yoy_pct": None}
        return {"revenue_yoy_pct": round((ttm_now / ttm_prev - 1) * 100, 2)}

    def _compute_price_technicals(
        self,
        daily: dict[str, float],
        *,
        current_price: float | None,
        high_52w: float | None,
        low_52w: float | None,
        returns: dict[str, Any],
    ) -> dict[str, Any]:
        if not daily:
            return {
                "ma_20": None,
                "ma_50": None,
                "ma_200": None,
                "rsi_14": None,
                "pct_from_52w_high": None,
                "pct_above_52w_low": None,
                "range_position_pct": None,
                "distance_to_ma_20_pct": None,
                "distance_to_ma_50_pct": None,
                "distance_to_ma_200_pct": None,
                "returns": dict(returns),
            }

        sorted_items = sorted(daily.items(), key=lambda x: x[0])
        closes = np.array([v for _, v in sorted_items], dtype=float)

        def moving_average(window: int) -> float | None:
            if len(closes) < window:
                return None
            return round(float(np.mean(closes[-window:])), 2)

        ma_20 = moving_average(20)
        ma_50 = moving_average(50)
        ma_200 = moving_average(200)
        rsi_14 = self._rsi(closes, window=14)

        def pct_distance(base: float | None) -> float | None:
            if current_price in (None, 0) or base in (None, 0):
                return None
            try:
                return round((float(current_price) / float(base) - 1) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                return None

        range_position = None
        if (
            current_price is not None
            and high_52w not in (None, 0)
            and low_52w is not None
            and not math.isclose(float(high_52w), float(low_52w))
        ):
            try:
                range_position = round(
                    (float(current_price) - float(low_52w))
                    / (float(high_52w) - float(low_52w))
                    * 100,
                    1,
                )
            except (TypeError, ValueError, ZeroDivisionError):
                range_position = None

        return {
            "ma_20": ma_20,
            "ma_50": ma_50,
            "ma_200": ma_200,
            "rsi_14": rsi_14,
            "pct_from_52w_high": pct_distance(high_52w),
            "pct_above_52w_low": pct_distance(low_52w),
            "range_position_pct": range_position,
            "distance_to_ma_20_pct": pct_distance(ma_20),
            "distance_to_ma_50_pct": pct_distance(ma_50),
            "distance_to_ma_200_pct": pct_distance(ma_200),
            "returns": dict(returns),
        }

    def _rsi(self, closes: np.ndarray, *, window: int) -> float | None:
        if len(closes) <= window:
            return None
        deltas = np.diff(closes[-(window + 1) :])
        gains = np.clip(deltas, 0, None)
        losses = np.clip(-deltas, 0, None)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if math.isclose(avg_gain, 0.0) and math.isclose(avg_loss, 0.0):
            return 50.0
        if math.isclose(avg_loss, 0.0):
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _simple_news_sentiment(self, news: list[dict[str, Any]]) -> dict[str, Any]:
        pos_kw = {"beats", "surges", "growth", "strong", "record", "upgrade", "buy"}
        neg_kw = {"miss", "decline", "loss", "cut", "downgrade", "sell", "warn", "risk"}
        pos = neg = 0
        keywords: list[str] = []
        for n in news:
            title = (n.get("title") or "").lower()
            words = set(title.replace(",", " ").split())
            hit_pos = words & pos_kw
            hit_neg = words & neg_kw
            if hit_pos:
                pos += 1
                keywords.extend(hit_pos)
            if hit_neg:
                neg += 1
                keywords.extend(hit_neg)
        neutral = max(0, len(news) - pos - neg)
        uniq_kw = list(dict.fromkeys(keywords))[:10]
        return {
            "positive": pos,
            "negative": neg,
            "neutral": neutral,
            "keywords": uniq_kw,
        }
