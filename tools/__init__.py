"""Tool registry. Each tool module exports a TOOLS list of
(DEFINITION, execute_fn) pairs. Tools return a ToolResult — text for the LLM
plus an optional phone_action that the Android client executes."""

from typing import Any, Callable

from . import get_time, grocery, spotify, tesla
from ._result import ToolResult

__all__ = ["ToolResult", "all_definitions", "execute"]

_MODULES = (get_time, grocery, spotify, tesla)

_TOOLS: dict[str, dict[str, Any]] = {}
for _mod in _MODULES:
    for _definition, _executor in _mod.TOOLS:
        _name = _definition["function"]["name"]
        _TOOLS[_name] = {"definition": _definition, "execute": _executor}


def all_definitions() -> list[dict[str, Any]]:
    return [t["definition"] for t in _TOOLS.values()]


def execute(name: str, args: dict[str, Any]) -> ToolResult:
    tool = _TOOLS.get(name)
    if tool is None:
        raise ValueError(f"unknown tool: {name}")
    fn: Callable[[dict[str, Any]], ToolResult] = tool["execute"]
    return fn(args)
