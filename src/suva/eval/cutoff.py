"""Choose the score cut-off of the delivered relevance list by F2 on the labelled period.

Suva scores the delivered Q2 2026 list by recall and F2, which weights recall four times as much
as precision. For every cut-off this prints the list length, recall, precision and F2 per
quarter of the labelled period, then picks the best cut-off on one quarter and scores it on the
other, in both directions, and does the same for a fixed list length (top K).

    python -m suva.eval.cutoff data/results/triage_2025q4_2026q1.jsonl [--out report.md]
"""

import argparse
import json
from pathlib import Path

from suva.config import get_settings
from suva.db import open_corpus
from suva.eval.score_triage import load_relevant, load_triage, rank
from suva.triage import RELEVANCE_THRESHOLD

QUARTERS = {"Q4 2025": ("2025-10-01", "2025-12-31"), "Q1 2026": ("2026-01-01", "2026-03-31")}
CUTOFFS = range(20, 81)
TOP_K = range(10, 201)


def metrics(predicted: list[str], relevant: set[str]) -> dict[str, float]:
    hits = len(set(predicted) & relevant)
    precision = hits / len(predicted) if predicted else 0.0
    recall = hits / len(relevant)
    f2 = 5 * precision * recall / (4 * precision + recall) if hits else 0.0
    return {"n": len(predicted), "hits": hits, "recall": recall, "precision": precision, "f2": f2}


def at_cutoff(scores: dict[str, float], relevant: set[str], cutoff: int) -> dict[str, float]:
    return metrics([d for d, s in scores.items() if s >= cutoff], relevant)


def at_top(scores: dict[str, float], relevant: set[str], k: int) -> dict[str, float]:
    return metrics(rank(scores)[:k], relevant)


def best(rule, scores: dict[str, float], relevant: set[str], values: range) -> int:
    """The value with the highest F2; ties go to the longer list (recall matters more)."""
    longer = 1 if rule is at_top else -1
    return max(values, key=lambda v: (rule(scores, relevant, v)["f2"], longer * v))


def by_quarter(triage: Path, corpus: Path, relevant: set[str]) -> dict[str, tuple[dict, set]]:
    with open_corpus(corpus) as f:
        dates = {r["docket"]: r["decision_date"] for r in map(json.loads, f)}
    scores = load_triage(triage)
    split = {}
    for quarter, (start, end) in QUARTERS.items():
        in_quarter = {d: s for d, s in scores.items() if start <= dates.get(d, "") <= end}
        split[quarter] = in_quarter, relevant & in_quarter.keys()
    return split


def cell(m: dict[str, float]) -> str:
    return f"{m['n']} | {m['recall']:.2f} | {m['precision']:.2f} | {m['f2']:.3f}"


def render(split: dict[str, tuple[dict, set]]) -> str:
    names = list(split)
    lines = [
        "# Cut-off of the relevance list (F2)",
        "",
        "Labelled period, quarters by decision date: "
        + ", ".join(f"{q} {len(rel)} relevant of {len(sc)}" for q, (sc, rel) in split.items())
        + ". Rows are the cut-offs at which either quarter's list changes.",
        "",
        "| score >= | " + " | ".join(f"{q} n | R | P | F2" for q in names) + " |",
        "|---|" + "---|---|---|---|" * len(names),
    ]
    previous = None
    for cutoff in CUTOFFS:
        row = [at_cutoff(*split[q], cutoff) for q in names]
        key = tuple(m["n"] for m in row)
        if key != previous:
            lines.append(f"| {cutoff} | " + " | ".join(cell(m) for m in row) + " |")
        previous = key
    lines += [
        "",
        "## Tuned on one quarter, checked on the other",
        "",
        "| rule | tuned on | value | F2 there | checked on | n | R | P | F2 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label, rule, values in (("score >=", at_cutoff, CUTOFFS), ("top K", at_top, TOP_K)):
        for tuned, held in (names, names[::-1]):
            value = best(rule, *split[tuned], values)
            there = rule(*split[tuned], value)["f2"]
            lines.append(
                f"| {label} | {tuned} | {value} | {there:.3f} | {held} | "
                f"{cell(rule(*split[held], value))} |"
            )
    lines += ["", f"## Shipped cut-off: score >= {RELEVANCE_THRESHOLD}", ""]
    for q in names:
        lines.append(f"- {q}: n | R | P | F2 = {cell(at_cutoff(*split[q], RELEVANCE_THRESHOLD))}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("triage", type=Path, help="JSONL or CSV with docket and score")
    parser.add_argument("--corpus", type=Path, default=get_settings().corpus_path)
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    args = parser.parse_args(argv)

    relevant, _ = load_relevant()
    report = render(by_quarter(args.triage, args.corpus, relevant))
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
