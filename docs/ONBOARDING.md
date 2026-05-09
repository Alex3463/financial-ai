# 팀 온보딩 — 프로젝트 스켈레톤과 단일 진입점

이 문서는 **레포를 처음 연 개발자가 10~15분 안에 구조를 잡고**, 이후 기능을 **어디를 고치면 되는지** 바로 찾을 수 있게 정리했습니다. 상세 설계는 상위 폴더의 `project_blueprint.md`, `blue_print_overview.md`를 참고합니다.

---

## 1. 단일 진입점 (Single Entry Point)

**프로덕션 플로 전체는 오직 아래 한 줄로 시작합니다.**

```bash
python scripts/run_pipeline.py --ticker <티커>
```

- 모든 단계(수집 → 피처 → 리포트 → 평가 → 신호 → CSV 로그)는 **`scripts/run_pipeline.py`가 순서대로 호출**합니다.
- 콘솔 **`[pipeline]`** 로그로 1/5~5/5 진행·`--skip-llm` vs LLM 분기·저장 경로를 요약합니다.
- `src/` 아래 모듈은 **직접 실행하는 진입점이 아니라**, 파이프라인이 **임포트해서 쓰는 라이브러리**입니다.
- 예외적으로 **보조 도구만** 별도 스크립트가 있습니다 (아래 표).

### 보조 스크립트 (진입점이 아님)

| 스크립트 | 역할 |
|----------|------|
| `scripts/list_gateway_models.py` | 게이트웨이에서 노출 모델 목록만 조회·`logs/` 저장 |
| `run_pipeline.py --list-models` | 위와 동일 목적을 플래그로 처리 |

개발·디버깅 시 **`--skip-llm`** 으로 LLM 없이 나머지 단계만 돌릴 수 있습니다.
- 배치: **`--tickers`** 또는 **`--tickers-file`**
- 배치(공백 나열): **`--ticker AAPL TSLA NVDA`**
- Judge(M2): config의 `eval.use_llm_judge: true` 또는 **`--judge`** / **`--no-judge`**
게이트웨이 모델 목록을 실행 시작마다 보고 싶을 때만 **`--model-log`** 를 붙입니다(기본값은 조회 생략).

---

## 2. 한 장 짜리 데이터 흐름

```
티커 + config.yaml
       │
       ▼
┌──────────────────┐     snapshot.json
│ ingest/yahoo.py  │ ──────────────────────────┐
└──────────────────┘                           │
       │                                       │
       ▼                                       │
┌──────────────────┐     (메모리상 features)    │
│features/builder  │                           │
└──────────────────┘                           │
       │                                       │
       ▼                                       │
┌──────────────────┐     context.json          │
│report/composer   │ ◄── Jinja: prompts/report.j2
└──────────────────┘                           │
       │                                       │
       ▼                                       │
┌──────────────────┐     reports/…/날짜.md       │
│report/llm.py     │ ─────────────────────────► │
└──────────────────┘                           │
       │                                       │
       ▼                                       │
┌──────────────────┐     eval.json             │  원자료 교차검사용
│eval/rules.py     │ ◄── context (valuation 등)──┘
│eval/judge.py      │ (선택, M2) LLM Judge 6항목 채점
│eval/rubric.py     │ (집계) 규칙+Judge → 100점 루브릭
└──────────────────┘
       │
       ▼
┌──────────────────┐     signal.json
│trading_stub/     │
│signal.py         │ ──► tracking/prediction_log.csv
└──────────────────┘
```

- **`fio/storage.py`**: JSON·CSV 읽기/쓰기 유틸 (표준 라이브러리 `io` 와 이름 충돌을 피하기 위해 패키지명 `fio`).

---

## 3. 디렉터리 스켈레톤 (무엇이 소스이고 무엇이 산출물인가)

| 경로 | 성격 | 설명 |
|------|------|------|
| `config.yaml` | 소스 | LLM·수집·평가 스위치. 실행 시 반드시 참조됨. |
| `prompts/` | 소스 | 리포트용 Jinja 템플릿 (`report.j2`) + Judge용 `judge.j2` |
| `scripts/` | 진입점 | 사람이 실행하는 스크립트만 둠. |
| `src/` | 소스 | 도메인 로직 전부. **여기만 수정하면 파이프라인 동작이 바뀜.** |
| `artifacts/` | 산출물 | 티커·날짜별 스냅샷·컨텍스트·평가·신호 JSON. **git 무시 권장.** |
| `reports/` | 산출물 | 최종 Markdown 리포트. |
| `tracking/` | 산출물 | `prediction_log.csv` 누적. |
| `logs/` | 로컬 로그 | 게이트웨이 모델 목록 등. **git 무시.** |

배치 실행(`--tickers`, `--tickers-file`)의 경우 요약이 `artifacts/_batch/<날짜>/batch_summary.json`에 저장되며, 실패가 있으면 `errors.json`이 생성됩니다.

---

## 4. `src/` 모듈 책임 (수정 시 출발점)

| 모듈 | 책임 | 바꾸면 영향이 가는 것 |
|------|------|------------------------|
| `ingest/yahoo.py` | yfinance 수집·스냅샷 스키마 | `snapshot.json` 필드, 이후 전 단계 |
| `features/builder.py` | 수익률·밸류·감성 등 파생 지표 | `context.json` 안의 피처 블록 |
| `report/composer.py` | 컨텍스트 조립·Jinja 렌더·LLM 호출 조립 | 프롬프트 입력 형태·토큰 예산 메시지 |
| `report/llm.py` | OpenAI 호환 클라이언트·API 키 로드·게이트웨이 UA·**모델 목록 조회** | 모든 LLM 호출·WAF 통과 |
| `eval/rules.py` | 정규식·키워드 기반 채점 | `eval.json` 점수·플래그 |
| `eval/rubric.py` | 항목별 null·penalty·총점·등급 문구 | 총점 해석 |
| `eval/judge.py` | (M2) LLM Judge(6항목) | `eval.use_llm_judge` 또는 `--judge` 시 호출 |
| `trading_stub/signal.py` | 리포트 텍스트에서 의견·불릿 추출·신호 JSON | `signal.json` |
| `fio/storage.py` | JSON/CSV 저장 헬퍼 | 저장 형식만 |

---

## 5. “이걸 바꾸고 싶다” 빠른 매핑

| 목표 | 주로 손댈 파일 |
|------|----------------|
| 리포트 문구·섹션·지시사항 | `prompts/report.j2`, `report/composer.py` |
| 다른 LLM/게이트웨이 URL·모델 | `config.yaml`, `report/llm.py`, 환경변수 `FINANCIAL_AI_MODEL` |
| 채점 규칙(출처 비율·리스크 키워드 등) | `eval/rules.py`, 필요 시 `eval/rubric.py` |
| 수집 데이터 필드(재무 항목 추가 등) | `ingest/yahoo.py`, `features/builder.py`, 컨텍스트 필드는 `report/composer.py` |
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
| M1 배치 | `run_pipeline`을 감싸 티커 리스트 루프 + `ingest.sleep_between_tickers` 활용 |
| M2 Judge | `eval/judge.py` + `prompts/judge.j2` + `rubric.aggregate` 연결 (현재 구현됨, 튜닝 가능) |
| M3 트래킹 | `tracking/prediction_log.csv` 후속 필드를 채우는 별도 스크립트 |
| M4 백테스트 | `signal.to_backtest_input()` 계약 고정 + 테스트 |

---

## 8. 체크리스트 (신규 팀원 첫날)

- [ ] `pip install -r requirements.txt` 후 `python scripts/run_pipeline.py --ticker AAPL --skip-llm` 성공
- [ ] `artifacts/`, `reports/` 에 파일 생기는지 확인
- [ ] `config.yaml` 과 `prompts/report.j2` 열어보기
- [ ] `src/report/llm.py` 에서 키·UA·base_url 흐름 한 번 읽기
- [ ] 상위 폴더 `blue_print_overview.md` 와 본 레포 구조 대조

문의·결정이 필요하면 **단일 진입점 동작을 깨지 않는 한** `src/` 와 `prompts/` 만 수정하는 습관을 유지하면 충돌이 적습니다.
