from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from web.access_log import client_ip_from_headers, visitors
from web.jobs import JobManager
from web.pipeline_runner import (
    compute_sentiment_for_run,
    list_history,
    load_existing_run,
    refresh_community_for_run,
    run_for_dashboard,
)
from web.security import (
    SECURITY_HEADERS,
    analyze_rate_limiter,
    auth_required_for_write,
    auth_token_configured,
    clamp_limit,
    client_rate_key,
    demo_open_mode,
    is_public_mode,
    sanitize_run_paths,
    validate_date,
    validate_job_id,
    validate_ticker,
    verify_request_token,
    verify_visitors_access,
)

from report.composer import today_str
from run_pipeline import load_config
from web.cache import is_complete_run

STATIC_DIR = Path(__file__).resolve().parent / "static"
_max_jobs = int(os.environ.get("DASHBOARD_MAX_CONCURRENT_JOBS", "2"))
jobs = JobManager(max_running=_max_jobs)
_analyze_limiter = analyze_rate_limiter()

app = FastAPI(
    title="Financial AI Demo",
    description="티커 입력 → 파이프라인 실행 → 탭별 결과 대시보드",
    version="0.1.0",
    docs_url="/api/docs" if os.environ.get("DASHBOARD_OPENAPI", "").lower() == "true" else None,
    redoc_url=None,
)

_SKIP_LOG_PREFIXES = ("/static/", "/favicon.ico")
_SKIP_LOG_EXACT = {"/api/visitors", "/api/health"}


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, val in SECURITY_HEADERS.items():
            response.headers.setdefault(key, val)
        return response


class _AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path not in _SKIP_LOG_EXACT and not any(
            path.startswith(p) for p in _SKIP_LOG_PREFIXES
        ):
            ip = client_ip_from_headers(
                client_host=request.client.host if request.client else None,
                headers={k.lower(): v for k, v in request.headers.items()},
            )
            visitors.record(
                ip=ip,
                path=path,
                method=request.method,
                user_agent=request.headers.get("user-agent", ""),
            )
        return await call_next(request)


app.add_middleware(_SecurityHeadersMiddleware)
app.add_middleware(_AccessLogMiddleware)


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    date: str | None = Field(default=None, max_length=10)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/info")
def info() -> dict[str, Any]:
    public_url = os.environ.get("DASHBOARD_PUBLIC_URL", "").strip()
    return {
        "name": "Financial AI Demo",
        "version": "0.1.0",
        "mode": os.environ.get("DASHBOARD_MODE", "local"),
        "public_url": public_url or None,
        "github_url": os.environ.get(
            "DASHBOARD_GITHUB_URL",
            "https://github.com/Alex3463/financial-ai",
        ),
        "disclaimer": "투자 권유가 아닙니다. 데모·참고용입니다.",
        "auth_required_for_analyze": auth_required_for_write(),
        "demo_open": demo_open_mode(),
        "has_api_token": auth_token_configured(),
    }


@app.get("/api/history")
def history(limit: int = 30) -> dict[str, Any]:
    return {"items": list_history(limit=clamp_limit(limit))}


@app.get("/api/visitors")
def get_visitors(request: Request, active_window_sec: int = 300) -> dict[str, Any]:
    window = max(60, min(active_window_sec, 3600))
    snap = visitors.snapshot(active_window_sec=window)
    if verify_visitors_access(request):
        return snap
    return {
        "active_count": snap["active_count"],
        "active_window_sec": window,
        "active": [],
        "recent": [],
        "detail_requires_auth": True,
    }


@app.get("/api/runs/{ticker}/{date}")
def get_run(ticker: str, date: str) -> dict[str, Any]:
    sym = validate_ticker(ticker)
    date_str = validate_date(date)
    data = load_existing_run(sym, date_str)
    if not data:
        raise HTTPException(status_code=404, detail="해당 티커/날짜 산출물이 없습니다.")
    return sanitize_run_paths(data)


@app.post("/api/community/{ticker}/{date}")
def run_community_refresh(ticker: str, date: str, request: Request) -> dict[str, Any]:
    """Yahoo Finance 커뮤니티(종토방) 글 재수집."""
    verify_request_token(request)
    sym = validate_ticker(ticker)
    date_str = validate_date(date)
    payload = refresh_community_for_run(sym, date_str)
    if payload.get("error"):
        raise HTTPException(status_code=404, detail=payload["error"])
    return {"ticker": sym, "date": date_str, "community": payload}


@app.get("/api/community/{ticker}/{date}")
def get_community(ticker: str, date: str) -> dict[str, Any]:
    sym = validate_ticker(ticker)
    date_str = validate_date(date)
    data = load_existing_run(sym, date_str)
    if not data:
        raise HTTPException(status_code=404, detail="해당 티커/날짜 산출물이 없습니다.")
    return {
        "ticker": sym,
        "date": date_str,
        "community": data.get("community") or {},
    }


@app.post("/api/sentiment/{ticker}/{date}")
def run_sentiment(ticker: str, date: str, request: Request) -> dict[str, Any]:
    """캐시된 뉴스에 FinBERT 감성분석을 실행(또는 기존 결과 반환)합니다."""
    verify_request_token(request)
    sym = validate_ticker(ticker)
    date_str = validate_date(date)
    result = compute_sentiment_for_run(sym, date_str)
    if result.get("error") == "news_enrichment.json 없음":
        raise HTTPException(status_code=404, detail="뉴스 데이터가 없습니다.")
    return {"ticker": sym, "date": date_str, "sentiment_analysis": result}


@app.get("/api/cache/{ticker}")
def cache_status(ticker: str, date: str | None = None) -> dict[str, Any]:
    cfg = load_config()
    sym = validate_ticker(ticker)
    date_str = validate_date(date) if date else today_str()
    return {
        "ticker": sym,
        "date": date_str,
        "complete": is_complete_run(cfg, sym, date_str),
    }


@app.post("/api/analyze")
def start_analyze(req: AnalyzeRequest, request: Request) -> dict[str, str]:
    verify_request_token(request)
    _analyze_limiter.check(client_rate_key(request))

    sym = validate_ticker(req.ticker)
    date_str = validate_date(req.date) if req.date else today_str()

    job = jobs.create(sym, date_str)

    def runner(progress):
        return run_for_dashboard(sym, date=date_str, progress=progress)

    try:
        jobs.run_in_background(job, runner)
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    jid = validate_job_id(job_id)
    job = jobs.get(jid)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    payload = jobs.to_dict(job)
    if payload.get("result"):
        payload["result"] = sanitize_run_paths(payload["result"])
    return payload


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
