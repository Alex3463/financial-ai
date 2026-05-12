# 금융 AI 리포트 파이프라인

Yahoo Finance(`yfinance`)로 주식 데이터를 모으고, LLM(기본 **OpenAI Agents SDK** 다중 에이전트)으로 Markdown 리포트를 생성한 뒤, 규칙 기반으로 요약 점수를 매기고 매매 신호 스텁까지 한 번에 실행하는 **소규모 엔드투엔드 파이프라인**입니다.

> 투자 권유가 아닙니다. 생성물은 참고용이며, 실제 거래 전 반드시 원자료와 교차 검증하세요.

---

## 팀 온보딩 · 단일 진입점

**전체 파이프라인의 유일한 실행 진입점은 `scripts/run_pipeline.py` 입니다.**  
`src/` 는 라이브러리 코드이며, 직접 `python src/...` 로 돌리지 않습니다.

| 구분 | 경로 | 역할 |
|------|------|------|
| **메인 진입점** | `scripts/run_pipeline.py` | 수집·뉴스 enrich → 피처·컨텍스트 → 리포트 → 평가 → 신호·CSV 오케스트레이션 |
| 보조 | `scripts/list_gateway_models.py` | 사용 가능 LLM 모델 목록만 조회 (`run_pipeline.py --list-models` 와 동등 목적) |
| 에이전트 가이드 | [AGENTS.md](AGENTS.md) | Codex/자동화 도구용 레포 규칙 요약 |
| Claude Code | [CLAUDE.md](CLAUDE.md) | Claude Code용 동일 계열 안내 |

스켈레톤·데이터 흐름·「무엇을 바꾸면 무엇이 바뀌는지」는 **[docs/ONBOARDING.md](docs/ONBOARDING.md)** 에 정리되어 있습니다. 새 팀원은 해당 문서를 먼저 읽는 것을 권장합니다.

---

## 한 줄 실행

```bash
cd financial-ai
uv sync                              # .venv 생성 + 의존성 설치 (기본 Python 3.12는 .python-version 기준)

uv run python -m pytest -q            # 프로젝트 .venv 기준 단위 테스트
uv run scripts/run_pipeline.py --ticker AAPL
```

> `uv` 가 없다면 [uv 설치 가이드](https://docs.astral.sh/uv/getting-started/installation/)를 참고하세요 (`brew install uv` 또는 `curl -LsSf https://astral.sh/uv/install.sh | sh`).
> `.venv` 를 직접 활성화하고 싶다면 `source .venv/bin/activate` 후 `python scripts/run_pipeline.py …` 도 동일하게 동작합니다.  
> **`uv run` 사용 시** 다른 경로의 `VIRTUAL_ENV`가 켜져 있으면 무시될 수 있으므로, 혼동이 있으면 `deactivate` 후 `uv run`만 쓰는 것을 권장합니다.

### 실행 전제 조건

- **Python 의존성**: `uv sync`가 `pyproject.toml` / `uv.lock` 기준으로 설치합니다. 뉴스 HTML→Markdown 변환에 필요한 `markdownify`, 리포트 agents 경로의 `openai-agents` 등이 포함됩니다.
- **Node.js / `npx`**: 심층 뉴스 읽기(deep-read)는 `Playwright MCP`를 `npx @playwright/mcp@latest`로 실행합니다. **Node.js와 `npx`가 설치**되어 있어야 하며, Cursor 등 GUI 환경에서 PATH에 없을 수 있어 파이프라인이 MCP 기동 시 **`/opt/homebrew/bin`·`/usr/local/bin` 등을 PATH 앞에 보강**합니다. 그래도 실패하면 `npx` 절대 경로를 `config.yaml`의 `mcp.playwright.command`에 지정하세요.
- **`uvx`**: `agents` 모드에서 `yfinance` MCP를 띄울 때 사용합니다. 일반적으로 `uv` 설치 시 같이 제공됩니다. 첫 실행이 느리면 최대 30초까지 기다리고 1회 재시도한 뒤, 실패 시 도구 없이 컨텍스트 기반 리포트로 계속 진행합니다.
- **첫 deep-read 실행**: `npx`가 `@playwright/mcp` 패키지를 내려받을 수 있어야 하므로, 첫 실행은 이후 실행보다 조금 더 오래 걸릴 수 있습니다. 파이프라인은 전역 npm 캐시 충돌을 피하려고 기본적으로 `.playwright-mcp/npm-cache`를 사용합니다.

기본값으로 오늘 날짜(UTC) 폴더에 산출물이 생깁니다.

실행 중 콘솔에는 **`[pipeline]`** 접두사로 단계(1/5~5/5)·주요 분기(`--skip-llm` / LLM agents·legacy)·저장 경로 요약이 출력됩니다.

---

## 평가 점수·등급 (루브릭 / 100점 만점)

이 프로젝트의 평가는 청사진(`project_blueprint.md`)의 9항목 루브릭(총 100점)을 따릅니다.

- **M0 (rules-only)**: 규칙 엔진이 3항목만 채점합니다.
  - `source_transparency` (0–10), `risk_coverage` (0–10), `forecast_verifiability` (0–5) + 페널티(예: 데이터 불일치 -5)
  - 이 모드에서는 `eval.json`에 `rubric_mode: "M0_rules_only"` 로 기록됩니다.
  - `total_score`는 **원점수(대략 0~25 + 페널티)** 이고, `score_normalized_100`는 **25점 만점 기준으로 100점 환산**한 값입니다.
- **M2 (rules + LLM Judge)**: LLM Judge가 나머지 6항목을 채웁니다.
  - `data_accuracy`(0–20), `financial_quality`(0–15), `valuation_soundness`(0–20), `logic_consistency`(0–10), `bias_check`(0–5), `readability`(0–5)
  - `eval.use_llm_judge: true` 또는 실행 시 `--judge` 로 활성화됩니다.
  - 이 모드에서는 `rubric_mode: "M2_full"` 이고, `total_score`가 **100점 스케일(±페널티)** 로 직접 의미를 갖습니다.

콘솔과 `eval.json`의 `grade_note`가 “현재 어떤 모드로 등급을 냈는지”를 설명합니다.

---

## 파이프라인 단계 (콘솔 1/5~5/5와 대응)

| 단계 | 내용 | 산출물(주요) |
|------|------|----------------|
| **1/5** | yfinance 수집 + 뉴스 후보 심층 읽기(Playwright MCP)·digest | `snapshot.json`, `news/*.md`, `news_enrichment.json` |
| **2/5** | 피처·컨텍스트 조립 | `context.json` |
| **3/5** | LLM 리포트 (`llm.mode: agents` 기본, 또는 `legacy`) | `reports/<티커>/<날짜>.md`, agents 시 `artifacts/.../sections/*.json` |
| **4/5** | 규칙 평가(M0) + (선택) LLM Judge(M2) | `eval.json` |
| **5/5** | 신호 스텁·예측 로그 한 줄 | `signal.json`, `tracking/prediction_log.csv` |

---

## 설정 (`config.yaml`)

- **`llm.mode`**: `"agents"`(기본, OpenAI Agents SDK + 도메인 에이전트 + 컴포저) 또는 `"legacy"`(단일 호출·`prompts/report.j2` 계열).
- **`llm.model`**: 사용할 모델 ID (게이트웨이에서 실제 호출 가능한 이름이어야 함).
- **`llm.base_url`**: OpenAI 호환 Chat Completions 베이스 URL.
- **`llm.api_key_env`**: 기본 `OPENAI_API_KEY` (환경변수가 가장 우선).
- **`agents.*`**: 병렬 실행, MCP 도구 사용, 토큰 예산 등.
- **`mcp.playwright`**: deep-read용 `Playwright MCP` 실행 커맨드/timeout 설정. 기본값은 `npx @playwright/mcp@latest --headless --isolated` 계열입니다.
  - `command: "npx"`일 때 npm 다운로드 캐시는 기본적으로 `.playwright-mcp/npm-cache`로 격리됩니다.
  - 다른 캐시를 쓰려면 `mcp.playwright.env.npm_config_cache`를 명시하세요.
- **`mcp.yfinance`**: Agents 리포트 단계의 보강용 `yfinance` MCP 실행 커맨드와 초기화 timeout/retry 설정입니다. 실패해도 파이프라인은 `[pipeline] [경고]`를 남기고 기존 `context.json`만으로 리포트를 생성합니다.
- **키 설정(단일 방식)**: **오직 `.env`로만 설정**합니다. `financial-ai/.env` 또는 `financial-ai/api_guide/.env` 중 하나에 `OPENAI_API_KEY=...` 를 넣으세요.

모델은 키·계정에 따라 일부만 허용될 수 있습니다. 목록은 아래 명령으로 확인하세요.

---

## 자주 쓰는 명령

### 전체 파이프라인

```bash
uv run python -m pytest -q
uv run scripts/run_pipeline.py --ticker AAPL
uv run scripts/run_pipeline.py --ticker 005930.KS --date 2026-05-09
```

### 배치(여러 티커 한 번에)

```bash
# 쉼표 구분
uv run scripts/run_pipeline.py --tickers AAPL,MSFT,GOOG

# 공백 나열도 가능
uv run scripts/run_pipeline.py --ticker AAPL MSFT GOOG

# 파일 기반 (한 줄 1티커, # 주석 가능)
uv run scripts/run_pipeline.py --tickers-file tickers.txt
```

배치 결과는 `artifacts/_batch/<날짜>/batch_summary.json`에 요약 저장되며, 실패가 있으면 `errors.json`이 같이 생성됩니다.

### 사용 가능한 LLM 모델만 조회 (선택용)

```bash
uv run scripts/run_pipeline.py --list-models
# 또는
uv run scripts/list_gateway_models.py
```

결과는 콘솔에 출력되고, `logs/available_models_latest.txt` 및 날짜별 로그에 저장됩니다.

### 옵션 요약

| 옵션 | 설명 |
|------|------|
| `--ticker` | 단일 티커 (배치 모드와 동시 사용 불가) |
| `--tickers` | 쉼표 구분 다종목 배치: `AAPL,MSFT,GOOG` |
| `--tickers-file` | 파일 기반 배치 (한 줄 1티커, `#` 주석 가능) |
| `--date` | 아티팩트 폴더 날짜 `YYYY-MM-DD` (기본: 오늘 UTC) |
| `--skip-llm` | LLM 리포트 생성 생략(스텁). 평가·신호 파이프라인만 점검할 때 사용 |
| `--judge` | 이번 실행만 LLM Judge(M2) 강제 ON (config 무시) |
| `--no-judge` | 이번 실행만 Judge OFF (config의 `eval.use_llm_judge` 무시) |
| `--list-models` | 게이트웨이 모델 목록만 조회 후 종료 |
| `--model-log` | (선택) 실행 시작 시 모델 목록 조회·콘솔·`logs/` 저장 |

환경 변수 **`FINANCIAL_AI_MODEL`** 로 `config.yaml`의 모델을 덮어쓸 수 있습니다.  
환경 변수 **`FINANCIAL_AI_USER_AGENT`** 로 게이트웨이 User-Agent를 조정할 수 있습니다.

---

## 디렉터리 구조 (요약)

```
financial-ai/
├── README.md
├── AGENTS.md            # 코딩 에이전트용 운영 메모
├── CLAUDE.md            # Claude Code용 동일 계열 안내
├── docs/
│   └── ONBOARDING.md    # 스켈레톤·확장 포인트 (팀 온보딩)
├── api_guide/           # .env 템플릿만 제공 (키 파일은 커밋 금지)
├── config.yaml
├── pyproject.toml        # uv 의존성·메타데이터 (단일 출처)
├── uv.lock               # 잠금 파일 (커밋 대상)
├── .python-version       # uv 가 사용할 Python 버전
├── prompts/
│   ├── report.j2
│   └── judge.j2
├── scripts/
│   ├── run_pipeline.py  # ★ 단일 진입점
│   └── list_gateway_models.py
├── src/
│   ├── agents/          # Agents 리포트·MCP·postcheck
│   ├── ingest/yahoo.py
│   ├── news/enrichment.py
│   ├── features/builder.py
│   ├── report/composer.py
│   ├── report/llm.py
│   ├── eval/
│   ├── trading_stub/signal.py
│   └── fio/storage.py   # 표준 라이브러리 io 와 이름 충돌 방지
├── artifacts/      # 실행 시 생성 (git 무시)
├── reports/
├── tracking/
└── logs/
```

자세한 책임 분리는 [docs/ONBOARDING.md](docs/ONBOARDING.md) 문서 3~5절을 참고하세요.

---

## 문제 해결

- **`npx: command not found` / Playwright MCP 실행 실패**
  - Node.js 설치 후 터미널에서 `npx @playwright/mcp@latest --help` 로 확인합니다.
  - 파이프라인은 MCP 기동 시 PATH에 Homebrew 등 일반 경로를 앞에 붙이지만, 여전히 실패하면 `config.yaml`의 `mcp.playwright.command`에 `npx` **절대 경로**를 넣습니다.

- **첫 실행에서 뉴스 심층 읽기가 느림**
  `npx`가 `@playwright/mcp` 패키지를 내려받는 첫 실행일 수 있습니다. 이후 실행은 더 빨라집니다.

- **`npm error ENOTEMPTY ... playwright-core` / `McpError: Connection closed`**
  npm 캐시의 `_npx` 임시 설치 디렉터리가 꼬였을 때 나는 오류입니다. 현재 파이프라인은 Playwright MCP 시작 실패를 `news_enrichment.json`의 실패 항목으로 기록하고 나머지 리포트·평가·신호 단계는 계속 진행합니다. deep-read를 다시 살리고 싶으면 아래 순서로 정리하세요.

  ```bash
  rm -rf .playwright-mcp/npm-cache
  uv run scripts/run_pipeline.py --ticker AAPL --skip-llm
  ```

  예전 실행이 전역 npm 캐시(`~/.npm/_npx/...`)를 쓰던 중 실패했다면 `npm cache verify` 후에도 같은 오류가 날 수 있습니다. 그 경우 `~/.npm/_npx`의 깨진 임시 디렉터리를 지우거나, `config.yaml`의 `mcp.playwright.env.npm_config_cache`를 별도 경로로 지정하세요.

- **`yfinance-... MCP 초기화 실패 - 도구 없이 계속`**
  Agents 리포트 단계의 yfinance MCP가 30초 안에 초기화되지 않거나 `uvx` 실행에 실패한 경우입니다. 이 MCP는 이미 저장된 `context.json`을 보강하는 선택 도구라서, 경고 후 도구 없이 리포트를 계속 생성합니다. 반복되면 `uvx --python 3.12 yfmcp@0.11.1` 실행 가능 여부와 `config.yaml`의 `mcp.yfinance.client_session_timeout_seconds` 값을 확인하세요.

- **배치 중 특정 티커만 `postcheck` 오류**
  Agents 리포트는 `src/agents/postcheck.py`에서 제목·섹션·PER·밸류 산식·출처 등을 검증합니다. 실패 시 `errors.json`에 메시지가 남습니다. 프롬프트·모델 출력이 계약에서 벗어나면 발생할 수 있으며, 로그와 `artifacts/<티커>/<날짜>/sections/` 산출물을 함께 보세요.

- **`403` / `"error code: 1010"`**  
  일부 게이트웨이는 비브라우저 클라이언트를 차단합니다. 이 프로젝트의 `report/llm.py`는 OpenAI SDK 요청에 브라우저형 `User-Agent`를 넣습니다. 필요 시 **`FINANCIAL_AI_USER_AGENT`** 로 변경 가능합니다.

- **`permission_denied - No access to Model '…'`**  
  해당 키로 그 모델을 쓸 권한이 없습니다. `--list-models`로 노출되는 ID 중 하나로 바꾸거나 관리 콘솔에서 권한을 확인하세요.

- **한국 상장 종목**  
  `005930.KS` 형식을 사용합니다. 재무 필드가 비는 경우가 많습니다.

---

## 변경 이력

최신 항목이 위에 오며, [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 스타일에 가깝게 **날짜 → 두괄 요약 → 세부 불릿**으로 정리합니다. 상세 커밋은 `git log` 및 [GitHub 커밋 기록](https://github.com/Alex3463/financial-ai/commits/main)을 참고하세요.

### 2026-05-12

- **런타임·검증 강화**
  - Playwright/yfinance MCP 기동 시 PATH에 `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin` 등을 선행 주입하고, `npx`는 절대 경로 폴백으로 해석해 GUI 터미널에서의 `npx` 미탐지를 완화했습니다.
  - 리포트 계약 검사(`postcheck`): 섹션 헤더·`### 2. 재무 현황` 본문 추출 규칙을 완화하고, 밸류 산식 문자열 비교 시 `×`/`*`·전각 `=`·공백 차이를 흡수해 배치 시 일부 티커만 실패하던 문제를 줄였습니다.
  - Composer 프롬프트에 재무 현황 헤더 스타일 권고 추가, `postcheck` 단위 테스트 보강.
- **ETF 리포트(신규)**
  - `llm.mode: agents`에서 `ETF/FUND/ETN` 등 자산을 감지해 **ETF 전용 헤더/계약(postcheck)** 으로 리포트를 생성합니다.
  - yfinance `funds_data`에서 **Top Holdings, 보수(Expense Ratio), 회전율(Turnover), 총자산(AUM), 섹터/자산군 비중**을 수집해 ETF 리포트(특히 섹션 3)에 활용합니다.
  - 평가(`eval.json`)도 ETF에 맞게 **ETF 전용 M0 루브릭(비용·구성·의사결정 포함)** 으로 분기하고, 리포트에 `투자 의견`(매수/중립/매도) 및 `섹터 기반 전망(3~12개월)`을 포함하도록 강화했습니다.
- **기능·데이터 확장** (동일 날짜 병합 기록)
  - 목표가·손절가·VIX 등 리포트·트래킹 컨텍스트 확장, 테스트 및 리포트 생성 경로 개선.

### 2026-05-11

- **에이전트 파이프라인·운영**
  - Python 3.12·`uv`/`pyproject.toml`/`uv.lock` 기준으로 의존성 고정, `requirements.txt` 제거.
  - OpenAI Agents SDK 기반 다중 에이전트 리포트, `yfinance` MCP(`uvx`)·Playwright MCP 뉴스 심층 읽기, `news/enrichment.py` 및 `src/agents/` 모듈 정비.
  - Playwright MCP 설정·뉴스 enrich 오류 처리·게이트웨이 모델/프롬프트 설정 개선.
  - README·ONBOARDING을 `uv` 워크플로 중심으로 갱신.

### 2026-05-09

- **초기 공개**
  - yfinance 수집 → LLM 리포트 → 규칙·(선택) Judge 평가 → 신호 스텁·CSV 로그까지의 단일 진입점 파이프라인 초기 커밋.

---

## 로드맵 (설계 문서 기준)

- **M0**: 현재 — 규칙만으로 부분 자동 채점.
- **M2**: LLM Judge로 나머지 루브릭 항목(6개) 자동 채점 (`eval.use_llm_judge`, `--judge`).

상세 설계는 저장소 상위의 `project_blueprint.md`, `blue_print_overview.md`를 참고하면 됩니다.
