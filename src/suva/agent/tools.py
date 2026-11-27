"""Tools of the side-panel agent. Each takes keyword arguments from the model's JSON call and
returns plain text for the model to read. Lookups never write; `propose_summary` stores a
proposal that changes nothing until the user applies it in the chat; `update_memory` changes the
agent's memory at once (the user sees the step and edits or resets it on the knowledge page)."""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from suva import classify, db, laws
from suva.agent import memory
from suva.eval.metrics import citation_issues, word_count

RULING_PAGE = 24_000  # characters of ruling text per read_ruling call
SUMMARY_PREVIEW = 700  # characters of each summary in list_rulings


class ToolError(Exception):
    """A problem the model can fix (unknown docket, missing argument): reported back to it."""


@dataclass
class Context:
    conn: sqlite3.Connection
    chat_id: str
    lang: str = "de"  # UI language: summaries and law texts in this language first
    proposals: list[int] = field(default_factory=list)  # made during the current turn
    read: set[str] = field(default_factory=set)  # rulings read with read_ruling this turn


@dataclass
class Tool:
    name: str
    signature: str
    description: str
    run: Callable[..., str]
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON schema of the arguments

    def schema(self) -> dict[str, Any]:
        """The tool as the OpenAI `tools` parameter declares it (native Apertus tool calling)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}, **self.parameters},
            },
        }


def _require(value: Any, name: str) -> Any:
    if value in (None, ""):
        raise ToolError(f"Argument «{name}» fehlt.")
    return value


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


# ---------------------------------------------------------------- laws


def read_article(ctx: Context, law: str = "", art: str = "", lang: str | None = None) -> str:
    """One article of the UVG, ATSG or UVV. The law comes from `law` or from the reference
    itself ("4 ATSG"); a reference naming a different law than `law` is an error, never a
    silent lookup in the wrong law."""
    lang = lang if lang in laws.LANGS else ctx.lang
    ref = str(_require(art, "art"))
    known = ", ".join(laws.LAWS)
    given = laws.law_code(law) if law else None
    if law and given is None:
        raise ToolError(f"Unbekanntes Gesetz «{law}». Verfügbar: {known}.")
    named = laws.law_in(ref)
    if given and named and given != named:
        raise ToolError(f"«{ref}» nennt das {named}, law ist aber {given}. Gib nur eines an.")
    code = given or named or laws.DEFAULT
    if not laws.key(ref):
        raise ToolError(f'«{ref}» enthält keine Artikelnummer, z. B. "4" oder "1a".')
    article = laws.get(ref, lang, code)
    if article is None:
        raise ToolError(
            f"Art. {laws.key(ref)} {code} gibt es nicht. Nimm eine Nummer aus der Übersicht."
        )
    head = laws.label(article, code, lang) + (f" – {article['title']}" if article["title"] else "")
    return "\n".join(
        [
            head,
            f"Fassung in Kraft seit {laws.in_force(lang, code)} (aktuelle Fassung; ein Urteil "
            "wendet oft die zur Zeit des Unfalls geltende Fassung an)",
            "Gliederung: " + " > ".join(article["path"]),
            f"Link: {article['url']}",
            "",
            article["text"] or "(kein Text)",
        ]
    )


# ---------------------------------------------------------------- knowledge base


def _statutes(cited: str | list[dict[str, Any]] | None, limit: int = 8) -> str:
    """Substantive provisions cited, most cited first; BGG procedure left out as noise."""
    if isinstance(cited, str) or cited is None:
        cited = json.loads(cited or "[]")
    kept = [s for s in cited if s["law"] != "BGG"]
    return ", ".join(f"Art. {s['art']} {s['law']}" for s in kept[:limit])


def _category_label(slug: str | None, lang: str) -> str:
    label = classify.CATEGORIES.get(slug or "")
    return (label.fr if lang == "fr" else label.de) if label else ""


def list_rulings(
    ctx: Context,
    query: str = "",
    category: str = "",
    relevant_only: bool = True,
    limit: int = 80,
) -> str:
    """Rulings of the knowledge base with headline data and summary."""
    if category and category not in classify.CATEGORIES:
        raise ToolError(
            f"Unbekannte Kategorie «{category}». Erlaubt: {', '.join(classify.CATEGORIES)}"
        )
    limit = max(1, min(int(limit or 80), 150))
    total, items = db.list_rulings(
        ctx.conn,
        q=query or None,
        category=category or None,
        label="relevant" if relevant_only else None,
        sort="date",
        order="desc",
        limit=limit,
    )
    if not items:
        return (
            "Keine Urteile gefunden. Versuche andere Stichwörter, ohne Kategorie, "
            "oder search_rulings."
        )
    dockets = [item["docket"] for item in items]
    marks = ",".join("?" * len(dockets))
    summaries: dict[str, dict[str, str]] = {}
    for row in ctx.conn.execute(
        f"SELECT docket, lang, text FROM summaries WHERE docket IN ({marks}) ORDER BY id", dockets
    ):
        summaries.setdefault(row["docket"], {})[row["lang"]] = row["text"]
    statutes = {
        row["docket"]: row["statutes"]
        for row in ctx.conn.execute(
            f"SELECT c.docket, c.statutes FROM classification c WHERE c.docket IN ({marks}) "
            "AND c.id = (SELECT MAX(id) FROM classification WHERE docket = c.docket)",
            dockets,
        )
    }
    out = [f"{total} Urteile gefunden, {len(items)} gezeigt (neueste zuerst)."]
    for item in items:
        cls = item.get("classification") or {}
        date = item.get("decision_date") or item.get("publication_date") or ""
        line = [f"\n## {item['docket']} ({date}) – {item.get('title') or ''}".rstrip(" –")]
        if cls:
            line.append(f"Kategorie: {_category_label(cls.get('primary'), ctx.lang)}")
        if cited := _statutes(statutes.get(item["docket"])):
            line.append(f"Zitierte Normen: {cited}")
        if item.get("score") is not None:
            line.append(f"Relevanz für die Suva: {item['score']}/100")
        texts = summaries.get(item["docket"], {})
        text = texts.get(ctx.lang) or next(iter(texts.values()), "")
        line.append(
            "Zusammenfassung: " + _clip(text, SUMMARY_PREVIEW)
            if text
            else "Noch keine Zusammenfassung."
        )
        out.append("\n".join(line))
    return "\n".join(out)


def search_rulings(ctx: Context, query: str = "", limit: int = 15) -> str:
    """Full-text search over the text of every ruling (not only the relevant ones)."""
    query = str(_require(query, "query"))
    limit = max(1, min(int(limit or 15), 40))
    sql = (
        "SELECT r.docket, r.decision_date, r.title, "
        "snippet(rulings_fts, 2, '«', '»', ' … ', 28) AS snip, "
        f"(SELECT t.score FROM triage t WHERE t.docket = r.docket {db._TRIAGE_ORDER}) "
        "AS score "
        "FROM rulings_fts JOIN rulings r ON r.id = rulings_fts.rowid "
        "WHERE rulings_fts MATCH ? ORDER BY bm25(rulings_fts) LIMIT ?"
    )
    rows = ctx.conn.execute(sql, (db.fts_query(query), limit)).fetchall()
    mode = "alle Wörter"
    if not rows:  # no ruling has every word: rank by any of them
        any_word = " OR ".join(db.fts_query(word) for word in query.split())
        rows = ctx.conn.execute(sql, (any_word, limit)).fetchall()
        mode = "irgendeines der Wörter"
    if not rows:
        return "Kein Urteil enthält diese Wörter."
    out = [f"{len(rows)} Treffer ({mode}), beste zuerst:"]
    for row in rows:
        score = f", Relevanz {row['score']}/100" if row["score"] is not None else ""
        out.append(
            f"\n## {row['docket']} ({row['decision_date'] or ''}{score}) – {row['title'] or ''}\n"
            f"{row['snip']}"
        )
    return "\n".join(out)


def read_ruling(ctx: Context, docket: str = "", offset: int = 0) -> str:
    docket = str(_require(docket, "docket")).strip()
    detail = db.get_ruling_detail(ctx.conn, docket)
    if detail is None:
        raise ToolError(f"Das Urteil {docket} ist nicht in der Wissensdatenbank.")
    ctx.read.add(detail["docket"])
    offset = max(0, int(offset or 0))
    text = detail["text"] or ""
    out = []
    if offset == 0:
        cls = detail.get("classification") or {}
        triage = detail.get("triage") or {}
        out += [
            f"# {detail['docket']} – {detail.get('title') or ''}",
            f"Datum: {detail.get('decision_date') or ''}, "
            f"Abteilung: {detail.get('division') or ''}, "
            f"Sprache: {detail.get('language') or ''}",
        ]
        if cls:
            out.append(f"Kategorie: {_category_label(cls.get('primary'), ctx.lang)}")
            if cited := _statutes(cls.get("statutes"), limit=12):
                out.append(f"Zitierte Normen: {cited}")
        if triage:
            reason = triage.get("reasoning_fr" if ctx.lang == "fr" else "reasoning_de") or ""
            out.append(f"Relevanz für die Suva: {triage.get('score')}/100. {reason}".strip())
        for lang in ("de", "fr"):
            summary = (detail["summaries"] or {}).get(lang)
            out.append(
                f"\nAktuelle Zusammenfassung {lang.upper()}:\n"
                + (summary["text"] if summary else "(keine)")
            )
        out.append("\nUrteilstext:")
    page = text[offset : offset + RULING_PAGE]
    out.append(page)
    end = offset + len(page)
    if end < len(text):
        out.append(f"\n[… Zeichen {offset}–{end} von {len(text)}. Weiter mit offset={end}.]")
    return "\n".join(out)


# ---------------------------------------------------------------- summaries


def propose_summary(
    ctx: Context, docket: str = "", lang: str = "", text: str = "", rationale: str = ""
) -> str:
    docket = str(_require(docket, "docket")).strip()
    if lang not in ("de", "fr"):
        raise ToolError("lang muss «de» oder «fr» sein.")
    text = str(_require(text, "text")).strip()
    if db.get_ruling(ctx.conn, docket) is None:
        raise ToolError(f"Das Urteil {docket} ist nicht in der Wissensdatenbank.")
    if docket not in ctx.read:
        # A summary written from memory is not checked against the ruling: read it first.
        raise ToolError(
            f'Lies das Urteil zuerst mit read_ruling {{"docket": "{docket}"}} und schreibe '
            "die Zusammenfassung dann aus dem Urteilstext."
        )
    proposal_id = db.add_proposal(
        ctx.conn, ctx.chat_id, docket, lang=lang, text=text, rationale=str(rationale or "")
    )
    ctx.proposals.append(proposal_id)
    notes = citation_issues(text, lang)
    words = word_count(text)
    result = (
        f"Vorschlag #{proposal_id} für {docket} ({lang.upper()}, {words} Wörter) gespeichert. "
        "Er wird dem Benutzer als Karte mit «Übernehmen»/«Verwerfen» gezeigt; geändert ist noch "
        "nichts. Sage dem Benutzer, dass er den Vorschlag prüfen und übernehmen kann."
    )
    if notes:
        result += " Hinweise der Stilprüfung: " + "; ".join(notes)
    return result


# ---------------------------------------------------------------- memory

# After saving, the model tended to go on researching the ruling open in the UI: stop it there.
MEMORY_SAVED = (
    "Er gilt ab der nächsten Frage. Hat der Benutzer nur um das Merken gebeten, bestätige ihm "
    "jetzt in einem Satz, was du gespeichert hast, ohne weitere Tool-Aufrufe und ohne "
    "Fallbeurteilung."
)


def update_memory(ctx: Context, content: str = "", mode: str = "append") -> str:
    """Add to the agent's knowledge text or rewrite it."""
    content = str(_require(content, "content")).strip()
    if mode not in ("append", "replace"):
        raise ToolError("mode muss «append» oder «replace» sein.")
    old = memory.text(ctx.conn)
    new = f"{old.rstrip()}\n\n{content}" if mode == "append" else content
    if len(new) > memory.MAX_CONTENT:
        raise ToolError(
            f"Der Text würde zu lang (höchstens {memory.MAX_CONTENT} Zeichen, er kostet bei "
            "jeder Frage Kontext). Fasse die Regel kürzer oder lass den Benutzer auf der Seite "
            "«Agent-Wissen» kürzen."
        )
    memory.save(ctx.conn, new, updated_by="agent")
    if mode == "append":
        return f"Dein Wissen ist ergänzt. {MEMORY_SAVED}"
    return f"Dein Wissen ist neu geschrieben. {MEMORY_SAVED}\n\nBisheriger Text:\n{old}"


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        Tool(
            "read_article",
            '{"law": "ATSG", "art": "4"}  (optional "lang": "de"|"fr")',
            "Volltext eines Artikels des UVG, ATSG oder der UVV mit Fedlex-Link. law ist "
            '"UVG", "ATSG" oder "UVV" (ohne law: UVG), art die Nummer aus der Übersicht, '
            'z. B. "6" oder "1a". Nur für den Fall einschlägige Artikel.',
            read_article,
            {
                "properties": {
                    "law": {"type": "string", "enum": list(laws.LAWS), "description": "Erlass"},
                    "art": {"type": "string", "description": 'Artikelnummer, z. B. "6" oder "1a"'},
                    "lang": {"type": "string", "enum": ["de", "fr"]},
                },
                "required": ["law", "art"],
            },
        ),
        Tool(
            "list_rulings",
            '{"query": "", "category": "", "relevant_only": true, "limit": 80}',
            "Urteile der Wissensdatenbank mit Titel, Datum, Kategorie, zitierten Normen und "
            "Zusammenfassung. Ohne Argumente: alle für die Suva relevanten Urteile. query: "
            "Stichwörter (alle müssen vorkommen), category: eine Kategorie aus der Liste, "
            "relevant_only=false: auch nicht relevante Urteile.",
            list_rulings,
            {
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Stichwörter, alle müssen vorkommen",
                    },
                    "category": {"type": "string", "enum": list(classify.CATEGORIES)},
                    "relevant_only": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
            },
        ),
        Tool(
            "search_rulings",
            '{"query": "Meniskus Abnützung", "limit": 15}',
            "Volltextsuche über den Text aller Urteile (auch nicht relevante), mit Textauszug. "
            "Wenige präzise Stichwörter, keine ganzen Sätze.",
            search_rulings,
            {
                "properties": {
                    "query": {"type": "string", "description": "Wenige präzise Stichwörter"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            "read_ruling",
            '{"docket": "8C_129/2025", "offset": 0}',
            "Ein Urteil lesen: Metadaten, aktuelle Zusammenfassungen DE/FR und der Urteilstext "
            f"in Abschnitten von {RULING_PAGE} Zeichen (weiter mit offset).",
            read_ruling,
            {
                "properties": {
                    "docket": {
                        "type": "string",
                        "description": "Geschäftsnummer, z. B. 8C_129/2025",
                    },
                    "offset": {"type": "integer", "description": "Zeichen-Offset im Urteilstext"},
                },
                "required": ["docket"],
            },
        ),
        Tool(
            "propose_summary",
            '{"docket": "8C_129/2025", "lang": "de", "text": "...", "rationale": "..."}',
            "Eine neue Zusammenfassung eines Urteils vorschlagen (eine Sprache pro Aufruf). "
            "Nur wenn der Benutzer darum bittet und nachdem du das Urteil mit read_ruling "
            "gelesen hast. Ändert nichts, bis der Benutzer den Vorschlag übernimmt.",
            propose_summary,
            {
                "properties": {
                    "docket": {"type": "string"},
                    "lang": {"type": "string", "enum": ["de", "fr"]},
                    "text": {"type": "string", "description": "Die neue Zusammenfassung"},
                    "rationale": {"type": "string", "description": "Was geändert wurde und warum"},
                },
                "required": ["docket", "lang", "text"],
            },
        ),
        Tool(
            "update_memory",
            '{"content": "...", "mode": "append"}',
            "Dein Wissen ändern: eine dauerhafte Vorgabe oder Vorliebe des Benutzers speichern. "
            'mode "append" (Standard) hängt content am Ende an, "replace" ersetzt den ganzen '
            "Text durch content. Nur wenn der Benutzer eine Vorgabe für künftige Antworten macht "
            "oder dich bittet, dir etwas zu merken.",
            update_memory,
            {
                "properties": {
                    "content": {"type": "string", "description": "Der Text"},
                    "mode": {"type": "string", "enum": ["append", "replace"]},
                },
                "required": ["content"],
            },
        ),
    ]
}


def run(ctx: Context, name: str, args: dict[str, Any]) -> str:
    """Run tool `name`; a usage problem comes back as text so the model can correct itself."""
    tool = TOOLS.get(name)
    if tool is None:
        return f"Fehler: Unbekanntes Tool «{name}». Verfügbar: {', '.join(TOOLS)}."
    try:
        return tool.run(ctx, **args)
    except ToolError as exc:
        return f"Fehler: {exc}"
    except TypeError as exc:
        return f"Fehler: falsche Argumente für {name} ({exc}). Signatur: {tool.signature}"
