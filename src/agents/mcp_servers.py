from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from agents.mcp import MCPServerStdio

DEFAULT_YFINANCE_COMMAND = "uvx"
DEFAULT_YFINANCE_ARGS = ["--python", "3.12", "yfmcp@0.11.1"]


def tools_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("agents", {}).get("tools_enabled", True))


def _merged_yfinance_config(cfg: dict[str, Any]) -> dict[str, Any]:
    yfinance_cfg = (cfg.get("mcp", {}) or {}).get("yfinance", {}) or {}
    return {
        "command": yfinance_cfg.get("command", DEFAULT_YFINANCE_COMMAND),
        "args": list(yfinance_cfg.get("args", DEFAULT_YFINANCE_ARGS)),
        "env": dict(yfinance_cfg.get("env", {})),
    }


def _validate_command(command: str) -> None:
    if Path(command).is_absolute():
        if not Path(command).exists():
            raise RuntimeError(f"MCP command not found: {command}")
        return

    if shutil.which(command):
        return

    if command == "uvx":
        raise RuntimeError(
            "mcp.yfinance.command is set to 'uvx', but 'uvx' was not found on PATH. "
            "Set config.yaml mcp.yfinance.command to '/Users/hwani/.local/bin/uvx' "
            "or add '~/.local/bin' to PATH before running the pipeline."
        )

    raise RuntimeError(f"MCP command '{command}' was not found on PATH.")


def make_yfinance_server(cfg: dict[str, Any], *, name: str) -> MCPServerStdio | None:
    if not tools_enabled(cfg):
        return None

    mcp_cfg = _merged_yfinance_config(cfg)
    command = str(mcp_cfg["command"])
    _validate_command(command)

    extra_env = dict(mcp_cfg.get("env", {}))
    env = {**os.environ, **extra_env} if extra_env else None

    return MCPServerStdio(
        name=name,
        params={
            "command": command,
            "args": list(mcp_cfg.get("args", [])),
            "env": env,
        },
        cache_tools_list=True,
    )
