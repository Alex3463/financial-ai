from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from web.app import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_path_traversal_ticker_rejected(client: TestClient) -> None:
    res = client.get("/api/runs/../../.env/2026-06-08")
    assert res.status_code in (400, 404, 422)


def test_invalid_date_rejected(client: TestClient) -> None:
    res = client.get("/api/runs/AAPL/not-a-date")
    assert res.status_code == 400


def test_security_headers(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"


def test_analyze_requires_token_in_public_mode(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_MODE", "public")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "secret-test-token")
    monkeypatch.delenv("DASHBOARD_DEMO_OPEN", raising=False)

    res = client.post("/api/analyze", json={"ticker": "AAPL"})
    assert res.status_code == 401

    ok = client.post(
        "/api/analyze",
        json={"ticker": "AAPL"},
        headers={"X-Dashboard-Token": "secret-test-token"},
    )
    assert ok.status_code == 200
    assert "job_id" in ok.json()


def test_visitors_redacted_in_public_without_token(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_MODE", "public")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "secret-test-token")
    data = client.get("/api/visitors").json()
    assert data.get("detail_requires_auth") is True
    assert data.get("active") == []


def test_openapi_disabled_by_default(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 404
