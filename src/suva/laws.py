"""The federal laws the agent quotes, as data: UVG, ATSG and UVV.

The UVG is not enough on its own: under Art. 1 UVG the ATSG applies to accident insurance unless
the UVG departs from it, so the definition of accident (Art. 4 ATSG), invalidity (Art. 7, 8, 16
ATSG), revision (Art. 17 ATSG), repayment (Art. 25 ATSG) and the procedure (Art. 49-61 ATSG) are
ATSG articles, and the UVV holds the details (insured earnings, integrity compensation). In
Suva's example summaries the ATSG is cited more often than the UVG.

`fetch` asks Fedlex's SPARQL endpoint for the consolidated version of each law in force today,
downloads its German and French HTML and parses every article (number, heading, the Title/Chapter it
belongs to and the text without footnotes). The result is committed as `data/laws/<law>.json`,
so the app never needs Fedlex at runtime. Annexes are not articles and are left out.

Run `python -m suva.laws [UVG ATSG UVV]` to refresh the snapshots.
"""

import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "laws"
LANGS = {"de": "DEU", "fr": "FRA"}


@dataclass(frozen=True)
class Law:
    code: str  # the German abbreviation, the key in LAWS
    sr: str
    eli: str  # path under fedlex.data.admin.ch/eli/ and www.fedlex.admin.ch/eli/
    names: dict[str, str]  # abbreviation per UI language
    titles: dict[str, str]
    aliases: tuple[str, ...]  # every abbreviation that names this law (de, fr, it)

    @property
    def snapshot(self) -> Path:
        return DATA_DIR / f"{self.code.lower()}.json"

    @property
    def base_url(self) -> str:
        return f"https://www.fedlex.admin.ch/eli/{self.eli}/"

    def page_url(self, lang: str, anchor: str = "") -> str:
        return f"{self.base_url}{lang}" + (f"#{anchor}" if anchor else "")


LAWS: dict[str, Law] = {
    law.code: law
    for law in [
        Law(
            "UVG",
            "832.20",
            "cc/1982/1676_1676_1676",
            {"de": "UVG", "fr": "LAA"},
            {
                "de": "Bundesgesetz über die Unfallversicherung",
                "fr": "Loi fédérale sur l'assurance-accidents",
            },
            ("UVG", "LAA", "LAINF"),
        ),
        Law(
            "ATSG",
            "830.1",
            "cc/2002/510",
            {"de": "ATSG", "fr": "LPGA"},
            {
                "de": "Bundesgesetz über den Allgemeinen Teil des Sozialversicherungsrechts",
                "fr": "Loi fédérale sur la partie générale du droit des assurances sociales",
            },
            ("ATSG", "LPGA"),
        ),
        Law(
            "UVV",
            "832.202",
            "cc/1983/38_38_38",
            {"de": "UVV", "fr": "OLAA"},
            {
                "de": "Verordnung über die Unfallversicherung",
                "fr": "Ordonnance sur l'assurance-accidents",
            },
            ("UVV", "OLAA", "OAINF"),
        ),
    ]
}
DEFAULT = "UVG"
ALIASES = {alias: law.code for law in LAWS.values() for alias in law.aliases}
# Any law abbreviation as a word; longest first so "OLAA" is not read as "LAA".
ALIAS_PATTERN = "|".join(sorted(map(re.escape, ALIASES), key=len, reverse=True))
_ALIAS = re.compile(rf"(?<![\w-])({ALIAS_PATTERN})(?![\w-])")

_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?date ?file WHERE {
  ?cons jolux:isMemberOf <%s> ; jolux:dateApplicability ?date ; jolux:isRealizedBy ?expr .
  ?expr jolux:language <http://publications.europa.eu/resource/authority/language/%s> ;
        jolux:isEmbodiedBy ?manif .
  ?manif jolux:isExemplifiedBy ?file .
  FILTER(CONTAINS(STR(?file), "/html/") && ?date <= "%s"^^xsd:date)
} ORDER BY DESC(?date) LIMIT 1
"""


def law_code(name: str | None) -> str | None:
    """ "ATSG", "lpga", "LAA" -> the German code ("ATSG", "UVG"); None for anything else."""
    return ALIASES.get((name or "").strip().upper())


def law_in(ref: str) -> str | None:
    """The law a citation names: "Art. 4 ATSG" -> "ATSG", "art. 18 OLAA" -> "UVV", "6" -> None."""
    match = _ALIAS.search(ref)
    return ALIASES[match.group(1)] if match else None


# ---------------------------------------------------------------- fetch and parse


def _latest_html(client: httpx.Client, law: Law, lang: str) -> tuple[str, str]:
    """(date in force, HTML file URL) of the consolidated version in force today in `lang`.

    Fedlex also lists versions that take effect later; those are skipped."""
    eli = f"https://fedlex.data.admin.ch/eli/{law.eli}"
    response = client.post(
        SPARQL,
        data={"query": _QUERY % (eli, LANGS[lang], date.today().isoformat())},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    rows = response.json()["results"]["bindings"]
    if not rows:
        raise LookupError(f"Fedlex has no consolidated {lang} HTML for {law.code} ({law.eli})")
    return rows[0]["date"]["value"], rows[0]["file"]["value"]


def _text(node: Tag) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _tidy(text: str) -> str:
    """Close the gaps the markup leaves: "1 a" -> "1a", "Titel a ." -> "Titel a."."""
    text = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s+", " ", text))
    return re.sub(r"\b(\d+) ([a-z])\b", r"\1\2", text).strip()


def _drop_footnote_refs(node: Tag) -> None:
    for ref in node.select("sup > a[href^='#fn']"):
        ref.parent.decompose()


def _section_path(article: Tag) -> list[str]:
    """Headings of the enclosing Title, Chapter and Section, outermost first."""
    path = []
    for section in article.find_parents("section"):
        heading = section.find(["h1", "h2", "h3", "h4", "h5"], recursive=False)
        if heading:
            heading = BeautifulSoup(str(heading), "html.parser")
            for sup in heading.find_all("sup"):
                sup.decompose()
            path.append(_tidy(_text(heading)))
    return path[::-1]


def _body(article: Tag) -> str:
    """Article text: paragraphs as "1 ...", list items as "a. ...", footnotes removed."""
    body = article.find("div", class_="collapseable")
    if body is None:
        return ""
    body = BeautifulSoup(str(body), "html.parser")
    for footnotes in body.find_all("div", class_="footnotes"):
        footnotes.decompose()
    _drop_footnote_refs(body)
    lines = []
    for node in body.find_all(["p", "dt", "dd"]):
        if node.find_parent(["dd", "p"]) is not None:
            continue  # nested; its text is part of the enclosing item
        text = _text(node)
        if not text:
            continue
        if node.name == "dd" and lines and re.fullmatch(r"[a-z0-9]+(?:bis|ter)?\.", lines[-1]):
            lines[-1] = f"{lines[-1]} {text}"
        else:
            lines.append(text)
    return "\n".join(lines)


def parse(html: str, lang: str, law: Law | None = None) -> list[dict[str, Any]]:
    law = law or LAWS[DEFAULT]
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    for article in soup.find_all("article", id=re.compile(r"^art_")):
        anchor = article["id"]
        heading = article.find("h6")
        if heading is None:
            continue
        _drop_footnote_refs(heading)
        # The number is set in markup inside the first link ("<b>Art. 90</b><i>c</i>
        # <sup>bis</sup>", "<b>Art. 40 </b>und <b>41</b>"); the title is the plain text after it,
        # in the same link or in later ones.
        links = heading.find_all("a")
        number, title = "", ""
        if links:
            parts = [_text(n) if isinstance(n, Tag) else str(n) for n in links[0].children]
            marked = [isinstance(n, Tag) for n in links[0].children]
            last = max((i for i, m in enumerate(marked) if m), default=-1)
            number = _tidy(re.sub(r"^Art\.\s*", "", " ".join(parts[: last + 1])))
            rest = [" ".join(parts[last + 1 :])] + [_text(a) for a in links[1:]]
            title = _tidy(re.sub(r"\s+", " ", " ".join(rest)))
        text = _body(article)
        if not text and re.search(r"\b(?:Aufgehoben|Abrogé)", _text(article)):
            text = "Aufgehoben." if lang == "de" else "Abrogé."
        articles.append(
            {
                "id": anchor,
                "number": number,
                "title": title,
                "path": _section_path(article),
                "text": text,
                "url": law.page_url(lang, anchor),
            }
        )
    return articles


def fetch(code: str = DEFAULT) -> dict[str, Any]:
    """Download law `code` as in force today, in German and French, and write its snapshot."""
    law = LAWS[code]
    result: dict[str, Any] = {"law": law.code, "sr": law.sr, "eli": law.eli, "languages": {}}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for lang in LANGS:
            in_force_, url = _latest_html(client, law, lang)
            response = client.get(url)
            response.raise_for_status()
            result["languages"][lang] = {
                "in_force": in_force_,
                "source": url,
                "articles": parse(response.content.decode("utf-8"), lang, law),
            }
    law.snapshot.parent.mkdir(parents=True, exist_ok=True)
    law.snapshot.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    _snapshot.cache_clear()
    articles.cache_clear()
    return result


# ---------------------------------------------------------------- lookups

_REF = re.compile(r"(\d+)[\s_]*([a-z](?![a-z]))?[\s_]*(bis|ter|quater|quinquies)?")


def key(number: str) -> str:
    """Normalise an article reference: "Art. 1 a", "1a", "art_1_a", "Art. 6 Abs. 2 UVG" ->
    "1a" / "6"; "" when there is no article number. The law name is ignored: use `law_in`."""
    match = _REF.search(_ALIAS.sub(" ", number).lower())
    return "".join(part or "" for part in match.groups()) if match else ""


@cache
def _snapshot(code: str) -> dict[str, Any]:
    return json.loads(LAWS[code].snapshot.read_text(encoding="utf-8"))


@cache
def articles(lang: str = "de", law: str = DEFAULT) -> dict[str, dict[str, Any]]:
    """Articles of law `law` by normalised number. Combined repealed articles such as
    "Art. 40 und 41" are reachable under each number."""
    by_key: dict[str, dict[str, Any]] = {}
    for article in _snapshot(law)["languages"][lang]["articles"]:
        parts = article["id"].removeprefix("art_").split("_")
        if len(parts) > 1 and all(p.isdigit() for p in parts):
            for part in parts:
                by_key[part] = article
        else:
            by_key["".join(parts)] = article
    return by_key


def in_force(lang: str = "de", law: str = DEFAULT) -> str:
    return _snapshot(law)["languages"][lang]["in_force"]


def get(number: str, lang: str = "de", law: str | None = None) -> dict[str, Any] | None:
    """The article `number` of `law`; without `law`, of the law the reference names ("Art. 4
    ATSG"), else of the UVG."""
    code = law or law_in(number) or DEFAULT
    return articles(lang, code).get(key(number))


def label(article: dict[str, Any], law: str, lang: str) -> str:
    """ "Art. 4 ATSG" / "art. 4 LPGA"."""
    return f"{'Art.' if lang == 'de' else 'art.'} {article['number']} {LAWS[law].names[lang]}"


def repealed(article: dict[str, Any]) -> bool:
    return bool(re.fullmatch(r"(?:Aufgehoben|Abrogé)[^.]*\.?", article["text"].strip()))


def outline(lang: str = "de", law: str = DEFAULT) -> str:
    """Every article heading of `law`, grouped under its Title/Chapter, one line each."""
    name = LAWS[law].names[lang]
    lines, last_path = [], None
    seen = set()
    for article in articles(lang, law).values():
        if article["id"] in seen:
            continue
        seen.add(article["id"])
        if article["path"] != last_path:
            lines.append("## " + " > ".join(article["path"]))
            last_path = article["path"]
        gone = "(aufgehoben)" if repealed(article) else ""
        parts = [f"Art. {article['number']} {name}", article["title"], gone]
        lines.append(" ".join(p for p in parts if p))
    return "\n".join(lines)


def outlines(lang: str = "de") -> str:
    """The outline of every law, each under a heading with its title, SR number and version."""
    blocks = []
    for law in LAWS.values():
        head = (
            f"# {law.names[lang]}: {law.titles[lang]} (SR {law.sr}), "
            f"Fassung in Kraft seit {in_force(lang, law.code)}"
        )
        blocks.append(f"{head}\n\n{outline(lang, law.code)}")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    for code in sys.argv[1:] or list(LAWS):
        data = fetch(law_code(code) or code)
        print(
            code,
            {lang: (v["in_force"], len(v["articles"])) for lang, v in data["languages"].items()},
        )
