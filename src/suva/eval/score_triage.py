"""Score a triage ranking against the rulings Suva considered relevant in Q4 2025 and Q1 2026.

Input is JSONL rows `{"docket": "8C_78/2025", "score": 0.93}` or a CSV with `docket` and
`score` columns, covering the rulings of that period (higher score = more relevant).

    python -m suva.eval.score_triage triage.jsonl [--threshold 0.5] [--out report.md]
"""

import argparse
import csv
import json
from pathlib import Path

from suva.eval.examples import RELEVANT_PATH, docket_sort_key, normalise_docket, read_jsonl

PRECISION_AT = (10, 30)
RECALL_AT = (30, 60)


def load_triage(path: Path) -> dict[str, float]:
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        rows = read_jsonl(path)
    scores: dict[str, float] = {}
    for row in rows:
        docket = normalise_docket(str(row["docket"]))
        if docket is None:
            raise ValueError(f"unrecognised docket in {path}: {row['docket']!r}")
        scores[docket] = max(float(row["score"]), scores.get(docket, float("-inf")))
    return scores


def load_relevant(path: Path = RELEVANT_PATH) -> tuple[set[str], list[str]]:
    """Relevant dockets, plus labels of listed decisions that have no Federal Court docket."""
    rulings = json.loads(path.read_text(encoding="utf-8"))["rulings"]
    dockets = {r["docket"] for r in rulings if r["docket"]}
    return dockets, [r["label"] for r in rulings if not r["docket"]]


def rank(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda d: (-scores[d], docket_sort_key(d)))


def precision_at(ranked: list[str], relevant: set[str], k: int) -> float:
    return sum(d in relevant for d in ranked[:k]) / k


def recall_at(ranked: list[str], relevant: set[str], k: int) -> float:
    return sum(d in relevant for d in ranked[:k]) / len(relevant)


def evaluate(scores: dict[str, float], relevant: set[str], threshold: float | None = None) -> dict:
    ranked = rank(scores)
    position = {docket: i for i, docket in enumerate(ranked, start=1)}
    metrics = {
        "scored": len(ranked),
        "relevant": len(relevant),
        "coverage": len(relevant & scores.keys()) / len(relevant),
        **{f"precision@{k}": precision_at(ranked, relevant, k) for k in PRECISION_AT},
        **{f"recall@{k}": recall_at(ranked, relevant, k) for k in RECALL_AT},
    }
    if threshold is not None:
        predicted = {d for d, score in scores.items() if score >= threshold}
        hits = len(predicted & relevant)
        metrics["predicted_relevant"] = len(predicted)
        metrics["recall@threshold"] = hits / len(relevant)
        metrics["precision@threshold"] = hits / len(predicted) if predicted else 0.0

    cutoff = max(RECALL_AT)
    missed = [d for d in relevant if position.get(d, cutoff + 1) > cutoff]
    missed.sort(key=lambda d: (position.get(d, len(ranked) + 1), docket_sort_key(d)))
    metrics["missed"] = [
        {"docket": d, "rank": position.get(d), "score": scores.get(d)} for d in missed
    ]
    return metrics


def render_report(
    metrics: dict, unscoreable: list[str], source: str, threshold: float | None
) -> str:
    lines = [
        "# Triage evaluation",
        "",
        f"Triage output: `{source}` ({metrics['scored']} rulings scored). Reference: "
        f"{metrics['relevant']} relevant Federal Court rulings from Suva's Q4 2025 / Q1 2026 list.",
        "",
        "| metric | value |",
        "|---|---|",
        f"| coverage (relevant rulings present in the output) | {metrics['coverage']:.2f} |",
    ]
    lines += [f"| precision@{k} | {metrics[f'precision@{k}']:.2f} |" for k in PRECISION_AT]
    lines += [f"| recall@{k} | {metrics[f'recall@{k}']:.2f} |" for k in RECALL_AT]
    if threshold is not None:
        lines += [
            f"| rulings with score >= {threshold:g} | {metrics['predicted_relevant']} |",
            f"| recall at score >= {threshold:g} | {metrics['recall@threshold']:.2f} |",
            f"| precision at score >= {threshold:g} | {metrics['precision@threshold']:.2f} |",
        ]
    lines += [
        "",
        f"## Relevant rulings outside the top {max(RECALL_AT)} ({len(metrics['missed'])})",
        "",
    ]
    if metrics["missed"]:
        lines += ["| docket | rank | score |", "|---|---|---|"]
        for miss in metrics["missed"]:
            if miss["rank"] is None:
                lines.append(f"| {miss['docket']} | not in output | - |")
            else:
                lines.append(f"| {miss['docket']} | {miss['rank']} | {miss['score']:g} |")
    else:
        lines.append("None.")
    if unscoreable:
        lines += ["", "## Listed decisions without a Federal Court docket (not scored)", ""]
        lines += [f"- {label}" for label in unscoreable]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("triage", type=Path, help="JSONL or CSV with docket and score")
    parser.add_argument("--relevant", type=Path, default=RELEVANT_PATH)
    parser.add_argument(
        "--threshold", type=float, help="score from which a ruling counts as relevant"
    )
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    args = parser.parse_args(argv)

    relevant, unscoreable = load_relevant(args.relevant)
    metrics = evaluate(load_triage(args.triage), relevant, args.threshold)
    report = render_report(metrics, unscoreable, str(args.triage), args.threshold)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
