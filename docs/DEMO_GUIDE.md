# 발표 당일 데모 가이드

발표·시연 전 **체크리스트**, 실행 방법, 탭별 시연 포인트, 자주 나는 오류 대응을 정리했습니다.

---

## 발표 전 체크리스트 (D-1 ~ 당일 30분 전)

### 환경

- [ ] `cd financial-ai` 후 `uv sync` 완료
- [ ] `.env` 또는 `api_guide/.env`에 `OPENAI_API_KEY` 설정
- [ ] `uv run python -m pytest -q` 통과 (최소 `tests/test_web_*.py`)
- [ ] Node.js + `npx` 동작 확인 (`which npx`)
- [ ] (공개 URL 사용 시) `brew install cloudflared` 설치
- [ ] (선택) `config.yaml`의 `llm.model`이 키로 호출 가능한지 `--list-models`로 확인

### 사전 실행으로 캐시 준비 (권장)

발표 중 LLM 대기를 줄이려면 **미리 1~2종목**을 돌려 둡니다.

```bash
cd financial-ai
uv run scripts/run_pipeline.py --ticker AAPL
uv run scripts/run_pipeline.py --ticker 005930.KS
```

→ `artifacts/AAPL/<오늘날짜>/`, `reports/AAPL/<오늘날짜>.md` 생성 확인

### 네트워크·전원

- [ ] 발표 노트북 **절전 모드 해제** (터널·서버 끊김 방지)
- [ ] Wi‑Fi 안정성 확인 (deep-read·LLM 호출)
- [ ] 공개 URL은 **서버가 켜져 있는 동안만** 유효함을 팀에 공지

---

## 실행 방법

### A. CLI 데모 (터미널 중심)

```bash
cd financial-ai
uv run scripts/run_pipeline.py --ticker AAPL
```

**시연 포인트**: 콘솔 `[pipeline] 1/5 ~ 5/5` 진행, 뉴스 deep-read 성공/실패 줄, `eval.json` 점수 한 줄

**빠른 데모** (LLM 생략):

```bash
uv run scripts/run_pipeline.py --ticker AAPL --skip-llm
```

**Judge 포함** (M2 full):

```bash
uv run scripts/run_pipeline.py --ticker AAPL --judge
```

산출물 확인:

```bash
ls artifacts/AAPL/$(date -u +%Y-%m-%d)/
cat reports/AAPL/$(date -u +%Y-%m-%d).md | head -40
```

### B. 웹 대시보드 (발표 권장)

**로컬만**:

```bash
uv run scripts/run_dashboard.py
# → http://127.0.0.1:8765/
```

**인터넷 공개** (청중·팀원 원격 접속):

```bash
uv run scripts/run_dashboard.py --public
```

콘솔에 **API 토큰**과 `?token=...` 이 포함된 공유 URL이 출력됩니다:

```
https://xxxx-yyyy-zzzz.trycloudflare.com?token=...
```

- 팀원에게는 **토큰 포함 URL**을 공유해야 **리포트 생성** 버튼이 동작합니다.
- 조회·캐시된 리포트 열람은 토큰 없이도 가능합니다.
- 보안 상세: [SECURITY.md](SECURITY.md)

동일 URL은 `logs/dashboard.public_url`에도 저장됩니다.

**장시간 켜 두기** (터미널 닫아도 유지):

```bash
chmod +x scripts/deploy_local.sh
./scripts/deploy_local.sh
# 공개 URL: logs/dashboard.public_url
```

중지:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.financialai.dashboard.plist
```

---

## 탭별 시연 시나리오 (약 5~8분)

### 1. 사이드바 — 분석 실행

1. 티커 입력: `AAPL` (또는 `005930.KS`)
2. **캐시가 있으면** 즉시 로드 → 「캐시」 배지 설명
3. **새 분석**이 필요하면 「캐시 무시」 체크 후 실행
4. 진행 로그에 `1/5 ~ 5/5` 메시지가 쌓이는 것을 보여줌

**옵션 설명**:

| 체크박스 | 용도 |
|----------|------|
| LLM 생략 | 스텁 리포트, 1분 내 파이프라인 구조만 시연 |
| LLM Judge 끄기 (기본 체크) | M0 규칙만, Judge API 호출 생략 |
| Judge 강제 켜기 | M2 full 100점 루브릭 |
| 강제 재생성 | 캐시 무시 |

### 2. 요약 탭

- 투자 의견(매수/중립/매도), 현재가·목표가·손절가
- 시스템 신호 배지, 신뢰도, 품질 등급·점수
- 핵심 근거·리스크 트리거 불릿

**한 줄 멘트**: 「LLM 리포트를 파싱해 의사결정에 필요한 숫자만 카드로 올렸습니다.」

### 3. 리포트 탭

- 6섹션 구조화 카드 (투자 요약 표, 재무·성장·리스크·밸류·결론)
- Agents 모드의 **도메인 에이전트 → 컴포저** 결과물

### 4. 뉴스 탭

- **FinBERT 종합 감성** 히어로 (긍정/부정/중립, 평균 점수)
- Playwright deep-read로 읽은 기사 요약
- 기사별 **감성 배지** + 긍정/중립/부정 **확률 바**
- 원문 링크 — 「헤드라인만이 아니라 본문 기반」 강조

### 5. 상세 데이터 탭

- **주가 캔들 차트** (3M/6M/12M), 목표가·손절 참고선
- 평가 breakdown 아코디언 (루브릭 항목별 점수)
- 원본 JSON (snapshot / context / signal) — 기술 질문 대비

### 6. 부가 UI

- **접속 현황**: 공개 URL로 팀원이 들어오면 active IP 수 증가 (근사)
- **최근 실행**: 과거 `artifacts/` 즉시 재로드
- **URL 해시**: `#AAPL/2026-06-08` 복사 → 특정 결과 공유

---

## 발표 스크립트 제안 (3분 버전)

1. **문제** (30초): 종목 리서치는 데이터·뉴스·서술·품질 검증이 분산되어 있다.
2. **해결** (30초): 5단계 파이프라인 + 다중 에이전트 + 자동 루브릭.
3. **라이브** (90초): 대시보드에서 `AAPL` 로드(캐시) → 요약·리포트·뉴스·차트 순으로 클릭.
4. **아키텍처** (30초): `ARCHITECTURE.md` 다이어그램 1장 — ingest → context → agents → eval → signal.
5. **면책** (10초): 투자 권유 아님, 데모·참고용.

---

## 트러블슈팅

### Error 1033 (Cloudflare)

**증상**: 공개 URL 접속 시 Cloudflare Error 1033

**원인**: `run_dashboard.py --public` 또는 launchd 서비스가 **꺼짐** (Ctrl+C, Mac 절전, 재부팅)

**해결**:

```bash
uv run scripts/run_dashboard.py --public
# 또는
./scripts/deploy_local.sh
```

→ **새 URL**을 팀에 다시 공유 (`logs/dashboard.public_url`)

### 공개 URL이 바뀜

`trycloudflare.com` quick tunnel은 **재시작마다 URL이 변경**됩니다.

- 항상 **최신** `logs/dashboard.public_url` 또는 콘솔 출력만 공유
- UI 헤더 「공개 링크」도 `/api/info`의 `public_url` 기준

### `npx: command not found` / deep-read 전부 실패

```bash
brew install node
which npx   # /opt/homebrew/bin/npx 등
```

`config.yaml` → `mcp.playwright.command`를 절대 경로로 지정

실패해도 파이프라인은 계속 — `news_enrichment.json`의 `failures[]` 확인

### LLM 403 / permission_denied

```bash
uv run scripts/run_pipeline.py --list-models
```

→ 노출된 모델 ID로 `config.yaml`의 `llm.model` 변경

### yfinance MCP 경고

`[pipeline] [경고] … MCP 초기화 실패 - 도구 없이 계속`

→ 선택 도구 실패, **리포트는 context만으로 생성됨**. 발표에는 영향 적음.

### 캐시 때문에 「새 결과」가 안 나옴

- UI에서 **「강제 재생성 (캐시 무시)」** 체크
- 또는 `artifacts/<티커>/<날짜>/` 폴더 삭제 후 재실행

### 포트 충돌 (8765)

```bash
uv run scripts/run_dashboard.py --port 8766
```

`--public` 시 cloudflared도 동일 포트를 가리켜야 함 (기본 8765 권장)

### 한국 종목 데이터 부족

`005930.KS` 사용, 일부 재무 필드 비어 있을 수 있음 → 리포트·eval에서 N/A 설명

---

## 발표 당일 타임라인 예시

| 시각 | 작업 |
|------|------|
| T-30분 | `uv sync`, API 키 확인, 사전 캐시 티커 2개 확인 |
| T-15분 | `./scripts/deploy_local.sh` 또는 `--public` 기동 |
| T-10분 | 공개 URL 팀 채팅에 공유, 본인 브라우저에서 `#AAPL/날짜` 로드 테스트 |
| T-0 | 발표 시작 — 요약 탭부터 |
| T+발표 | 서비스 중지 여부는 팀 정책에 따름 |

---

## 관련 문서

- [ARCHITECTURE.md](ARCHITECTURE.md) — 구조·다이어그램
- [FEATURES.md](FEATURES.md) — 기능 상세
- [../README.md](../README.md) — 전체 명령·옵션 참조
