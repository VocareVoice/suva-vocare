"""The shots of docs/demo_video_script.md: cut time, caption, voice-over and on-screen action.

`parts` names the clips record.py writes for a shot; a shot with two parts has a cut between
them (the live summary and the agent answer take minutes). `split` is the share of the shot's
time the first part gets. `uncaptioned` parts show no caption (it would hide the
"Zusammenfassung erstellt" toast).
"""

SHOTS = [
    {
        "n": 1,
        "seconds": 10,
        "parts": ["1"],
        "title_card": 3.0,
        "caption": "Praecedens - Federal Supreme Court rulings for Suva, powered by Apertus",
        "voice": "Every quarter the Federal Supreme Court publishes about two thousand rulings. "
        "Suva's lawyers search bger.ch by hand for the few dozen that matter to accident "
        "insurance.",
        "action": "Title card, then the app on Wissensbasis (start page).",
    },
    {
        "n": 2,
        "seconds": 11,
        "parts": ["2"],
        "caption": "Knowledge base: relevant rulings by insurance branch and legal category",
        "voice": "Praecedens fetches every ruling and keeps the relevant ones in a knowledge base, "
        "by insurance branch and legal category, each with a one-line headline.",
        "action": "Hover the branch list, click Unfallversicherung, then the category label "
        "Unfallbegriff & Listenverletzung (row 8C_686/2025).",
    },
    {
        "n": 3,
        "seconds": 14,
        "parts": ["3"],
        "caption": "April-June 2026: 2,096 rulings, 131 rated by Apertus, 100 relevant",
        "voice": "Here are all rulings of April to June 2026, ranked by relevance. A deterministic "
        "filter drops those unrelated to accident insurance; Apertus rates the rest, with a score "
        "and an explanation.",
        "action": "Alle Urteile, Zeitraum Q2 2026, sort Score; hover down the first rows.",
    },
    {
        "n": 4,
        "seconds": 14,
        "parts": ["4"],
        "caption": "Score and reasoning - written by Apertus in German and in French",
        "voice": "Rank three: a ruling on the definition of an accident. The score comes with a "
        "reasoning, written separately in German and in French - the lawyer reads it in the "
        "language of the interface.",
        "action": "Open 8C_686/2025; point at Relevanz and Begründung; switch the UI to FR and "
        "back to DE.",
    },
    {
        "n": 5,
        "seconds": 18,
        "parts": ["5"],
        "caption": "Two summaries in Suva's house style - written, not translated",
        "voice": "The summaries follow Suva's house style: facts, the cantonal decision, the "
        "principle the Court recalls, its application and the outcome - every statement with its "
        "consideration. German and French are each written from the ruling, not translated. "
        "Every cited statute links to its passage in the original.",
        "action": "Highlight the 'Aussagen der ersten Stunde' passage in Text DE and in Text FR; "
        "click the chip Art. 4 ATSG under Zitierte Normen.",
    },
    {
        "n": 6,
        "seconds": 14,
        "parts": ["6a", "6b"],
        "split": 0.65,
        "uncaptioned": ["6b"],
        "caption": "Summarise on demand",
        "cut_caption": "Apertus 70B - cut",
        "voice": "And the rulings the triage did not flag? This invalidity insurance ruling scored "
        "just below the threshold, but how much weight an expert report keeps against the "
        "treating doctors matters for accident insurance too. One click, and Apertus writes both "
        "summaries on demand.",
        "action": "Back to Alle Urteile, Triage: Nicht relevant, open 9C_197/2026 (score 27), "
        "click Zusammenfassen; cut; the finished DE | FR summary.",
    },
    {
        "n": 7,
        "seconds": 16,
        "parts": ["7a", "7b"],
        "split": 0.62,
        "caption": "Legal assistant: searches the knowledge base, cites rulings and statutes",
        "cut_caption": "Apertus 70B - cut",
        "voice": "The lawyer can also describe a case. The assistant searches the knowledge base "
        "and the statutes and answers with links to the rulings - here, straight back to the "
        "ruling we just read.",
        "action": "Category view of shot 2, Neuer Chat, ask the question, Senden; cut; the answer "
        "with Relevante Urteile, hover 8C_686/2025.",
    },
    {
        "n": 8,
        "seconds": 23,
        "parts": ["8"],
        "closing_card": True,
        "voice": "Everything you saw - triage, reasoning, summaries, the assistant - runs on "
        "Apertus, the Swiss open model, and nothing else: on-premise, air-gapped or in a Swiss "
        "cloud. On the practice period, our top 60 held 96 percent of Suva's picks for Q4 2025, "
        "and every hold-out summary got the outcome right.",
        "action": "Closing card over the dimmed detail page of 8C_686/2025.",
    },
]

AGENT_QUESTION = (
    "Eine Versicherte meldet einen Sturz erst, nachdem die Suva Leistungen abgelehnt hat. "
    "Welche Urteile gibt es zu den Aussagen der ersten Stunde?"
)
