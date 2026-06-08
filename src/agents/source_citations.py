"""리포트 출처 태그를 엔드유저가 읽을 수 있는 형태로 정규화."""

from __future__ import annotations

import re

YAHOO_FINANCE = "Yahoo Finance"
YAHOO_ETF_PROFILE = "Yahoo Finance ETF profile"
YAHOO_ETF_HOLDINGS = "Yahoo Finance ETF holdings"
YAHOO_PRICE = "Yahoo Finance price history"
YAHOO_VIX = "Yahoo Finance VIX"

_CITATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"provided\s*input|input\s*slice|슬라이스\s*입력|입력\s*슬라이스|제공\s*입력", re.I), YAHOO_FINANCE),
    (re.compile(r"holdings\s*table|concentration_note|top_holdings|holdings\s*summary", re.I), YAHOO_ETF_HOLDINGS),
    (
        re.compile(
            r"fund_operations|expense_ratio|holdings_turnover|total_net_assets|asset_classes|sector_weightings|funds_data|fund\s*profile",
            re.I,
        ),
        YAHOO_ETF_PROFILE,
    ),
    (re.compile(r"\^vix|vix\.close|vix\s*market", re.I), YAHOO_VIX),
    (re.compile(r"yf\.history\.volume|volume\s*trading|거래량", re.I), YAHOO_PRICE),
    (re.compile(r"yf\.history|yfinance\.price|snapshot\s*fields|trailingpe|\.info\.|\.close|rsi|이평", re.I), YAHOO_PRICE),
    (
        re.compile(
            r"metadata\.|company_profile\.|price_technicals|volume_summary|market_context|cashflow_summary|consensus_summary|financials\.health",
            re.I,
        ),
        YAHOO_FINANCE,
    ),
    (re.compile(r"business\s*profile|summary_line", re.I), YAHOO_ETF_PROFILE),
    (re.compile(r"입력:\s*analyst view", re.I), "Yahoo Finance analyst consensus"),
    (re.compile(r"입력:\s*valuation analysis|valuation\s*formula|\w+\s*valuation:", re.I), "Yahoo Finance valuation"),
    (re.compile(r"입력:\s*", re.I), YAHOO_FINANCE),
]


def _with_as_of(label: str, data_as_of: str) -> str:
    label = (label or "").strip()
    if data_as_of and data_as_of not in label:
        return f"{label}, {data_as_of}"
    return label


def _is_public_url(source: str) -> bool:
    return bool(re.match(r"https?://", source, re.I)) or "finance.yahoo.com" in source.lower()


def normalize_citation_source(source: str, *, data_as_of: str = "") -> str:
    raw = (source or "").strip()
    if not raw:
        return _with_as_of(YAHOO_FINANCE, data_as_of)
    if _is_public_url(raw):
        return raw if raw.startswith("http") else f"https://{raw.lstrip('/')}"

    matched_labels = [label for pattern, label in _CITATION_RULES if pattern.search(raw)]
    if matched_labels:
        # 복합 출처 문자열이면 더 구체적인 라벨 우선 (ETF profile > generic Yahoo Finance)
        priority = [
            "Yahoo Finance analyst consensus",
            "Yahoo Finance valuation",
            YAHOO_ETF_HOLDINGS,
            YAHOO_ETF_PROFILE,
            YAHOO_VIX,
            YAHOO_PRICE,
            YAHOO_FINANCE,
        ]
        for pref in priority:
            if pref in matched_labels:
                return _with_as_of(pref, data_as_of)
        return _with_as_of(matched_labels[0], data_as_of)

    if "/" in raw or ";" in raw:
        for part in re.split(r"[/;]", raw):
            part = part.strip()
            if not part:
                continue
            normalized = normalize_citation_source(part, data_as_of=data_as_of)
            if normalized != part:
                return normalized

    if re.search(r"[_\.]|formula_text|context\.", raw):
        return _with_as_of(YAHOO_FINANCE, data_as_of)
    return raw


def sanitize_report_prose(report_md: str) -> str:
    """본문에 노출된 내부 필드명·백틱 키를 사용자 친화 문구로 치환."""
    text = report_md or ""
    text = re.sub(r"`metadata\.asset_type\s*=\s*\w+`에?\s*기반하며,?\s*", "", text)
    text = re.sub(r"`metadata\.asset_type`", "ETF 유형", text)
    text = re.sub(r"`company_profile\.summary_line`", "펀드 설명", text)
    text = re.sub(r"metadata\.asset_type\s*=\s*ETF", "ETF", text)
    text = re.sub(r"아래는 입력에 제공된\s*", "아래는 ", text)
    text = re.sub(r"holdings table provided in input", "Yahoo Finance ETF holdings", text, flags=re.I)
    text = re.sub(r"provided input slice", "Yahoo Finance", text, flags=re.I)
    text = re.sub(r"provided input", "Yahoo Finance", text, flags=re.I)
    text = re.sub(r"\s*/\s*provided input", "", text, flags=re.I)
    text = re.sub(r"concentration_note/", "Yahoo Finance ETF holdings, ", text, flags=re.I)
    text = re.sub(r"\(입력 제공\)", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text


def normalize_report_citations(report_md: str, *, data_as_of: str = "") -> str:
    text = sanitize_report_prose(report_md)

    def rewrite(match: re.Match[str]) -> str:
        return f"[출처: {normalize_citation_source(match.group(1), data_as_of=data_as_of)}]"

    return re.sub(r"\[출처:\s*([^\]]+)\]", rewrite, text)


def polish_stock_report_markdown(report_md: str, *, data_as_of: str = "") -> str:
    polished = re.sub(r"`?formula_text`?\s*[:：]\s*", "산식: ", report_md)
    polished = polished.replace("formula_text", "valuation formula")
    return normalize_report_citations(polished, data_as_of=data_as_of)


def polish_etf_report_markdown(report_md: str, *, data_as_of: str = "") -> str:
    return normalize_report_citations(report_md, data_as_of=data_as_of)
