import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from suva.fetch.entscheidsuche import Entry

SUBJECT_LABELS = ("Gegenstand", "Objet", "Oggetto")
WHITESPACE_RE = re.compile(r"\s+")


def paragraphs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [WHITESPACE_RE.sub(" ", para.get_text()).strip() for para in soup.select("div.para")]


def plain_text(paras: list[str]) -> str:
    lines: list[str] = []
    for para in paras:
        if para or (lines and lines[-1]):
            lines.append(para)
    return "\n".join(lines).strip()


def subject(paras: list[str]) -> str | None:
    """The block following the `Gegenstand` / `Objet` / `Oggetto` label."""
    for i, para in enumerate(paras):
        if para.rstrip(": ") not in SUBJECT_LABELS:
            continue
        block: list[str] = []
        for following in paras[i + 1 :]:
            if not following:
                if block:
                    break
                continue
            block.append(following)
        title = " ".join(block).strip().rstrip(",").strip()
        return title or None
    return None


def bger_url(entry: Entry) -> str:
    docid = f"aza://{entry.decision_date:%d-%m-%Y}-{entry.docket.replace('/', '-')}"
    return (
        "https://www.bger.ch/ext/eurospider/live/de/php/aza/http/index.php"
        f"?lang=de&type=show_document&highlight_docid={quote(docid, safe='')}"
    )


def build_record(entry: Entry, meta: dict, html: str) -> dict:
    paras = paragraphs(html)
    title = subject(paras)
    if title is None and meta.get("Abstract"):
        title = meta["Abstract"][0]["Text"].split(" | ")[0].strip() or None
    return {
        "docket": entry.docket,
        "decision_date": entry.decision_date.isoformat(),
        "publication_date": None,
        "division": entry.docket.split("_")[0],
        "language": meta.get("Sprache"),
        "title": title,
        "url": bger_url(entry),
        "text": plain_text(paras),
        "source": "entscheidsuche.ch",
    }
