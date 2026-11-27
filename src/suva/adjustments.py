"""LLM summary of the experts' relevance-score corrections ("Anpassungen").

Legal experts can override the triage score of a ruling (`db.set_expert_score`). This module
asks the LLM what those corrections have in common: where the triage over- or underrates, and
what the triage prompt should take into account. The result is shown in the UI only; feeding it
back into the triage prompt is the next step of the feedback loop and not automated.
"""

from typing import Any

from suva import classify, triage
from suva.llm import LLMClient, Message
from suva.summarize import PROMPTS_DIR

# More corrections than this are cut, newest first, to keep the prompt short.
MAX_ITEMS = 60
LANGUAGES = {"de": "Deutsch", "fr": "Französisch"}
# The prompt's section headings in each output language; left alone, the model keeps the German.
HEADINGS = {
    "de": ["Überblick", "Muster", "Vorschläge für den Triage-Prompt"],
    "fr": ["Vue d'ensemble", "Tendances", "Propositions pour le prompt de triage"],
}


def _clip(text: str | None, limit: int = 500) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def stats(items: list[dict[str, Any]]) -> dict[str, int]:
    """Counts the page shows next to the summary and the prompt states as facts."""
    threshold = triage.RELEVANCE_THRESHOLD

    def diff(i: dict[str, Any]) -> int:
        return i["expert_score"] - (
            i["model_score"] if i["model_score"] is not None else i["expert_score"]
        )

    return {
        "total": len(items),
        "raised": sum(diff(i) > 0 for i in items),
        "lowered": sum(diff(i) < 0 for i in items),
        "added_to_kb": sum(
            i["expert_score"] >= threshold and (i["model_score"] or 0) < threshold for i in items
        ),
        "removed_from_kb": sum(
            i["expert_score"] < threshold and (i["model_score"] or 0) >= threshold for i in items
        ),
    }


def _direction(i: dict[str, Any]) -> str:
    if i["model_score"] is None or i["model_score"] == i["expert_score"]:
        return ""
    diff = i["expert_score"] - i["model_score"]
    word = (
        "höher bewertet, Triage hat unterschätzt"
        if diff > 0
        else "tiefer bewertet, Triage hat überschätzt"
    )
    return f" ({word}, {diff:+d})"


def _case(i: dict[str, Any]) -> str:
    headline = i.get("headline_de") or i.get("title") or ""
    labels = [
        table[slug].de
        for table, slug in (
            (classify.BRANCHES, i.get("branch")),
            (classify.CATEGORIES, i.get("primary_category")),
        )
        if slug in table
    ]
    category = " / ".join(labels)
    model = i["model_score"] if i["model_score"] is not None else "–"
    lines = [
        f"### {i['docket']} ({category or 'nicht klassifiziert'})",
        f"Gegenstand: {_clip(headline, 200)}",
        f"Score der Triage: {model} → Score der Fachperson: {i['expert_score']}{_direction(i)}",
        f"Begründung der Triage: {_clip(i.get('model_reasoning_de'))}",
        f"Begründung der Fachperson: {_clip(i.get('comment')) or '(keine angegeben)'}",
    ]
    return "\n".join(lines)


def build_messages(items: list[dict[str, Any]], lang: str) -> list[Message]:
    system = (PROMPTS_DIR / "adjustments_summary.md").read_text(encoding="utf-8").strip()
    s = stats(items)
    shown = items[:MAX_ITEMS]
    facts = (
        f"Schwelle für «relevant» (Wissensbasis): Score {triage.RELEVANCE_THRESHOLD}.\n"
        f"Anpassungen: {s['total']} (höher bewertet: {s['raised']}, tiefer bewertet: "
        f"{s['lowered']}; neu in der Wissensbasis: {s['added_to_kb']}, aus der Wissensbasis "
        f"entfernt: {s['removed_from_kb']})."
        + (f"\nGezeigt werden die {MAX_ITEMS} neuesten." if len(items) > MAX_ITEMS else "")
    )
    user = (
        f"{facts}\n\n"
        + "\n\n".join(_case(i) for i in shown)
        + f"\n\nAntworte auf {LANGUAGES[lang]}, mit diesen Überschriften: "
        + ", ".join(f"## {h}" for h in HEADINGS[lang])
        + "."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def summarize(items: list[dict[str, Any]], llm: LLMClient, lang: str = "de") -> str:
    text = llm.chat(build_messages(items, lang), max_tokens=1200).strip()
    # A reasoning model may prepend its thinking; keep only the answer.
    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()
    return text
