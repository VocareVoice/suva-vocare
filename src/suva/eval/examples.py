"""Parse Suva's example summaries and the labelled list of relevant rulings.

Run `python -m suva.eval.examples` to (re)write `data/eval/examples.jsonl` and
`data/eval/relevant_q4_2025_q1_2026.json` and print a coverage report.
"""

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[3]
JUDGEMENTS_DIR = REPO_ROOT / "judgements"
EVAL_DIR = REPO_ROOT / "data" / "eval"
RELEVANT_XLSX = JUDGEMENTS_DIR / "BG_Urteile_2025_Q4_2026_Q1.xlsx"
EXAMPLES_PATH = EVAL_DIR / "examples.jsonl"
RELEVANT_PATH = EVAL_DIR / "relevant_q4_2025_q1_2026.json"
SPLIT_PATH = EVAL_DIR / "split.json"
GLOSSARY_PATH = EVAL_DIR / "glossary.json"

DOCKET_RE = re.compile(r"(?<![0-9A-Za-z])(\d{1,2}[A-Z])[_ ]?(\d{1,4})[/_-](\d{4})(?!\d)")
AZA_DOCID_RE = re.compile(r"aza://(\d{2})-(\d{2})-(\d{4})-([0-9A-Z_-]+)")
DATE_RE = re.compile(r"(\d{1,2})(?:er)?\.?[\s-]+([^\W\d_]+)[\s-]+(\d{4})")
URL_RE = re.compile(r"https?://\S+")
AUTHOR_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<code>[^)]+)\)\s*,?\s*(?P<role>.*)$")

MONTHS = {
    **dict.fromkeys(["januar", "janvier", "gennaio"], 1),
    **dict.fromkeys(["februar", "février", "febbraio"], 2),
    **dict.fromkeys(["märz", "mars", "marzo"], 3),
    **dict.fromkeys(["april", "avril", "aprile"], 4),
    **dict.fromkeys(["mai", "maggio"], 5),
    **dict.fromkeys(["juni", "juin", "giugno"], 6),
    **dict.fromkeys(["juli", "juillet", "luglio"], 7),
    **dict.fromkeys(["august", "août", "agosto"], 8),
    **dict.fromkeys(["september", "septembre", "settembre"], 9),
    **dict.fromkeys(["oktober", "okober", "octobre", "ottobre"], 10),
    **dict.fromkeys(["november", "novembre"], 11),
    **dict.fromkeys(["dezember", "décembre", "dicembre"], 12),
}

# The heading wording tells which language the ruling itself was written in.
TITLE_LANGS = (
    ("BGer-Urteil", "de"),
    ("Entscheid", "de"),
    ("Urteil", "de"),
    ("Arrêt", "fr"),
    ("Sentenza", "it"),
)


@dataclass
class Example:
    docket: str
    source_file: str
    title: str
    ruling_date: str | None
    ruling_lang: str | None
    leading_case: bool
    text_de: str
    text_fr: str
    url: str | None
    author: str | None
    author_code: str | None
    author_role: str | None


@dataclass
class RelevantRuling:
    quarter: str
    label: str
    docket: str | None
    ruling_date: str | None
    ruling_lang: str | None
    created: str
    sharepoint_page: str | None
    has_example: bool


def normalise_docket(text: str) -> str | None:
    """Return the first docket in `text` as `8C_129/2025`, or None."""
    match = DOCKET_RE.search(text)
    if not match:
        return None
    division, number, year = match.groups()
    return f"{division}_{int(number)}/{year}"


def docket_sort_key(docket: str) -> tuple[str, int, int]:
    division, rest = docket.split("_", 1)
    number, year = rest.split("/")
    return division, int(year), int(number)


def parse_date(text: str) -> date | None:
    """Find a written-out DE/FR/IT date such as `4. August 2025` or `1er septembre 2025`."""
    for day, month, year in DATE_RE.findall(text):
        month_number = MONTHS.get(month.lower())
        if month_number:
            return date(int(year), month_number, int(day))
    return None


def title_language(title: str) -> str | None:
    for prefix, lang in TITLE_LANGS:
        if title.startswith(prefix):
            return lang
    return None


class _SummaryHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.sections: dict[str, list[str]] = {}
        self.hrefs: dict[str, list[str]] = {}
        self._tag: str | None = None
        self._section: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("h1", "h2", "p"):
            self._tag = tag
            self._buffer = []
        elif tag == "a" and self._section is not None:
            href = dict(attrs).get("href")
            if href:
                self.hrefs.setdefault(self._section, []).append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._tag:
            return
        text = " ".join("".join(self._buffer).split())
        if tag == "h1":
            self.title = text
        elif tag == "h2":
            self._section = text
            self.sections.setdefault(text, [])
        elif self._section is not None and text:
            self.sections[self._section].append(text)
        self._tag = None

    def handle_data(self, data: str) -> None:
        if self._tag:
            self._buffer.append(data)


def parse_example(path: Path) -> Example:
    parser = _SummaryHTML()
    parser.feed(path.read_text(encoding="utf-8"))
    sections = parser.sections

    link_texts = sections.get("Link zum Urteil", [])
    url = next(iter(parser.hrefs.get("Link zum Urteil", [])), None)
    if url is None:
        url = next((m.group(0) for t in link_texts for m in [URL_RE.search(t)] if m), None)

    ruling_date = None
    docket = None
    docid = AZA_DOCID_RE.search(url or "")
    if docid:
        day, month, year, docid_docket = docid.groups()
        ruling_date = date(int(year), int(month), int(day))
        docket = normalise_docket(docid_docket)
    docket = docket or normalise_docket(path.stem)
    if docket is None:
        raise ValueError(f"{path.name}: no docket in link or filename")
    ruling_date = ruling_date or parse_date(parser.title)

    author = author_code = author_role = None
    author_lines = sections.get("Autor", [])
    if author_lines:
        match = AUTHOR_RE.match(author_lines[0])
        if match:
            author, author_code, author_role = match["name"], match["code"], match["role"] or None
        else:
            author = author_lines[0]

    return Example(
        docket=docket,
        source_file=path.name,
        title=parser.title,
        ruling_date=ruling_date.isoformat() if ruling_date else None,
        ruling_lang=title_language(parser.title),
        leading_case=bool(re.search(r"pubblicazione|Publikation|publication", parser.title)),
        text_de="\n\n".join(sections.get("Text DE", [])),
        text_fr="\n\n".join(sections.get("Text FR", [])),
        url=url,
        author=author,
        author_code=author_code,
        author_role=author_role,
    )


def load_examples(judgements_dir: Path = JUDGEMENTS_DIR) -> list[Example]:
    examples = [parse_example(p) for p in judgements_dir.glob("*.html")]
    return sorted(examples, key=lambda e: docket_sort_key(e.docket))


def _resolve_partial_docket(
    label: str, ruling_date: date | None, examples: list[Example]
) -> str | None:
    """Resolve a label like `BGer-Urteil 458/2025` that lacks the division prefix."""
    match = re.search(r"(?<![\w/])(\d{1,4})/(\d{4})\b", label)
    if not match:
        return None
    suffix = f"_{int(match[1])}/{match[2]}"
    candidates = [
        e.docket
        for e in examples
        if e.docket.endswith(suffix)
        and (ruling_date is None or e.ruling_date == ruling_date.isoformat())
    ]
    return candidates[0] if len(candidates) == 1 else None


def load_relevant(xlsx_path: Path, examples: list[Example]) -> list[RelevantRuling]:
    from openpyxl import load_workbook

    by_docket = {e.docket: e for e in examples}
    sheet = load_workbook(xlsx_path).active
    rulings = []
    for row in sheet.iter_rows(min_row=2):
        quarter, label, created, link = (cell for cell in row[:4])
        if not label.value:
            continue
        label_text = str(label.value).strip()
        page = unquote(link.hyperlink.target.rsplit("/", 1)[-1]) if link.hyperlink else None
        page_text = (page or "").removesuffix(".aspx")

        ruling_date = parse_date(label_text) or parse_date(page_text)
        docket = normalise_docket(label_text) or _resolve_partial_docket(
            label_text, ruling_date, examples
        )
        example = by_docket.get(docket) if docket else None
        if ruling_date is None and example and example.ruling_date:
            ruling_date = date.fromisoformat(example.ruling_date)

        rulings.append(
            RelevantRuling(
                quarter=str(quarter.value).strip(),
                label=label_text,
                docket=docket,
                ruling_date=ruling_date.isoformat() if ruling_date else None,
                ruling_lang=title_language(page_text) or (example.ruling_lang if example else None),
                created=created.value.isoformat(),
                sharepoint_page=page,
                has_example=example is not None,
            )
        )
    return rulings


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_split(path: Path = SPLIT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def coverage_report(examples: list[Example], rulings: list[RelevantRuling]) -> dict:
    relevant_dockets = {r.docket for r in rulings if r.docket}
    return {
        "relevant_total": len(rulings),
        "relevant_with_example": [r.docket for r in rulings if r.has_example],
        "relevant_without_example": [r.docket or r.label for r in rulings if not r.has_example],
        "examples_outside_relevant_list": [
            e.docket for e in examples if e.docket not in relevant_dockets
        ],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judgements", type=Path, default=JUDGEMENTS_DIR)
    parser.add_argument("--xlsx", type=Path, default=RELEVANT_XLSX)
    parser.add_argument("--out", type=Path, default=EVAL_DIR)
    args = parser.parse_args(argv)

    examples = load_examples(args.judgements)
    rulings = load_relevant(args.xlsx, examples)
    report = coverage_report(examples, rulings)

    write_jsonl(args.out / EXAMPLES_PATH.name, [asdict(e) for e in examples])
    payload = {
        "source": args.xlsx.name,
        "description": (
            "Complete list of rulings Suva considered relevant in 2025 Q4 and 2026 Q1 "
            "(quarter of the ruling date). Every other ruling of that period is not relevant."
        ),
        "rulings": [asdict(r) for r in rulings],
        "coverage": report,
    }
    (args.out / RELEVANT_PATH.name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"{len(examples)} examples -> {args.out / EXAMPLES_PATH.name}")
    print(f"{len(rulings)} relevant rulings -> {args.out / RELEVANT_PATH.name}")
    for key in ("relevant_with_example", "relevant_without_example"):
        print(f"\n{key} ({len(report[key])}):")
        print("  " + ", ".join(report[key]))
    outside = report["examples_outside_relevant_list"]
    print(f"\nexamples_outside_relevant_list ({len(outside)}):")
    print("  " + ", ".join(outside))


if __name__ == "__main__":
    main()
