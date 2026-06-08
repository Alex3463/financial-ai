from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.jobs import JobManager
from web.pipeline_runner import list_history, load_existing_run, run_for_dashboard

from report.composer import today_str
from run_pipeline import load_config
from web.cache import is_complete_run

STATIC_DIR = Path(__file__).resolve().parent / "static"
jobs = JobManager()

app = FastAPI(
    title="Financial AI Demo",
    description="티커 입력 → 파이프라인 실행 → 탭별 결과 대시보드",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    date: str | None = None
    skip_llm: bool = False
    judge: bool = False
    no_judge: bool = False
    force_refresh: bool = False


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
        "disclaimer": "투자 권유가 아닙니다. 데모·참고용입니다.",
    }


@app.get("/api/history")
def history(limit: int = 30) -> dict[str, Any]:
    return {"items": list_history(limit=limit)}


@app.get("/api/runs/{ticker}/{date}")
def get_run(ticker: str, date: str) -> dict[str, Any]:
    data = load_existing_run(ticker, date)
    if not data:
        raise HTTPException(status_code=404, detail="해당 티커/날짜 산출물이 없습니다.")
    return data


@app.get("/api/cache/{ticker}")
def cache_status(ticker: str, date: str | None = None) -> dict[str, Any]:
    cfg = load_config()
    sym = ticker.strip().upper()
    date_str = date or today_str()
    return {
        "ticker": sym,
        "date": date_str,
        "complete": is_complete_run(cfg, sym, date_str),
    }


@app.post("/api/analyze")
def start_analyze(req: AnalyzeRequest) -> dict[str, str]:
    ticker = req.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="티커를 입력하세요.")

    date_str = req.date or today_str()
    job = jobs.create(ticker, date_str)

    def runner(progress):
        return run_for_dashboard(
            ticker,
            date=date_str,
            skip_llm=req.skip_llm,
            judge=req.judge,
            no_judge=req.no_judge,
            force_refresh=req.force_refresh,
            progress=progress,
        )

    jobs.run_in_background(job, runner)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return jobs.to_dict(job)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
