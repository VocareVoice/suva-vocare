"""Deterministic checks of how the agent loop reads tool calls Apertus writes as text, and that
no such call ever becomes the answer. No endpoint needed: `python -m suva.agent.selftest`."""

import sys
from typing import Any

from suva import db
from suva.agent import loop
from suva.llm import Reply, ToolCall

ANSWER_DE = (
    "Es stellt sich die Frage, ob ein Unfall im Sinne von [[Art. 4 ATSG]] vorliegt und ob der "
    "Kausalzusammenhang gegeben ist. Das Verschulden eines anderen Mitarbeiters ändert an der "
    "Leistungspflicht der Unfallversicherung grundsätzlich nichts."
)
ANSWER_FR = (
    "La question est de savoir si l'événement constitue un accident au sens de l'[[art. 4 LPGA]] "
    "et si le lien de causalité naturelle et adéquate est établi. La maladresse d'un collègue "
    "ne change en principe rien à l'obligation de prester de l'assurance-accidents."
)
ANSWER_EN = (
    "Let me search more specifically for cases involving another employee's carelessness "
    "causing injury, focusing on causation and benefit reduction. This is the answer and it "
    "will be in English for the user."
)
# The final answer from the conversation this test was written for (2026-11-28).
LIVE_REPLY = (
    "Let me search more specifically for cases involving another employee's carelessness "
    "causing injury, focusing on causation and benefit reduction.\n\nTool call 6: More "
    'targeted search\n```json\n{"tool_call": "search_rulings", "query": "Kausalität '
    'Arbeitsunfall anderer Mitarbeiter Verschulden Leistungskürzung UVG", "limit": 8}\n```'
)

PARSE_CASES: list[tuple[str, str, list[tuple[str, dict[str, Any]]]]] = [
    (
        "tool_call key, flat args, fenced, prose around",
        LIVE_REPLY,
        [
            (
                "search_rulings",
                {
                    "query": "Kausalität Arbeitsunfall anderer Mitarbeiter Verschulden "
                    "Leistungskürzung UVG",
                    "limit": 8,
                },
            )
        ],
    ),
    (
        "tool + args",
        '{"tool": "read_article", "args": {"law": "UVG", "art": "6 Abs. 2"}}',
        [("read_article", {"law": "UVG", "art": "6 Abs. 2"})],
    ),
    (
        "name + arguments as a JSON string",
        '{"name": "read_ruling", "arguments": "{\\"docket\\": \\"8C_1/2025\\"}"}',
        [("read_ruling", {"docket": "8C_1/2025"})],
    ),
    (
        "function as a string + parameters",
        'Ich suche:\n```json\n{"function": "search_rulings", "parameters": {"query": "Meniskus"}}'
        "\n```",
        [("search_rulings", {"query": "Meniskus"})],
    ),
    (
        "OpenAI shape",
        '{"type": "function", "function": {"name": "read_article", "arguments": '
        '{"law": "ATSG", "art": "4"}}}',
        [("read_article", {"law": "ATSG", "art": "4"})],
    ),
    (
        "nested tool_call object",
        '{"tool_call": {"name": "search_rulings", "arguments": {"query": "Sturz"}}}',
        [("search_rulings", {"query": "Sturz"})],
    ),
    (
        "type naming the tool, flat args",
        '```json\n{"type": "list_rulings", "category": "unfallbegriff", "limit": 5}\n```',
        [("list_rulings", {"category": "unfallbegriff", "limit": 5})],
    ),
    (
        "tool name as key",
        '{"read_ruling": {"docket": "8C_2/2025"}}',
        [("read_ruling", {"docket": "8C_2/2025"})],
    ),
    (
        "several calls, fenced separately",
        'Zuerst:\n```json\n{"tool": "read_article", "args": {"law": "UVG", "art": "4"}}\n```\n'
        'Dann:\n```json\n{"tool": "read_article", "args": {"law": "ATSG", "art": "4"}}\n```',
        [
            ("read_article", {"law": "UVG", "art": "4"}),
            ("read_article", {"law": "ATSG", "art": "4"}),
        ],
    ),
    (
        "a list of calls",
        '{"tool_calls": [{"function": {"name": "read_ruling", "arguments": "{\\"docket\\": '
        '\\"8C_3/2025\\"}"}}, {"name": "search_rulings", "args": {"query": "Knie"}}]}',
        [("read_ruling", {"docket": "8C_3/2025"}), ("search_rulings", {"query": "Knie"})],
    ),
    (
        "name with key=value arguments",
        'read_article with law="UVV", art="25"',
        [("read_article", {"law": "UVV", "art": "25"})],
    ),
    (
        "arguments only, after English prose",
        'Let me try a broader search without category first:\n\n```json\n{\n  "query": '
        '"Ungeschick Arbeitsunfall Kollege Verletzung",\n  "limit": 10\n}\n```',
        [("search_rulings", {"query": "Ungeschick Arbeitsunfall Kollege Verletzung", "limit": 10})],
    ),
    (
        "arguments only, a docket",
        '{"docket": "8C_4/2025"}',
        [("read_ruling", {"docket": "8C_4/2025"})],
    ),
    (
        "arguments only, a category",
        '{"category": "kausalitaet"}',
        [("list_rulings", {"category": "kausalitaet"})],
    ),
    (
        "label, name, key and quoted value",
        'Tool call: search_rulings with query "Ungeschick anderer Arbeitnehmer Unfallbegriff"',
        [("search_rulings", {"query": "Ungeschick anderer Arbeitnehmer Unfallbegriff"})],
    ),
    (
        "label, two quoted values",
        'Tool call: list_rulings with category "unfallbegriff" and query "Ungeschick"',
        [("list_rulings", {"category": "unfallbegriff", "query": "Ungeschick"})],
    ),
    ("a plain answer", ANSWER_DE, []),
]
# Replies that hold no call to run but must not be shown as the answer either.
NOT_ANSWERS = [
    'Die Werte {"a": 1} sind Beispiele.',
    '```json\n{"content": "Merk dir das"}\n```',  # update_memory is never inferred
    "```json\n[1, 2]\n```",
    # the template's declaration of a tool, echoed with the arguments filled in
    '```text\ntype search_rulings = (_: {\n  query: "Ungeschick",\n  limit: 5\n}) => any;\n```',
]


class ScriptedLLM:
    """Returns the scripted replies in order, recording whether tools were on."""

    def __init__(self, replies: list[Reply]) -> None:
        self.replies = replies
        self.tools_on: list[bool] = []

    def chat_tools(self, messages: Any, tools: Any, **params: Any) -> Reply:
        self.tools_on.append(bool(tools))
        return self.replies.pop(0) if self.replies else Reply(LIVE_REPLY, [])


def run(
    replies: list[Reply],
    text: str = "Ein Arbeiter wurde verletzt.",
    lang: str = "de",
    chat_id: str = "c",
    conn: Any = None,
    max_steps: int = 10,
) -> tuple[list[dict], Any]:
    conn = conn or db.connect(":memory:")
    if not db.chat_exists(conn, chat_id):
        db.create_chat(conn, chat_id)
    llm = ScriptedLLM(replies)
    events = list(loop.run_turn(conn, llm, chat_id, text, lang=lang, max_steps=max_steps))  # type: ignore[arg-type]
    return events, conn


def answer(events: list[dict]) -> str:
    return next(e["message"]["text"] for e in events if e["type"] == "answer")


def steps(events: list[dict]) -> list[str]:
    return [
        e["tool"] if e["tool"] != "correction" else f"correction:{e['args']['kind']}"
        for e in events
        if e["type"] == "step"
    ]


def check_loop() -> list[str]:
    failures = []

    def expect(name: str, ok: bool, detail: Any) -> None:
        if not ok:
            failures.append(f"{name}: {detail}")

    # The live reply is run as a call, then the model answers.
    events, _ = run([Reply(LIVE_REPLY, []), Reply(ANSWER_DE, [])])
    expect("text call runs", steps(events) == ["search_rulings"], steps(events))
    expect("text call runs: answer", "Unfall" in answer(events), answer(events))

    # Tools off and the model keeps writing the call: the answer is the fallback, never JSON.
    events, _ = run(
        [Reply("", [ToolCall("1", "read_article", '{"law": "ATSG", "art": "4"}')])]
        + [Reply(LIVE_REPLY, [])] * 10,
        max_steps=1,
    )
    text = answer(events)
    expect("no JSON in answer", "{" not in text and "search_rulings" not in text, text)
    expect("fallback names what was read", "Art. 4 ATSG" in text, text)
    expect("fallback is German", text.startswith("Ich konnte"), text)

    # Same in French: corrections and fallback in French.
    events, _ = run(
        [Reply("", [ToolCall("1", "read_article", '{"law": "ATSG", "art": "4"}')])]
        + [Reply(LIVE_REPLY, [])] * 10,
        lang="fr",
        max_steps=1,
    )
    text = answer(events)
    corrections = [e["result"] for e in events if e["type"] == "step" and e["tool"] == "correction"]
    expect("fr fallback", text.startswith("Je n'ai pas pu") and "art. 4 LPGA" in text, text)
    expect(
        "fr corrections", all("[Système]" in c for c in corrections) and corrections, corrections
    )

    # An English answer to a German question is sent back once.
    events, _ = run([Reply(ANSWER_EN, []), Reply(ANSWER_DE, [])])
    expect("language correction", steps(events) == ["correction:language"], steps(events))
    expect("language: German answer", answer(events).startswith("Es stellt"), answer(events))
    expect("German not flagged", not loop.wrong_language(ANSWER_DE, "de"), ANSWER_DE)
    expect("German flagged for French", loop.wrong_language(ANSWER_DE, "fr"), ANSWER_DE)
    expect("French not flagged", not loop.wrong_language(ANSWER_FR, "fr"), ANSWER_FR)

    # A stuck answer stored earlier is not replayed: the follow-up sees the no-answer note.
    conn = db.connect(":memory:")
    db.create_chat(conn, "c")
    db.add_chat_message(conn, "c", "user", "Frage", {"lang": "de"})
    db.add_chat_message(conn, "c", "assistant", LIVE_REPLY, {})
    replayed = loop.history(conn, "c", "de")
    expect("history drops call text", "tool_call" not in replayed[-1]["content"], replayed)
    return failures


def main() -> int:
    failures = []
    for name, reply, expected in PARSE_CASES:
        got = loop.parse_calls(reply)
        if got != expected:
            failures.append(f"parse {name}: got {got}, expected {expected}")
        if bool(expected) != loop.is_call_text(reply):
            failures.append(f"is_call_text {name}: {loop.is_call_text(reply)}")
    for reply in NOT_ANSWERS:
        if loop.parse_calls(reply) or not loop.is_call_text(reply):
            failures.append(f"not an answer: {reply!r}: {loop.parse_calls(reply)}")
    failures += check_loop()
    for failure in failures:
        print("FAIL", failure)
    print(f"{len(PARSE_CASES)} parser cases, loop scenarios: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
