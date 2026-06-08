from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

ACTIVE_WINDOW_SEC = 300  # 5분 이내 요청 = 접속 중
MAX_EVENTS = 200


@dataclass
class AccessEvent:
    at: float
    ip: str
    path: str
    method: str
    user_agent: str


@dataclass
class VisitorStore:
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _events: deque[AccessEvent] = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))
    _last_seen: dict[str, AccessEvent] = field(default_factory=dict)

    def record(
        self,
        *,
        ip: str,
        path: str,
        method: str,
        user_agent: str,
    ) -> None:
        now = time.time()
        ev = AccessEvent(
            at=now,
            ip=ip or "unknown",
            path=path,
            method=method,
            user_agent=(user_agent or "")[:160],
        )
        with self._lock:
            self._events.appendleft(ev)
            key = ip or "unknown"
            self._last_seen[key] = ev

    def snapshot(self, *, active_window_sec: int = ACTIVE_WINDOW_SEC) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            events = list(self._events)
            last_seen = dict(self._last_seen)

        active = []
        for ip, ev in last_seen.items():
            if now - ev.at <= active_window_sec:
                active.append(
                    {
                        "ip": ip,
                        "last_seen_at": _iso(ev.at),
                        "seconds_ago": int(now - ev.at),
                        "last_path": ev.path,
                        "user_agent": _short_ua(ev.user_agent),
                    }
                )
        active.sort(key=lambda x: x["seconds_ago"])

        recent = [
            {
                "at": _iso(e.at),
                "ip": e.ip,
                "method": e.method,
                "path": e.path,
                "user_agent": _short_ua(e.user_agent),
            }
            for e in events[:40]
        ]

        return {
            "active_count": len(active),
            "active_window_sec": active_window_sec,
            "active": active,
            "recent": recent,
        }


def _iso(ts: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_ua(ua: str) -> str:
    if not ua:
        return "—"
    if "Chrome" in ua:
        return "Chrome"
    if "Safari" in ua and "Chrome" not in ua:
        return "Safari"
    if "Firefox" in ua:
        return "Firefox"
    if "curl" in ua.lower():
        return "curl"
    return ua[:48] + ("…" if len(ua) > 48 else "")


def client_ip_from_headers(
    *,
    client_host: str | None,
    headers: dict[str, str],
) -> str:
    for key in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        val = headers.get(key) or headers.get(key.upper())
        if val:
            return val.split(",")[0].strip()
    return client_host or "unknown"


visitors = VisitorStore()
