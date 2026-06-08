from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from agents.mcp import MCPServerStdio

DEFAULT_YFINANCE_COMMAND = "uvx"
DEFAULT_YFINANCE_ARGS = ["--python", "3.12", "yfmcp@0.11.1"]
DEFAULT_PLAYWRIGHT_COMMAND = "npx"
DEFAULT_PLAYWRIGHT_ARGS = ["@playwright/mcp@latest"]
NPM_CACHE_ENV_KEYS = ("npm_config_cache", "NPM_CONFIG_CACHE")

# Cursor/GUI에서 띄운 Python은 ~/.zshrc를 안 읽어 PATH에 Homebrew가 없는 경우가 많습니다.
_NPX_FALLBACK_PATHS = (
    "/opt/homebrew/bin/npx",  # Apple Silicon Homebrew
    "/usr/local/bin/npx",  # Intel Homebrew / legacy
)


def _path_prefixes_for_mcp() -> list[str]:
    """존재하는 디렉터리만 — shutil.which / 자식 프로세스가 node 등을 찾도록 PATH 앞에 붙임."""
    candidates = (
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
    )
    return [p for p in candidates if Path(p).is_dir()]


def _merge_path_with_prefixes(path_value: str | None) -> str:
    parts = _path_prefixes_for_mcp()
    if path_value:
        parts.append(path_value)
    return ":".join(parts)


def tools_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("agents", {}).get("tools_enabled", True))


def _merged_yfinance_config(cfg: dict[str, Any]) -> dict[str, Any]:
    yfinance_cfg = (cfg.get("mcp", {}) or {}).get("yfinance", {}) or {}
    return {
        "command": yfinance_cfg.get("command", DEFAULT_YFINANCE_COMMAND),
        "args": list(yfinance_cfg.get("args", DEFAULT_YFINANCE_ARGS)),
        "env": dict(yfinance_cfg.get("env", {})),
        "client_session_timeout_seconds": float(
            yfinance_cfg.get("client_session_timeout_seconds", 30)
        ),
        "max_retry_attempts": int(yfinance_cfg.get("max_retry_attempts", 1)),
    }


def _resolve_command(command: str, *, path: str | None = None) -> str:
    if Path(command).is_absolute():
        if not Path(command).exists():
            raise RuntimeError(f"MCP command not found: {command}")
        return command

    which_path = path or os.environ.get("PATH")
    resolved = shutil.which(command, path=which_path)
    if resolved:
        return resolved

    if command == "npx":
        for candidate in _NPX_FALLBACK_PATHS:
            p = Path(candidate)
            if p.exists():
                return str(p)
        raise RuntimeError(
            "mcp.playwright.command is set to 'npx', but 'npx' was not found on PATH. "
            "Install Node.js (e.g. `brew install node`) or set config.yaml "
            "mcp.playwright.command to an absolute path such as "
            "'/opt/homebrew/bin/npx'."
        )

    if command == "uvx":
        fallback = Path.home() / ".local" / "bin" / "uvx"
        if fallback.exists():
            return str(fallback)
        raise RuntimeError(
            "mcp.yfinance.command is set to 'uvx', but 'uvx' was not found on PATH. "
            "Set config.yaml mcp.yfinance.command to an absolute path "
            "or add '~/.local/bin' to PATH before running the pipeline."
        )

    raise RuntimeError(f"MCP command '{command}' was not found on PATH.")


def _has_flag(args: list[str], flag: str) -> bool:
    return flag in args


def _append_flag(args: list[str], flag: str, value: str | None = None) -> None:
    if _has_flag(args, flag):
        return
    args.append(flag)
    if value is not None:
        args.append(value)


def _playwright_output_dir(cfg: dict[str, Any]) -> Path:
    playwright_cfg = (cfg.get("mcp", {}) or {}).get("playwright", {}) or {}
    rel = playwright_cfg.get("output_dir", ".playwright-mcp")
    path = Path(rel)
    if not path.is_absolute():
        root = Path(cfg.get("_project_root", "."))
        path = (root / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_npx_command(command: str) -> bool:
    return Path(command).name == "npx"


def _playwright_npm_cache_dir(cfg: dict[str, Any]) -> Path:
    path = _playwright_output_dir(cfg) / "npm-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _merged_playwright_config(cfg: dict[str, Any]) -> dict[str, Any]:
    playwright_cfg = (cfg.get("mcp", {}) or {}).get("playwright", {}) or {}
    args = list(playwright_cfg.get("args", DEFAULT_PLAYWRIGHT_ARGS))
    command = playwright_cfg.get("command", DEFAULT_PLAYWRIGHT_COMMAND)
    env = dict(playwright_cfg.get("env", {}))
    if _is_npx_command(str(command)) and not any(key in env for key in NPM_CACHE_ENV_KEYS):
        env["npm_config_cache"] = str(_playwright_npm_cache_dir(cfg))
    _append_flag(args, "--headless")
    _append_flag(args, "--isolated")
    _append_flag(args, "--timeout-navigation", str(playwright_cfg.get("timeout_navigation_ms", 30000)))
    _append_flag(args, "--timeout-action", str(playwright_cfg.get("timeout_action_ms", 15000)))
    _append_flag(args, "--output-dir", str(_playwright_output_dir(cfg)))
    return {
        "command": command,
        "args": args,
        "env": env,
        "client_session_timeout_seconds": float(
            playwright_cfg.get("client_session_timeout_seconds", 30)
        ),
        "max_retry_attempts": int(playwright_cfg.get("max_retry_attempts", 1)),
    }


def make_yfinance_server(cfg: dict[str, Any], *, name: str) -> MCPServerStdio | None:
    if not tools_enabled(cfg):
        return None

    mcp_cfg = _merged_yfinance_config(cfg)
    extra_env = dict(mcp_cfg.get("env", {}))
    merged = {**os.environ, **extra_env}
    lookup_path = _merge_path_with_prefixes(merged.get("PATH"))
    command = _resolve_command(str(mcp_cfg["command"]), path=lookup_path)
    if merged.get("PATH") != lookup_path:
        merged["PATH"] = lookup_path
    env = merged

    return MCPServerStdio(
        name=name,
        params={
            "command": command,
            "args": list(mcp_cfg.get("args", [])),
            "env": env,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=float(mcp_cfg["client_session_timeout_seconds"]),
        max_retry_attempts=int(mcp_cfg["max_retry_attempts"]),
    )


def make_playwright_server(cfg: dict[str, Any], *, name: str) -> MCPServerStdio | None:
    if not tools_enabled(cfg):
        return None

    mcp_cfg = _merged_playwright_config(cfg)
    extra_env = dict(mcp_cfg.get("env", {}))
    merged = {**os.environ, **extra_env}
    lookup_path = _merge_path_with_prefixes(merged.get("PATH"))
    command = _resolve_command(str(mcp_cfg["command"]), path=lookup_path)
    if merged.get("PATH") != lookup_path:
        merged["PATH"] = lookup_path
    env = merged

    return MCPServerStdio(
        name=name,
        params={
            "command": command,
            "args": list(mcp_cfg.get("args", [])),
            "env": env,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=float(mcp_cfg["client_session_timeout_seconds"]),
        max_retry_attempts=int(mcp_cfg["max_retry_attempts"]),
        require_approval="never",
    )
