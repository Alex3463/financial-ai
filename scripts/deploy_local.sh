#!/usr/bin/env bash
# 로컬 Mac 서버에 financial-ai 대시보드·의존성을 안전하게 배포합니다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
UID_NUM="$(id -u)"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
PATH_PREFIX="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin"

echo "[deploy] 프로젝트: ${ROOT}"

echo "[deploy] 의존성 동기화 (uv sync)…"
export PATH="${PATH_PREFIX}:${PATH}"
uv sync

echo "[deploy] 단위 테스트 (웹·캐시)…"
uv run python -m pytest tests/test_web_dashboard.py tests/test_web_cache.py -q --tb=no

mkdir -p "${ROOT}/logs" "${LAUNCH_AGENTS}"

_render_plist() {
  local src="$1" dest="$2"
  sed \
    -e "s|__PROJECT_ROOT__|${ROOT}|g" \
    -e "s|__UV_BIN__|$(command -v uv)|g" \
    -e "s|__HOME__|${HOME}|g" \
    "${src}" > "${dest}"
}

echo "[deploy] LaunchAgent plist 설치…"
_render_plist "${ROOT}/launchd/com.financialai.dashboard.plist.template" \
  "${LAUNCH_AGENTS}/com.financialai.dashboard.plist"

if [[ -f "${ROOT}/launchd/com.financialai.daily-pipeline.plist.template" ]]; then
  _render_plist "${ROOT}/launchd/com.financialai.daily-pipeline.plist.template" \
    "${LAUNCH_AGENTS}/com.financialai.daily-pipeline.plist"
fi

_bootout() {
  launchctl bootout "gui/${UID_NUM}" "$1" 2>/dev/null || true
}

_bootstrap() {
  launchctl bootstrap "gui/${UID_NUM}" "$1"
}

echo "[deploy] 기존 대시보드 프로세스 정리…"
_bootout "${LAUNCH_AGENTS}/com.financialai.dashboard.plist"
pkill -f "scripts/run_dashboard.py" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:8765" 2>/dev/null || true
sleep 1

echo "[deploy] 대시보드 서비스 기동 (launchd)…"
_bootstrap "${LAUNCH_AGENTS}/com.financialai.dashboard.plist"

echo "[deploy] 공개 URL 확인 (최대 30초)…"
for _ in $(seq 1 30); do
  if [[ -f "${ROOT}/logs/dashboard.public_url" ]]; then
    echo "[deploy] 공개 URL: $(cat "${ROOT}/logs/dashboard.public_url")"
    break
  fi
  sleep 1
done

if curl -fsS "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
  echo "[deploy] 로컬 헬스체크 OK: http://127.0.0.1:8765/"
else
  echo "[deploy] [경고] 로컬 헬스체크 실패 — logs/dashboard.stderr.log 확인" >&2
fi

echo "[deploy] 완료."
