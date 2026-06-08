from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

# Yahoo Finance 티커: 영숫자·점·하이픈 (경로 조작 문자 금지)
TICKER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,19}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
JOB_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def validate_ticker(raw: str) -> str:
    sym = (raw or "").strip().upper()
    if not sym or not TICKER_RE.match(sym):
        raise HTTPException(
            status_code=400,
            detail="유효하지 않은 티커 형식입니다 (영숫자·점·하이픈, 최대 20자).",
        )
    if ".." in sym or "/" in sym or "\\" in sym:
        raise HTTPException(status_code=400, detail="유효하지 않은 티커입니다.")
    return sym


def validate_date(raw: str) -> str:
    d = (raw or "").strip()
    if not DATE_RE.match(d):
        raise HTTPException(
            status_code=400,
            detail="날짜는 YYYY-MM-DD 형식이어야 합니다.",
        )
    return d


def validate_job_id(raw: str) -> str:
    jid = (raw or "").strip().lower()
    if not JOB_ID_RE.match(jid):
        raise HTTPException(status_code=400, detail="유효하지 않은 작업 ID입니다.")
    return jid


def clamp_limit(limit: int, *, default: int = 30, maximum: int = 100) -> int:
    if limit <= 0:
        return default
    return min(limit, maximum)


def safe_path_under(base: Path, *parts: str) -> Path:
    """base 디렉터리 밖으로 나가는 경로 조작을 차단합니다."""
    root = base.resolve()
    target = root.joinpath(*parts).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="허용되지 않은 경로입니다.")
    return target


def is_public_mode() -> bool:
    return os.environ.get("DASHBOARD_MODE", "").strip().lower() == "public"


def auth_token_configured() -> bool:
    return bool(os.environ.get("DASHBOARD_API_TOKEN", "").strip())


def auth_required_for_write() -> bool:
    """공개 모드이거나 DASHBOARD_REQUIRE_AUTH=1 이면 쓰기 API에 토큰 필요."""
    if os.environ.get("DASHBOARD_REQUIRE_AUTH", "").strip().lower() in ("1", "true", "yes"):
        return True
    return is_public_mode() and not demo_open_mode()


def demo_open_mode() -> bool:
    return os.environ.get("DASHBOARD_DEMO_OPEN", "").strip().lower() in ("1", "true", "yes")


def extract_bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-dashboard-token", "").strip()


def verify_request_token(request: Request) -> None:
    if not auth_required_for_write():
        return
    expected = os.environ.get("DASHBOARD_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="서버에 API 토큰이 설정되지 않았습니다. DASHBOARD_API_TOKEN을 설정하세요.",
        )
    got = extract_bearer_token(request)
    if not got or got != expected:
        raise HTTPException(status_code=401, detail="인증이 필요합니다 (API 토큰).")


def visitors_auth_required() -> bool:
    """공개 모드에서는 방문자 IP 목록을 토큰 없이 노출하지 않습니다."""
    return is_public_mode()


def verify_visitors_access(request: Request) -> bool:
    """True = 전체 상세, False = 집계만."""
    if not visitors_auth_required():
        return True
    expected = os.environ.get("DASHBOARD_API_TOKEN", "").strip()
    if not expected:
        return False
    return extract_bearer_token(request) == expected


def is_local_client(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost")


def sanitize_run_paths(payload: dict[str, Any]) -> dict[str, Any]:
    """응답에서 절대 경로 노출을 줄입니다."""
    out = dict(payload)
    paths = out.get("paths")
    if isinstance(paths, dict):
        out["paths"] = {
            k: Path(str(v)).name if k.endswith("_dir") else Path(str(v)).name
            for k, v in paths.items()
        }
    return out


class RateLimiter:
    """IP별 슬라이딩 윈도우 요청 제한."""

    def __init__(self, max_calls: int, window_sec: int) -> None:
        self._max = max_calls
        self._window = window_sec
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self._window:
                q.popleft()
            if len(q) >= self._max:
                raise HTTPException(
                    status_code=429,
                    detail=f"요청 한도 초과 (IP당 {self._window // 60}분에 {self._max}회). 잠시 후 다시 시도하세요.",
                )
            q.append(now)


def analyze_rate_limiter() -> RateLimiter:
    if demo_open_mode():
        max_calls = int(os.environ.get("DASHBOARD_RATE_LIMIT", "2"))
    elif auth_token_configured():
        max_calls = int(os.environ.get("DASHBOARD_RATE_LIMIT", "10"))
    else:
        max_calls = int(os.environ.get("DASHBOARD_RATE_LIMIT", "3"))
    window = int(os.environ.get("DASHBOARD_RATE_WINDOW_SEC", "3600"))
    return RateLimiter(max_calls=max_calls, window_sec=window)


def client_rate_key(request: Request) -> str:
    from web.access_log import client_ip_from_headers

    ip = client_ip_from_headers(
        client_host=request.client.host if request.client else None,
        headers={k.lower(): v for k, v in request.headers.items()},
    )
    return ip or "unknown"


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    ),
}
