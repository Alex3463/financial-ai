from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from run_pipeline import paths_for_date

# 파이프라인 5단계가 끝났을 때 항상 남는 핵심 산출물
REQUIRED_ARTIFACTS = (
    "snapshot.json",
    "context.json",
    "eval.json",
    "signal.json",
)
MIN_REPORT_CHARS = 80


def is_complete_run(cfg: dict[str, Any], ticker: str, date_str: str) -> bool:
    """티커·날짜에 대한 end-to-end 실행이 이미 완료됐는지 확인."""
    paths = paths_for_date(cfg, ticker.upper(), date_str, ensure_dirs=False)
    art = paths["artifacts_dir"]
    report_md = paths["report_md"]

    if not art.is_dir():
        return False
    for name in REQUIRED_ARTIFACTS:
        if not (art / name).is_file():
            return False
    if not report_md.is_file():
        return False
    try:
        if len(report_md.read_text(encoding="utf-8").strip()) < MIN_REPORT_CHARS:
            return False
    except OSError:
        return False

    manifest = art / "run_manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("status") != "complete":
                return False
        except (json.JSONDecodeError, OSError):
            pass

    return True
