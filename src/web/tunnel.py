from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def find_cloudflared() -> str | None:
    for candidate in (
        shutil.which("cloudflared"),
        "/opt/homebrew/bin/cloudflared",
        "/usr/local/bin/cloudflared",
    ):
        if candidate:
            return candidate
    return None


def _poll_log_for_url(log_path: Path, deadline: float) -> str | None:
    seen = ""
    while time.monotonic() < deadline:
        if log_path.is_file():
            text = log_path.read_text(encoding="utf-8", errors="ignore")
            if text != seen:
                seen = text
                match = TUNNEL_URL_RE.search(text)
                if match:
                    return match.group(0)
        time.sleep(0.3)
    return None


def start_quick_tunnel(
    port: int,
    *,
    log_dir: Path | None = None,
    on_url: Callable[[str], None] | None = None,
    timeout_sec: float = 90.0,
) -> tuple[subprocess.Popen[str] | None, str | None]:
    """cloudflared quick tunnel → trycloudflare.com 공개 URL."""
    binary = find_cloudflared()
    if not binary:
        raise FileNotFoundError(
            "cloudflared가 없습니다. macOS: brew install cloudflared"
        )

    base = log_dir or Path(".playwright-mcp")
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / "cloudflared-tunnel.log"
    log_path.write_text("", encoding="utf-8")

    proc = subprocess.Popen(
        [
            binary,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{port}",
            "--logfile",
            str(log_path),
            "--loglevel",
            "info",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    deadline = time.monotonic() + timeout_sec
    public_url = _poll_log_for_url(log_path, deadline)
    if public_url and on_url:
        on_url(public_url)

    return proc, public_url
