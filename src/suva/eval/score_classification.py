"""Score the classification against the topic and branch labels of Suva's 55 example summaries.

The labels in `split.json` map onto the taxonomy of `suva.classify`; the full rulings are in
`example_rulings.jsonl.gz` (fetched from entscheidsuche.ch, as the corpus). Every ruling is
classified twice: as `suva classify` does (Apertus for rulings that pass the triage pre-filter)
and from the subject line alone, the fallback for all other rulings.

    python -m suva.eval.score_classification [--out docs/eval_classification.md] [--workers 8]
"""

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from suva import classify
from suva.db import open_corpus
from suva.eval.examples import EVAL_DIR, SPLIT_PATH, docket_sort_key
from suva.llm import LLMClient

RULINGS_PATH = EVAL_DIR / "example_rulings.jsonl.gz"

TOPICS = {
    "einkommensvergleich": "invaliditaetsgrad",
    "verfahren": "verfahren",
    "natuerliche-kausalitaet": "natuerliche-kausalitaet",
    "adaequate-kausalitaet": "adaequate-kausalitaet",
    "rentenrevision": "rentenrevision",
    "unfallbegriff": "unfallbegriff",
    "listenverletzung": "unfallbegriff",
    "hilflosigkeit-pflege": "hilflosigkeit-pflege",
    "taggeld-leistungskuerzung": "taggeld-leistungskuerzung",
    "beweis-gutachten": "beweis-gutachten",
    "unterstellung": "unterstellung-praemien",
    "integritaetsentschaedigung": "integritaetsentschaedigung",
    "berufskrankheit": "berufskrankheit",
    "rueckforderung-erlass": "rueckforderung-erlass",
    "haftung": "regress-haftung",
}
# "general" means the branch cannot be told from the summary; those rulings only count for the
# category. VVG is private insurance, outside social insurance.
BRANCHES = {"UV": "uv", "IV": "iv", "VVG": "other", "general": None}


def load_gold(path: Path = SPLIT_PATH) -> list[dict[str, Any]]:
    labels = json.loads(path.read_text(encoding="utf-8"))["labels"]
    return [
        {
            "docket": label["docket"],
            "category": TOPICS[label["topic"]],
            "branch": BRANCHES[label["branch"]],
        }
        for label in labels
    ]


def load_rulings(path: Path = RULINGS_PATH) -> dict[str, dict[str, Any]]:
    with open_corpus(path) as f:
        return {r["docket"]: r for r in map(json.loads, f) if r}


def score(gold: list[dict[str, Any]], predicted: dict[str, classify.Classification]) -> dict:
    with_branch = [g for g in gold if g["branch"]]
    primary = sum(predicted[g["docket"]].primary == g["category"] for g in gold)
    anywhere = sum(
        g["category"] in (predicted[g["docket"]].primary, *predicted[g["docket"]].secondary)
        for g in gold
    )
    branch = sum(predicted[g["docket"]].branch == g["branch"] for g in with_branch)
    return {
        "n": len(gold),
        "primary": primary / len(gold),
        "anywhere": anywhere / len(gold),
        "n_branch": len(with_branch),
        "branch": branch / len(with_branch),
        "methods": Counter(p.method for p in predicted.values()),
    }


def _label(slug: str) -> str:
    return classify.CATEGORIES[slug].de.split(" (")[0]


def _cell(c: classify.Classification, gold: str) -> str:
    mark = "ok" if c.primary == gold else "**x**"
    extra = f" (+ {', '.join(map(_label, c.secondary))})" if c.secondary else ""
    return f"{c.branch} / {_label(c.primary)}{extra} {mark}"


def render_report(
    gold: list[dict[str, Any]],
    llm: dict[str, classify.Classification],
    subject: dict[str, classify.Classification],
    subjects: dict[str, str],
    model: str,
) -> str:
    a, b = score(gold, llm), score(gold, subject)
    methods = ", ".join(f"{n} {m}" for m, n in sorted(a["methods"].items()))
    lines = [
        "| | `suva classify` (Apertus) | subject line only |",
        "|---|---|---|",
        f"| primary category correct | {a['primary']:.2f} | {b['primary']:.2f} |",
        f"| gold category among primary + secondary | {a['anywhere']:.2f} | {b['anywhere']:.2f} |",
        f"| branch correct ({a['n_branch']} rulings with a branch label) "
        f"| {a['branch']:.2f} | {b['branch']:.2f} |",
        "",
        f"{a['n']} rulings, model `{model}`, prompt `{classify.PROMPT_VERSION}`; "
        f"methods used: {methods}.",
        "",
        "| ruling | gold | Apertus | subject line | subject |",
        "|---|---|---|---|---|",
    ]
    for g in sorted(gold, key=lambda g: docket_sort_key(g["docket"])):
        p, s = llm[g["docket"]], subject[g["docket"]]
        lines.append(
            f"| {g['docket']} | {g['branch'] or '-'} / {_label(g['category'])} "
            f"| {_cell(p, g['category'])} | {_cell(s, g['category'])} "
            f"| {subjects[g['docket']]} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m suva.eval.score_classification")
    parser.add_argument("--out", type=Path, help="write the Markdown tables here")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    gold = load_gold()
    rulings = load_rulings()
    llm = LLMClient()

    dockets = [g["docket"] for g in gold]
    facts = {d: classify.facts(rulings[d]) for d in dockets}
    with ThreadPoolExecutor(args.workers) as pool:
        results = pool.map(lambda d: classify.classify_ruling(rulings[d], llm), dockets)
        predicted = dict(zip(dockets, results, strict=True))
    report = render_report(
        gold,
        predicted,
        {d: classify.classify_subject(rulings[d], facts[d]) for d in dockets},
        {d: facts[d].subject for d in dockets},
        llm.model,
    )
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
