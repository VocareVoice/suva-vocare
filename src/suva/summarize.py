"""German and French summaries of a ruling in Suva's style. Placeholder until the summary
workstream lands."""

import sqlite3

from suva.llm import LLMClient

PROMPT_VERSION = "stub"
LANGUAGES = ("de", "fr")


def summarize(conn: sqlite3.Connection, docket: str, llm: LLMClient) -> dict[str, str]:
    """Return {"de": ..., "fr": ...} summaries of ruling `docket`. Does not persist."""
    raise NotImplementedError("summarize is not implemented yet")
