"""Grocery list tools. Two lists supported:
- 'main': the default everyday grocery list
- 'wholesale': bulk items from Costco / Sam's Club

When the user mentions 'Costco', 'Sam's', 'Sam's Club', or 'wholesale',
the LLM should pass list='wholesale'.
"""

import sqlite3
from pathlib import Path
from typing import Any

from ._result import ToolResult

DB_PATH = Path("data/jarvis.sqlite")
DB_PATH.parent.mkdir(exist_ok=True)

# Apply the schema once at import time so the file is ready to use.
with sqlite3.connect(DB_PATH) as _conn:
    _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grocery_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item       TEXT NOT NULL,
            list_name  TEXT NOT NULL DEFAULT 'main',
            added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _normalize_list(value: str | None) -> str:
    if not value:
        return "main"
    v = value.lower().strip()
    if v in {"wholesale", "costco", "sams", "sam's", "sam's club", "sams club", "bulk"}:
        return "wholesale"
    return "main"


def _add(args: dict[str, Any]) -> ToolResult:
    item = (args.get("item") or "").strip()
    if not item:
        return ToolResult(text="No item provided.")
    list_name = _normalize_list(args.get("list"))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO grocery_items (item, list_name) VALUES (?, ?)",
            (item, list_name),
        )
    return ToolResult(text=f"Added '{item}' to the {list_name} list.")


def _read(args: dict[str, Any]) -> ToolResult:
    list_arg = (args.get("list") or "").lower().strip()
    if list_arg == "all":
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT item, list_name FROM grocery_items ORDER BY list_name, id"
            ).fetchall()
        if not rows:
            return ToolResult(text="Both lists are empty.")
        by_list: dict[str, list[str]] = {}
        for item, ln in rows:
            by_list.setdefault(ln, []).append(item)
        parts = [f"{ln}: {', '.join(items)}" for ln, items in by_list.items()]
        return ToolResult(text="; ".join(parts))

    list_name = _normalize_list(list_arg or None)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT item FROM grocery_items WHERE list_name = ? ORDER BY id",
            (list_name,),
        ).fetchall()
    if not rows:
        return ToolResult(text=f"The {list_name} list is empty.")
    return ToolResult(
        text=f"On the {list_name} list: " + ", ".join(r[0] for r in rows) + "."
    )


def _clear(args: dict[str, Any]) -> ToolResult:
    list_arg = (args.get("list") or "").lower().strip()
    if list_arg == "all":
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM grocery_items")
        return ToolResult(text="Cleared both lists.")

    list_name = _normalize_list(list_arg or None)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM grocery_items WHERE list_name = ?", (list_name,))
    return ToolResult(text=f"Cleared the {list_name} list.")


_LIST_DESCRIPTION = (
    "Which list. 'main' is the default everyday grocery list. "
    "'wholesale' is for bulk items from Costco or Sam's Club — use it when "
    "the user mentions Costco, Sam's, Sam's Club, or 'wholesale'."
)

TOOLS: list[tuple[dict[str, Any], Any]] = [
    (
        {
            "type": "function",
            "function": {
                "name": "add_to_grocery_list",
                "description": "Add a single item to the grocery list.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item": {
                            "type": "string",
                            "description": "The item to add (e.g., 'milk', 'bananas').",
                        },
                        "list": {
                            "type": "string",
                            "description": _LIST_DESCRIPTION,
                            "enum": ["main", "wholesale"],
                        },
                    },
                    "required": ["item"],
                },
            },
        },
        _add,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "read_grocery_list",
                "description": "Read the current items on the grocery list.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "list": {
                            "type": "string",
                            "description": (
                                _LIST_DESCRIPTION
                                + " Pass 'all' to read both lists."
                            ),
                            "enum": ["main", "wholesale", "all"],
                        },
                    },
                },
            },
        },
        _read,
    ),
    (
        {
            "type": "function",
            "function": {
                "name": "clear_grocery_list",
                "description": (
                    "Remove all items from a grocery list. Only call this when "
                    "the user explicitly asks to clear or empty the list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "list": {
                            "type": "string",
                            "description": (
                                _LIST_DESCRIPTION
                                + " Pass 'all' to clear both lists."
                            ),
                            "enum": ["main", "wholesale", "all"],
                        },
                    },
                },
            },
        },
        _clear,
    ),
]
