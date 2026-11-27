"""Score generated summaries against Suva's human summaries.

Input is JSONL with one summary per row: `{"docket": "8C_78/2025", "lang": "de", "text": "..."}`.
Only the hold-out dockets of `data/eval/split.json` are scored unless `--all` is given.

    python -m suva.eval.score_summaries generated.jsonl [--all] [--judge] [--out report.md]

`--judge` additionally asks the LLM configured by `LLM_NAME`, `LLM_BASE_URL` and
`LLM_API_KEY` (via `suva.llm`) to grade each summary with the rubric in
`src/suva/prompts/judge_summary.md`.
"""

import argparse
import re
import statistics
from pathlib import Path
from string import Template

from suva.eval.examples import (
    EXAMPLES_PATH,
    GLOSSARY_PATH,
    SPLIT_PATH,
    load_split,
    normalise_docket,
    read_jsonl,
)
from suva.eval.glossary import load_glossary
from suva.eval.metrics import (
    chrf,
    citation_issues,
    foreign_statutes,
    glossary_usage,
    rouge_l,
    word_count,
)
from suva.llm import LLMClient, parse_json

JUDGE_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "judge_summary.md"
JUDGE_CRITERIA = ("legal_accuracy", "coverage", "style", "terminology")
LANGS = ("de", "fr")
LANGUAGE_NAMES = {"de": "German", "fr": "French"}


def score_text(candidate: str, reference: str, lang: str, glossary: dict) -> dict:
    usage = glossary_usage(candidate, reference, glossary, lang)
    words, ref_words = word_count(candidate), word_count(reference)
    return {
        "words": words,
        "ref_words": ref_words,
        "length_ratio": words / ref_words if ref_words else None,
        "rouge_l": rouge_l(candidate, reference),
        "chrf": chrf(candidate, reference),
        "glossary_recall": usage["recall"],
        "glossary_missing": usage["missing"],
        "style_issues": [
            *(f"avoid '{form}'" for form in usage["avoid_hits"]),
            *(f"foreign statute '{abbr}'" for abbr in foreign_statutes(candidate, glossary, lang)),
            *citation_issues(candidate, lang),
        ],
    }


def judge_prompt(docket: str, lang: str, candidate: str, reference: str) -> str:
    template = Template(JUDGE_PROMPT_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        docket=docket, language=LANGUAGE_NAMES[lang], reference=reference, candidate=candidate
    )


def parse_judgement(text: str) -> dict:
    try:
        data = parse_json(text)
    except ValueError:
        # Judges often put unescaped quotes into the free-text comment; the scores still parse.
        data = {c: m[1] for c in JUDGE_CRITERIA if (m := re.search(rf'"{c}"\s*:\s*(\d+)', text))}
        comment = re.search(r'"comment"\s*:\s*"(.*)"\s*}', text, re.S)
        data["comment"] = comment[1] if comment else ""
    if not isinstance(data, dict):
        raise ValueError(f"judge answer is not a JSON object: {text[:200]!r}")
    scores = {}
    for criterion in JUDGE_CRITERIA:
        value = int(data[criterion])
        if not 1 <= value <= 5:
            raise ValueError(f"{criterion}={value} is outside 1-5")
        scores[criterion] = value
    return {**scores, "comment": str(data.get("comment", "")).strip()}


def load_generated(path: Path) -> dict[tuple[str, str], str]:
    generated = {}
    for row in read_jsonl(path):
        docket = normalise_docket(row["docket"])
        if docket is None or row["lang"] not in LANGS:
            raise ValueError(f"bad row in {path}: docket={row['docket']!r} lang={row['lang']!r}")
        generated[docket, row["lang"]] = row["text"]
    return generated


def score_all(
    generated: dict[tuple[str, str], str],
    examples: list[dict],
    targets: list[str],
    glossary: dict,
    judge: LLMClient | None = None,
) -> list[dict]:
    by_docket = {e["docket"]: e for e in examples}
    rows = []
    for docket in targets:
        example = by_docket[docket]
        for lang in LANGS:
            candidate = generated.get((docket, lang))
            if candidate is None:
                continue
            reference = example[f"text_{lang}"]
            row = {
                "docket": docket,
                "lang": lang,
                "ref_original": example["ruling_lang"] == lang,
                **score_text(candidate, reference, lang, glossary),
            }
            if judge:
                prompt = judge_prompt(docket, lang, candidate, reference)
                row["judge"] = parse_judgement(judge.chat([{"role": "user", "content": prompt}]))
            rows.append(row)
    return rows


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return statistics.mean(present) if present else None


def _fmt(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _judge_mean(row: dict) -> float | None:
    judgement = row.get("judge")
    return statistics.mean(judgement[c] for c in JUDGE_CRITERIA) if judgement else None


def render_report(
    rows: list[dict], missing: list[tuple[str, str]], unknown: list[tuple[str, str]], source: str
) -> str:
    judged = any("judge" in row for row in rows)
    lines = [
        "# Summary evaluation",
        "",
        f"Generated summaries: `{source}`. Scored {len(rows)} summaries against Suva's human "
        "summaries. `orig` marks references written in the ruling's own language; the other "
        "language is usually the author's translation and a less reliable reference.",
        "",
        "## Overview",
        "",
        "| lang | n | length ratio | ROUGE-L | chrF | glossary recall | with style issues"
        + (" | judge (1-5) |" if judged else " |"),
        "|---|---|---|---|---|---|---" + ("|---|" if judged else "|"),
    ]
    for lang in (*LANGS, "all"):
        subset = [r for r in rows if lang in ("all", r["lang"])]
        if not subset:
            continue
        cells = [
            lang,
            str(len(subset)),
            _fmt(_mean([r["length_ratio"] for r in subset])),
            _fmt(_mean([r["rouge_l"] for r in subset])),
            _fmt(_mean([r["chrf"] for r in subset]), 1),
            _fmt(_mean([r["glossary_recall"] for r in subset])),
            str(sum(bool(r["style_issues"]) for r in subset)),
        ]
        if judged:
            cells.append(_fmt(_mean([_judge_mean(r) for r in subset])))
        lines.append("| " + " | ".join(cells) + " |")

    if judged:
        lines += ["", "| criterion | de | fr | all |", "|---|---|---|---|"]
        for criterion in JUDGE_CRITERIA:
            means = [
                _fmt(
                    _mean(
                        [
                            r["judge"][criterion]
                            for r in rows
                            if "judge" in r and lang in ("all", r["lang"])
                        ]
                    )
                )
                for lang in (*LANGS, "all")
            ]
            lines.append(f"| {criterion} | " + " | ".join(means) + " |")

    lines += [
        "",
        "## Per summary",
        "",
        "| docket | lang | words gen/ref | ratio | ROUGE-L | chrF | glossary | issues"
        + (" | judge |" if judged else " |"),
        "|---|---|---|---|---|---|---|---" + ("|---|" if judged else "|"),
    ]
    for r in rows:
        cells = [
            r["docket"],
            r["lang"] + (" (orig)" if r["ref_original"] else ""),
            f"{r['words']}/{r['ref_words']}",
            _fmt(r["length_ratio"]),
            _fmt(r["rouge_l"]),
            _fmt(r["chrf"], 1),
            _fmt(r["glossary_recall"]),
            "; ".join(r["style_issues"]) or "-",
        ]
        if judged:
            cells.append(_fmt(_judge_mean(r)))
        lines.append("| " + " | ".join(cells) + " |")

    details = [r for r in rows if r["glossary_missing"] or r.get("judge", {}).get("comment")]
    if details:
        lines += ["", "## Details", ""]
        for r in details:
            lines.append(f"- **{r['docket']} {r['lang']}**")
            if r["glossary_missing"]:
                lines.append(f"  - missing terms: {', '.join(r['glossary_missing'])}")
            if r.get("judge", {}).get("comment"):
                lines.append(f"  - judge: {r['judge']['comment']}")
    if missing:
        lines += ["", "## Not generated", ""]
        lines += [f"- {docket} {lang}" for docket, lang in missing]
    if unknown:
        lines += ["", "## Skipped (not a scored docket)", ""]
        lines += [f"- {docket} {lang}" for docket, lang in unknown]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated", type=Path, help="JSONL of docket/lang/text rows")
    parser.add_argument("--examples", type=Path, default=EXAMPLES_PATH)
    parser.add_argument("--split", type=Path, default=SPLIT_PATH)
    parser.add_argument("--glossary", type=Path, default=GLOSSARY_PATH)
    parser.add_argument("--all", action="store_true", help="score every docket with an example")
    parser.add_argument("--judge", action="store_true", help="add the LLM-judge rubric scores")
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    args = parser.parse_args(argv)

    examples = read_jsonl(args.examples)
    generated = load_generated(args.generated)
    targets = [e["docket"] for e in examples] if args.all else load_split(args.split)["holdout"]
    judge = LLMClient() if args.judge else None
    rows = score_all(generated, examples, targets, load_glossary(args.glossary), judge)
    missing = [(d, lang) for d in targets for lang in LANGS if (d, lang) not in generated]
    unknown = sorted(key for key in generated if key[0] not in targets)

    report = render_report(rows, missing, unknown, str(args.generated))
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
