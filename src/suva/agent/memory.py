"""The agent's knowledge: one short free text on style and working habits that goes into every
system prompt of the side-panel agent.

The default (knowledge_default.md) condenses the summary pipeline's style instructions
(prompts/summary_style.md, summary_de.md, summary_fr.md) to their essentials, so the agent writes
and revises summaries in Suva's style without carrying the full prompts and examples in every
turn. Until someone edits it, the text is not stored and follows that file; edited, it keeps its
own text until it is reset. Users edit it on the "Agent-Wissen" page; the agent adds to it with
update_memory. MAX_CONTENT keeps it small: it costs context on every agent call.
"""

import sqlite3
from pathlib import Path
from typing import Any

from suva import db

DEFAULT_PATH = Path(__file__).parent / "knowledge_default.md"
MAX_CONTENT = 6_000  # characters, about 1,500 tokens


def default_text() -> str:
    return DEFAULT_PATH.read_text(encoding="utf-8").strip()


def get(conn: sqlite3.Connection) -> dict[str, Any]:
    """The text in effect, whether it is the default, and who changed it last when."""
    row = db.get_knowledge(conn)
    base = {"max_length": MAX_CONTENT}
    if row is None or row["content"] is None:
        return {
            **base,
            "content": default_text(),
            "default": True,
            "updated_by": None,
            "updated_at": None,
        }
    return {
        **base,
        "content": row["content"],
        "default": False,
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


def text(conn: sqlite3.Connection) -> str:
    return get(conn)["content"]


def save(conn: sqlite3.Connection, content: str, *, updated_by: str) -> None:
    """Store a new text; the default text itself is stored as "follow the default"."""
    content = content.replace("\r\n", "\n").strip()
    if content == default_text():
        reset(conn)
    else:
        db.save_knowledge(conn, content, updated_by=updated_by)


def reset(conn: sqlite3.Connection) -> None:
    db.save_knowledge(conn, None, updated_by="default")
