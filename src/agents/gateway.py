from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from agents import (
    Agent,
    ModelSettings,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)
from report.llm import LLMProvider, _GATEWAY_BROWSER_UA

T = TypeVar("T", bound=BaseModel)

_PROMPTS_DIR = Path(__file__).with_name("prompts")


def build_async_openai_client(cfg: dict[str, Any]) -> AsyncOpenAI:
    provider = LLMProvider(cfg)
    kwargs: dict[str, Any] = {
        "api_key": provider.api_key,
        "default_headers": {"User-Agent": _GATEWAY_BROWSER_UA},
    }
    if provider.base_url:
        kwargs["base_url"] = provider.base_url
    return AsyncOpenAI(**kwargs)


def configure_agents_sdk(cfg: dict[str, Any]) -> None:
    client = build_async_openai_client(cfg)
    set_default_openai_client(client, use_for_tracing=False)
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)


def agent_model_name(cfg: dict[str, Any]) -> str:
    return LLMProvider(cfg).model


def per_agent_max_tokens(cfg: dict[str, Any]) -> int:
    return int(cfg.get("agents", {}).get("per_agent_max_tokens", 1500))


def composer_max_tokens(cfg: dict[str, Any]) -> int:
    return int(cfg.get("agents", {}).get("composer_max_tokens", 3500))


def build_model_settings(
    cfg: dict[str, Any],
    *,
    max_tokens: int,
    enable_tools: bool,
) -> ModelSettings:
    temperature = float(cfg.get("llm", {}).get("temperature", 0.2))
    kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if enable_tools:
        kwargs["parallel_tool_calls"] = False
    return ModelSettings(**kwargs)


def load_prompt_text(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def coerce_output(output: Any, output_type: type[T]) -> T:
    if isinstance(output, output_type):
        return output
    if isinstance(output, str):
        try:
            return output_type.model_validate_json(output)
        except ValidationError:
            pass
    return output_type.model_validate(output)


async def run_structured_agent(
    *,
    cfg: dict[str, Any],
    name: str,
    instructions: str,
    input_text: str,
    output_type: type[T],
    max_tokens: int,
    mcp_servers: Sequence[Any] | None = None,
) -> T:
    agent = Agent(
        name=name,
        instructions=instructions,
        model=agent_model_name(cfg),
        model_settings=build_model_settings(
            cfg,
            max_tokens=max_tokens,
            enable_tools=bool(mcp_servers),
        ),
        output_type=output_type,
        mcp_servers=list(mcp_servers or []),
    )
    result = await Runner.run(agent, input_text)
    return coerce_output(result.final_output, output_type)
