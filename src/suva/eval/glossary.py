"""Load the DE/FR glossary and refresh its support counts from the examples.

Run `python -m suva.eval.glossary` after editing `data/eval/glossary.json`.
"""

import json
from pathlib import Path

from suva.eval.examples import EXAMPLES_PATH, GLOSSARY_PATH, read_jsonl
from suva.eval.metrics import contains_term, term_support


def load_glossary(path: Path = GLOSSARY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def with_support(glossary: dict, examples: list[dict]) -> dict:
    terms = [{**term, "support": term_support(term, examples)} for term in glossary["terms"]]
    statutes = [
        {
            **statute,
            "support": sum(
                contains_term(e["text_de"], [statute["de"]])
                and contains_term(e["text_fr"], [statute["fr"]])
                for e in examples
            ),
        }
        for statute in glossary["statutes"]
    ]
    return {**glossary, "statutes": statutes, "terms": terms}


def dumps(glossary: dict) -> str:
    """One list entry per line, so diffs of the hand-curated file stay readable."""
    lines = ["{"]
    keys = list(glossary)
    for i, key in enumerate(keys):
        value = glossary[key]
        comma = "," if i < len(keys) - 1 else ""
        if isinstance(value, list):
            items = [json.dumps(item, ensure_ascii=False) for item in value]
            lines.append(f"  {json.dumps(key)}: [")
            lines.extend(
                f"    {item}{',' if j < len(items) - 1 else ''}" for j, item in enumerate(items)
            )
            lines.append(f"  ]{comma}")
        else:
            lines.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> None:
    glossary = with_support(load_glossary(), read_jsonl(EXAMPLES_PATH))
    GLOSSARY_PATH.write_text(dumps(glossary), encoding="utf-8")
    unsupported = [t["de"] for t in glossary["terms"] if t["support"] == 0]
    print(
        f"{len(glossary['terms'])} terms, {len(glossary['statutes'])} statutes -> {GLOSSARY_PATH}"
    )
    if unsupported:
        print("terms without support:", ", ".join(unsupported))


if __name__ == "__main__":
    main()
