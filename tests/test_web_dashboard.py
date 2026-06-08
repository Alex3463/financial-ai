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
