"""The agent loop: Apertus answers a chat message, calling tools as it goes.

Tools use the endpoint's native tool calling: they go in the `tools` parameter, which the
Apertus chat template declares to the model (without it, the template tells the model it has no
tools), and calls come back as tool_calls, answered with "tool" messages. A call the endpoint's
parser misses and leaves in the text ({"read_ruling": {...}}, Apertus's own call shape) is still
recognised and run; one that cannot be run never becomes the answer. Every step is stored, so
the chat survives reloads; earlier turns are replayed as question and answer only, which keeps
the context small (the model can look things up again).
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
# Shown when the model keeps writing tool calls as its answer, with the sources it consulted.
NO_ANSWER = {
    "de": "Ich konnte die Recherche nicht zu einer Antwort zusammenführen. Bitte stellen Sie "
    "die Frage noch einmal, gerne enger gefasst.",
    "fr": "Je n'ai pas pu conclure la recherche par une réponse. Veuillez reposer la question, "
    "de préférence de manière plus précise.",
}
CONSULTED = {
    "de": ("Gelesene Artikel:", "Gefundene Urteile:"),
    "fr": ("Articles lus :", "Arrêts trouvés :"),
}
LAW_NAMES_FR = {"UVG": "LAA", "ATSG": "LPGA", "UVV": "OLAA"}
# Guard notes sent back to the model, in the user's language: a note in German pulls a French
# answer towards German.
NOTES = {
    "de": {
        "forced": "[System] Keine weiteren Tool-Aufrufe. Antworte jetzt mit dem, was du bisher "
        "gefunden hast.",
        "callshape": "[System] Deine Antwort ist ein als Text geschriebener Tool-Aufruf, keine "
        "Antwort; es ist nichts geschehen.",
        "callshape_forced": "Du kannst keine Tools mehr aufrufen. Antworte jetzt in ganzen "
        "Sätzen auf Deutsch mit dem, was du bisher gefunden hast, ohne JSON.",
        "callshape_tools": "Rufe das Tool als Tool-Aufruf auf, oder antworte in ganzen Sätzen.",
        "notool": "[System] Du hast {tool} nur beschrieben, nicht aufgerufen; es ist nichts "
        "geschehen. Rufe das Tool jetzt als Tool-Aufruf auf, nicht als Text.",
        "unseen": "[System] Diese Geschäftsnummern stammen aus keinem Tool-Ergebnis: {dockets}. "
        "Das heisst nicht, dass es sie nicht gibt: lies sie mit read_ruling oder lass sie weg. "
        "Nenne nur Urteile, die du in Tool-Ergebnissen gesehen hast.",
        "language": "[System] Der Benutzer schreibt Deutsch. Schreibe deine Antwort noch einmal, "
        "vollständig auf Deutsch.",
    },
    "fr": {
        "forced": "[Système] Plus d'appels d'outils. Réponds maintenant avec ce que tu as "
        "trouvé jusqu'ici.",
        "callshape": "[Système] Ta réponse est un appel d'outil écrit sous forme de texte, pas "
        "une réponse ; rien ne s'est passé.",
        "callshape_forced": "Tu ne peux plus appeler d'outils. Réponds maintenant en phrases "
        "complètes, en français, avec ce que tu as trouvé jusqu'ici, sans JSON.",
        "callshape_tools": "Appelle l'outil par un appel d'outil, ou réponds en phrases complètes.",
        "notool": "[Système] Tu as seulement décrit {tool}, sans l'appeler ; rien ne s'est "
        "passé. Appelle maintenant l'outil par un appel d'outil, pas sous forme de texte.",
        "unseen": "[Système] Ces numéros de dossier ne proviennent d'aucun résultat d'outil : "
        "{dockets}. Cela ne veut pas dire qu'ils n'existent pas : lis-les avec read_ruling ou "
        "laisse-les de côté. Ne cite que des arrêts vus dans des résultats d'outils.",
        "language": "[Système] L'utilisateur écrit en français. Réécris ta réponse, entièrement "
        "en français.",
    },
}
# Words that mark a language, none shared between them: Apertus sometimes slips into English
# (mostly when it answers with the reasoning it writes next to its tool calls) or, for a French
# user, into the German of the prompt.
MARKERS = {
    "en": re.compile(
        r"\b(?:the|and|of|to|is|are|for|with|this|that|which|be|by|it|let|we)\b", re.I
    ),
    "de": re.compile(
        r"\b(?:der|die|das|und|ist|nicht|mit|ein|eine|zu|den|von|für|auf|dass|sich|im)\b", re.I
    ),
    "fr": re.compile(r"\b(?:le|la|les|et|est|une|un|pour|que|dans|pas|au|qui|sur|en)\b", re.I),
}


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


def history(conn: sqlite3.Connection, chat_id: str, lang: str = "de") -> list[Message]:
    """Earlier turns as plain question/answer pairs. An answer that is a tool call written as
    text (stored before the guard caught every shape) is replayed as the no-answer note: the
    model would otherwise copy it into every following answer."""
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
            content = message["content"]
            if is_call_text(content):
                content = NO_ANSWER.get(lang, NO_ANSWER["de"])
            messages.append({"role": "assistant", "content": content})
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


# key="value", key: value, or key "value" (`search_rulings with query "Sturz"`).
KV_ARG = re.compile(
    r"""(\w+)(?:\s*[=:]\s*(?:"([^"]*)"|'([^']*)'|([\w./-]+))|\s+(?:"([^"]*)"|'([^']*)'))"""
)
# A label Apertus puts before a call it writes out ("Tool call 6: search_rulings ...").
CALL_LABEL = re.compile(
    r"^(?:tool[ -]?call|tool-aufruf|aufruf|appel d'outil)[^:\n]{0,40}:\s*", re.I
)


def _kv_call(reply: str) -> tuple[str, dict[str, Any]] | None:
    """A tool's name followed by key="value" arguments on the same line, as Apertus sometimes
    writes a call out (`read_article with law="UVV", art="25"`, `read_ruling(docket=...)`)."""
    for named in TOOL_NAME.finditer(reply):
        tool = tools.TOOLS[named.group(0)]
        properties = tool.parameters.get("properties", {})
        required = set(tool.parameters.get("required", []))
        line = reply[named.end() :].split("\n", 1)[0]
        args: dict[str, Any] = {}
        for match in KV_ARG.finditer(line):
            key = match.group(1)
            value = next(g for g in match.groups()[1:] if g is not None)
            if key not in properties:
                continue
            kind = properties[key].get("type")
            if kind == "integer" and value.isdigit():
                args[key] = int(value)
            elif kind == "boolean" and value.lower() in ("true", "false"):
                args[key] = value.lower() == "true"
            else:
                args[key] = value
        if args and required <= set(args):
            return tool.name, args
    return None


def looks_like_call(reply: str) -> bool:
    """The reply is a tool call written as text rather than an answer: it opens with a tool's
    name, or names one followed by arguments (`read_article with law="UVV"`, `read_ruling(`)."""
    head = CALL_LABEL.sub("", reply.lstrip(" \t\n`*>-[").split("\n", 1)[0])
    if TOOL_NAME.match(head):
        return True
    return any(
        re.match(r"\s*(?:\(|\{|=|with\b|mit\b|avec\b|:)", reply[m.end() : m.end() + 12])
        and KV_ARG.search(reply[m.end() : m.end() + 200])
        for m in TOOL_NAME.finditer(reply)
    )


CALL_KEYS = ("tool", "tool_call", "function", "name", "type")
ARG_KEYS = ("args", "arguments", "parameters")


def _as_call(obj: Any) -> tuple[str, dict[str, Any]] | None:
    """`obj` as a tool call, in any of the shapes Apertus writes one in, or None: the tool's
    name under "tool", "tool_call", "function" or "name" and its arguments under "args",
    "arguments" or "parameters" (an object or a JSON string) or as the remaining keys;
    {"type": "<tool>", ...arguments} (it copies the "type" of the template's tool
    declarations); a nested call ({"type": "function", "function": {...}}, {"tool_call":
    {...}}) and {"<tool>": {...}}."""
    if not isinstance(obj, dict):
        return None
    for key in ("function", "tool_call", "tool"):
        if isinstance(obj.get(key), dict):
            return _as_call(obj[key])
    for key in CALL_KEYS:
        name = obj.get(key)
        # A name under any key but "type" always means a call (an unknown tool is reported back
        # to the model); "type" only when it names one of our tools.
        if not isinstance(name, str) or (key == "type" and name not in tools.TOOLS):
            continue
        nested = next((obj[k] for k in ARG_KEYS if k in obj), None)
        if isinstance(nested, str):
            try:
                nested = json.loads(nested or "{}", strict=False)
            except json.JSONDecodeError:
                return None
        if nested is None:
            nested = {k: v for k, v in obj.items() if k not in (*CALL_KEYS, "id")}
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
    if not calls and looks_like_call(reply) and (kv := _kv_call(reply)):
        calls.append(kv)
    if not calls:
        calls = _args_only_calls(reply)
    return calls


# Tools a call may be inferred for from its arguments alone: the ones that only read.
READ_ONLY = ("read_article", "list_rulings", "search_rulings", "read_ruling")


def _json_objects(reply: str) -> Iterator[dict[str, Any]]:
    """The top-level JSON objects in `reply`."""
    decoder = json.JSONDecoder(strict=False)
    brace = reply.find("{")
    while brace != -1:
        try:
            obj, end = decoder.raw_decode(reply, brace)
        except json.JSONDecodeError:
            brace = reply.find("{", brace + 1)
            continue
        if isinstance(obj, dict):
            yield obj
        brace = reply.find("{", end)


def _args_only_calls(reply: str) -> list[tuple[str, dict[str, Any]]]:
    """Calls written as their arguments only, without the tool's name (`{"query": "Ungeschick
    Arbeitsunfall", "limit": 10}`): the read-only tool those arguments fit, preferring the one
    whose required arguments they fill (search_rulings over list_rulings for a query)."""
    calls = []
    for obj in _json_objects(reply):
        fits = [
            (len(tool.parameters.get("required", [])), tool.name)
            for tool in map(tools.TOOLS.get, READ_ONLY)
            if tool
            and obj
            and set(obj) <= set(tool.parameters.get("properties", {}))
            and set(tool.parameters.get("required", [])) <= set(obj)
        ]
        fits.sort(reverse=True)
        if fits and (len(fits) == 1 or fits[0][0] > fits[1][0]):
            calls.append((fits[0][1], obj))
    return calls


def is_call_text(reply: str) -> bool:
    """The reply holds a tool call written as text, or any JSON object, neither of which may be
    shown as the answer."""
    return (
        bool(parse_calls(reply))
        or looks_like_call(reply)
        or "```json" in reply
        or ("```" in reply and bool(TOOL_NAME.search(reply)))  # a tool's declaration, echoed
        or any(_json_objects(reply))
    )


def wrong_language(reply: str, lang: str) -> bool:
    """The reply is mostly in another language than the user's."""
    counts = {code: len(words.findall(reply)) for code, words in MARKERS.items()}
    own = counts.pop(lang)
    return any(count >= 5 and count > own for count in counts.values())


def consulted(lang: str, steps: list[tuple[str, dict[str, Any], list[str]]]) -> str:
    """The articles read and rulings found this turn, as a fallback when no answer came."""
    articles, dockets = [], []
    for name, args, found in steps:
        if name == "read_article" and args.get("law") and args.get("art"):
            law, art = str(args["law"]).upper(), str(args["art"])
            if lang == "fr":
                law, art = LAW_NAMES_FR.get(law, law), art.replace("Abs.", "al.")
            articles.append(f"[[{'art.' if lang == 'fr' else 'Art.'} {art} {law}]]")
        dockets.extend(d for d in found if d not in dockets)
    parts = []
    lists = (list(dict.fromkeys(articles)), dockets[:8])
    for label, items in zip(CONSULTED[lang], lists, strict=True):
        if items:
            parts.append(label + "\n" + "\n".join(f"- {item}" for item in items))
    return "\n\n".join(parts)


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
        *history(conn, chat_id, lang),
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
    notes = NOTES[lang]
    seen: set[str] = set()
    called: set[str] = set()  # tools called this turn
    steps: list[tuple[str, dict[str, Any], list[str]]] = []  # tool calls that ran, with dockets
    known = known_dockets(conn, chat_id) | ({docket} if docket else set())
    calls, forced, checked, described, translated, reply = 0, False, False, False, False, ""
    callshaped = 0  # corrections of a tool call written as the answer
    for _ in range(max_steps + 4):  # bound on model calls: tool steps plus a few corrections
        if calls >= max_steps and not forced:
            forced = True
            messages.append({"role": "user", "content": notes["forced"]})
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
            if is_call_text(reply):
                # A call written as text that could not be run (tools are off, or its arguments
                # did not parse) must not become the answer.
                if callshaped < 2:
                    callshaped += 1
                    yield correction(
                        "callshape",
                        reply,
                        notes["callshape"]
                        + " "
                        + notes["callshape_forced" if forced else "callshape_tools"],
                    )
                    continue
                break
            named = next((m for m in TOOL_NAME.finditer(reply) if m.group(0) not in called), None)
            if named and not forced and not described:
                described = True  # it wrote the call out as prose instead of making it, once
                yield correction("notool", reply, notes["notool"].format(tool=named.group(0)))
                continue
            unseen = sorted(set(re.findall(DOCKET, reply)) - known)
            if unseen and not checked:
                checked = True  # cited rulings it never looked up: research or drop them, once
                yield correction("unseen", reply, notes["unseen"].format(dockets=", ".join(unseen)))
                forced = False if calls < max_steps else forced
                continue
            if wrong_language(reply, lang) and not translated:
                translated = True
                yield correction("language", reply, notes["language"])
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
            if not error:
                steps.append((name, args, found))
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

    if not reply or is_call_text(reply):  # no answer came, or only calls written as text
        reply = "\n\n".join(filter(None, [NO_ANSWER[lang], consulted(lang, steps)]))
    stored = db.add_chat_message(conn, chat_id, "assistant", reply, {"proposals": ctx.proposals})
    yield {
        "type": "answer",
        "message": public_message(linker, conn, db.get_chat_message(conn, stored)),
    }
