"""The agent loop: Apertus answers a chat message, calling tools as it goes.

The endpoint has no native tool calling, so the model calls a tool by replying with one JSON
object, {"tool": ..., "args": {...}}; anything else is its answer. Tool results go back as a
user message. Every step is stored, so the chat survives reloads; earlier turns are replayed as
question and answer only, which keeps the context small (the model can look things up again).
"""

import json
import re
import sqlite3
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from string import Template
from typing import Any

from suva import classify, db, laws, summarize
from suva.agent import tools
from suva.agent.links import DOCKET, Linker
from suva.llm import LLMClient, Message

PROMPT_PATH = Path(__file__).parent / "prompt.md"
LANG_NAMES = {"de": "Deutsch", "fr": "Französisch"}
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TOOL_CALL = re.compile(r'\{\s*"tool"\s*:')
TOOL_RESULT_LIMIT = 60_000  # characters of one tool result sent to the model
STORED_RESULT_LIMIT = 4_000  # characters of a tool result kept in the chat history


@cache
def _static_prompt_parts(lang: str) -> dict[str, str]:
    signatures = "\n".join(
        f"- {tool.name} {tool.signature}\n  {tool.description}" for tool in tools.TOOLS.values()
    )
    return {
        "tools": signatures,
        "categories": ", ".join(
            f"{slug} ({label.de})" for slug, label in classify.CATEGORIES.items()
        ),
        "style": Template(summarize.prompt("summary_style")).safe_substitute(
            length=f"DE {summarize.LENGTH['de']}, FR {summarize.LENGTH['fr']}"
        ),
        "style_de": summarize.prompt("summary_de"),
        "style_fr": summarize.prompt("summary_fr"),
        "outline": laws.outlines(lang),
        "in_force": laws.in_force(lang),
    }


def system_prompt(conn: sqlite3.Connection, lang: str, max_steps: int) -> str:
    stats = db.list_stats(conn)
    return Template(PROMPT_PATH.read_text(encoding="utf-8")).safe_substitute(
        **_static_prompt_parts(lang),
        total=stats["total"],
        relevant=stats["relevant"],
        lang_name=LANG_NAMES.get(lang, "Deutsch"),
        max_steps=max_steps,
    )


def _user_content(text: str, docket: str | None) -> str:
    if docket:
        return f"[Kontext: Der Benutzer hat gerade das Urteil {docket} geöffnet.]\n\n{text}"
    return text


def history(conn: sqlite3.Connection, chat_id: str) -> list[Message]:
    """Earlier turns as plain question/answer pairs."""
    messages: list[Message] = []
    for message in db.chat_messages(conn, chat_id):
        if message["role"] == "user":
            messages.append(
                {
                    "role": "user",
                    "content": _user_content(message["content"], message["data"].get("docket")),
                }
            )
        elif message["role"] == "assistant":
            messages.append({"role": "assistant", "content": message["content"]})
    return messages


def parse_call(reply: str) -> tuple[str, dict[str, Any]] | None:
    """The tool call in `reply`, or None when the reply is an answer. Raises ValueError for a
    call that is not valid JSON, so the model can be told to fix it."""
    match = TOOL_CALL.search(reply)
    if match is None:
        return None
    try:
        call, _ = json.JSONDecoder(strict=False).raw_decode(reply[match.start() :])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Kein gültiges JSON: {exc}") from exc
    name, args = call.get("tool"), call.get("args") or {}
    if not isinstance(name, str) or not isinstance(args, dict):
        raise ValueError('Erwartet {"tool": "<name>", "args": {...}}')
    return name, args


def known_dockets(conn: sqlite3.Connection, chat_id: str) -> set[str]:
    """Dockets the model has seen in this chat: in tool results or earlier answers."""
    known: set[str] = set()
    for message in db.chat_messages(conn, chat_id):
        if message["role"] == "tool":
            known.update(message["data"].get("dockets", []))
        elif message["role"] == "assistant":
            known.update(re.findall(DOCKET, message["content"]))
    return known


def _looks_like_json(reply: str) -> bool:
    return bool(re.match(r"\s*(?:```(?:json)?\s*)?[\[{]", reply))


def public_message(
    linker: Linker, conn: sqlite3.Connection, message: dict[str, Any]
) -> dict[str, Any]:
    """A stored message as the UI shows it: answers with checked links and their proposals."""
    data = message["data"]
    out = {"id": message["id"], "role": message["role"], "created_at": message["created_at"]}
    if message["role"] == "assistant":
        out["text"] = linker.render(message["content"])
        out["proposals"] = [
            p for pid in data.get("proposals", []) if (p := db.get_proposal(conn, pid))
        ]
    elif message["role"] == "tool":
        out.update(tool=data.get("tool"), args=data.get("args", {}), error=data.get("error", False))
    else:
        out.update(text=message["content"], docket=data.get("docket"))
    return out


def public_chat(conn: sqlite3.Connection, chat_id: str, lang: str) -> list[dict[str, Any]]:
    linker = Linker(conn, lang)
    return [public_message(linker, conn, m) for m in db.chat_messages(conn, chat_id)]


def run_turn(
    conn: sqlite3.Connection,
    llm: LLMClient,
    chat_id: str,
    text: str,
    *,
    docket: str | None = None,
    lang: str = "de",
    max_steps: int = 10,
) -> Iterator[dict[str, Any]]:
    """Answer one user message. Yields events for the UI: "user", "step" per tool call, then
    "answer" (or "error")."""
    lang = lang if lang in LANG_NAMES else "de"
    linker = Linker(conn, lang)
    messages: list[Message] = [
        {"role": "system", "content": system_prompt(conn, lang, max_steps)},
        *history(conn, chat_id),
        {"role": "user", "content": _user_content(text, docket)},
    ]
    user_id = db.add_chat_message(conn, chat_id, "user", text, {"docket": docket, "lang": lang})
    yield {
        "type": "user",
        "message": public_message(linker, conn, db.get_chat_message(conn, user_id)),
    }

    ctx = tools.Context(conn=conn, chat_id=chat_id, lang=lang)
    seen: set[str] = set()
    known = known_dockets(conn, chat_id) | ({docket} if docket else set())
    calls, forced, rewrote, checked, reply = 0, False, False, False, ""
    for _ in range(max_steps + 4):  # bound on model calls: tool steps plus a few corrections
        if calls >= max_steps and not forced:
            forced = True
            messages.append(
                {
                    "role": "user",
                    "content": "[System] Keine weiteren Tool-Aufrufe. Antworte jetzt "
                    "mit dem, was du bisher gefunden hast.",
                }
            )
        # Strip control characters: Apertus sometimes emits NUL in place of a letter.
        reply = CONTROL.sub("", llm.chat(messages, temperature=0.2, max_tokens=4000)).strip()
        try:
            call = None if forced else parse_call(reply)
        except ValueError as exc:
            calls += 1
            messages += [
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": f"[Tool-Fehler] {exc}. Antworte mit genau einem JSON-Objekt "
                    '{"tool": "<name>", "args": {...}} '
                    "oder mit deiner Antwort ohne JSON.",
                },
            ]
            continue
        if call is None and _looks_like_json(reply) and not rewrote:
            rewrote = True  # the model mimicked the tool format for its answer: ask once for prose
            messages += [
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": "[System] Das ist JSON. Schreibe dieselbe Antwort als "
                    "Text mit Markdown im vorgegebenen Format, mit Zitierungen in [[...]].",
                },
            ]
            continue
        unseen = sorted(set(re.findall(DOCKET, reply)) - known) if call is None else []
        if unseen and not checked:
            checked = True  # cited rulings it never looked up: research them or drop them, once
            messages += [
                {"role": "assistant", "content": reply},
                {
                    "role": "user",
                    "content": f"[System] Diese Geschäftsnummern stammen aus keinem "
                    f"Tool-Ergebnis: {', '.join(unseen)}. Recherchiere mit den Tools oder lass "
                    "sie weg. Nenne nur Urteile, die du in Tool-Ergebnissen gesehen hast.",
                },
            ]
            forced = False if calls < max_steps else forced
            continue
        if call is None:
            break

        calls += 1
        name, args = call
        key = json.dumps([name, args], sort_keys=True, ensure_ascii=False)
        if key in seen:
            result = "Dieses Ergebnis hast du bereits oben erhalten. Nutze es oder antworte."
        else:
            seen.add(key)
            result = tools.run(ctx, name, args)
        error = result.startswith("Fehler:")
        found = sorted(set(re.findall(DOCKET, result)))
        known.update(found)
        db.add_chat_message(
            conn,
            chat_id,
            "tool",
            result[:STORED_RESULT_LIMIT],
            {"tool": name, "args": args, "error": error, "dockets": found},
        )
        yield {"type": "step", "tool": name, "args": args, "error": error}
        if len(result) > TOOL_RESULT_LIMIT:
            result = result[:TOOL_RESULT_LIMIT] + "\n[… gekürzt]"
        messages += [
            {
                "role": "assistant",
                "content": json.dumps({"tool": name, "args": args}, ensure_ascii=False),
            },
            {"role": "user", "content": f"[Tool-Ergebnis {name}]\n{result}"},
        ]

    stored = db.add_chat_message(
        conn, chat_id, "assistant", reply or "…", {"proposals": ctx.proposals}
    )
    yield {
        "type": "answer",
        "message": public_message(linker, conn, db.get_chat_message(conn, stored)),
    }
