"""Spotify tools.

The server uses Spotify's Web API (Client Credentials flow — no user login
required, public catalog only) to translate fuzzy queries like 'Time from
Interstellar' into a specific track URI. The Android client receives the URI
in a phone_action and plays it via the Spotify App Remote SDK.

For pure transport controls (pause/resume/skip), the server doesn't need to
hit the Web API at all — it just emits a phone_action."""

import os
from typing import Any

from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

from ._result import ToolResult

_sp: Spotify | None = None


def _client() -> Spotify:
    global _sp
    if _sp is None:
        _sp = Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=os.getenv("SPOTIFY_CLIENT_ID"),
                client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            ),
        )
    return _sp


def _play_song(args: dict[str, Any]) -> ToolResult:
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult(text="No song provided.")
    try:
        result = _client().search(q=query, type="track", limit=1)
    except Exception as e:
        return ToolResult(text=f"Spotify search failed: {e}")

    items = result.get("tracks", {}).get("items", []) if result else []
    if not items:
        return ToolResult(text=f"Couldn't find '{query}' on Spotify.")
    track = items[0]
    name = track["name"]
    artist = track["artists"][0]["name"] if track.get("artists") else "Unknown"
    return ToolResult(
        text=f"Playing {name} by {artist}.",
        phone_action={"type": "spotify_play", "uri": track["uri"]},
    )


def _play_playlist(args: dict[str, Any]) -> ToolResult:
    query = (args.get("query") or "").strip()
    if not query:
        return ToolResult(text="No playlist provided.")
    try:
        result = _client().search(q=query, type="playlist", limit=1)
    except Exception as e:
        return ToolResult(text=f"Spotify search failed: {e}")

    items = result.get("playlists", {}).get("items", []) if result else []
    items = [it for it in items if it]
    if not items:
        return ToolResult(text=f"Couldn't find a playlist matching '{query}'.")
    pl = items[0]
    name = pl["name"]
    return ToolResult(
        text=f"Playing the {name} playlist.",
        phone_action={"type": "spotify_play", "uri": pl["uri"]},
    )


def _pause(args: dict[str, Any]) -> ToolResult:
    return ToolResult(text="Paused.", phone_action={"type": "spotify_pause"})


def _resume(args: dict[str, Any]) -> ToolResult:
    return ToolResult(text="Resuming.", phone_action={"type": "spotify_resume"})


def _skip_next(args: dict[str, Any]) -> ToolResult:
    return ToolResult(text="Skipping.", phone_action={"type": "spotify_skip_next"})


def _skip_previous(args: dict[str, Any]) -> ToolResult:
    return ToolResult(
        text="Going back.", phone_action={"type": "spotify_skip_previous"}
    )


TOOLS: list[tuple[dict[str, Any], Any]] = [
    (
        {
            "type": "function",
            "function": {
                "name": "play_song",
                "description": (
                    "Play a specific song on Spotify. Use for any 'play X', "
                    "'put on X', or fuzzy queries like 'that song from Interstellar'. "
                    "The server will search Spotify and return the best match."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "What to search for. Include the song name and "
                                "artist if known, e.g., 'Hot In Herre Nelly'."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        _play_song,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "play_playlist",
                "description": (
                    "Play a Spotify playlist by name. Use for 'play my chill "
                    "playlist', 'put on Today's Top Hits', etc."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Playlist name or description.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        _play_playlist,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "pause_music",
                "description": "Pause whatever is currently playing on Spotify.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _pause,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "resume_music",
                "description": "Resume Spotify playback after a pause.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _resume,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "skip_to_next_track",
                "description": "Skip to the next track on Spotify.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _skip_next,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "skip_to_previous_track",
                "description": "Go back to the previous track on Spotify.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _skip_previous,
    ),
]
