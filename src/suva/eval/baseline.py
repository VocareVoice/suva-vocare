"""Run the triage, summary and classification pipelines with another model, as a baseline.

Same pipeline code and prompts as the product, only the endpoint and the model change: a model
whose name starts with `gemini` goes to Gemini's OpenAI-compatible endpoint with
`GEMINI_API_KEY` from `.env`, any other to the gateway of `LLM_BASE_URL`. Every model gets its own
response cache under `data/cache/llm-baseline/`, so its calls, tokens and time are measured
from scratch and a rerun resumes. Results go to `--out` only, never to the app database or
`data/results/`. Results: docs/eval_baseline_gemini.md.

    python -m suva.eval.baseline classify --model gemini-3.8-flash --out DIR
    python -m suva.eval.baseline triage --model gemini-3.8-flash --out DIR [--scoring generated]
    python -m suva.eval.baseline summaries --model gemini-3.8-flash --out DIR
    python -m suva.eval.baseline blind DIR/summaries_a.jsonl DIR/summaries_b.jsonl --out DIR/blind

Gemini's endpoint returns no token logprobs, so its triage level is the generated digit;
`--scoring generated` scores Apertus the same way from the same (cached) replies.
"""

import argparse
import json
import random
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from suva import classify, summarize, triage
from suva.config import Settings
from suva.db import open_corpus
from suva.eval import score_classification, score_summaries, score_triage
from suva.eval.examples import (
    EXAMPLES_PATH,
    REPO_ROOT,
    docket_sort_key,
    load_split,
    read_jsonl,
)
from suva.eval.glossary import load_glossary
from suva.llm import Completion, LLMClient, Message

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "llm-baseline"
CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "rulings.jsonl.gz"
LABELLED_QUARTERS = ("2025 Q4", "2026 Q1")

_current = threading.local()


class BaselineSettings(Settings):
    gemini_api_key: str = ""


class MeteredClient(LLMClient):
    """`LLMClient` that logs every endpoint call (tokens, seconds, ruling) to `calls.jsonl`.

    Cache hits are not logged, so the log of a resumed run still counts each call once.
    """

    def __init__(
        self, model: str, log: Path, *, logprobs: bool = True, reasoning_effort: str | None = None
    ) -> None:
        base = BaselineSettings()
        settings = base.model_copy(update={"llm_cache_dir": CACHE_ROOT / model})
        self.gemini = model.startswith("gemini")
        if self.gemini:
            settings = settings.model_copy(
                update={"llm_base_url": GEMINI_BASE_URL, "llm_api_key": base.gemini_api_key}
            )
        super().__init__(settings, model=model)
        self.logprobs = logprobs and not self.gemini
        self.reasoning_effort = reasoning_effort
        self.task = ""
        self._log = log
        self._lock = threading.Lock()

    @property
    def client(self) -> Any:
        create = super().client.chat.completions.create

        def metered(**kwargs: Any) -> Any:
            start = time.monotonic()
            response = create(**kwargs)
            usage = response.usage
            details = getattr(usage, "completion_tokens_details", None)
            row = {
                "task": self.task,
                "model": self.model,
                "docket": getattr(_current, "docket", None),
                "prompt_tokens": usage.prompt_tokens if usage else None,
                # Billed output includes thinking tokens, which some endpoints leave out of
                # completion_tokens.
                "output_tokens": usage.total_tokens - usage.prompt_tokens if usage else None,
                "reasoning_tokens": getattr(details, "reasoning_tokens", None),
                "seconds": round(time.monotonic() - start, 2),
            }
            with self._lock, self._log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            return response

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=metered)))

    def complete(self, messages: list[Message], **params: Any) -> Completion:
        if self.gemini:
            # Gemini's endpoint rejects these fields.
            params.pop("logprobs", None)
            params.pop("top_logprobs", None)
        if self.reasoning_effort:
            params.setdefault("reasoning_effort", self.reasoning_effort)
        completion = super().complete(messages, **params)
        return completion if self.logprobs else completion._replace(logprobs=None)


def run_all(
    items: dict[str, Any], step: Callable[[Any], Any], workers: int
) -> dict[str, Any | Exception]:
    """`step` over `items` by docket in parallel; a failure is kept as its exception."""

    def one(docket: str) -> Any:
        _current.docket = docket
        try:
            return step(items[docket])
        finally:
            _current.docket = None

    results: dict[str, Any] = {}
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(one, docket): docket for docket in items}
        for future in as_completed(futures):
            docket = futures[future]
            try:
                results[docket] = future.result()
            except Exception as exc:
                results[docket] = exc
                print(f"{docket}: failed ({exc!r})")
    return results


def record_run(args: argparse.Namespace, task: str, started: float, results: dict, **extra) -> None:
    run = {
        "task": task,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        **extra,
        "rulings": len(results),
        "failed": sorted(d for d, r in results.items() if isinstance(r, Exception)),
        "wall_seconds": round(time.monotonic() - started, 1),
    }
    with (args.out / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")
    print(json.dumps(run))


def quarter(date: str | None) -> str | None:
    return f"{date[:4]} Q{(int(date[5:7]) - 1) // 3 + 1}" if date else None


def triage_report(
    scores: dict[str, float], quarters: dict[str, str], relevant: list[dict], label: str
) -> str:
    lines = [
        f"# Triage: {label}",
        "",
        "| quarter | scored | relevant | P@10 | P@30 | R@30 | R@60 |",
        "|---|---|---|---|---|---|---|",
    ]
    for q in (*LABELLED_QUARTERS, "both"):
        subset = {d: s for d, s in scores.items() if q in ("both", quarters[d])}
        wanted = {r["docket"] for r in relevant if r["docket"] and q in ("both", r["quarter"])}
        m = score_triage.evaluate(subset, wanted)
        lines.append(
            f"| {q} | {m['scored']} | {m['relevant']} | {m['precision@10']:.2f} "
            f"| {m['precision@30']:.2f} | {m['recall@30']:.2f} | {m['recall@60']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def run_triage(args: argparse.Namespace, llm: MeteredClient) -> None:
    with open_corpus(CORPUS_PATH) as f:
        rulings = {
            r["docket"]: r
            for r in map(json.loads, f)
            if r and quarter(r.get("decision_date")) in LABELLED_QUARTERS
        }
    examples = triage.load_examples(EXAMPLES_PATH)
    glossary = triage.load_glossary(EXAMPLES_PATH)
    started = time.monotonic()
    results = run_all(
        rulings, lambda r: triage.triage_ruling(r, llm, examples, glossary), args.workers
    )
    name = f"triage_{args.model}_{args.scoring}"
    with (args.out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
        for docket in sorted(results, key=docket_sort_key):
            r = results[docket]
            row = {"docket": docket, "quarter": quarter(rulings[docket]["decision_date"])}
            row |= {"error": repr(r)} if isinstance(r, Exception) else asdict(r)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    # A failed ruling is left out of the ranking, as if it had not been scored.
    scores = {d: r.score for d, r in results.items() if not isinstance(r, Exception)}
    llm_calls = sum(1 for r in results.values() if getattr(r, "model", None) == args.model)
    relevant = json.loads(score_triage.RELEVANT_PATH.read_text(encoding="utf-8"))["rulings"]
    quarters = {d: quarter(r["decision_date"]) for d, r in rulings.items()}
    report = triage_report(scores, quarters, relevant, f"`{args.model}`, {args.scoring} level")
    (args.out / f"{name}.md").write_text(report, encoding="utf-8")
    print(report)
    record_run(args, "triage", started, results, scoring=args.scoring, llm=llm_calls)


def run_summaries(args: argparse.Namespace, llm: MeteredClient) -> None:
    holdout = load_split()["holdout"]
    rulings = {d: r for d, r in score_classification.load_rulings().items() if d in holdout}
    started = time.monotonic()
    results = run_all(rulings, lambda r: summarize.summarize_ruling(r, llm), args.workers)
    path = args.out / f"summaries_{args.model}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for docket in holdout:
            r = results[docket]
            if isinstance(r, Exception):
                continue
            for lang, text in r.summaries.items():
                row = {"docket": docket, "lang": lang, "text": text}
                row["headline"] = r.headlines.get(lang)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    generated = score_summaries.load_generated(path)
    rows = score_summaries.score_all(
        generated, read_jsonl(EXAMPLES_PATH), holdout, load_glossary(score_summaries.GLOSSARY_PATH)
    )
    missing = [
        (d, lang) for d in holdout for lang in summarize.LANGUAGES if (d, lang) not in generated
    ]
    report = score_summaries.render_report(rows, missing, [], str(path))
    (args.out / f"summaries_{args.model}.md").write_text(report, encoding="utf-8")
    print(report)
    record_run(args, "summaries", started, results)


def run_classify(args: argparse.Namespace, llm: MeteredClient) -> None:
    gold = score_classification.load_gold()
    all_rulings = score_classification.load_rulings()
    rulings = {g["docket"]: all_rulings[g["docket"]] for g in gold}
    started = time.monotonic()
    results = run_all(rulings, lambda r: classify.classify_ruling(r, llm), args.workers)
    with (args.out / f"classification_{args.model}.jsonl").open("w", encoding="utf-8") as f:
        for docket in sorted(results, key=docket_sort_key):
            r = results[docket]
            row = {"docket": docket} | (
                {"error": repr(r)} if isinstance(r, Exception) else asdict(r)
            )
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    # A failed ruling counts as wrong: it gets the subject-line fallback the product would use.
    predicted = {
        d: classify.classify_subject(rulings[d], classify.facts(rulings[d]))
        if isinstance(r, Exception)
        else r
        for d, r in results.items()
    }
    m = score_classification.score(gold, predicted)
    methods = ", ".join(f"{n} {k}" for k, n in sorted(m["methods"].items()))
    wrong = [g["docket"] for g in gold if predicted[g["docket"]].primary != g["category"]]
    report = "\n".join(
        [
            f"# Classification: `{args.model}`",
            "",
            "| metric | value |",
            "|---|---|",
            f"| primary category correct | {m['primary']:.2f} |",
            f"| gold category among primary + secondary | {m['anywhere']:.2f} |",
            f"| branch correct ({m['n_branch']} with a branch label) | {m['branch']:.2f} |",
            "",
            f"{m['n']} rulings, prompt `{classify.PROMPT_VERSION}`; methods used: {methods}.",
            f"Primary category wrong: {', '.join(sorted(wrong, key=docket_sort_key))}.",
        ]
    )
    (args.out / f"classification_{args.model}.md").write_text(report + "\n", encoding="utf-8")
    print(report)
    record_run(args, "classify", started, results)


def write_blind(args: argparse.Namespace) -> None:
    """A reading packet with the two models' summaries as sides A and B, drawn at random per
    ruling, and the key in a separate file to open after the reading."""
    sides = [score_summaries.load_generated(p) for p in (args.first, args.second)]
    holdout = load_split()["holdout"]
    rulings = score_classification.load_rulings()
    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "rulings").mkdir(exist_ok=True)
    key, lines = {}, ["# Blind reading packet", ""]
    for docket in holdout:
        order = [0, 1]
        rng.shuffle(order)
        key[docket] = {"A": str(args.first if order[0] == 0 else args.second)}
        key[docket]["B"] = str(args.second if order[0] == 0 else args.first)
        ruling_file = f"rulings/{docket.replace('/', '_')}.txt"
        (args.out / ruling_file).write_text(rulings[docket]["text"], encoding="utf-8")
        lines += [f"## {docket}", "", f"Ruling: `{ruling_file}`", ""]
        for lang in summarize.LANGUAGES:
            for label, index in zip("AB", order, strict=True):
                text = sides[index].get((docket, lang), "(not generated)")
                lines += [f"### {label} ({lang})", "", text, ""]
    (args.out / "packet.md").write_text("\n".join(lines), encoding="utf-8")
    (args.out / "key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"Wrote {args.out / 'packet.md'}; key in {args.out / 'key.json'}")


def usage(out: Path) -> str:
    """Endpoint calls, tokens and model seconds per task and model, from `calls.jsonl`."""
    totals: dict[tuple[str, str], Counter] = defaultdict(Counter)
    dockets: dict[tuple[str, str], set] = defaultdict(set)
    for row in read_jsonl(out / "calls.jsonl"):
        key = (row["task"], row["model"])
        totals[key].update(
            calls=1,
            prompt=row["prompt_tokens"] or 0,
            output=row["output_tokens"] or 0,
            reasoning=row["reasoning_tokens"] or 0,
            seconds=row["seconds"],
        )
        dockets[key].add(row["docket"])
    lines = [
        "| task | model | calls | rulings | calls/ruling | prompt tokens | output tokens "
        "| of which thinking | model seconds |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (task, model), t in sorted(totals.items()):
        n = len(dockets[task, model])
        lines.append(
            f"| {task} | {model} | {t['calls']} | {n} | {t['calls'] / n:.1f} | {t['prompt']} "
            f"| {t['output']} | {t['reasoning']} | {t['seconds']:.0f} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m suva.eval.baseline", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, workers in (("triage", 8), ("summaries", 4), ("classify", 8)):
        sub = commands.add_parser(name)
        sub.add_argument("--model", required=True)
        sub.add_argument("--out", type=Path, required=True, help="directory for the results")
        sub.add_argument("--workers", type=int, default=workers)
        sub.add_argument("--reasoning-effort", help="passed to the endpoint with every call")
        if name == "triage":
            sub.add_argument(
                "--scoring",
                choices=("expected", "generated"),
                default="expected",
                help="relevance level from the digit's logprobs or the generated digit",
            )
    blind = commands.add_parser("blind")
    blind.add_argument("first", type=Path, help="summaries JSONL of one model")
    blind.add_argument("second", type=Path, help="summaries JSONL of the other model")
    blind.add_argument("--out", type=Path, required=True)
    blind.add_argument("--seed", type=int, default=0)
    report = commands.add_parser("usage", help="calls, tokens and model time from calls.jsonl")
    report.add_argument("out", type=Path)
    args = parser.parse_args(argv)

    if args.command == "blind":
        return write_blind(args)
    if args.command == "usage":
        return print(usage(args.out))
    args.out.mkdir(parents=True, exist_ok=True)
    if args.command == "triage" and args.scoring == "expected" and args.model.startswith("gemini"):
        parser.error("Gemini's endpoint returns no logprobs; use --scoring generated")
    llm = MeteredClient(
        args.model,
        args.out / "calls.jsonl",
        logprobs=getattr(args, "scoring", "expected") == "expected",
        reasoning_effort=args.reasoning_effort,
    )
    llm.task = args.command
    {"triage": run_triage, "summaries": run_summaries, "classify": run_classify}[args.command](
        args, llm
    )


if __name__ == "__main__":
    main()
