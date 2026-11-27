"""The agent loop: Apertus answers a chat message, calling tools as it goes.

Tools use the endpoint's native tool calling: they go in the `tools` parameter, which the
Apertus chat template declares to the model (without it, the template tells the model it has no
tools), and calls come back as tool_calls, answered with "tool" messages. A call the endpoint's
parser misses and leaves in the text ({"read_ruling": {...}}, Apertus's own call shape) is still
recognised. Every step is stored, so the chat survives reloads; earlier turns are replayed as
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

from suva import classify, db, laws
from suva.agent import memory, tools
from suva.agent.links import DOCKET, Linker
from suva.llm import LLMClient, Message

PROMPT_PATH = Path(__file__).parent / "prompt.md"
LANG_NAMES = {"de": "Deutsch", "fr": "Französisch"}
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# A tool named in an answer: Apertus sometimes writes "Tool-Aufruf: update_memory mit …" as text.
TOOL_NAME = re.compile(r"\b(?:" + "|".join(map(re.escape, tools.TOOLS)) + r")\b")
TOOL_RESULT_LIMIT = 60_000  # characters of one tool result sent to the model
STORED_RESULT_LIMIT = 4_000  # characters of a tool result kept in the chat history


@cache
def _static_prompt_parts(lang: str) -> dict[str, str]:
    return {
        "categories": ", ".join(
            f"{slug} ({label.de})" for slug, label in classify.CATEGORIES.items()
        ),
        "outline": laws.outlines(lang),
        "in_force": laws.in_force(lang),
    }


def system_prompt(conn: sqlite3.Connection, lang: str, max_steps: int) -> str:
    stats = db.list_stats(conn)
    return Template(PROMPT_PATH.read_text(encoding="utf-8")).safe_substitute(
        **_static_prompt_parts(lang),
        memory=memory.text(conn),
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


def _bare_args_call(reply: str) -> tuple[str, dict[str, Any]] | None:
    """A tool's name followed by a bare JSON object of its arguments, as Apertus sometimes
    writes a call out (`update_memory ... {"content": "...", "mode": "append"}`)."""
    decoder = json.JSONDecoder(strict=False)
    for named in TOOL_NAME.finditer(reply):
        tool = tools.TOOLS[named.group(0)]
        properties = set(tool.parameters.get("properties", {}))
        required = set(tool.parameters.get("required", []))
        brace = reply.find("{", named.end())
        while brace != -1:
            try:
                args, _ = decoder.raw_decode(reply[brace:])
            except json.JSONDecodeError:
                brace = reply.find("{", brace + 1)
                continue
            if (
                isinstance(args, dict)
                and args
                and set(args) <= properties
                and required <= set(args)
            ):
                return tool.name, args
            break
    return None


def _as_call(obj: Any) -> tuple[str, dict[str, Any]] | None:
    """`obj` as a tool call, in any of the shapes Apertus writes one in, or None:
    {"tool"|"name": "<tool>", "args"|"arguments"|"parameters": {...}}, the same with the
    arguments as the remaining keys, {"type": "<tool>", ...arguments} (it copies the "type"
    of the template's tool declarations), {"type": "function", "function": {...}} and
    {"<tool>": {...}}."""
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get("function"), dict):
        return _as_call(obj["function"])
    for key in ("tool", "name", "type"):
        name = obj.get(key)
        # "tool" and "name" always mean a call (an unknown tool is reported back to the model);
        # "type" only when it names one of our tools.
        if not isinstance(name, str) or (key == "type" and name not in tools.TOOLS):
            continue
        nested = next((obj[k] for k in ("args", "arguments", "parameters") if k in obj), None)
        if isinstance(nested, str):
            try:
                nested = json.loads(nested or "{}", strict=False)
            except json.JSONDecodeError:
                return None
        if nested is None:
            nested = {k: v for k, v in obj.items() if k not in ("tool", "name", "type")}
        return (name, nested) if isinstance(nested, dict) else None
    if len(obj) == 1:  # {"read_ruling": {...}}
        name, args = next(iter(obj.items()))
        if name in tools.TOOLS and isinstance(args, dict | None):
            return name, args or {}
    return None


def parse_calls(reply: str) -> list[tuple[str, dict[str, Any]]]:
    """Every tool call written as text in `reply`, in order; empty if there is none. Apertus
    sometimes writes several at once (one per article it wants to read)."""
    decoder = json.JSONDecoder(strict=False)
    calls: list[tuple[str, dict[str, Any]]] = []
    brace = reply.find("{")
    while brace != -1:
        try:
            obj, end = decoder.raw_decode(reply, brace)
        except json.JSONDecodeError:
            brace = reply.find("{", brace + 1)
            continue
        call = _as_call(obj)
        if call:
            calls.append(call)
            brace = reply.find("{", end)
        else:  # not a call itself, but it may wrap one ({"tool_calls": [...]})
            brace = reply.find("{", brace + 1)
    if not calls and (bare := _bare_args_call(reply)):
        calls.append(bare)
    return calls


def known_dockets(conn: sqlite3.Connection, chat_id: str) -> set[str]:
    """Dockets the model has seen in this chat: in tool results or earlier answers."""
    known: set[str] = set()
    for message in db.chat_messages(conn, chat_id):
        if message["role"] == "tool":
            known.update(message["data"].get("dockets", []))
        elif message["role"] == "assistant":
            known.update(re.findall(DOCKET, message["content"]))
    return known


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
        out.update(
            tool=data.get("tool"),
            args=data.get("args", {}),
            error=data.get("error", False),
            result=message["content"],
        )
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

    def correction(kind: str, reply: str, note: str) -> dict[str, Any]:
        """A guard sent the reply back to the model: kept as a step, so the UI can show it."""
        result = f"Antwort des Modells:\n{reply}\n\nKorrektur:\n{note}"
        args = {"kind": kind}
        db.add_chat_message(
            conn,
            chat_id,
            "tool",
            result[:STORED_RESULT_LIMIT],
            {"tool": "correction", "args": args, "error": True},
        )
        messages.extend(
            [{"role": "assistant", "content": reply}, {"role": "user", "content": note}]
        )
        return {
            "type": "step",
            "tool": "correction",
            "args": args,
            "error": True,
            "result": result[:STORED_RESULT_LIMIT],
        }

    ctx = tools.Context(conn=conn, chat_id=chat_id, lang=lang)
    schemas = [tool.schema() for tool in tools.TOOLS.values()]
    seen: set[str] = set()
    called: set[str] = set()  # tools called this turn
    known = known_dockets(conn, chat_id) | ({docket} if docket else set())
    calls, forced, checked, described, reply = 0, False, False, False, ""
    for _ in range(max_steps + 3):  # bound on model calls: tool steps plus a few corrections
        if calls >= max_steps and not forced:
            forced = True
            messages.append(
                {
                    "role": "user",
                    "content": "[System] Keine weiteren Tool-Aufrufe. Antworte jetzt "
                    "mit dem, was du bisher gefunden hast.",
                }
            )
        step = llm.chat_tools(
            messages, None if forced else schemas, temperature=0.2, max_tokens=4000
        )
        # Strip control characters: Apertus sometimes emits NUL in place of a letter.
        reply = CONTROL.sub("", step.content).strip()
        pending = [(call.id, call.name, call.arguments) for call in step.tool_calls]
        if not pending and not forced:
            # Fallback: calls the endpoint's parser missed and left in the text.
            pending = [
                (f"text-{calls}-{i}", name, json.dumps(args, ensure_ascii=False))
                for i, (name, args) in enumerate(parse_calls(reply))
            ]
            if pending:
                reply = ""

        if not pending:
            named = next((m for m in TOOL_NAME.finditer(reply) if m.group(0) not in called), None)
            if named and not forced and not described:
                described = True  # it wrote the call out as prose instead of making it, once
                yield correction(
                    "notool",
                    reply,
                    f"[System] Du hast {named.group(0)} nur beschrieben, nicht aufgerufen; es ist "
                    "nichts geschehen. Rufe das Tool jetzt als Tool-Aufruf auf, nicht als Text.",
                )
                continue
            unseen = sorted(set(re.findall(DOCKET, reply)) - known)
            if unseen and not checked:
                checked = True  # cited rulings it never looked up: research or drop them, once
                yield correction(
                    "unseen",
                    reply,
                    f"[System] Diese Geschäftsnummern stammen aus keinem Tool-Ergebnis: "
                    f"{', '.join(unseen)}. Das heisst nicht, dass es sie nicht gibt: lies sie "
                    "mit read_ruling oder lass sie weg. Nenne nur Urteile, die du in "
                    "Tool-Ergebnissen gesehen hast.",
                )
                forced = False if calls < max_steps else forced
                continue
            break

        messages.append(
            {
                "role": "assistant",
                "content": reply,
                "tool_calls": [
                    {"id": cid, "type": "function", "function": {"name": name, "arguments": raw}}
                    for cid, name, raw in pending
                ],
            }
        )
        for call_id, name, raw in pending:
            calls += 1
            called.add(name)
            try:
                args = json.loads(raw or "{}", strict=False)
            except json.JSONDecodeError as exc:
                args = None
                result = f"Fehler: Die Argumente sind kein gültiges JSON ({exc})."
            if args is not None and not isinstance(args, dict):
                args, result = None, "Fehler: Die Argumente müssen ein JSON-Objekt sein."
            if args is not None:
                key = json.dumps([name, args], sort_keys=True, ensure_ascii=False)
                if key in seen:
                    result = (
                        "Dieses Ergebnis hast du bereits oben erhalten. Nutze es oder antworte."
                    )
                else:
                    seen.add(key)
                    result = tools.run(ctx, name, args)
            args = args if args is not None else {"raw": raw}
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
            yield {
                "type": "step",
                "tool": name,
                "args": args,
                "error": error,
                "result": result[:STORED_RESULT_LIMIT],
            }
            if len(result) > TOOL_RESULT_LIMIT:
                result = result[:TOOL_RESULT_LIMIT] + "\n[… gekürzt]"
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result})

    stored = db.add_chat_message(
        conn, chat_id, "assistant", reply or "…", {"proposals": ctx.proposals}
    )
    yield {
        "type": "answer",
        "message": public_message(linker, conn, db.get_chat_message(conn, stored)),
    }
