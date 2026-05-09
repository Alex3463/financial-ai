from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Mindlogic 게이트웨이 앞단(WAF)이 비브라우저 User-Agent 를 차단하는 경우가 있어,
# OpenAI SDK 요청에 브라우저 UA 를 넣습니다. (문서: Mindlogic API Gateway)
_GATEWAY_BROWSER_UA = os.environ.get(
    "FINANCIAL_AI_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)


def load_optional_api_key_file(path: Path | None) -> str | None:
    if not path or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"YOUR_API_KEY\s*=\s*['\"]([^'\"]+)['\"]", text)
    if m and m.group(1) not in ("YOUR_API_KEY", ""):
        return m.group(1).strip()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            k = key.strip().upper()
            if k in ("OPENAI_API_KEY", "API_KEY", "YOUR_API_KEY"):
                v = val.strip().strip('"').strip("'")
                if v and v != "YOUR_API_KEY":
                    return v
        m = re.search(r'api_key\s*=\s*["\']([^"\']+)["\']', line)
        if m and m.group(1) != "YOUR_API_KEY":
            return m.group(1).strip()
    return None


def fetch_gateway_models(config: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """
    OpenAI 호환 게이트웨이의 GET /models/ 결과를 반환합니다.
    성공 시 (목록, None), 실패 시 ([], 에러메시지).
    """
    try:
        prov = LLMProvider(config)
    except RuntimeError as e:
        return [], str(e)
    base = (prov.base_url or "").rstrip("/")
    if not base:
        return [], "config.yaml의 llm.base_url이 비어 있습니다."

    url = base + "/models/"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {prov.api_key}",
            "User-Agent": _GATEWAY_BROWSER_UA,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:800]
        return [], f"HTTP {e.code}: {body}"
    except Exception as e:
        return [], str(e)

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return [], "응답에 data 배열이 없습니다."

    out: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not mid:
            continue
        out.append(
            {
                "id": mid,
                "owned_by": item.get("owned_by") or "",
                "created": item.get("created"),
            }
        )
    return out, None


def format_gateway_models_log(config: dict[str, Any], models: list[dict[str, Any]], error: str | None) -> str:
    """사람이 읽기 쉬운 텍스트 한 덩어리 (파일 저장·콘솔 출력용)."""
    llm = config.get("llm", {})
    configured = os.environ.get("FINANCIAL_AI_MODEL") or llm.get("model", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        f"# 게이트웨이 사용 가능 모델 목록",
        f"# 조회 시각 (UTC): {ts}",
        f"# base_url: {llm.get('base_url', '')}",
        f"# 현재 설정 모델 (config / FINANCIAL_AI_MODEL): {configured}",
        "",
    ]
    if error:
        lines.append(f"# 조회 실패: {error}")
        lines.extend(
            [
                "",
                "# 해결: API 키·네트워크·User-Agent(FINANCIAL_AI_USER_AGENT)를 확인하세요.",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.append(f"# 총 {len(models)}개")
    lines.append("")
    for i, m in enumerate(models, 1):
        mid = m.get("id", "")
        ob = m.get("owned_by") or ""
        extra = f"  |  provider: {ob}" if ob else ""
        lines.append(f"{i:3}. {mid}{extra}")
    lines.extend(
        [
            "",
            "# ── 선택 방법 ──",
            "# 1) config.yaml 의 llm.model 에 위 목록의 id 중 하나를 넣거나,",
            "# 2) 실행 전 FINANCIAL_AI_MODEL 환경변수로 지정.",
            "# 참고: 키별로 특정 모델만 허용될 수 있음 (403 permission_denied).",
            "",
        ]
    )
    return "\n".join(lines)


def write_gateway_models_log(
    project_root: Path, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], str | None, str]:
    """
    logs/available_models_latest.txt 및 날짜별 스냅샷에 목록을 기록합니다.
    반환: (모델목록, 오류문자열 또는 None, 로그 전체 텍스트)
    """
    models, err = fetch_gateway_models(config)
    text = format_gateway_models_log(config, models, err)
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / "available_models_latest.txt"
    out_path.write_text(text, encoding="utf-8")
    hist = log_dir / f"available_models_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.txt"
    hist.write_text(text, encoding="utf-8")
    return models, err, text


class LLMProvider:
    def __init__(self, config: dict[str, Any]):
        llm = config.get("llm", {})
        self.provider = llm.get("provider", "openai")
        self.model = os.environ.get("FINANCIAL_AI_MODEL") or llm["model"]
        self.temperature = float(llm.get("temperature", 0.2))
        self.max_tokens = int(llm.get("max_tokens", 4096))
        self.base_url = llm.get("base_url")
        env_name = llm.get("api_key_env", "OPENAI_API_KEY")
        self.api_key = os.environ.get(env_name)
        key_file = llm.get("api_key_file")
        if key_file:
            p = Path(key_file)
            if not p.is_absolute():
                root = Path(config.get("_project_root", "."))
                p = (root / p).resolve()
            loaded = load_optional_api_key_file(p)
            if loaded:
                self.api_key = loaded
        if not self.api_key:
            raise RuntimeError(
                f"LLM API 키가 없습니다. 환경변수 {env_name}을 설정하거나 "
                "financial-ai/.env 또는 financial-ai/api_guide/.env 에 키를 설정하세요."
            )

    def generate(
        self,
        system_msg: str,
        user_msg: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        temp = self.temperature if temperature is None else temperature
        mtok = self.max_tokens if max_tokens is None else max_tokens
        if self.provider == "openai":
            from openai import OpenAI

            kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "default_headers": {"User-Agent": _GATEWAY_BROWSER_UA},
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            client = OpenAI(**kwargs)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=temp,
                max_tokens=mtok,
            )
            choice = resp.choices[0].message
            return (choice.content or "").strip()

        if self.provider == "anthropic":
            import anthropic

            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=self.model,
                max_tokens=mtok,
                system=system_msg,
                messages=[{"role": "user", "content": user_msg}],
                temperature=temp,
            )
            return resp.content[0].text

        raise ValueError(f"지원하지 않는 LLM provider: {self.provider}")
