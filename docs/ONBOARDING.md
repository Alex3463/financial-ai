# 팀 온보딩 — 프로젝트 스켈레톤과 단일 진입점

이 문서는 **레포를 처음 연 개발자가 10~15분 안에 구조를 잡고**, 이후 기능을 **어디를 고치면 되는지** 바로 찾을 수 있게 정리했습니다. 사용자 관점 요약은 **[README.md](../README.md)**, 날짜별 변경 요약은 README의 **「변경 이력」** 을 참고하세요. 상세 설계는 상위 폴더의 `project_blueprint.md`, `blue_print_overview.md`를 참고합니다.

---

## 1. 단일 진입점 (Single Entry Point)

**프로덕션 플로 전체는 오직 아래 한 줄로 시작합니다.**

```bash
uv run scripts/run_pipeline.py --ticker <티커>
```

> 첫 실행 전에는 `uv sync` 한 번이면 의존성·`.venv`·Python(3.12)이 모두 준비됩니다.

- 콘솔 **`[pipeline]`** 로그로 **1/5~5/5** 진행·`--skip-llm` vs LLM·**`agents` vs `legacy`** 분기·저장 경로를 요약합니다.
  - **1/5**: `ingest` + **`news/enrichment`** (Playwright MCP deep-read, 실패 시에도 이후 단계 계속).
  - **2/5**: `features/builder` + **`report/composer.ContextBuilder`** → `context.json`.
  - **3/5**: `config.yaml`의 **`llm.mode`** — 기본 **`agents`** (`src/agents/orchestrator.py` → 도메인 에이전트 → 컴포저 → **`postcheck`**) 또는 **`legacy`** (`compose_markdown_report` + `prompts/report.j2` + `report/llm.py`).
  - **4/5**: `eval/rules` + (선택) `eval/judge` → `eval.json`.
  - **5/5**: `trading_stub/signal` + `tracking/prediction_log.csv`.
- `src/` 아래 모듈은 **직접 실행하는 진입점이 아니라**, 파이프라인이 **임포트해서 쓰는 라이브러리**입니다.
- 코딩 에이전트용 운영 메모: 루트 **[AGENTS.md](../AGENTS.md)** (Codex 계열), **[CLAUDE.md](../CLAUDE.md)** (Claude Code). 내용이 겹치므로 **하나만 정독**해도 됩니다.

뉴스 deep-read는 `npx @playwright/mcp@latest`로 Playwright MCP를 실행합니다. GUI 터미널 등에서 `PATH`에 Homebrew가 없을 수 있어, MCP 기동 시 **`/opt/homebrew/bin`·`/usr/local/bin`·`~/.local/bin`** 을 PATH 앞에 붙이고 `npx` 절대 경로 폴백을 시도합니다(`src/agents/mcp_servers.py`). 첫 실행에서는 패키지 다운로드 때문에 시간이 걸릴 수 있고, npm 캐시는 전역 `~/.npm/_npx` 대신 레포 로컬 **`.playwright-mcp/npm-cache`** 를 기본으로 씁니다. MCP 시작이 실패해도 파이프라인은 `news_enrichment.json`에 실패 사유를 남기고 리포트·평가·신호 단계로 계속 진행합니다.

**`uv run` 사용 시** 다른 경로의 `VIRTUAL_ENV`가 활성화되어 있으면 무시될 수 있습니다. 경고가 나오면 `deactivate` 후 `uv run`만 사용하는 것이 안전합니다.

Agents 리포트 단계의 **yfinance MCP**(`uvx`)도 보강용 도구라서, 초기화 timeout/retry 이후 실패하면 `[pipeline] [경고]`를 남기고 기존 `context.json`만으로 계속 실행합니다.

### 보조 스크립트 (진입점이 아님)

| 스크립트 | 역할 |
|----------|------|
| `scripts/list_gateway_models.py` | 게이트웨이에서 노출 모델 목록만 조회·`logs/` 저장 |
| `run_pipeline.py --list-models` | 위와 동일 목적을 플래그로 처리 |

개발·디버깅 시 **`--skip-llm`** 으로 LLM 없이 나머지 단계만 돌릴 수 있습니다.

- 단위 테스트는 **`uv run python -m pytest -q`** 로 실행합니다. `pyproject.toml`의 dev dependency group에 고정된 프로젝트 `.venv`의 pytest를 사용합니다.
- 배치: **`--tickers`** / **`--tickers-file`** / **`--ticker AAPL TSLA NVDA`** (공백 나열).
- Judge(M2): `eval.use_llm_judge: true` 또는 **`--judge`** / **`--no-judge`**.
- 게이트웨이 모델 목록을 실행 시작마다 보고 싶을 때만 **`--model-log`** (기본은 조회 생략).

---

## 2. 한 장 짜리 데이터 흐름

```
티커 + config.yaml
       │
       ▼
┌──────────────────┐     snapshot.json
│ ingest/yahoo.py  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     news/*.md, news_enrichment.json
│ news/enrichment   │     (Playwright MCP; 실패 시 failures[] 기록)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     (메모리 features)
│features/builder  │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────┐     context.json
│ report/composer.py       │     ContextBuilder.build(...)
│ (ContextBuilder)         │
└────────┬─────────────────┘
         │
         ├──────────────────────────────┐
         ▼                              ▼
┌────────────────────┐        ┌─────────────────────────────┐
│ llm.mode: legacy   │        │ llm.mode: agents (기본)      │
│ composer +         │        │ agents/orchestrator.py      │
│ prompts/report.j2  │        │ → slices, domain agents,    │
│ report/llm.py      │        │ composer_agent, postcheck   │
└────────┬───────────┘        │ → reports/…/날짜.md           │
         │                    │ → artifacts/…/sections/*.json│
         │                    └──────────────┬──────────────┘
         │                                   │
         └───────────────┬───────────────────┘
                         ▼
                reports/<티커>/<날짜>.md
                         │
                         ▼
┌──────────────────┐     eval.json        ◄── context 등 원자료 교차검사용
│ eval/rules.py    │
│ eval/judge.py    │     (선택 M2)
│ eval/rubric.py   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     signal.json
│ trading_stub/    │ ──► tracking/prediction_log.csv
│ signal.py        │
└──────────────────┘
```

- **`fio/storage.py`**: JSON·CSV 읽기/쓰기 유틸 (표준 라이브러리 `io` 와 이름 충돌을 피하기 위해 패키지명 `fio`).

---

## 3. 디렉터리 스켈레톤 (무엇이 소스이고 무엇이 산출물인가)

| 경로 | 성격 | 설명 |
|------|------|------|
| `config.yaml` | 소스 | LLM·`llm.mode`·agents·MCP·수집·평가 스위치. 실행 시 반드시 참조됨. |
| `prompts/` | 소스 | **legacy** 리포트용 Jinja `report.j2` + Judge용 `judge.j2` |
| `src/agents/prompts/` | 소스 | **agents** 모드용 마크다운 지시문(컴포저·도메인 에이전트) |
| `AGENTS.md`, `CLAUDE.md` | 소스 | 사람이 아닌 코딩 에이전트용 짧은 운영 규칙 |
| `scripts/` | 진입점 | 사람이 실행하는 스크립트만 둠. |
| `src/` | 소스 | 도메인 로직 전부. **여기만 수정하면 파이프라인 동작이 바뀜.** |
| `artifacts/` | 산출물 | 티커·날짜별 스냅샷·뉴스·컨텍스트·평가·신호 JSON, agents 시 `sections/`. **git 무시 권장.** |
| `reports/` | 산출물 | 최종 Markdown 리포트. |
| `tracking/` | 산출물 | `prediction_log.csv` 누적. |
| `logs/` | 로컬 로그 | 게이트웨이 모델 목록 등. **git 무시.** |

배치 실행(`--tickers`, `--tickers-file`)의 경우 요약이 `artifacts/_batch/<날짜>/batch_summary.json`에 저장되며, 실패가 있으면 **`errors.json`** 이 생성됩니다. Agents 리포트가 **`postcheck`** 에서 거절되면 해당 티커가 배치 실패로 기록됩니다.

---

## 4. `src/` 모듈 책임 (수정 시 출발점)

| 모듈 | 책임 | 바꾸면 영향이 가는 것 |
|------|------|------------------------|
| `ingest/yahoo.py` | yfinance 수집·스냅샷 스키마 | `snapshot.json` 필드, 이후 전 단계 |
| `news/enrichment.py` | 뉴스 후보 선정·Playwright MCP deep-read·digest | `news_enrichment.json`, `context.json`의 뉴스 블록 |
| `features/builder.py` | 수익률·밸류·VIX·기술·거래량 등 파생 지표 | `context.json` 안의 피처 블록 |
| `report/composer.py` | **ContextBuilder**: 컨텍스트 조립·토큰 예산 메시지 | `context.json` 형태 |
| `agents/orchestrator.py` | agents 리포트 오케스트레이션·섹션 아티팩트 기록 | `reports/*.md`, `artifacts/.../sections/` |
| `agents/*_agent.py`, `composer_agent.py` | 도메인별·최종 합성 리포트 생성 | 리포트 문장·구조 |
| `agents/postcheck.py` | 최종 Markdown 계약 검증(PER·산식·섹션 등) | 검증 실패 시 파이프라인 예외·배치 `errors.json` |
| `agents/mcp_servers.py` | Playwright / yfinance MCP stdio 서버 생성·PATH | deep-read·도구 보강 성공률 |
| `report/llm.py` | OpenAI 호환 클라이언트·키·UA·**모델 목록 조회** | **legacy** 리포트·Judge·(agents SDK 설정과 병행) |
| `eval/rules.py` | 정규식·키워드 기반 채점 | `eval.json` 점수·플래그 |
| `eval/rubric.py` | 항목별 null·penalty·총점·등급 문구 | 총점 해석 |
| `eval/judge.py` | (M2) LLM Judge(6항목) | `eval.use_llm_judge` 또는 `--judge` 시 호출 |
| `trading_stub/signal.py` | 리포트 텍스트에서 의견·불릿 추출·신호 JSON | `signal.json` |
| `fio/storage.py` | JSON/CSV 저장 헬퍼 | 저장 형식만 |

**legacy 전용**: `prompts/report.j2` + `compose_markdown_report` 경로는 `run_pipeline.py`에서 `llm.mode != "agents"` 일 때 사용됩니다.

---

## 5. “이걸 바꾸고 싶다” 빠른 매핑

| 목표 | 주로 손댈 파일 |
|------|----------------|
| **agents** 리포트 톤·섹션·지시문 | `src/agents/prompts/*.md`, `composer_agent.py`, `agents/orchestrator.py` |
| **legacy** 리포트 문구·섹션 | `prompts/report.j2`, `report/composer.py` (`compose_markdown_report`) |
| 리포트 검증 규칙(섹션·PER·산식 등) | `agents/postcheck.py`, `tests/test_postcheck.py` |
| 다른 LLM/게이트웨이 URL·모델 | `config.yaml`, `report/llm.py`, 환경변수 `FINANCIAL_AI_MODEL` |
| 채점 규칙(출처 비율·리스크 키워드 등) | `eval/rules.py`, 필요 시 `eval/rubric.py` |
| 수집 데이터 필드(재무 항목 추가 등) | `ingest/yahoo.py`, `features/builder.py`, 컨텍스트 필드는 `report/composer.py` |
| 뉴스 deep-read·MCP | `news/enrichment.py`, `agents/mcp_servers.py`, `config.yaml`의 `mcp.*` |
| 신호 산출 규칙 | `trading_stub/signal.py` |
| CSV 컬럼·로그 스키마 | `scripts/run_pipeline.py` 내 `row` / `fieldnames`, `fio/storage.py` |

---

## 6. 설정·환경 변수 읽는 순서 (혼동 방지)

1. 셸 환경 변수 (`OPENAI_API_KEY`, `FINANCIAL_AI_MODEL`, `FINANCIAL_AI_USER_AGENT` 등)
2. 스크립트 시작 시 `scripts/run_pipeline.py` 가 `.env` 를 로드 (`financial-ai/.env`, `financial-ai/api_guide/.env` 등)

**팀 규칙 제안**: 공유 저장소에는 키 파일을 넣지 말고, README 수준에서 “로컬 경로 + 환경변수”만 문서화합니다.

---

## 7. 이후 디벨롭을 위한 마일스톤 힌트

| 단계 | 방향 |
|------|------|
| M1 배치 | 이미 `run_pipeline.py`에 티커 루프·`ingest.sleep_between_tickers` 지원. 요약·오류는 `artifacts/_batch/<날짜>/`. |
| M2 Judge | `eval/judge.py` + `prompts/judge.j2` + `rubric.aggregate` (구현됨, 튜닝 가능) |
| M3 트래킹 | `tracking/prediction_log.csv` 후속 필드를 채우는 별도 스크립트 |
| M4 백테스트 | `signal.to_backtest_input()` 계약 고정 + 테스트 |

---

## 8. 체크리스트 (신규 팀원 첫날)

- [ ] `uv sync` 후 `uv run python -m pytest -q` 성공
- [ ] `uv run scripts/run_pipeline.py --ticker AAPL --skip-llm` 성공
- [ ] `artifacts/`, `reports/` 에 파일 생기는지 확인
- [ ] deep-read 실패가 있으면 `artifacts/<티커>/<날짜>/news_enrichment.json`의 `failures[].error` 확인 (`npx`·npm 캐시 등)
- [ ] Agents 리포트 중 yfinance MCP 경고가 보이면 `config.yaml`의 `mcp.yfinance` timeout/retry와 `uvx` 실행 가능 여부 확인
- [ ] 배치 실패 시 `artifacts/_batch/<날짜>/errors.json` 과 해당 티커의 `sections/`·리포트 초안 흔적 확인
- [ ] `config.yaml` 에서 `llm.mode`, `agents.*`, `mcp.*` 열어보기
- [ ] **agents** 경로: `src/agents/orchestrator.py`, `postcheck.py` 흐름 한 번 읽기
- [ ] **legacy** 경로: `prompts/report.j2`, `report/composer.py` 의 `compose_markdown_report` 연결 확인
- [ ] `src/report/llm.py` 에서 키·UA·base_url 흐름 한 번 읽기
- [ ] 상위 폴더 `blue_print_overview.md` 와 본 레포 구조 대조

문의·결정이 필요하면 **단일 진입점 동작을 깨지 않는 한** `src/`·`prompts/`·`src/agents/` 만 수정하는 습관을 유지하면 충돌이 적습니다.
