from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def execute(args: dict[str, Any]) -> str:
    tz_name = args.get("timezone")
    try:
        now = datetime.now(ZoneInfo(tz_name)) if tz_name else datetime.now()
    except ZoneInfoNotFoundError:
        return f"Unknown timezone: {tz_name}"
    return now.strftime("%-I:%M %p on %A, %B %-d, %Y")
