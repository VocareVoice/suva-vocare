"""Turn the agent's citations into links, but only to things that exist.

The agent cites `[[UVG 6]]` / `[[Art. 6 Abs. 2 UVG]]` / `[[Art. 4 ATSG]]` and `[[8C_129/2025]]`;
bare mentions ("Art. 6 Abs. 2 UVG", "art. 18 OLAA", "8C_129/2025") are linked too. An article of
a law in `suva.laws` (UVG, ATSG, UVV, under their German or French abbreviation) becomes a
Fedlex link, a ruling in the knowledge base an in-app link (#/r/...). A citation without a law
name ("Art. 6") means the UVG. Citations of articles or rulings that do not exist stay plain
text, marked as unverified, so a made-up reference never looks like a source. Markdown links
the model writes itself are kept only when they point to one of those targets.
"""

import re
import sqlite3
from typing import Any
from urllib.parse import quote, unquote

from suva import laws

DOCKET = r"\d{1,2}[A-Z]_\d{1,5}/\d{4}"
_LAW_REF = (
    r"(?:Art\.|art\.|Artikel|article)\s*\d+\s*[a-z]?(?:\s*(?:bis|ter|quater))?"
    r"(?:\s*(?:Abs\.|al\.|Bst\.|lit\.|let\.|Ziff\.|ch\.)\s*\d*[a-z]?)*"
    rf"\s+(?:{laws.ALIAS_PATTERN})(?![\w-])"
)
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_TOKEN = re.compile(r"\[\[([^\]\n]+)\]\]")
_BARE = re.compile(rf"({_LAW_REF})|\b({DOCKET})\b")
# Wraps links already resolved while the rest is scanned: a private-use character, which is
# removed from the model's text first, so the text cannot forge a placeholder.
_MARK = ""
_FEDLEX = tuple(law.base_url for law in laws.LAWS.values())


def ruling_href(docket: str) -> str:
    return "#/r/" + quote(docket, safe="")


class Linker:
    def __init__(self, conn: sqlite3.Connection, lang: str = "de") -> None:
        self.conn = conn
        self.lang = lang if lang in laws.LANGS else "de"
        self.refs: dict[str, dict[str, Any]] = {}  # every verified reference, by href

    def _ruling(self, docket: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT docket, title FROM rulings WHERE docket = ?", (docket,)
        ).fetchone()
        return dict(row) if row else None

    def _resolve(self, ref: str) -> tuple[str, str] | None:
        """(label, href) for a citation, None when it names nothing that exists."""
        ref = ref.strip()
        if m := re.fullmatch(rf"(?:BGer\s+|Urteil\s+|arrêt\s+)?({DOCKET})", ref):
            ruling = self._ruling(m.group(1))
            if ruling is None:
                return None
            href = ruling_href(ruling["docket"])
            self.refs[href] = {"type": "ruling", "docket": ruling["docket"], "href": href}
            return ruling["docket"], href
        code = laws.law_in(ref)
        if code or re.fullmatch(r"(?:Art\.\s*)?\d+\s*[a-z]?", ref):
            code = code or laws.DEFAULT
            if not laws.key(ref):
                return None
            article = laws.get(ref, self.lang, code)
            if article is None:
                return None
            # Keep the precise form the model wrote ("Art. 6 Abs. 2 UVG") as the label.
            label = ref if re.search(r"^(?:Art|art)", ref) else laws.label(article, code, self.lang)
            self.refs[article["url"]] = {
                "type": "law",
                "law": code,
                "article": article["number"],
                "href": article["url"],
            }
            return label, article["url"]
        return None

    def render(self, text: str) -> str:
        """`text` with citations as markdown links; unknown citations as plain text."""
        kept: list[str] = []

        def hold(markdown: str) -> str:
            kept.append(markdown)
            return f"{_MARK}{len(kept) - 1}{_MARK}"

        def own_link(m: re.Match[str]) -> str:
            label, href = m.group(1), m.group(2)
            if href.startswith(_FEDLEX) or href.startswith("#/r/"):
                resolved = self._resolve(label) or self._resolve_href(href)
                if resolved:
                    return hold(f"[{label}]({resolved[1]})")
            return label  # unverifiable link target: keep the words, drop the link

        def token(m: re.Match[str]) -> str:
            resolved = self._resolve(m.group(1))
            if resolved is None:
                return hold(f"{m.group(1)} (?)")
            return hold(f"[{resolved[0]}]({resolved[1]})")

        def bare(m: re.Match[str]) -> str:
            resolved = self._resolve(m.group(0))
            return hold(f"[{m.group(0)}]({resolved[1]})") if resolved else m.group(0)

        text = re.sub(rf"[{_MARK}\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        text = _MD_LINK.sub(own_link, text)
        text = _TOKEN.sub(token, text)
        text = _BARE.sub(bare, text)
        return re.sub(rf"{_MARK}(\d+){_MARK}", lambda m: kept[int(m.group(1))], text)

    def _resolve_href(self, href: str) -> tuple[str, str] | None:
        if href.startswith("#/r/"):
            return self._resolve(unquote(href[4:]))
        law = next((law for law in laws.LAWS.values() if href.startswith(law.base_url)), None)
        if law and (m := re.search(r"#art_([\w]+)$", href)):
            return self._resolve(f"Art. {m.group(1)} {law.code}")
        return None
