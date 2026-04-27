from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """What every tool returns: text the LLM uses to phrase its reply, plus
    an optional phone_action the Android client executes (e.g., a Spotify
    play command)."""

    text: str
    phone_action: dict[str, Any] | None = None
