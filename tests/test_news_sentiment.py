from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from news.sentiment import (  # noqa: E402
    _normalize_score_items,
    _scores_from_result,
    aggregate_sentiment,
    analyze_news_sentiment,
    classify_aggregate_label,
    enrich_with_finbert_sentiment,
)


def test_scores_from_single_dict_transformers5() -> None:
    """transformers 5.x return_all_scores=True 가 단일 dict를 줄 때의 회귀."""
    raw = {"label": "positive", "score": 0.9}
    scores = _scores_from_result(raw)
    assert scores["positive"] == 0.9
    assert scores["negative"] == 0.0


def test_scores_from_all_labels_list() -> None:
    raw = [
        {"label": "positive", "score": 0.7},
        {"label": "neutral", "score": 0.2},
        {"label": "negative", "score": 0.1},
    ]
    scores = _scores_from_result(raw)
    assert scores["positive"] == 0.7
    assert scores["negative"] == 0.1
    nested = _normalize_score_items([raw])
    assert len(nested) == 3


def test_classify_aggregate_label() -> None:
    assert classify_aggregate_label(0.5) == "positive"
    assert classify_aggregate_label(-0.2) == "negative"
    assert classify_aggregate_label(0.0) == "neutral"


@patch("news.sentiment._get_finbert_pipeline")
def test_analyze_news_sentiment(mock_pipe: MagicMock) -> None:
    mock_pipe.return_value = lambda text: [
        [
            {"label": "positive", "score": 0.7},
            {"label": "negative", "score": 0.2},
            {"label": "neutral", "score": 0.1},
        ]
    ]

    rows = analyze_news_sentiment(
        [
            {
                "title": "Tesla stock jumps",
                "summary": "Strong deliveries beat estimates.",
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["sentiment_label"] == "positive"
    assert rows[0]["sentiment_score"] == 0.5
    assert rows[0]["sentiment_label_ko"] == "긍정"


def test_aggregate_sentiment() -> None:
    agg = aggregate_sentiment(
        [{"sentiment_score": 0.4}, {"sentiment_score": 0.2}]
    )
    assert agg["article_count"] == 2
    assert agg["sentiment_label"] == "positive"
    assert agg["avg_score"] == 0.3


@patch.dict(os.environ, {}, clear=False)
@patch("news.sentiment.analyze_news_sentiment")
def test_enrich_with_finbert_sentiment(mock_analyze: MagicMock) -> None:
    os.environ.pop("FINANCIAL_AI_SKIP_SENTIMENT", None)
    mock_analyze.return_value = [
        {
            "title": "Apple shares rise",
            "url": "https://example.com/a",
            "positive": 0.8,
            "negative": 0.1,
            "neutral": 0.1,
            "sentiment_score": 0.7,
            "sentiment_label": "positive",
            "sentiment_label_ko": "긍정",
        }
    ]
    enrichment = {
        "deep_read_articles": [
            {
                "title": "Apple shares rise",
                "url": "https://example.com/a",
                "summary_bullets": ["Earnings beat."],
            }
        ],
        "company_relevant_articles": [],
    }
    out = enrich_with_finbert_sentiment(enrichment, cfg={"news": {"sentiment": {"enabled": True}}})
    assert out["sentiment_analysis"]["aggregate"]["sentiment_label"] == "positive"
    assert out["deep_read_articles"][0]["sentiment"]["sentiment_label_ko"] == "긍정"
