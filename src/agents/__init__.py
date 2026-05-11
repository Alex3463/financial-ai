from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LOCAL_DIR = Path(__file__).resolve().parent
_SRC_DIR = _LOCAL_DIR.parent


def _find_sdk_init() -> Path:
    for entry in sys.path:
        if not entry:
            continue
        try:
            root = Path(entry).resolve()
        except OSError:
            continue
        if root == _SRC_DIR:
            continue
        candidate = root / "agents" / "__init__.py"
        if candidate.is_file():
            return candidate
    raise ImportError(
        "OpenAI Agents SDK package 'agents' was not found outside the local src/agents package. "
        "Run `uv add openai-agents==0.17.1` and retry."
    )


_SDK_INIT = _find_sdk_init()
_SDK_DIR = _SDK_INIT.parent
__path__ = [str(_SDK_DIR), str(_LOCAL_DIR)]

_spec = importlib.util.spec_from_file_location(
    __name__,
    _SDK_INIT,
    submodule_search_locations=__path__,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Failed to load OpenAI Agents SDK from {_SDK_INIT}")

_module = sys.modules[__name__]
_module.__file__ = str(_SDK_INIT)
_module.__spec__ = _spec
_module.__path__ = __path__
_spec.loader.exec_module(_module)

_module.__file__ = str(_LOCAL_DIR / "__init__.py")
_module.__path__ = __path__
