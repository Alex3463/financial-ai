from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from web.app import app  # noqa: E402


def test_health_and_info() -> None:
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
    info = client.get("/api/info").json()
    assert info["name"] == "Financial AI Demo"
    assert "disclaimer" in info


def test_index_and_static() -> None:
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert "Financial AI" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_history_endpoint() -> None:
    client = TestClient(app)
    data = client.get("/api/history").json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_community_endpoint() -> None:
    client = TestClient(app)
    data = client.get("/api/runs/AAPL/2026-06-08").json()
    if data:
        assert "community" in data
        assert "raw" in data["community"] or data["community"] == {}


def test_spy_etf_run_payload() -> None:
    client = TestClient(app)
    res = client.get("/api/runs/SPY/2026-06-08")
    if res.status_code != 200:
        return
    data = res.json()
    assert data.get("context", {}).get("metadata", {}).get("asset_type") == "ETF"
    fund = data.get("context", {}).get("fund_profile") or {}
    assert fund.get("top_holdings")
    assert "ETF 분석 리포트" in (data.get("report_md") or "")


def test_visitors_endpoint() -> None:
    client = TestClient(app)
    client.get("/api/health")
    data = client.get("/api/visitors").json()
    assert "active_count" in data
    assert "active" in data
    assert data["active_count"] >= 1
