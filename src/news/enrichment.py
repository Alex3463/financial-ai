from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md

from agents.mcp_servers import make_playwright_server
from fio.storage import write_json
from report.llm import LLMProvider

DEFAULT_MAX_DEEP_READS = 2
DEFAULT_WAIT_AFTER_NAVIGATION_SEC = 1.0
MIN_ARTICLE_TEXT_LENGTH = 400
MAX_ARTICLE_MARKDOWN_CHARS = 12000
GENERIC_COMPANY_TOKENS = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "holdings",
    "holding",
    "group",
    "plc",
    "ltd",
    "limited",
    "sa",
    "ag",
    "nv",
    "class",
    "common",
}
COMPANY_EVENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("실적", ("earnings", "results", "guidance", "outlook", "forecast", "margin", "profit")),
    ("제품", ("launch", "product", "device", "service", "subscription", "feature", "release")),
    ("규제", ("regulation", "regulatory", "antitrust", "lawsuit", "fine", "privacy", "tariff")),
    ("M&A", ("acquisition", "merger", "deal", "stake", "buyout", "partnership")),
    ("구조조정", ("layoff", "restructuring", "cost cut", "buyback", "dividend")),
)

IMPACT_KEYWORD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "실적",
        (
            "earnings",
            "results",
            "revenue",
            "profit",
            "margin",
            "guidance",
            "forecast",
            "outlook",
            "beat",
            "miss",
            "실적",
            "가이던스",
        ),
    ),
    (
        "AI",
        (
            " ai ",
            "artificial intelligence",
            "chip",
            "gpu",
            "llm",
            "data center",
            "on-device ai",
            "온디바이스 ai",
            "인공지능",
        ),
    ),
    (
        "제품",
        (
            "launch",
            "product",
            "device",
            "iphone",
            "ipad",
            "mac",
            "service",
            "subscription",
            "제품",
            "출시",
        ),
    ),
    (
        "규제",
        (
            "regulation",
            "regulatory",
            "antitrust",
            "lawsuit",
            "fine",
            "privacy",
            "tariff",
            "규제",
            "반독점",
            "소송",
        ),
    ),
    (
        "M&A",
        (
            "acquisition",
            "merger",
            "deal",
            "stake",
            "buyout",
            "m&a",
            "인수",
            "합병",
        ),
    ),
    (
        "매크로",
        (
            "fed",
            "rate",
            "inflation",
            "macro",
            "economy",
            "recession",
            "yield",
            "금리",
            "인플레이션",
            "거시",
        ),
    ),
)

ARTICLE_EXTRACTION_SCRIPT = """
() => {
  const seen = new Set();
  const candidates = [];
  const addCandidate = (element, selector) => {
    if (!element || seen.has(element)) {
      return;
    }
    seen.add(element);
    const text = (element.innerText || "").replace(/\\s+/g, " ").trim();
    const html = element.innerHTML || "";
    if (!text && !html) {
      return;
    }
    candidates.push({
      selector,
      textLength: text.length,
      htmlLength: html.length,
      preview: text.slice(0, 500),
      html,
    });
  };

  for (const selector of ["article", "main", "[role='main']"]) {
    for (const element of document.querySelectorAll(selector)) {
      addCandidate(element, selector);
    }
  }

  let longest = null;
  for (const element of document.querySelectorAll("section, div")) {
    const text = (element.innerText || "").replace(/\\s+/g, " ").trim();
    if (text.length < 300) {
      continue;
    }
    const html = element.innerHTML || "";
    const candidate = {
      selector: "longest_text_block",
      textLength: text.length,
      htmlLength: html.length,
      preview: text.slice(0, 500),
      html,
    };
    if (!longest || candidate.textLength > longest.textLength) {
      longest = candidate;
    }
  }

  if (!candidates.length && longest) {
    candidates.push(longest);
  }
  if (!candidates.length) {
    addCandidate(document.body, "document.body");
  }

  candidates.sort((left, right) => {
    const leftScore = left.textLength + Math.min(left.htmlLength, 10000) / 50;
    const rightScore = right.textLength + Math.min(right.htmlLength, 10000) / 50;
    return rightScore - leftScore;
  });

  const best = candidates[0] || {
    selector: "document.body",
    textLength: 0,
    htmlLength: 0,
    preview: "",
    html: document.body ? document.body.innerHTML : "",
  };

  return {
    pageTitle: document.title || "",
    url: location.href,
    selectorUsed: best.selector,
    textLength: best.textLength,
    preview: best.preview,
    html: best.html,
  };
}
""".strip()


def _is_http_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _slugify(value: str) -> str:
    lowered = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:80] or "article"


def _normalize_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (value or "").lower())


def _build_company_aliases(ticker: str, company_name: str) -> set[str]:
    aliases: set[str] = set()
    ticker_token = (ticker or "").strip().lower()
    if ticker_token:
        aliases.add(ticker_token)

    for token in _normalize_tokens(company_name):
        if len(token) <= 1 or token in GENERIC_COMPANY_TOKENS:
            continue
        aliases.add(token)
    return aliases


def _contains_alias(text: str, aliases: set[str]) -> bool:
    padded = f" {text.lower()} "
    return any(re.search(rf"\b{re.escape(alias)}\b", padded) for alias in aliases)


def _clean_text(value: str, *, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _extract_impact_labels(article: dict[str, Any]) -> list[str]:
    text = f" {article.get('title', '')} {article.get('summary', '')} ".lower()
    labels: list[str] = []
    for label, keywords in IMPACT_KEYWORD_GROUPS:
        if any(keyword in text for keyword in keywords):
            labels.append(label)
    return labels


def _extract_company_event_labels(article: dict[str, Any]) -> list[str]:
    text = f" {article.get('title', '')} {article.get('summary', '')} ".lower()
    labels: list[str] = []
    for label, keywords in COMPANY_EVENT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            labels.append(label)
    return labels


def _score_company_relevance(
    article: dict[str, Any],
    *,
    ticker: str,
    company_name: str,
) -> dict[str, Any]:
    title = str(article.get("title", "")).strip()
    summary = str(article.get("summary", "")).strip()
    text = f"{title} {summary}".strip()
    title_lower = title.lower()
    summary_lower = summary.lower()
    url_lower = str(article.get("link", "")).lower()

    aliases = _build_company_aliases(ticker, company_name)
    title_match = _contains_alias(title_lower, aliases)
    summary_match = _contains_alias(summary_lower, aliases)
    url_match = any(alias and alias in url_lower for alias in aliases)
    event_labels = _extract_company_event_labels(article)
    impact_labels = _extract_impact_labels(article)

    score = 0
    reasons: list[str] = []
    if title_match:
        score += 100
        reasons.append("제목에 회사명/티커 직접 언급")
    elif summary_match:
        score += 80
        reasons.append("요약에 회사명/티커 직접 언급")
    elif url_match:
        score += 60
        reasons.append("URL에 회사 식별자 포함")

    if score > 0 and event_labels:
        score += 20
        reasons.append("회사 이벤트: " + ", ".join(event_labels[:2]))
    elif score > 0 and impact_labels:
        score += 5
        reasons.append("관련 키워드: " + ", ".join(impact_labels[:2]))

    return {
        "score": score,
        "reasons": reasons,
        "event_labels": event_labels,
        "impact_labels": impact_labels,
        "company_match": score > 0,
    }


def select_deep_read_candidates(
    articles: list[dict[str, Any]],
    *,
    ticker: str = "",
    company_name: str = "",
    max_articles: int = DEFAULT_MAX_DEEP_READS,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for article in articles:
        url = str(article.get("link") or "").strip()
        if not _is_http_url(url):
            continue
        relevance = _score_company_relevance(article, ticker=ticker, company_name=company_name)
        if not relevance["company_match"]:
            continue
        chosen = dict(article)
        chosen["selection_reason"] = " / ".join(relevance["reasons"]) or "회사 관련 기사"
        chosen["company_relevance_score"] = relevance["score"]
        chosen["company_event_labels"] = relevance["event_labels"]
        chosen["impact_labels"] = relevance["impact_labels"]
        ranked.append(chosen)
    ranked.sort(
        key=lambda article: (
            article.get("company_relevance_score") or 0,
            str(article.get("published") or ""),
        ),
        reverse=True,
    )
    return ranked[:max_articles]


def html_fragment_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag_name in ("script", "style", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()
    markdown = html_to_md(str(soup), heading_style="ATX")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def build_fallback_summary(
    article: dict[str, Any],
    *,
    preview_text: str = "",
) -> list[str]:
    bullets: list[str] = []
    summary = _clean_text(article.get("summary", ""), limit=180)
    if summary:
        bullets.append(summary)
    preview = _clean_text(preview_text, limit=180)
    if preview and preview not in bullets:
        bullets.append(preview)
    if not bullets:
        bullets.append(_clean_text(article.get("title", ""), limit=180))
    return bullets[:3]


def _extract_json_block(result_text: str) -> dict[str, Any]:
    match = re.search(
        r"### Result\s*(.*?)\s*### Ran Playwright code",
        result_text,
        re.S,
    )
    if not match:
        raise ValueError("Playwright evaluation result did not include a parsable JSON block.")
    payload = match.group(1).strip()
    return json.loads(payload)


def _call_result_text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _build_summary_prompt(article: dict[str, Any], markdown_text: str) -> tuple[str, str]:
    body = markdown_text[:MAX_ARTICLE_MARKDOWN_CHARS]
    system_msg = (
        "당신은 금융 뉴스 요약가입니다. 기사에 나온 사실만 사용해 투자 판단에 중요한 핵심을 "
        "2~3개의 한국어 bullet로 요약하세요. JSON만 반환하세요."
    )
    user_msg = (
        "다음 기사를 2~3개 bullet로 요약하세요.\n"
        '반환 형식: {"bullets":["...","..."]}\n'
        "- bullet은 중복 없이 사실 중심으로 작성합니다.\n"
        "- 숫자, 가이던스, 규제 변화, 제품/AI 이벤트, 수익성 영향이 있으면 우선 반영합니다.\n"
        "- 각 bullet은 120자 안팎으로 간결하게 씁니다.\n\n"
        f"제목: {article.get('title', '')}\n"
        f"출처: {article.get('publisher', '')}\n"
        f"URL: {article.get('link', '')}\n\n"
        "기사 Markdown:\n"
        f"```md\n{body}\n```"
    )
    return system_msg, user_msg


def _parse_summary_response(raw_text: str) -> list[str]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    payload = json.loads(text)
    bullets = payload.get("bullets") if isinstance(payload, dict) else None
    if not isinstance(bullets, list):
        raise ValueError("Summary response did not contain a bullets list.")
    cleaned = [_clean_text(str(item), limit=180) for item in bullets if str(item).strip()]
    if not cleaned:
        raise ValueError("Summary response contained no usable bullets.")
    return cleaned[:3]


def summarize_article_markdown(
    article: dict[str, Any],
    markdown_text: str,
    *,
    llm_provider: LLMProvider | None,
    preview_text: str = "",
) -> tuple[list[str], str]:
    if llm_provider is None:
        return build_fallback_summary(article, preview_text=preview_text), "fallback"

    system_msg, user_msg = _build_summary_prompt(article, markdown_text)
    try:
        response = llm_provider.generate(
            system_msg,
            user_msg,
            temperature=0.1,
            max_tokens=300,
        )
        return _parse_summary_response(response), "llm"
    except Exception:
        return build_fallback_summary(article, preview_text=preview_text), "fallback"


async def _extract_article_payload(
    server: Any,
    article: dict[str, Any],
    *,
    wait_after_navigation_sec: float,
) -> dict[str, Any]:
    await server.call_tool("browser_navigate", {"url": article["link"]})
    if wait_after_navigation_sec > 0:
        await server.call_tool("browser_wait_for", {"time": wait_after_navigation_sec})
    result = await server.call_tool("browser_evaluate", {"function": ARTICLE_EXTRACTION_SCRIPT})
    payload = _extract_json_block(_call_result_text(result))
    if int(payload.get("textLength") or 0) < MIN_ARTICLE_TEXT_LENGTH:
        raise ValueError(
            f"Extracted article body was too short ({payload.get('textLength', 0)} chars)."
        )
    return payload


async def _enrich_news_async(
    cfg: dict[str, Any],
    *,
    ticker: str,
    company_name: str,
    news_items: list[dict[str, Any]],
    artifacts_dir: Path,
    llm_provider: LLMProvider | None,
) -> dict[str, Any]:
    company_relevant_articles = select_deep_read_candidates(
        news_items,
        ticker=ticker,
        company_name=company_name,
        max_articles=max(len(news_items), DEFAULT_MAX_DEEP_READS),
    )
    candidates = company_relevant_articles[:DEFAULT_MAX_DEEP_READS]
    status = {
        "selected_count": len(candidates),
        "deep_read_count": 0,
        "failed_count": 0,
        "summary_modes": [],
    }
    enrichment: dict[str, Any] = {
        "ticker": ticker,
        "status": status,
        "deep_read_articles": [],
        "company_relevant_articles": [
            {
                "title": article.get("title", ""),
                "publisher": article.get("publisher", ""),
                "published": article.get("published", ""),
                "url": article.get("link", ""),
                "selection_reason": article.get("selection_reason", ""),
                "company_relevance_score": article.get("company_relevance_score"),
            }
            for article in company_relevant_articles
        ],
        "failures": [],
        "selected_articles": [
            {
                "title": article.get("title", ""),
                "publisher": article.get("publisher", ""),
                "published": article.get("published", ""),
                "url": article.get("link", ""),
                "selection_reason": article.get("selection_reason", ""),
            }
            for article in candidates
        ],
    }

    news_dir = artifacts_dir / "news"
    news_dir.mkdir(parents=True, exist_ok=True)

    server = make_playwright_server(cfg, name=f"playwright-news-{ticker}")
    if not candidates:
        return enrichment
    if server is None:
        status["failed_count"] = len(candidates)
        enrichment["failures"] = [
            {
                "title": article.get("title", ""),
                "url": article.get("link", ""),
                "error": "Playwright MCP server is disabled or unavailable.",
            }
            for article in candidates
        ]
        return enrichment

    wait_after_navigation_sec = float(
        (((cfg.get("mcp", {}) or {}).get("playwright", {}) or {}).get(
            "wait_after_navigation_sec",
            DEFAULT_WAIT_AFTER_NAVIGATION_SEC,
        ))
    )

    async with server:
        for index, article in enumerate(candidates, start=1):
            try:
                payload = await _extract_article_payload(
                    server,
                    article,
                    wait_after_navigation_sec=wait_after_navigation_sec,
                )
                markdown_text = html_fragment_to_markdown(str(payload.get("html") or ""))
                if len(markdown_text) < MIN_ARTICLE_TEXT_LENGTH:
                    raise ValueError(
                        f"Converted markdown was too short ({len(markdown_text)} chars)."
                    )

                file_name = f"{index:02d}-{_slugify(article.get('title', ''))}.md"
                markdown_path = news_dir / file_name
                markdown_path.write_text(markdown_text + "\n", encoding="utf-8")

                summary_bullets, summary_mode = summarize_article_markdown(
                    article,
                    markdown_text,
                    llm_provider=llm_provider,
                    preview_text=str(payload.get("preview") or ""),
                )

                digest = {
                    "title": article.get("title", ""),
                    "publisher": article.get("publisher", ""),
                    "published": article.get("published", ""),
                    "url": article.get("link", ""),
                    "selection_reason": article.get("selection_reason", ""),
                    "markdown_path": str(markdown_path),
                    "summary_bullets": summary_bullets,
                    "source_url": article.get("link", ""),
                }
                enrichment["deep_read_articles"].append(digest)
                status["deep_read_count"] += 1
                status["summary_modes"].append(summary_mode)
            except Exception as exc:
                status["failed_count"] += 1
                enrichment["failures"].append(
                    {
                        "title": article.get("title", ""),
                        "url": article.get("link", ""),
                        "error": str(exc),
                    }
                )

    return enrichment


def enrich_news(
    cfg: dict[str, Any],
    *,
    ticker: str,
    company_name: str,
    news_items: list[dict[str, Any]],
    artifacts_dir: Path,
    use_llm_summary: bool,
) -> dict[str, Any]:
    llm_provider: LLMProvider | None = None
    if use_llm_summary:
        try:
            llm_provider = LLMProvider(cfg)
        except Exception:
            llm_provider = None

    enrichment = asyncio.run(
        _enrich_news_async(
            cfg,
            ticker=ticker,
            company_name=company_name,
            news_items=news_items,
            artifacts_dir=artifacts_dir,
            llm_provider=llm_provider,
        )
    )
    write_json(artifacts_dir / "news_enrichment.json", enrichment)
    return enrichment
