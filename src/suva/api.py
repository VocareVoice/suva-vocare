import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from suva import classify, db, summarize
from suva.config import get_settings
from suva.llm import LLMClient

WEB_DIR = Path(__file__).parent / "web"

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
    try:
        texts = summarize.summarize(conn, docket, llm)
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc)) from exc
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


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
