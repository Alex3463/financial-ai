from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any

MAX_FINBERT_CHARS = 512
LABEL_KO = {"positive": "긍정", "negative": "부정", "neutral": "중립"}


@lru_cache(maxsize=1)
def _get_finbert_pipeline():
    """ProsusAI/finbert — lazy load (첫 호출 시 모델 다운로드)."""
    from transformers import pipeline

    # transformers 5.x: return_all_scores=True 는 top-1 dict만 반환 → top_k=None 사용
    return pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        top_k=None,
    )


def sentiment_enabled(cfg: dict[str, Any] | None = None) -> bool:
    if os.environ.get("FINANCIAL_AI_SKIP_SENTIMENT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return False
    news_cfg = (cfg or {}).get("news", {}) or {}
    sent_cfg = news_cfg.get("sentiment", {}) or {}
    return sent_cfg.get("enabled", True) is not False


def _article_text(title: str, summary: str) -> str:
    text = f"{title.strip()}. {summary.strip()}".strip(" .")
    return text[:MAX_FINBERT_CHARS] if text else title[:MAX_FINBERT_CHARS]


def _normalize_score_items(raw: Any) -> list[dict[str, Any]]:
    """파이프라인 출력을 [{label, score}, ...] 리스트로 통일."""
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        if not raw:
            return []
        if isinstance(raw[0], dict):
            return raw
        if isinstance(raw[0], list):
            return raw[0]
    return []


def _scores_from_result(raw_scores: Any) -> dict[str, float]:
    items = _normalize_score_items(raw_scores)
    score_dict = {item["label"].lower(): float(item["score"]) for item in items}
    return {
        "positive": score_dict.get("positive", 0.0),
        "negative": score_dict.get("negative", 0.0),
        "neutral": score_dict.get("neutral", 0.0),
    }


def classify_aggregate_label(avg_score: float) -> str:
    if avg_score > 0.1:
        return "positive"
    if avg_score < -0.1:
        return "negative"
    return "neutral"


def analyze_text_sentiment(text: str) -> dict[str, Any]:
    if not text.strip():
        return {
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 1.0,
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
            "sentiment_label_ko": "중립",
        }

    finbert = _get_finbert_pipeline()
    batch = finbert(text[:MAX_FINBERT_CHARS])
    scores_raw = batch[0] if batch else []
    scores = _scores_from_result(scores_raw)
    sentiment_label = max(scores, key=scores.get)
    sentiment_score = scores["positive"] - scores["negative"]
    return {
        **scores,
        "sentiment_score": round(sentiment_score, 4),
        "sentiment_label": sentiment_label,
        "sentiment_label_ko": LABEL_KO.get(sentiment_label, sentiment_label),
    }


def analyze_news_sentiment(news_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for news in news_list:
        title = str(news.get("title") or news.get("headline") or "").strip()
        summary = str(news.get("summary") or "").strip()
        if not summary and news.get("summary_bullets"):
            bullets = news.get("summary_bullets") or []
            summary = " ".join(str(b) for b in bullets)
        text = _article_text(title, summary)
        sent = analyze_text_sentiment(text)
        rows.append(
            {
                "title": title,
                "url": news.get("url") or news.get("link") or "",
                **sent,
            }
        )
    return rows


def aggregate_sentiment(article_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not article_rows:
        return {
            "avg_score": 0.0,
            "sentiment_label": "neutral",
            "sentiment_label_ko": "중립",
            "article_count": 0,
        }
    avg = sum(r["sentiment_score"] for r in article_rows) / len(article_rows)
    label = classify_aggregate_label(avg)
    return {
        "avg_score": round(avg, 4),
        "sentiment_label": label,
        "sentiment_label_ko": LABEL_KO.get(label, label),
        "article_count": len(article_rows),
    }


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _match_key(title: str, url: str) -> str:
    u = _normalize_url(url)
    if u:
        return u
    return re.sub(r"\s+", " ", title.strip().lower())


def _articles_for_sentiment(enrichment: dict[str, Any]) -> list[dict[str, Any]]:
    deep = enrichment.get("deep_read_articles") or []
    if deep:
        source = deep
    else:
        source = enrichment.get("company_relevant_articles") or []

    rows: list[dict[str, Any]] = []
    for article in source[:12]:
        title = article.get("title") or article.get("headline") or ""
        summary = article.get("summary") or article.get("digest") or ""
        bullets = article.get("summary_bullets")
        rows.append(
            {
                "title": title,
                "summary": summary,
                "summary_bullets": bullets,
                "url": article.get("url") or article.get("link") or "",
            }
        )
    return rows


def _attach_sentiment_to_articles(
    articles: list[dict[str, Any]],
    sentiment_rows: list[dict[str, Any]],
) -> None:
    lookup = {_match_key(r["title"], r.get("url", "")): r for r in sentiment_rows}
    for article in articles:
        key = _match_key(
            article.get("title") or article.get("headline") or "",
            article.get("url") or article.get("link") or "",
        )
        row = lookup.get(key)
        if row:
            article["sentiment"] = {
                k: row[k]
                for k in (
                    "positive",
                    "negative",
                    "neutral",
                    "sentiment_score",
                    "sentiment_label",
                    "sentiment_label_ko",
                )
            }


def enrich_with_finbert_sentiment(
    enrichment: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """news_enrichment dict에 FinBERT 감성 결과를 병합합니다."""
    existing = enrichment.get("sentiment_analysis") or {}
    if existing and not existing.get("error"):
        if existing.get("skipped") or existing.get("articles") is not None:
            return enrichment
    if not sentiment_enabled(cfg):
        enrichment["sentiment_analysis"] = {
            "skipped": True,
            "reason": "disabled",
        }
        return enrichment

    news_items = _articles_for_sentiment(enrichment)
    if not news_items:
        enrichment["sentiment_analysis"] = {
            "model": "ProsusAI/finbert",
            "articles": [],
            "aggregate": aggregate_sentiment([]),
        }
        return enrichment

    try:
        article_rows = analyze_news_sentiment(news_items)
        enrichment["sentiment_analysis"] = {
            "model": "ProsusAI/finbert",
            "articles": article_rows,
            "aggregate": aggregate_sentiment(article_rows),
        }
        _attach_sentiment_to_articles(enrichment.get("deep_read_articles") or [], article_rows)
        _attach_sentiment_to_articles(
            enrichment.get("company_relevant_articles") or [], article_rows
        )
    except Exception as exc:
        enrichment["sentiment_analysis"] = {
            "error": f"{type(exc).__name__}: {exc}",
            "model": "ProsusAI/finbert",
        }
    return enrichment
