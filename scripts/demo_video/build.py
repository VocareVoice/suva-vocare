"""Cut the recorded clips into the demo video: cards, captions, synthetic voice-over, timing sheet.

Reads OUT/clips/ (written by record.py) and writes to OUT:

- Praecedens_demo_silent.mp4  the cut video with title card, captions and closing card
- voice_synth.m4a              a placeholder voice-over (macOS `say`), each line at its shot
- Praecedens_demo.mp4          the two muxed (assemble.sh)
- voiceover_timing.md          per shot: start-end, the line to speak, the on-screen action

Each shot gets the time of docs/demo_video_script.md, unless its voice line needs more; the
extra comes out of the shots with time to spare, so the total stays at TOTAL seconds. A clip
longer than its slot is sped up, a shorter one holds its last frame.

    uv run --with playwright python scripts/demo_video/build.py OUT
"""

import argparse
import html
import json
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright
from shots import SHOTS

HERE = Path(__file__).resolve().parent
LOGO = HERE.parents[1] / "src" / "suva" / "web" / "suva-logo.svg"
W, H, FPS = 1920, 1080, 30
TOTAL = 119.5
VOICE_LEAD = 0.4  # silence before each line
VOICE_TAIL = 0.5  # silence after each line before the next shot

FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"

CAPTION_HTML = """<div style="position:absolute;left:0;right:0;bottom:44px;display:flex;
  justify-content:center">
  <div style="max-width:1500px;background:rgba(17,24,39,.88);color:#fff;font:500 34px/1.3 {font};
    padding:16px 34px 17px 30px;border-radius:14px;border-left:8px solid #00a0b4;
    box-shadow:0 6px 24px rgba(0,0,0,.25)">{text}</div></div>"""

CUT_HTML = """<div style="position:absolute;top:28px;right:500px;background:rgba(17,24,39,.82);
  color:#fff;font:600 24px/1 {font};padding:12px 18px;border-radius:10px;letter-spacing:.02em">
  &#9986; {text}</div>"""

TITLE_HTML = """<div style="position:absolute;inset:0;background:#fff;display:flex;
  flex-direction:column;align-items:center;justify-content:center;font-family:{font};color:#111827">
  <img src="data:image/svg+xml;base64,{logo}" style="height:96px;margin-bottom:46px">
  <div style="font-size:128px;font-weight:700;letter-spacing:-.02em">Praecedens</div>
  <div style="font-size:42px;color:#374151;margin-top:22px">Federal Supreme Court rulings for Suva,
    powered by <b style="color:#00a0b4">Apertus</b></div>
  <div style="position:absolute;bottom:64px;font-size:28px;color:#6b7280">Team Vocare</div></div>"""

CLOSING_HTML = """<div style="position:absolute;inset:0;background:rgba(10,14,22,.80);display:flex;
  align-items:center;justify-content:center;font-family:{font}">
  <div style="width:1480px;color:#fff">
    <div style="font-size:72px;font-weight:700;margin-bottom:42px">100 %
      <span style="color:#3fd0e0">Apertus</span>
      <span style="font-size:34px;font-weight:400;color:#cbd5e1;margin-left:14px">
        apertus-v1-5-70b</span></div>
    {blocks}
    <div style="margin-top:46px;font-size:30px;color:#94a3b8">Praecedens &middot; Team Vocare</div>
  </div></div>"""

CLOSING_BLOCKS = [
    (
        "Open model",
        "Open weights, OpenAI-compatible endpoint; runs on-premise, air-gapped or in a "
        "Swiss cloud. No external CDNs, fonts or analytics in the UI.",
    ),
    (
        "Relevance",
        "Practice period with Suva's own labels: our top 60 of the quarter hold "
        "<b>96 %</b> (Q4 2025) and <b>77 %</b> (Q1 2026) of the rulings Suva listed; <b>all</b> of "
        "them score 28 or more, the relevance threshold.",
    ),
    (
        "Summaries",
        "10 hold-out rulings never shown to the model: outcome right in <b>20 of 20</b> "
        "DE/FR summaries; no statute, figure or date the ruling does not contain.",
    ),
    (
        "April-June 2026",
        "<b>2,096</b> rulings, <b>131</b> rated by Apertus, <b>100</b> relevant, "
        "top 30 summarised in DE and FR.",
    ),
]


def run(*cmd: str):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cmd], check=True)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout)


def render_cards(work: Path):
    import base64

    logo = base64.b64encode(LOGO.read_bytes()).decode()
    blocks = "".join(
        f'<div style="display:flex;gap:36px;margin:0 0 26px;font-size:33px;line-height:1.4">'
        f'<div style="flex:0 0 300px;color:#3fd0e0;font-weight:700">{k}</div>'
        f'<div style="color:#e5e7eb">{v}</div></div>'
        for k, v in CLOSING_BLOCKS
    )
    cards = {
        "title": TITLE_HTML.format(font=FONT, logo=logo),
        "closing": CLOSING_HTML.format(font=FONT, blocks=blocks),
    }
    for s in SHOTS:
        if s.get("caption"):
            cards[f"caption_{s['n']}"] = CAPTION_HTML.format(
                font=FONT, text=html.escape(s["caption"])
            )
        if s.get("cut_caption"):
            cards[f"cut_{s['n']}"] = CUT_HTML.format(font=FONT, text=html.escape(s["cut_caption"]))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        for name, body in cards.items():
            page.set_content(
                f'<html><body style="margin:0;background:transparent">{body}</body></html>'
            )
            page.screenshot(path=str(work / f"{name}.png"), omit_background=True)
        browser.close()


def synth_voice(work: Path, voice: str, rate: int) -> list[float]:
    lengths = []
    for s in SHOTS:
        aiff = work / f"voice_{s['n']}.aiff"
        subprocess.run(
            ["say", "-v", voice, "-r", str(rate), "-o", str(aiff), s["voice"]], check=True
        )
        lengths.append(duration(aiff))
    return lengths


def fit_slots(lengths: list[float]) -> list[float]:
    """Script times, stretched where a voice line needs more and shrunk where there is room."""
    script = [float(s["seconds"]) for s in SHOTS]
    need = [max(VOICE_LEAD + v + VOICE_TAIL, 0.0) for v in lengths]
    slots = [max(a, b) for a, b in zip(script, need, strict=True)]
    over = sum(slots) - TOTAL
    if over > 0:
        room = [sl - n for sl, n in zip(slots, need, strict=True)]
        if sum(room) < over:
            raise SystemExit(
                f"voice-over needs {sum(need):.1f} s, more than {TOTAL:.0f} s: raise --rate"
            )
        slots = [sl - over * r / sum(room) for sl, r in zip(slots, room, strict=True)]
    return slots


def fit_clip(clip: Path, seconds: float) -> str:
    """The filter that fits `clip` to `seconds`: speed it up, or hold its last frame."""
    length = duration(clip)
    if length > seconds:
        return f"setpts=PTS*{seconds / length:.5f},fps={FPS},trim=duration={seconds:.3f}"
    hold = seconds - length + 0.1
    return f"fps={FPS},tpad=stop_mode=clone:stop_duration={hold:.3f},trim=duration={seconds:.3f}"


def encode(args: list[str], out: Path):
    run(
        *args,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        str(out),
    )


def build_segments(out: Path, work: Path, slots: list[float]) -> list[Path]:
    clips = out / "clips"
    segs = []
    for s, slot in zip(SHOTS, slots, strict=True):
        n = s["n"]
        if s.get("closing_card"):
            seg = work / f"seg_{n}.mp4"
            encode(
                [
                    "-loop",
                    "1",
                    "-t",
                    f"{slot:.3f}",
                    "-i",
                    str(clips / f"{n}.png"),
                    "-loop",
                    "1",
                    "-t",
                    f"{slot:.3f}",
                    "-i",
                    str(work / "closing.png"),
                    "-filter_complex",
                    "[0:v]boxblur=6:1[b];[b][1:v]overlay=0:0,fade=t=in:d=0.6,"
                    f"fade=t=out:st={slot - 1:.3f}:d=1",
                ],
                seg,
            )
            segs.append(seg)
            continue
        parts = s["parts"]
        title = s.get("title_card", 0.0)
        if title:
            seg = work / f"seg_{n}_title.mp4"
            encode(
                [
                    "-loop",
                    "1",
                    "-t",
                    f"{title:.3f}",
                    "-i",
                    str(work / "title.png"),
                    "-vf",
                    f"fade=t=in:d=0.5,fade=t=out:st={title - 0.4:.3f}:d=0.4",
                ],
                seg,
            )
            segs.append(seg)
        rest = slot - title
        times = [rest] if len(parts) == 1 else [rest * s["split"], rest * (1 - s["split"])]
        for i, (part, t) in enumerate(zip(parts, times, strict=True)):
            clip = clips / f"{part}.mp4"
            seg = work / f"seg_{part}.mp4"
            graph = f"[0:v]{fit_clip(clip, t)}[v];[v][1:v]overlay=0:0"
            inputs = [
                "-i",
                str(clip),
                "-loop",
                "1",
                "-t",
                f"{t:.3f}",
                "-i",
                str(work / f"caption_{n}.png"),
            ]
            if i == 1 and s.get("cut_caption"):
                inputs += ["-loop", "1", "-t", "1.8", "-i", str(work / f"cut_{n}.png")]
                graph += "[c];[c][2:v]overlay=0:0:eof_action=pass"
            if title and i == 0:
                graph += ",fade=t=in:d=0.4"
            encode([*inputs, "-filter_complex", graph, "-t", f"{t:.3f}"], seg)
            segs.append(seg)
    return segs


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("out", type=Path, help="the directory record.py wrote clips/ to")
    ap.add_argument("--voice", default="Daniel", help="macOS voice for the placeholder voice-over")
    ap.add_argument(
        "--rate", type=int, default=182, help="words per minute of the placeholder voice"
    )
    args = ap.parse_args()
    out: Path = args.out
    work = out / "build"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    render_cards(work)
    lengths = synth_voice(work, args.voice, args.rate)
    slots = fit_slots(lengths)
    starts = [sum(slots[:i]) for i in range(len(slots))]

    segs = build_segments(out, work, slots)
    (work / "segments.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in segs))
    silent = out / "Praecedens_demo_silent.mp4"
    run(
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(work / "segments.txt"),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(silent),
    )

    inputs, labels = [], []
    for i, (s, start) in enumerate(zip(SHOTS, starts, strict=True)):
        inputs += ["-i", str(work / f"voice_{s['n']}.aiff")]
        ms = int((start + VOICE_LEAD) * 1000)
        labels.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    mix = ";".join(labels) + ";" + "".join(f"[a{i}]" for i in range(len(SHOTS)))
    mix += f"amix=inputs={len(SHOTS)}:normalize=0,apad,atrim=duration={sum(slots):.3f}"
    run(
        *inputs,
        "-filter_complex",
        mix,
        "-ac",
        "2",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out / "voice_synth.m4a"),
    )

    for name in ("assemble.sh", "README.md"):
        shutil.copy(HERE / name, out / name)
    subprocess.run([str(out / "assemble.sh"), str(out / "voice_synth.m4a")], check=True)

    rows = []
    for s, start, slot in zip(SHOTS, starts, slots, strict=True):
        rows.append(
            f"## Shot {s['n']} - {mmss(start)} to {mmss(start + slot)} ({slot:.1f} s)\n\n"
            f"Speak (start at {mmss(start + VOICE_LEAD)}):\n\n> {s['voice']}\n\n"
            f"On screen: {s['action']}\n"
        )
    (out / "voiceover_timing.md").write_text(
        "# Voice-over timing - Praecedens demo\n\n"
        f"Total {mmss(sum(slots))}. Record your voice against `Praecedens_demo_silent.mp4` "
        "(play it and "
        "speak each line when its shot starts), save the take as `voice.m4a` next to it and run "
        "`./assemble.sh voice.m4a`. The placeholder voice (`voice_synth.m4a`) starts each line "
        f"{VOICE_LEAD} s into its shot.\n\n" + "\n".join(rows)
    )
    (out / "slots.json").write_text(
        json.dumps(
            [
                {
                    "shot": s["n"],
                    "start": round(a, 2),
                    "seconds": round(b, 2),
                    "voice_seconds": round(v, 2),
                }
                for s, a, b, v in zip(SHOTS, starts, slots, lengths, strict=True)
            ],
            indent=1,
        )
    )
    print(
        f"total {sum(slots):.1f} s; "
        + ", ".join(f"{s['n']}: {b:.1f}" for s, b in zip(SHOTS, slots, strict=True))
    )


def mmss(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


if __name__ == "__main__":
    main()
