from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ._result import ToolResult

DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": (
            "Get the current time. Use this whenever the user asks what time "
            "it is, or for the time in a specific city/timezone."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "Optional IANA timezone name like 'America/Los_Angeles' "
                        "or 'Europe/London'. If omitted, uses the server's "
                        "local time."
                    ),
                },
            },
        },
    },
}


def execute(args: dict[str, Any]) -> ToolResult:
    tz_name = args.get("timezone")
    try:
        now = datetime.now(ZoneInfo(tz_name)) if tz_name else datetime.now()
    except ZoneInfoNotFoundError:
        return ToolResult(text=f"Unknown timezone: {tz_name}")
    return ToolResult(text=now.strftime("%-I:%M %p on %A, %B %-d, %Y"))


TOOLS: list[tuple[dict[str, Any], Any]] = [(DEFINITION, execute)]
