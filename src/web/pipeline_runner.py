from __future__ import annotations

import json
import sys
from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "api_guide" / ".env")

from report.composer import today_str  # noqa: E402
from run_pipeline import load_config, paths_for_date, run_single_pipeline  # noqa: E402
from web.cache import is_complete_run  # noqa: E402
from fio.storage import write_json  # noqa: E402
from news.sentiment import enrich_with_finbert_sentiment  # noqa: E402
from web.security import validate_date, validate_ticker  # noqa: E402


def make_pipeline_args(
    *,
    skip_llm: bool = False,
    judge: bool = False,
    no_judge: bool = False,
) -> Namespace:
    return Namespace(
        skip_llm=skip_llm,
        judge=judge,
        no_judge=no_judge,
        model_log=False,
        ticker=None,
        tickers=None,
        tickers_file=None,
        date=None,
        list_models=False,
    )


def run_for_dashboard(
    ticker: str,
    *,
    date: str | None = None,
    skip_llm: bool = False,
    judge: bool = False,
    no_judge: bool = False,
    force_refresh: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    sym = validate_ticker(ticker)
    date_str = validate_date(date) if date else today_str()

    if not force_refresh and is_complete_run(cfg, sym, date_str):
        if progress:
            progress(f"캐시: {sym}/{date_str} 기존 산출물 사용 (재생성 생략)")
        cached = load_existing_run(sym, date_str)
        if cached:
            cached["cached"] = True
            cached["cache_hit"] = True
            return cached

    args = make_pipeline_args(skip_llm=skip_llm, judge=judge, no_judge=no_judge)
    result = run_single_pipeline(
        cfg,
        sym,
        date_str,
        args,
        emit_model_log=False,
        progress=progress,
        return_result=True,
    ) or {}
    result["cached"] = False
    result["cache_hit"] = False
    return result


def load_existing_run(ticker: str, date: str) -> dict[str, Any] | None:
    cfg = load_config()
    sym = validate_ticker(ticker)
    date_str = validate_date(date)
    paths = paths_for_date(cfg, sym, date_str)
    art = paths["artifacts_dir"]
    report_md_path = paths["report_md"]
    if not art.is_dir():
        return None

    def _read_json(name: str) -> dict[str, Any] | None:
        p = art / name
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    context = _read_json("context.json")
    eval_data = _read_json("eval.json")
    signal = _read_json("signal.json")
    snapshot = _read_json("snapshot.json")
    news_enrichment = _read_json("news_enrichment.json")
    report_md = report_md_path.read_text(encoding="utf-8") if report_md_path.is_file() else ""

    if not context and not report_md:
        return None

    overview = {
        "company_name": (context or {}).get("metadata", {}).get("company_name", sym),
        "sector": (context or {}).get("metadata", {}).get("sector"),
        "current_price": (snapshot or {}).get("price", {}).get("current")
        or (context or {}).get("price_summary", {}).get("current_price"),
        "signal": (signal or {}).get("signal"),
        "confidence": (signal or {}).get("confidence"),
        "grade": (eval_data or {}).get("grade"),
        "score_normalized_100": (eval_data or {}).get("score_normalized_100"),
        "total_score": (eval_data or {}).get("total_score"),
    }

    return {
        "ticker": sym,
        "date": date_str,
        "paths": {
            "artifacts_dir": str(art),
            "report_md": str(report_md_path),
        },
        "overview": overview,
        "snapshot_summary": {
            "fetched_at": (snapshot or {}).get("fetched_at"),
            "price": (snapshot or {}).get("price"),
            "info": (snapshot or {}).get("info"),
            "news_count": len((snapshot or {}).get("news") or []),
        },
        "news_enrichment": news_enrichment or {},
        "context": context or {},
        "report_md": report_md,
        "eval": eval_data or {},
        "signal": signal or {},
        "token_check": (context or {}).get("_token_check"),
        "loaded_from_disk": True,
        "cached": True,
        "cache_hit": True,
    }


def compute_sentiment_for_run(ticker: str, date: str) -> dict[str, Any]:
    """캐시된 news_enrichment에 FinBERT 감성을 계산·저장합니다."""
    cfg = load_config()
    sym = validate_ticker(ticker)
    date_str = validate_date(date)
    paths = paths_for_date(cfg, sym, date_str, ensure_dirs=False)
    art = paths["artifacts_dir"]
    news_path = art / "news_enrichment.json"
    if not news_path.is_file():
        return {"error": "news_enrichment.json 없음", "articles": [], "aggregate": {}}

    enrichment = json.loads(news_path.read_text(encoding="utf-8"))
    sa_existing = enrichment.get("sentiment_analysis") or {}
    if sa_existing.get("error"):
        enrichment.pop("sentiment_analysis", None)
    if enrichment.get("sentiment_analysis") and not enrichment["sentiment_analysis"].get("error"):
        sa = enrichment["sentiment_analysis"]
        if sa.get("articles") is not None and not sa.get("skipped"):
            return sa

    enrich_with_finbert_sentiment(enrichment, cfg=cfg)
    write_json(news_path, enrichment)
    return enrichment.get("sentiment_analysis") or {}


def list_history(limit: int = 30) -> list[dict[str, str]]:
    cfg = load_config()
    base = Path(cfg.get("paths", {}).get("artifacts", "artifacts"))
    if not base.is_absolute():
        base = ROOT / base
    if not base.is_dir():
        return []

    rows: list[dict[str, str]] = []
    for ticker_dir in base.iterdir():
        if not ticker_dir.is_dir() or ticker_dir.name.startswith("_"):
            continue
        for date_dir in ticker_dir.iterdir():
            if not date_dir.is_dir():
                continue
            if (date_dir / "context.json").is_file() or (date_dir / "eval.json").is_file():
                rows.append({"ticker": ticker_dir.name, "date": date_dir.name})

    rows.sort(key=lambda r: (r["date"], r["ticker"]), reverse=True)
    return rows[:limit]
