import json
import logging
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from suva import classify, db, laws, summarize
from suva.agent import loop as agent_loop
from suva.config import get_settings
from suva.llm import LLMClient

WEB_DIR = Path(__file__).parent / "web"
logger = logging.getLogger(__name__)

app = FastAPI(title="Suva BGer triage")


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = db.connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_llm() -> LLMClient:
    return LLMClient()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
LLM = Annotated[LLMClient, Depends(get_llm)]


class FeedbackIn(BaseModel):
    verdict: Literal["relevant", "not_relevant"]
    corrected_score: int | None = Field(default=None, ge=0, le=100)
    comment: str | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/rulings")
def list_rulings(
    conn: Conn,
    q: str | None = None,
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    max_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    label: Literal["relevant", "not_relevant"] | None = None,
    division: str | None = None,
    language: Literal["de", "fr", "it"] | None = None,
    has_summary: bool | None = None,
    branch: str | None = None,
    category: str | None = None,
    sort: Literal["score", "date", "docket", "title", "language", "summary"] = "score",
    order: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    filters = {
        "q": q,
        "date_from": date_from,
        "date_to": date_to,
        "min_score": min_score,
        "max_score": max_score,
        "label": label,
        "division": division,
        "language": language,
        "has_summary": has_summary,
        "branch": branch,
        "category": category,
    }
    total, items = db.list_rulings(
        conn, sort=sort, order=order, limit=limit, offset=offset, **filters
    )
    return {"total": total, "items": items, "stats": db.list_stats(conn, **filters)}


@app.get("/api/facets")
def facets(conn: Conn) -> dict[str, Any]:
    result = db.facets(conn)
    result["classification"] = classify.taxonomy(result["classification"])
    return result


def _require_ruling(conn: sqlite3.Connection, docket: str) -> None:
    if db.get_ruling(conn, docket) is None:
        raise HTTPException(404, f"Unknown ruling {docket}")


# Dockets contain a slash (8C_129/2025), hence the path converters.
@app.post("/api/rulings/{docket:path}/summarize")
def summarize_ruling(docket: str, conn: Conn, llm: LLM) -> dict[str, Any]:
    _require_ruling(conn, docket)
    texts = summarize.summarize(conn, docket, llm)
    for lang, text in texts.items():
        db.save_summary(
            conn,
            docket,
            lang=lang,
            text=text,
            model=llm.model,
            prompt_version=summarize.PROMPT_VERSION,
        )
    return db.get_ruling_detail(conn, docket)


@app.post("/api/rulings/{docket:path}/feedback", status_code=201)
def post_feedback(docket: str, feedback: FeedbackIn, conn: Conn) -> dict[str, Any]:
    _require_ruling(conn, docket)
    db.save_feedback(conn, docket, **feedback.model_dump())
    return db.get_ruling_detail(conn, docket)


@app.get("/api/rulings/{docket:path}")
def ruling_detail(docket: str, conn: Conn) -> dict[str, Any]:
    detail = db.get_ruling_detail(conn, docket)
    if detail is None:
        raise HTTPException(404, f"Unknown ruling {docket}")
    return detail


# ---------------------------------------------------------------- agent chat

UILang = Literal["de", "fr"]
_busy_chats: set[str] = set()  # chats with a turn in progress; one turn at a time per chat


class ChatMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    docket: str | None = None  # the ruling open in the UI, if any
    lang: UILang = "de"


def _require_chat(conn: sqlite3.Connection, chat_id: str) -> None:
    if not db.chat_exists(conn, chat_id):
        raise HTTPException(404, f"Unknown chat {chat_id}")


@app.post("/api/chats", status_code=201)
def create_chat(conn: Conn) -> dict[str, Any]:
    chat_id = uuid.uuid4().hex
    db.create_chat(conn, chat_id)
    return {"id": chat_id, "messages": []}


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, conn: Conn, lang: UILang = "de") -> dict[str, Any]:
    _require_chat(conn, chat_id)
    return {"id": chat_id, "messages": agent_loop.public_chat(conn, chat_id, lang)}


@app.delete("/api/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: str, conn: Conn) -> None:
    db.delete_chat(conn, chat_id)


@app.post("/api/chats/{chat_id}/messages")
def post_chat_message(chat_id: str, message: ChatMessageIn, conn: Conn) -> StreamingResponse:
    """Run one agent turn. The response is NDJSON: one event per line ("user", then a "step"
    per tool call, then "answer" or "error")."""
    _require_chat(conn, chat_id)
    if chat_id in _busy_chats:
        raise HTTPException(409, "The agent is still answering the previous message")
    _busy_chats.add(chat_id)
    settings = get_settings()

    def events() -> Iterator[str]:
        # Own connection: the request's one is closed once the endpoint returns.
        own = db.connect(settings.db_path)
        try:
            llm = LLMClient(settings, cache=False, model=settings.agent_model)
            for event in agent_loop.run_turn(
                own,
                llm,
                chat_id,
                message.text.strip(),
                docket=message.docket,
                lang=message.lang,
                max_steps=settings.agent_max_steps,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:  # report to the chat instead of cutting the stream
            logger.exception("agent turn failed")
            yield json.dumps({"type": "error", "error": f"{type(exc).__name__}: {exc}"}) + "\n"
        finally:
            own.close()
            _busy_chats.discard(chat_id)

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _open_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict[str, Any]:
    proposal = db.get_proposal(conn, proposal_id)
    if proposal is None:
        raise HTTPException(404, f"Unknown proposal {proposal_id}")
    if proposal["status"] != "open":
        raise HTTPException(409, f"Proposal {proposal_id} is already {proposal['status']}")
    return proposal


@app.post("/api/proposals/{proposal_id}/apply")
def apply_proposal(proposal_id: int, conn: Conn) -> dict[str, Any]:
    """Make the proposed text the ruling's summary in that language; the old one is replaced."""
    _open_proposal(conn, proposal_id)
    proposal = db.apply_proposal(conn, proposal_id)
    return {"proposal": db.get_proposal(conn, proposal_id), "docket": proposal["docket"]}


@app.post("/api/proposals/{proposal_id}/discard")
def discard_proposal(proposal_id: int, conn: Conn) -> dict[str, Any]:
    _open_proposal(conn, proposal_id)
    db.set_proposal_status(conn, proposal_id, "discarded")
    return {"proposal": db.get_proposal(conn, proposal_id)}


@app.get("/api/laws")
def list_laws(lang: UILang = "de") -> list[dict[str, str]]:
    """The laws the law view offers: code, abbreviation and title in `lang`, SR number."""
    return [
        {"code": code.lower(), "law": law.names[lang], "title": law.titles[lang], "sr": law.sr}
        for code, law in laws.LAWS.items()
    ]


@app.get("/api/law/{code}")
def get_law(code: str, lang: UILang = "de") -> dict[str, Any]:
    """One law's snapshot in one language, every article in order, for the law view.
    `code` takes either language's abbreviation: uvg/laa, atsg/lpga, uvv/olaa."""
    name = laws.law_code(code)
    if name is None:
        raise HTTPException(404, f"Unknown law {code}; known: {', '.join(laws.LAWS)}")
    law = laws.LAWS[name]
    version = json.loads(law.snapshot.read_text(encoding="utf-8"))["languages"][lang]
    return {
        "code": name.lower(),
        "law": law.names[lang],
        "title": law.titles[lang],
        "sr": law.sr,
        "in_force": version["in_force"],
        "url": law.page_url(lang),
        "articles": [{**a, "key": laws.key(a["id"])} for a in version["articles"]],
    }


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
