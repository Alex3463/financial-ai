# 보안 가이드 (웹 공개 시)

Financial AI 대시보드를 **인터넷(`--public`) 또는 LAN(`--lan`)** 에 노출할 때의 위험과 대응을 정리합니다.

> 투자 데모용 프로젝트입니다. **프로덕션 금융 서비스 수준의 보안은 목표가 아닙니다.** 그러나 무인증 공개로 인한 비용·악용은 반드시 막아야 합니다.

---

## 주요 위험 (공개 전 점검)

| 위험 | 설명 | 심각도 |
|------|------|--------|
| **무인증 API** | 누구나 `/api/analyze`로 LLM·MCP 파이프라인 실행 → **API 비용·DoS** | 높음 |
| **경로 조작** | 악의적 `ticker`/`date`로 `artifacts/` 밖 파일 접근 시도 | 높음 |
| **정보 노출** | 방문자 IP·절대 경로·OpenAPI 스키마 노출 | 중간 |
| **동시 실행 남용** | 다수 Job으로 CPU·메모리·외부 API 고갈 | 중간 |
| **`.env` 키 유출** | 서버 침해 시 `OPENAI_API_KEY` 노출 (로컬 프로세스) | 높음 |
| **Playwright MCP** | 뉴스 URL 크롤링 — 악의적 파이프라인 유도 시 **SSRF 성격** (yfinance 뉴스 한정) | 중간 |
| **LAN 바인딩** | `0.0.0.0` — 같은 네트워크 전체에 무인증 노출 | 중간 |
| **임시 터널 URL** | `trycloudflare.com` — URL 유출 시 누구나 접속 | 중간 |

---

## 구현된 방어 (2026-06-08)

### 1. API 토큰 (`--public` 기본)

```bash
uv run scripts/run_dashboard.py --public
# 콘솔에 API 토큰 + ?token=... 포함 공유 URL 출력
```

- `POST /api/analyze` — 공개 모드에서 **토큰 필수**
- UI는 URL `?token=` → `sessionStorage`에 저장 후 `X-Dashboard-Token` 헤더로 전송
- 팀 공유: `https://….trycloudflare.com?token=생성된값`

수동 지정:

```bash
export DASHBOARD_API_TOKEN="your-secret"
uv run scripts/run_dashboard.py --public --token "$DASHBOARD_API_TOKEN"
```

### 2. 속도 제한·동시 실행 제한

| 항목 | 기본값 |
|------|--------|
| IP당 분석 요청 | 시간당 10회 (토큰 있음) / 3회 (토큰 없음 로컬) |
| 동시 파이프라인 Job | 2개 (`DASHBOARD_MAX_CONCURRENT_JOBS`) |

환경 변수: `DASHBOARD_RATE_LIMIT`, `DASHBOARD_RATE_WINDOW_SEC`

### 3. 입력 검증

- **티커**: `^[A-Z0-9][A-Z0-9.\-]{0,19}$` — `..`, `/` 차단
- **날짜**: `YYYY-MM-DD`
- **Job ID**: 12자 hex

### 4. 방문자 정보

- 공개 모드 + 토큰 없음: **접속자 수만** 표시, IP 목록 숨김
- 토큰 있음: IP·UA 상세 (운영자용)

### 5. HTTP 보안 헤더

`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy` 등 (`src/web/security.py`)

### 6. OpenAPI 비활성

`/api/docs` 기본 차단. 필요 시 `DASHBOARD_OPENAPI=true`

### 7. 응답 경로 축소

API 응답의 `paths`에서 디스크 **절대 경로 대신 파일명**만 반환

---

## 공개 모드 옵션

| 옵션 | 용도 |
|------|------|
| `--public` (기본) | 토큰 자동 생성, 분석은 토큰 필요 |
| `--public --demo-open` | 토큰 없이 열람 가능, **LLM 스텁만** 허용, 강한 속도 제한 |
| `--public --token <값>` | 고정 토큰으로 팀 공유 |

---

## 운영 권장 사항

1. **`.env`는 절대 커밋·공유하지 않음** — `OPENAI_API_KEY` 유출 방지
2. **발표 후 터널 종료** — `Ctrl+C` 또는 launchd 중지
3. **데모 종목은 사전 캐시** — 발표 중 무분별한 신규 LLM 호출 최소화
4. **고정 URL 필요 시** — Cloudflare Named Tunnel (Quick Tunnel은 URL 매번 변경)
5. **LAN 모드** — 신뢰할 수 있는 네트워크에서만, 가능하면 토큰 설정
6. **Mac 절전 금지** — Error 1033 = 서비스 중단

---

## 잔여 위험 (수용·추가 대책)

| 항목 | 권장 추가 대책 |
|------|----------------|
| 토큰 URL 유출 | 토큰 주기적 교체, 발표 후 무효화 |
| 읽기 API 무인증 | 민감 데이터 없음 — 데모 산출물만 노출 |
| DDoS | Cloudflare 터널 + rate limit; 상용 WAF는 미포함 |
| 서버 전체 침해 | 데모 전용 계정·키, 발표 후 키 로테이션 |

---

## 관련 코드

- `src/web/security.py` — 검증·rate limit·헤더
- `src/web/app.py` — 엔드포인트 적용
- `scripts/run_dashboard.py` — `--public` 토큰 생성

발표 당일: [DEMO_GUIDE.md](DEMO_GUIDE.md)
