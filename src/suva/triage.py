"""Relevance triage of a ruling for Suva. Placeholder until the triage workstream lands."""

import sqlite3
from dataclasses import dataclass
from typing import Literal

from suva.llm import LLMClient

PROMPT_VERSION = "stub"
RELEVANCE_THRESHOLD = 50


@dataclass
class TriageResult:
    score: int  # 0-100
    label: Literal["relevant", "not_relevant"]
    reasoning: str


def triage(conn: sqlite3.Connection, docket: str, llm: LLMClient) -> TriageResult:
    """Score how relevant ruling `docket` is for Suva and explain why. Does not persist."""
    raise NotImplementedError("triage is not implemented yet")
