from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from web.cache import is_complete_run  # noqa: E402
from web.pipeline_runner import run_for_dashboard  # noqa: E402


def _write_complete_run(base: Path, ticker: str, date: str) -> None:
    art = base / "artifacts" / ticker / date
    reports = base / "reports" / ticker
    art.mkdir(parents=True)
    reports.mkdir(parents=True)
    for name in ("snapshot.json", "context.json", "eval.json", "signal.json"):
        (art / name).write_text("{}", encoding="utf-8")
    (reports / f"{date}.md").write_text("# Report\n" + ("x" * 100), encoding="utf-8")
    (art / "run_manifest.json").write_text(
        json.dumps({"status": "complete", "ticker": ticker, "date": date}),
        encoding="utf-8",
    )


def test_is_complete_run_true(tmp_path: Path, monkeypatch) -> None:
    _write_complete_run(tmp_path, "AAPL", "2026-06-08")
    cfg = {
        "paths": {
            "artifacts": str(tmp_path / "artifacts"),
            "reports": str(tmp_path / "reports"),
            "tracking": str(tmp_path / "tracking"),
        }
    }
    monkeypatch.setattr("web.cache.paths_for_date", lambda c, t, d, **kw: {
        "artifacts_dir": tmp_path / "artifacts" / t / d,
        "report_md": tmp_path / "reports" / t / f"{d}.md",
    })
    assert is_complete_run(cfg, "AAPL", "2026-06-08") is True
    assert is_complete_run(cfg, "AAPL", "2026-06-09") is False


def test_run_for_dashboard_uses_cache(tmp_path: Path, monkeypatch) -> None:
    _write_complete_run(tmp_path, "AAPL", "2026-06-08")
    cfg = {
        "paths": {
            "artifacts": str(tmp_path / "artifacts"),
            "reports": str(tmp_path / "reports"),
            "tracking": str(tmp_path / "tracking"),
        }
    }
    monkeypatch.setattr("web.pipeline_runner.load_config", lambda: cfg)
    monkeypatch.setattr("web.pipeline_runner.paths_for_date", lambda c, t, d, **kw: {
        "artifacts_dir": tmp_path / "artifacts" / t / d,
        "report_md": tmp_path / "reports" / t / f"{d}.md",
    })
    monkeypatch.setattr("web.cache.paths_for_date", lambda c, t, d, **kw: {
        "artifacts_dir": tmp_path / "artifacts" / t / d,
        "report_md": tmp_path / "reports" / t / f"{d}.md",
    })

    called: list[bool] = []

    def fake_pipeline(*_a, **_k):
        called.append(True)
        return {"cached": False}

    monkeypatch.setattr("web.pipeline_runner.run_single_pipeline", fake_pipeline)

    logs: list[str] = []
    result = run_for_dashboard("AAPL", date="2026-06-08", progress=logs.append)
    assert result.get("cache_hit") is True
    assert called == []
    assert any("캐시" in line for line in logs)
