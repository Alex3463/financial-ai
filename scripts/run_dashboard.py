#!/usr/bin/env python3
"""Financial AI 데모 대시보드 웹서버."""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _run_uvicorn(host: str, port: int, reload: bool) -> None:
    import uvicorn

    uvicorn.run(
        "web.app:app",
        host=host,
        port=port,
        reload=reload,
        app_dir=str(SRC),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Financial AI 탭형 데모 대시보드")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="바인드 호스트 (공개 터널 시 127.0.0.1 유지, LAN은 0.0.0.0)",
    )
    parser.add_argument("--port", type=int, default=8765, help="포트 (기본: 8765)")
    parser.add_argument("--reload", action="store_true", help="개발용 자동 리로드")
    parser.add_argument(
        "--public",
        action="store_true",
        help="cloudflared quick tunnel로 인터넷 공개 URL 생성 (brew install cloudflared)",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        help="같은 Wi‑Fi/LAN에서 접속 가능하도록 0.0.0.0에 바인드",
    )
    parser.add_argument(
        "--token",
        default="",
        help="API 인증 토큰 (미지정 시 --public 에서 자동 생성)",
    )
    parser.add_argument(
        "--demo-open",
        action="store_true",
        help="공개 모드에서 토큰 없이 열기 (LLM 스텁만 허용, 속도 제한 강화)",
    )
    args = parser.parse_args()

    if args.token:
        os.environ["DASHBOARD_API_TOKEN"] = args.token.strip()
    if args.demo_open:
        os.environ["DASHBOARD_DEMO_OPEN"] = "true"

    host = "0.0.0.0" if args.lan else args.host
    port = args.port
    local_url = f"http://127.0.0.1:{port}/"

    if args.public:
        from web.tunnel import find_cloudflared, start_quick_tunnel

        if not find_cloudflared():
            print("cloudflared가 필요합니다: brew install cloudflared")
            sys.exit(1)

        os.environ.setdefault("DASHBOARD_MODE", "public")
        if not args.demo_open and not os.environ.get("DASHBOARD_API_TOKEN"):
            auto_token = secrets.token_urlsafe(18)
            os.environ["DASHBOARD_API_TOKEN"] = auto_token
            print(f"[보안] API 토큰 자동 생성 (분석 실행·방문자 상세용): {auto_token}", flush=True)
            print("[보안] 공유 URL에 ?token=... 를 붙여 팀원에게 전달하세요.", flush=True)

        server = threading.Thread(
            target=_run_uvicorn,
            kwargs={"host": "127.0.0.1", "port": port, "reload": False},
            daemon=True,
        )
        server.start()

        # uvicorn 기동 대기
        import urllib.error
        import urllib.request

        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            print("서버가 시작되지 않았습니다.")
            sys.exit(1)

        tunnel_proc: subprocess.Popen[str] | None = None

        def on_url(url: str) -> None:
            os.environ["DASHBOARD_PUBLIC_URL"] = url
            token = os.environ.get("DASHBOARD_API_TOKEN", "").strip()
            share_url = f"{url}?token={token}" if token else url
            url_file = ROOT / "logs" / "dashboard.public_url"
            url_file.parent.mkdir(parents=True, exist_ok=True)
            url_file.write_text(share_url + "\n", encoding="utf-8")
            print("\n" + "=" * 60, flush=True)
            print("공개 URL (누구나 접속 가능):", flush=True)
            print(f"  {share_url}", flush=True)
            print("=" * 60, flush=True)
            print(f"로컬: {local_url}", flush=True)
            print("종료: Ctrl+C\n", flush=True)

        print("cloudflared 터널 연결 중…", flush=True)
        try:
            tunnel_proc, public_url = start_quick_tunnel(
                port,
                log_dir=ROOT / ".playwright-mcp",
                on_url=on_url,
            )
            if not public_url:
                print("공개 URL을 가져오지 못했습니다. cloudflared 로그를 확인하세요.")
                sys.exit(1)
            os.environ["DASHBOARD_PUBLIC_URL"] = public_url

            while True:
                time.sleep(1)
                if tunnel_proc.poll() is not None:
                    print("cloudflared 터널이 종료되었습니다.")
                    break
        except KeyboardInterrupt:
            pass
        finally:
            if tunnel_proc and tunnel_proc.poll() is None:
                tunnel_proc.terminate()
        return

    print(f"대시보드: http://{host}:{port}/")
    if host == "0.0.0.0":
        print("LAN: 같은 네트워크 기기에서 위 주소로 접속 (본机 IP:8765)")
    print("공개 URL: --public 옵션 사용 (cloudflared 필요)")
    print("종료: Ctrl+C")
    _run_uvicorn(host=host, port=port, reload=args.reload)


if __name__ == "__main__":
    main()
