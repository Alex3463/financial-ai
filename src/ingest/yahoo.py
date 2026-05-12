from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

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


def _series_latest_date(s: pd.Series) -> str:
    if s is None or s.empty:
        return ""
    clean = s.dropna()
    if clean.empty:
        return ""
    idx = clean.index[-1]
    if hasattr(idx, "strftime"):
        return idx.strftime("%Y-%m-%d")
    return str(idx)[:10]


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


def _jsonable(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _fetch_url_text(url: str, *, timeout_s: float = 12.0) -> str:
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    req = Request(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        raw = resp.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="ignore")


def _extract_next_data_json(html: str) -> dict[str, Any] | None:
    marker = 'id="__NEXT_DATA__"'
    if marker not in html:
        return None
    try:
        start = html.index(marker)
        start = html.index(">", start) + 1
        end = html.index("</script>", start)
        payload = html[start:end].strip()
        if not payload:
            return None
        return json.loads(payload)
    except Exception:
        return None


def _walk_find_conversations(obj: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if isinstance(x.get("conversations"), list):
                for item in x.get("conversations") or []:
                    if isinstance(item, dict):
                        found.append(item)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return found


def _community_conversations_from_html(html: str, *, max_items: int = 20) -> list[dict[str, Any]]:
    data = _extract_next_data_json(html)
    if not data:
        return []
    convs = _walk_find_conversations(data)
    out: list[dict[str, Any]] = []
    for c in convs:
        msg = (
            c.get("message")
            or (c.get("content") or {}).get("text")
            or (c.get("content") or {}).get("body")
            or ""
        )
        if not isinstance(msg, str):
            msg = str(msg)
        msg = " ".join(msg.split()).strip()
        if not msg:
            continue
        msg = msg[:240]
        author = c.get("userDisplayName") or c.get("authorName") or ""
        created = c.get("createdAt") or c.get("created_at") or ""
        up = c.get("reactionCount") or c.get("upVotes") or c.get("upvoteCount") or None
        rec: dict[str, Any] = {"text": msg}
        if author:
            rec["author"] = str(author)[:64]
        if created:
            rec["created_at"] = str(created)[:32]
        if isinstance(up, (int, float)):
            rec["upvotes"] = int(up)
        out.append(rec)
        if len(out) >= max_items:
            break
    return out


def _fetch_yahoo_community(ticker: str, *, max_items: int = 20) -> dict[str, Any]:
    url = f"https://finance.yahoo.com/quote/{ticker}/community/"
    try:
        html = _fetch_url_text(url, timeout_s=12.0)
        convs = _community_conversations_from_html(html, max_items=max_items)
        return {
            "source_url": url,
            "status": "ok" if convs else "empty",
            "n_items": len(convs),
            "conversations": convs,
        }
    except URLError as e:
        return {"source_url": url, "status": "error", "error": str(e)}
    except Exception as e:
        return {"source_url": url, "status": "error", "error": str(e)}


def _holder_records(df: pd.DataFrame | None, *, max_rows: int = 5) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []

    key_map = {
        "Holder": "holder",
        "holder": "holder",
        "Shares": "shares",
        "shares": "shares",
        "Value": "value",
        "value": "value",
        "% Out": "pct_held",
        "pctHeld": "pct_held",
        "Date Reported": "date_reported",
        "dateReported": "date_reported",
    }
    records: list[dict[str, Any]] = []
    for raw in df.head(max_rows).to_dict(orient="records"):
        normalized: dict[str, Any] = {}
        for key, value in raw.items():
            out_key = key_map.get(str(key), str(key).strip().lower().replace(" ", "_"))
            jsonable = _jsonable(value)
            if jsonable is not None:
                normalized[out_key] = jsonable
        if normalized:
            records.append(normalized)
    return records


def _major_holder_records(df: pd.DataFrame | None, *, max_rows: int = 8) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []

    records: list[dict[str, Any]] = []
    for idx, row in df.head(max_rows).iterrows():
        values = [_jsonable(v) for v in row.tolist()]
        values = [v for v in values if v is not None]
        label = str(idx)
        if values:
            records.append({"label": label, "values": values})
    return records


def _fund_top_holdings_records(df: pd.DataFrame | None, *, max_rows: int = 10) -> list[dict[str, Any]]:
    """
    Extract Yahoo Finance 'Top Holdings' table for ETFs/funds from yfinance FundsData.

    Expected shape (common): index=Symbol, columns include 'Name' and 'Holding Percent' (0-1).
    """
    if df is None or df.empty:
        return []
    out: list[dict[str, Any]] = []
    try:
        cols = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}
        name_col = cols.get("name")
        pct_col = cols.get("holding_percent")
        for symbol, row in df.head(max_rows).iterrows():
            sym = str(symbol).strip()
            if not sym:
                continue
            rec: dict[str, Any] = {"symbol": sym}
            if name_col is not None:
                name_v = _jsonable(row.get(name_col))
                if name_v is not None:
                    rec["name"] = name_v
            if pct_col is not None:
                pct_v = row.get(pct_col)
                try:
                    if pct_v is not None and not pd.isna(pct_v):
                        rec["weight_pct"] = round(float(pct_v) * 100.0, 4)
                except (TypeError, ValueError):
                    pass
            out.append(rec)
    except Exception:
        return []
    return out


def _fund_operations_dict(df: pd.DataFrame | None) -> dict[str, Any]:
    """
    Extract decision-useful ETF/fund operation metrics from yfinance FundsData.

    Typical index labels:
    - Annual Report Expense Ratio
    - Annual Holdings Turnover
    - Total Net Assets
    """
    if df is None or df.empty:
        return {}
    try:
        col = df.columns[0]
        series = df[col]
        def pick(label: str) -> Any:
            try:
                return _jsonable(series.get(label))
            except Exception:
                return None
        return {
            "expense_ratio": pick("Annual Report Expense Ratio"),
            "holdings_turnover": pick("Annual Holdings Turnover"),
            "total_net_assets": pick("Total Net Assets"),
        }
    except Exception:
        return {}


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _default_benchmark_ticker(ticker: str) -> str:
    upper = ticker.upper()
    if upper.endswith((".KS", ".KQ")):
        return "^KS11"
    return "^GSPC"


def _published_date_str(pub_date: Any, ts: Any) -> str:
    if isinstance(pub_date, str):
        text = pub_date.strip()
        if text:
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except ValueError:
                if len(text) >= 10:
                    return text[:10]
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            return ""
    return ""


def _normalize_news_item(raw_item: dict[str, Any]) -> dict[str, str] | None:
    content = raw_item.get("content") if isinstance(raw_item.get("content"), dict) else {}
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    canonical = (
        content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
    )
    clickthrough = (
        content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
    )

    title = _first_str(content.get("title"), raw_item.get("title"))
    publisher = _first_str(provider.get("displayName"), raw_item.get("publisher"))
    link = _first_str(
        clickthrough.get("url"),
        canonical.get("url"),
        raw_item.get("link"),
    )
    summary = _first_str(
        content.get("summary"),
        content.get("description"),
        raw_item.get("summary"),
        raw_item.get("description"),
    )
    published = _published_date_str(content.get("pubDate"), raw_item.get("providerPublishTime"))

    if not any((title, publisher, link, summary)):
        return None

    return {
        "title": title,
        "publisher": publisher,
        "published": published,
        "link": link,
        "summary": summary,
    }


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
        benchmark_ticker = ingest_cfg.get("benchmark_ticker") or _default_benchmark_ticker(ticker)
        vix_ticker = ingest_cfg.get("vix_ticker", "^VIX")

        hist_daily = yf_obj.history(period=period)
        if hist_daily is None or hist_daily.empty:
            raise ValueError("가격 이력이 비어 있습니다.")

        hist_monthly = hist_daily["Close"].resample("ME").last().dropna()

        info = dict(yf_obj.info) if yf_obj.info else {}

        income = getattr(yf_obj, "quarterly_financials", None)
        balance = getattr(yf_obj, "quarterly_balance_sheet", None)
        cashflow = getattr(yf_obj, "quarterly_cashflow", None)
        institutional_holders = self._safe_frame_attr(yf_obj, "institutional_holders")
        mutualfund_holders = self._safe_frame_attr(yf_obj, "mutualfund_holders")
        major_holders = self._safe_frame_attr(yf_obj, "major_holders")
        benchmark_daily_close = self._fetch_benchmark_daily_close(benchmark_ticker, period)
        vix_daily_close = self._fetch_benchmark_daily_close(vix_ticker, period)

        news_list = []
        try:
            raw_news = yf_obj.news or []
            for n in raw_news[:news_count]:
                normalized = _normalize_news_item(n)
                if normalized is None:
                    continue
                news_list.append(normalized)
        except Exception:
            news_list = []

        recs = None
        try:
            recs = yf_obj.recommendations
        except Exception:
            recs = None

        fund_top_holdings: list[dict[str, Any]] = []
        fund_overview: dict[str, Any] = {}
        fund_operations: dict[str, Any] = {}
        asset_classes: dict[str, Any] = {}
        sector_weightings: dict[str, Any] = {}
        try:
            fd = getattr(yf_obj, "funds_data", None)
            if fd is not None:
                fund_top_holdings = _fund_top_holdings_records(getattr(fd, "top_holdings", None))
                ov = getattr(fd, "fund_overview", None)
                fund_overview = ov if isinstance(ov, dict) else {}
                fund_operations = _fund_operations_dict(getattr(fd, "fund_operations", None))
                ac = getattr(fd, "asset_classes", None)
                asset_classes = ac if isinstance(ac, dict) else {}
                sw = getattr(fd, "sector_weightings", None)
                sector_weightings = sw if isinstance(sw, dict) else {}
        except Exception:
            fund_top_holdings = []
            fund_overview = {}
            fund_operations = {}
            asset_classes = {}
            sector_weightings = {}

        community: dict[str, Any] = {}
        try:
            # Best-effort: may be blocked/geo-restricted; never fail ingestion.
            community = _fetch_yahoo_community(ticker, max_items=20)
        except Exception:
            community = {}

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
            fund_top_holdings=fund_top_holdings,
            fund_overview=fund_overview,
            fund_operations=fund_operations,
            asset_classes=asset_classes,
            sector_weightings=sector_weightings,
            benchmark_ticker=benchmark_ticker,
            benchmark_daily_close=benchmark_daily_close,
            vix_ticker=vix_ticker,
            vix_daily_close=vix_daily_close,
            institutional_holders=institutional_holders,
            mutualfund_holders=mutualfund_holders,
            major_holders=major_holders,
            community=community,
        )

    def _safe_frame_attr(self, yf_obj: yf.Ticker, attr: str) -> pd.DataFrame | None:
        try:
            value = getattr(yf_obj, attr, None)
        except Exception:
            return None
        return value if isinstance(value, pd.DataFrame) else None

    def _fetch_benchmark_daily_close(self, benchmark_ticker: str, period: str) -> dict[str, float]:
        if not benchmark_ticker:
            return {}
        try:
            benchmark_hist = yf.Ticker(benchmark_ticker).history(period=period)
        except Exception:
            return {}
        if benchmark_hist is None or benchmark_hist.empty or "Close" not in benchmark_hist:
            return {}
        return _series_to_float_dict(benchmark_hist["Close"])

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
        fund_top_holdings: list[dict[str, Any]] | None = None,
        fund_overview: dict[str, Any] | None = None,
        fund_operations: dict[str, Any] | None = None,
        asset_classes: dict[str, Any] | None = None,
        sector_weightings: dict[str, Any] | None = None,
        community: dict[str, Any] | None = None,
        *,
        benchmark_ticker: str | None = None,
        benchmark_daily_close: dict[str, float] | None = None,
        vix_ticker: str | None = None,
        vix_daily_close: dict[str, float] | None = None,
        institutional_holders: pd.DataFrame | None = None,
        mutualfund_holders: pd.DataFrame | None = None,
        major_holders: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        close = price_daily["Close"]
        high = price_daily["High"] if "High" in price_daily else pd.Series(dtype=float)
        low = price_daily["Low"] if "Low" in price_daily else pd.Series(dtype=float)
        volume = price_daily["Volume"] if "Volume" in price_daily else pd.Series(dtype=float)
        rolling_high = high.rolling(252, min_periods=1).max()
        rolling_low = low.rolling(252, min_periods=1).min()

        keys_info = [
            "longName",
            "quoteType",
            "sector",
            "industry",
            "longBusinessSummary",
            "website",
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
            "trailingEps",
            "forwardEps",
            "beta",
            "sharesOutstanding",
            "averageVolume",
            "targetMeanPrice",
            "targetLowPrice",
            "targetHighPrice",
            "numberOfAnalystOpinions",
            "recommendationKey",
        ]
        info_subset = {k: info.get(k) for k in keys_info}

        return {
            "ticker": ticker,
            "fetched_at": _utc_now_iso(),
            "price": {
                "current": float(close.iloc[-1]),
                "52w_high": float(rolling_high.iloc[-1]),
                "52w_low": float(rolling_low.iloc[-1]),
                "market_reference_date": _series_latest_date(close),
                "monthly_close": _series_to_float_dict(price_monthly),
                "daily_close": _series_to_float_dict(close),
                "daily_high": _series_to_float_dict(high),
                "daily_low": _series_to_float_dict(low),
                "daily_volume": _series_to_float_dict(volume),
                "benchmark_ticker": benchmark_ticker,
                "benchmark_daily_close": dict(benchmark_daily_close or {}),
                "vix_ticker": vix_ticker,
                "vix_daily_close": dict(vix_daily_close or {}),
            },
            "info": info_subset,
            "fund": {
                "top_holdings": list(fund_top_holdings or []),
                "fund_overview": dict(fund_overview or {}),
                "fund_operations": dict(fund_operations or {}),
                "asset_classes": dict(asset_classes or {}),
                "sector_weightings": dict(sector_weightings or {}),
                "source": "yfinance.funds_data",
            },
            "community": dict(community or {}),
            "financials": {
                "income_stmt": _df_to_nested_dict(income),
                "balance_sheet": _df_to_nested_dict(balance),
                "cashflow": _df_to_nested_dict(cashflow),
            },
            "news": news,
            "analyst_recs": self._parse_recs(recs),
            "holders": {
                "institutional_holders": _holder_records(institutional_holders),
                "mutualfund_holders": _holder_records(mutualfund_holders),
                "major_holders": _major_holder_records(major_holders),
            },
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
