from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _series_to_float_dict(s: pd.Series) -> dict[str, float]:
    out: dict[str, float] = {}
    for idx, val in s.items():
        if pd.isna(val):
            continue
        if hasattr(idx, "strftime"):
            key = idx.strftime("%Y-%m-%d")
        else:
            key = str(idx)
        try:
            out[key] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _df_to_nested_dict(df: pd.DataFrame | None) -> dict[str, dict[str, float]]:
    if df is None or df.empty:
        return {}
    result: dict[str, dict[str, float]] = {}
    for row_label, row in df.iterrows():
        inner: dict[str, float] = {}
        for col in df.columns:
            v = row[col]
            if pd.isna(v):
                continue
            col_key = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            try:
                inner[col_key] = float(v)
            except (TypeError, ValueError):
                continue
        if inner:
            result[str(row_label)] = inner
    return result


class YahooIngester:
    def fetch(self, ticker: str, config: dict[str, Any]) -> dict[str, Any]:
        ingest_cfg = config.get("ingest", {})
        retries = int(ingest_cfg.get("retry_attempts", 3))
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                return self._fetch_once(ticker, ingest_cfg)
            except Exception as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(2**attempt)
                else:
                    raise RuntimeError(f"[DataIngestion] {ticker} 수집 실패: {e}") from e
        raise RuntimeError(f"[DataIngestion] {ticker} 수집 실패: {last_err}")

    def _fetch_once(self, ticker: str, ingest_cfg: dict[str, Any]) -> dict[str, Any]:
        yf_obj = yf.Ticker(ticker)
        period = ingest_cfg.get("price_period", "1y")
        news_count = int(ingest_cfg.get("news_count", 10))

        hist_daily = yf_obj.history(period=period)
        if hist_daily is None or hist_daily.empty:
            raise ValueError("가격 이력이 비어 있습니다.")

        hist_monthly = hist_daily["Close"].resample("ME").last().dropna()

        info = dict(yf_obj.info) if yf_obj.info else {}

        income = getattr(yf_obj, "quarterly_financials", None)
        balance = getattr(yf_obj, "quarterly_balance_sheet", None)
        cashflow = getattr(yf_obj, "quarterly_cashflow", None)

        news_list = []
        try:
            raw_news = yf_obj.news or []
            for n in raw_news[:news_count]:
                title = (n.get("title") or "").strip()
                publisher = (n.get("publisher") or "").strip()
                link = (n.get("link") or "").strip()
                ts = n.get("providerPublishTime")

                # yfinance가 차단/실패 시 빈 title/publisher 및 epoch(0) 값을 주는 경우가 있어 필터링
                if not title and not publisher and not link:
                    continue

                pub = ""
                if isinstance(ts, (int, float)) and ts > 0:
                    try:
                        pub = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    except (OSError, OverflowError, ValueError):
                        pub = ""
                news_list.append(
                    {
                        "title": title,
                        "publisher": publisher,
                        "published": pub,
                        "link": link,
                    }
                )
        except Exception:
            news_list = []

        recs = None
        try:
            recs = yf_obj.recommendations
        except Exception:
            recs = None

        return self._build_snapshot(
            ticker,
            hist_monthly,
            hist_daily,
            info,
            income,
            balance,
            cashflow,
            news_list,
            recs,
        )

    def _build_snapshot(
        self,
        ticker: str,
        price_monthly: pd.Series,
        price_daily: pd.DataFrame,
        info: dict[str, Any],
        income: pd.DataFrame | None,
        balance: pd.DataFrame | None,
        cashflow: pd.DataFrame | None,
        news: list[dict[str, str]],
        recs: pd.DataFrame | None,
    ) -> dict[str, Any]:
        close = price_daily["Close"]
        rolling_high = price_daily["High"].rolling(252, min_periods=1).max()
        rolling_low = price_daily["Low"].rolling(252, min_periods=1).min()

        keys_info = [
            "longName",
            "sector",
            "industry",
            "marketCap",
            "trailingPE",
            "forwardPE",
            "priceToBook",
            "profitMargins",
            "revenueGrowth",
            "operatingMargins",
            "returnOnEquity",
            "totalDebt",
            "totalCash",
            "freeCashflow",
            "enterpriseValue",
            "ebitda",
        ]
        info_subset = {k: info.get(k) for k in keys_info}

        return {
            "ticker": ticker,
            "fetched_at": _utc_now_iso(),
            "price": {
                "current": float(close.iloc[-1]),
                "52w_high": float(rolling_high.iloc[-1]),
                "52w_low": float(rolling_low.iloc[-1]),
                "monthly_close": _series_to_float_dict(price_monthly),
                "daily_close": _series_to_float_dict(close),
            },
            "info": info_subset,
            "financials": {
                "income_stmt": _df_to_nested_dict(income),
                "balance_sheet": _df_to_nested_dict(balance),
                "cashflow": _df_to_nested_dict(cashflow),
            },
            "news": news,
            "analyst_recs": self._parse_recs(recs),
        }

    def _parse_recs(self, recs: pd.DataFrame | None) -> dict[str, Any]:
        if recs is None or recs.empty:
            return {
                "strongBuy": None,
                "buy": None,
                "hold": None,
                "sell": None,
                "strongSell": None,
                "mean_target": None,
            }
        latest = recs.iloc[-1]
        return {
            "strongBuy": int(latest.get("strongBuy", 0) or 0),
            "buy": int(latest.get("buy", 0) or 0),
            "hold": int(latest.get("hold", 0) or 0),
            "sell": int(latest.get("sell", 0) or 0),
            "strongSell": int(latest.get("strongSell", 0) or 0),
        }
