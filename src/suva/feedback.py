"""Collect the experts' feedback for a human-supervised prompt review (no LLM).

`suva feedback-export` writes what the legal experts changed in the app: score corrections
("Anpassungen") next to the model's triage, the free feedback rows, summaries edited by hand
or applied from an agent proposal next to the generated text they replaced, and the stored LLM
summaries of the corrections. The feedback-review skill (`.claude/skills/feedback-review/`)
reads this file to draft a report with suggested prompt changes; nothing here changes a prompt.
"""

import difflib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from suva import classify, db, summarize, triage

RESULTS_DIR = Path("data/results")
GENERATED_GLOB = "summaries_*.jsonl"


def generated_summaries(paths: list[Path]) -> dict[tuple[str, str], dict[str, Any]]:
    """Generated summaries by (docket, lang) from `export-summaries` files; a later file wins.
    Edited texts in those files are skipped, so the result is what the pipeline wrote."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                for lang, text in record.get("summaries", {}).items():
                    if text.get("prompt_version") != db.EDITED_VERSION:
                        found[record["docket"], lang] = {**text, "source": str(path)}
    return found


def word_diff(before: str, after: str) -> str:
    """`after` with removed words as [-...-] and added words as {+...+}."""
    a, b = re.findall(r"\S+", before), re.findall(r"\S+", after)
    parts: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            parts.append(" ".join(a[i1:i2]))
            continue
        if i2 > i1:
            parts.append(f"[-{' '.join(a[i1:i2])}-]")
        if j2 > j1:
            parts.append(f"{{+{' '.join(b[j1:j2])}+}}")
    return " ".join(parts)


def _labels(branch: str | None, category: str | None) -> dict[str, str | None]:
    branch_de = classify.BRANCHES[branch].de if branch in classify.BRANCHES else None
    category_de = classify.CATEGORIES[category].de if category in classify.CATEGORIES else None
    return {
        "branch": branch,
        "branch_de": branch_de,
        "category": category,
        "category_de": category_de,
    }


def score_corrections(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    threshold = triage.RELEVANCE_THRESHOLD
    items = []
    for i in reversed(db.list_adjustments(conn)):  # oldest first
        model = i["model_score"]
        items.append(
            {
                "docket": i["docket"],
                "decision_date": i["decision_date"],
                "language": i["language"],
                "title": i["title"],
                "headline_de": i["headline_de"],
                **_labels(i["branch"], i["primary_category"]),
                # "prefilter" or "gate": decided by rules in triage.py without an LLM call
                "model": i["model_name"],
                "model_score": model,
                "model_label": i["model_label"],
                "model_prompt_version": i["model_prompt_version"],
                "model_reasoning_de": i["model_reasoning_de"],
                "expert_score": i["expert_score"],
                "expert_label": i["expert_label"],
                "expert_comment": i["comment"],
                "adjusted_at": i["adjusted_at"],
                "delta": None if model is None else i["expert_score"] - model,
                "crosses_threshold": model is not None
                and (model >= threshold) != (i["expert_score"] >= threshold),
            }
        )
    return items


def edited_summaries(
    conn: sqlite3.Connection, generated: dict[tuple[str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    items = []
    for row in db.list_edited_summaries(conn):
        before = generated.get((row["docket"], row["lang"]))
        items.append(
            {
                "docket": row["docket"],
                "lang": row["lang"],
                "decision_date": row["decision_date"],
                "ruling_language": row["language"],
                "title": row["title"],
                "score": row["score"],
                **_labels(row["branch"], row["primary_category"]),
                # "manual": typed in the editor; "agent": a proposal of the side-panel agent
                "edited_by": row["edited_by"],
                "edited_at": row["edited_at"],
                "edited_text": row["text"],
                "generated_text": before["text"] if before else None,
                "generated_prompt_version": before["prompt_version"] if before else None,
                "generated_source": before["source"] if before else None,
                "word_diff": word_diff(before["text"], row["text"]) if before else None,
                "words": {
                    "generated": len(before["text"].split()) if before else None,
                    "edited": len(row["text"].split()),
                },
            }
        )
    return items


def export(conn: sqlite3.Connection, generated_paths: list[Path]) -> dict[str, Any]:
    corrections = score_corrections(conn)
    edits = edited_summaries(conn, generated_summaries(generated_paths))
    feedback = db.list_feedback(conn)
    return {
        "prompt_versions": {
            "triage": triage.PROMPT_VERSION,
            "summary": summarize.PROMPT_VERSION,
            "headline": summarize.HEADLINE_VERSION,
        },
        "relevance_threshold": triage.RELEVANCE_THRESHOLD,
        "generated_sources": [str(p) for p in generated_paths],
        "counts": {
            "score_corrections": len(corrections),
            "raised": sum((c["delta"] or 0) > 0 for c in corrections),
            "lowered": sum((c["delta"] or 0) < 0 for c in corrections),
            "crossing_threshold": sum(c["crosses_threshold"] for c in corrections),
            "with_comment": sum(bool(c["expert_comment"]) for c in corrections),
            "feedback_rows": len(feedback),
            "edited_summaries": len(edits),
            "edited_without_generated": sum(e["generated_text"] is None for e in edits),
        },
        "score_corrections": corrections,
        "feedback": feedback,
        "edited_summaries": edits,
        "adjustment_summaries": db.list_adjustment_summaries(conn),
    }
