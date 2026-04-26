"""Tool registry. Each tool module exports DEFINITION (OpenAI function-calling
schema) and an execute(args) -> str function. Adding a new tool is two steps:
create the module, register it below."""

from typing import Any, Callable

from . import get_time

_TOOLS: dict[str, dict[str, Any]] = {
    get_time.DEFINITION["function"]["name"]: {
        "definition": get_time.DEFINITION,
        "execute": get_time.execute,
    },
}


def all_definitions() -> list[dict[str, Any]]:
    return [t["definition"] for t in _TOOLS.values()]


def execute(name: str, args: dict[str, Any]) -> str:
    tool = _TOOLS.get(name)
    if tool is None:
        raise ValueError(f"unknown tool: {name}")
    fn: Callable[[dict[str, Any]], str] = tool["execute"]
    return fn(args)
