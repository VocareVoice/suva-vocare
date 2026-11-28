"""Record the screen clips of the demo video from a running Praecedens instance.

Drives headless Chromium at 1920x1080 through the shots of docs/demo_video_script.md and
writes one clip per shot part to OUT/clips/<part>.mp4, captured frame by frame with the
DevTools screencast (sharper than Playwright's built-in video). The long waits (live summary,
added ruling, agent answer) happen between two clips, so they never reach the video. A drawn
cursor stands in for the mouse, which headless Chromium does not render.

Run against a freshly loaded database with the summary of 9C_197/2026 and the add of
8C_700/2024 pre-warmed (see the preparation checklist of the script). With --only, the shots
that change the database (6, 7, 9) run only when one of their parts is asked for, so shots 8
and 10 can be recorded on a database that already holds the correction of shot 7:

    uv run --with playwright python scripts/demo_video/record.py \
        --base-url http://127.0.0.1:8090 OUT
"""

import argparse
import base64
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from shots import ADD_DOCKET, AGENT_QUESTION, EXPERT_COMMENT

W, H = 1920, 1080
PARTS = ["1", "2", "3", "4", "5", "6a", "6b", "7", "8", "9a", "9b", "10", "11a", "11b"]

CURSOR_JS = """
(() => {
  const install = () => {
    if (document.getElementById("__cursor")) return;
    const c = document.createElement("div");
    c.id = "__cursor";
    c.innerHTML = `<svg width="26" height="32" viewBox="0 0 26 32">
      <path d="M2 2 L2 26 L8 20 L12.5 30 L16.5 28.2 L12 18.5 L20.5 18.5 Z"
      fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>`;
    c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;" +
      "transform:translate(-100px,-100px);filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))";
    const ring = document.createElement("div");
    ring.style.cssText = "position:fixed;left:-20px;top:-20px;width:40px;height:40px;" +
      "border-radius:50%;" +
      "background:rgba(0,155,180,.35);z-index:2147483646;pointer-events:none;opacity:0;" +
      "transition:opacity .35s, transform .35s;transform:scale(.4)";
    document.documentElement.append(ring, c);
    addEventListener("mousemove", (e) => {
      c.style.transform = `translate(${e.clientX - 2}px,${e.clientY - 2}px)`;
      ring.style.left = `${e.clientX - 20}px`;
      ring.style.top = `${e.clientY - 20}px`;
    }, true);
    addEventListener("mousedown", () => {
      ring.style.transition = "none"; ring.style.opacity = "1"; ring.style.transform = "scale(.4)";
      requestAnimationFrame(() => {
        ring.style.transition = "opacity .45s, transform .45s";
        ring.style.opacity = "0"; ring.style.transform = "scale(1.3)";
      });
    }, true);
  };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", install);
  else install();
})();
"""

# Select text from `start` to the end of `end` inside `root`, growing the selection over
# `ms` milliseconds like a mouse drag; `end` is its first occurrence after `start`.
SELECT_JS = """
async ([root, start, end, ms]) => {
  const nodes = [];
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let text = "";
  for (let n; (n = walk.nextNode()); ) { nodes.push([n, text.length]); text += n.data; }
  const from = text.indexOf(start);
  if (from < 0) throw new Error("not found: " + start);
  const to = text.indexOf(end, from) + end.length;
  if (to < end.length) throw new Error("not found: " + end);
  const at = (i) => {
    for (let k = nodes.length - 1; k >= 0; k--)
      if (nodes[k][1] <= i) return [nodes[k][0], i - nodes[k][1]];
  };
  const sel = getSelection();
  const steps = Math.max(1, Math.round(ms / 30));
  for (let s = 1; s <= steps; s++) {
    const r = document.createRange();
    r.setStart(...at(from));
    r.setEnd(...at(from + Math.round(((to - from) * s) / steps)));
    sel.removeAllRanges(); sel.addRange(r);
    await new Promise((ok) => setTimeout(ok, 30));
  }
}
"""

# Adding a ruling the recording machine already fetched and rated replays from the caches in
# well under a second; hold the response so the progress card is on screen before the cut.
HOLD_ADD_JS = """
(ms) => {
  const f = window.fetch;
  window.fetch = async (url, opts) => {
    const res = f(url, opts);
    if (opts?.method !== "POST" || !String(url).endsWith("/api/rulings")) return res;
    await new Promise((ok) => setTimeout(ok, ms));
    return res;
  };
}
"""


class Screencast:
    """Collects DevTools screencast frames for one clip and encodes them to MP4."""

    def __init__(self, page: Page, out: Path):
        self.out = out
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.frames: list[tuple[float, bytes]] = []
        self.name = ""

    def _frame(self, ev):
        self.frames.append((time.time(), base64.b64decode(ev["data"])))
        self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

    def start(self, name: str):
        self.name, self.frames = name, []
        self.cdp.send(
            "Page.startScreencast",
            {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1},
        )

    def stop(self):
        stopped = time.time()
        self.cdp.send("Page.stopScreencast")
        frames_dir = self.out / "frames" / self.name
        shutil.rmtree(frames_dir, ignore_errors=True)
        frames_dir.mkdir(parents=True)
        lines = []
        for i, (ts, data) in enumerate(self.frames):
            path = frames_dir / f"{i:05d}.jpg"
            path.write_bytes(data)
            nxt = self.frames[i + 1][0] if i + 1 < len(self.frames) else stopped
            lines += [f"file '{path.resolve()}'", f"duration {max(nxt - ts, 0.001):.4f}"]
        lines.append(f"file '{(frames_dir / f'{len(self.frames) - 1:05d}.jpg').resolve()}'")
        (frames_dir / "list.txt").write_text("\n".join(lines) + "\n")
        clip = self.out / "clips" / f"{self.name}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(frames_dir / "list.txt"),
                "-vf",
                f"fps=30,scale={W}:{H},format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "16",
                str(clip),
            ],
            check=True,
        )
        print(f"clip {self.name}: {len(self.frames)} frames, {stopped - self.frames[0][0]:.1f} s")


class Director:
    """Mouse and keyboard moves paced for the camera."""

    def __init__(self, page: Page):
        self.page = page
        self.x, self.y = W * 0.55, H * 0.6

    def wait(self, ms: float):
        self.page.wait_for_timeout(ms)

    def glide(self, x: float, y: float, ms: float = 700):
        steps = max(1, int(ms / 16))
        x0, y0 = self.x, self.y
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            self.page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            self.page.wait_for_timeout(16)
        self.x, self.y = x, y

    def point(self, locator, ms: float = 700, dx: float = 0.5, dy: float = 0.5):
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        self.glide(box["x"] + box["width"] * dx, box["y"] + box["height"] * dy, ms)

    def click(
        self, locator, ms: float = 700, settle: float = 250, dx: float = 0.5, dy: float = 0.5
    ):
        self.point(locator, ms, dx, dy)
        self.wait(settle)
        self.page.mouse.down()
        self.wait(90)
        self.page.mouse.up()

    def scroll_to(self, locator, block: str = "start", ms: float = 900):
        locator.evaluate(f"e => e.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        self.wait(ms)


def record(base: str, out: Path, only: set[str] | None, agent_timeout_s: float):
    def wanted(part: str) -> bool:
        return only is None or part in only

    def done_after(part: str) -> bool:
        return only is not None and all(PARTS.index(p) <= PARTS.index(part) for p in only)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": W, "height": H}, device_scale_factor=1, locale="de-CH"
        )
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        cam = Screencast(page, out)
        d = Director(page)
        page.goto(f"{base}/#/")
        page.evaluate("localStorage.clear()")
        page.reload()
        page.locator("#navKb a[data-navbranch=uv]").wait_for()
        page.mouse.move(d.x, d.y)
        d.wait(1500)

        # 1: start page, no interaction
        if wanted("1"):
            cam.start("1")
            d.wait(7500)
            cam.stop()

        # 2: branch list, Unfallversicherung, category label of 8C_686/2025
        cam.start("2") if wanted("2") else None
        d.glide(W * 0.4, H * 0.45, 500)
        d.point(page.locator("#navKb a[data-navbranch=uv]"), 900)
        d.wait(500)
        d.point(page.locator("#navKb a[data-navbranch=iv]"), 500)
        d.wait(700)
        d.click(page.locator("#navKb a[data-navbranch=uv]"), 500)
        cat = page.locator('.entry[data-docket="8C_686/2025"] .entry__cat')
        cat.wait_for()
        d.wait(1300)
        d.click(cat, 1000)
        page.wait_for_function("location.hash.includes('cat=unfallbegriff')")
        d.wait(2800)
        cam.stop() if wanted("2") else None

        # 3: all rulings of Q2 2026 by score
        cam.start("3") if wanted("3") else None
        d.click(page.locator("a.navlink[data-nav=all]"), 900)
        period = page.locator("select[data-f=period]")
        period.wait_for()
        d.wait(1000)
        d.click(period, 700)
        period.select_option("2026q2")
        d.wait(1200)
        rows = page.locator("tbody tr")
        rows.first.wait_for()
        for i in range(5):
            d.point(rows.nth(i), 900 if i == 0 else 650, dx=0.35)
            d.wait(650)
        d.wait(800)
        cam.stop() if wanted("3") else None

        # 4: 8C_686/2025, score and reasoning, UI language FR and back
        cam.start("4") if wanted("4") else None
        d.click(page.locator('tbody tr[data-docket="8C_686/2025"] a.docket'), 600)
        page.locator(".dhead__name").wait_for()
        d.wait(1200)
        rel = page.get_by_text("Relevanz", exact=True).first
        d.point(rel, 900)
        d.wait(1300)
        d.point(page.get_by_text("Begründung", exact=True).first, 700, dx=0.2)
        d.wait(1500)
        d.click(page.locator("button[data-lang=fr]"), 1100)
        d.wait(1200)
        d.glide(W * 0.62, H * 0.35, 900)
        d.wait(1500)
        d.click(page.locator("button[data-lang=de]"), 1100)
        d.wait(1300)
        cam.stop() if wanted("4") else None

        # 5: the two summaries, the "Aussagen der ersten Stunde" passage, a statute chip
        cam.start("5") if wanted("5") else None
        de = page.locator(".summary[lang=de] .summary__text")
        fr = page.locator(".summary[lang=fr] .summary__text")
        d.glide(W * 0.3, H * 0.55, 700)
        d.wait(400)
        page.evaluate(
            SELECT_JS, [de.element_handle(), 'Den "Aussagen der ersten Stunde"', "(E. 3.3).", 1400]
        )
        d.wait(2300)
        d.glide(W * 0.48, H * 0.6, 700)
        page.evaluate(
            SELECT_JS, [fr.element_handle(), "Les « déclarations", "(consid. 3.3).", 1400]
        )
        d.wait(2300)
        page.evaluate("getSelection().removeAllRanges()")
        chip = page.locator('.statutes button[data-goto="ATSG 4"]').first
        d.scroll_to(chip, "center", 1200)
        d.point(chip, 800)
        d.wait(900)
        d.click(chip, 300)
        d.wait(3000)
        cam.stop() if wanted("5") else None

        if done_after("5"):
            return browser.close()

        # 6: a ruling the triage did not flag, summarised on demand
        if wanted("6a") or wanted("6b"):
            cam.start("6a") if wanted("6a") else None
            page.evaluate("scrollTo({top: 0, behavior: 'smooth'})")
            d.wait(700)
            d.click(page.locator(".dback"), 700)
            notrel = page.locator("button[data-label=not_relevant]")
            notrel.wait_for()
            d.wait(500)
            d.click(notrel, 800)
            row = page.locator("tbody tr").first
            page.locator("tbody tr", has_text="9C_197/2026").first.wait_for()
            d.wait(900)
            d.click(row.locator("a.docket"), 800)
            gen = page.locator("#genBtn")
            gen.wait_for()
            d.wait(1300)
            d.click(gen, 800)
            page.locator(".progress").first.wait_for()
            d.wait(2200)
            cam.stop() if wanted("6a") else None
            page.locator("#summaryCard .summaries").wait_for(timeout=40 * 60_000)
            page.locator("#toast").wait_for()
            if wanted("6b"):
                cam.start("6b")
            page.locator("#summaryCard").evaluate(
                "e => scrollTo({top: e.getBoundingClientRect().top + scrollY - 24})"
            )
            d.glide(W * 0.4, H * 0.5, 900)
            d.wait(3500)
            cam.stop() if wanted("6b") else None

        if done_after("6b"):
            return browser.close()

        # 7: an expert raises the score of 9C_197/2026 above the threshold
        if wanted("7"):
            cam.start("7")
            card = page.locator("#relevanceCard")
            d.scroll_to(card, "center", 900)
            d.click(page.locator("#scoreEdit"), 800)
            rng = page.locator("[data-score-range]")
            rng.wait_for()
            d.wait(700)
            d.point(rng, 700, dx=0.27)
            d.wait(250)
            page.mouse.down()
            d.glide(d.x + rng.bounding_box()["width"] * 0.19, d.y, 1400)
            page.mouse.up()
            d.wait(900)
            d.click(page.locator("[data-score-comment]"), 600)
            page.keyboard.type(EXPERT_COMMENT, delay=14)
            d.wait(400)
            d.click(page.locator("[data-score-save]"), 700)
            page.locator("#relevanceCard .relevance__expert").wait_for()
            d.glide(W * 0.62, H * 0.42, 700)
            d.wait(2600)
            cam.stop()
            print("expert score:", page.locator("#relevanceCard .score-lg").first.inner_text())

        # 8: the expert corrections next to the model's scores (the clip starts on the page)
        d.click(page.locator("a.navlink[data-nav=adjust]"), 900)
        adj = page.locator('.adjtable tr[data-docket="9C_197/2026"]')
        adj.wait_for()
        cam.start("8") if wanted("8") else None
        d.wait(900)
        d.point(adj.locator(".adjchange"), 900)
        d.wait(1300)
        d.point(adj.locator(".adjreason"), 800, dx=0.3)
        d.wait(1800)
        cam.stop() if wanted("8") else None

        # 9: add a ruling that is not in the database by its number
        if wanted("9a") or wanted("9b"):
            d.click(page.locator("a.navlink[data-nav=all]"), 900)
            add = page.locator("#addBtn")
            add.wait_for()
            cam.start("9a") if wanted("9a") else None
            d.wait(700)
            d.click(add, 700)
            d.click(page.locator("#addDocket"), 500)
            page.keyboard.type(ADD_DOCKET, delay=70)
            d.wait(400)
            page.evaluate(HOLD_ADD_JS, 4000)
            d.click(page.locator("#addForm button[type=submit]"), 600)
            page.locator("#addStatus .progress").wait_for()
            d.wait(2200)
            cam.stop() if wanted("9a") else None
            page.wait_for_function(f"decodeURIComponent(location.hash).includes({ADD_DOCKET!r})")
            page.locator("#relevanceCard").wait_for()
            page.locator("#toast.is-on").wait_for()
            cam.start("9b") if wanted("9b") else None
            d.point(page.locator("#relevanceCard .score-lg").first, 900)
            d.wait(1300)
            d.point(page.locator("#relevanceCard .reasoning"), 800, dx=0.3)
            d.wait(2500)
            cam.stop() if wanted("9b") else None

        # 10: the statutes, Art. 6 UVG through the article filter
        d.click(page.locator("a.navlink[data-nav=law]"), 900)
        q = page.locator("#lawQ")
        q.wait_for()
        cam.start("10") if wanted("10") else None
        d.wait(1000)
        d.click(q, 700)
        page.keyboard.type("6", delay=120)
        page.locator("#art-6").wait_for()
        d.wait(600)
        d.point(page.locator("#art-6 .lawart__text"), 900, dx=0.3)
        d.wait(2000)
        cam.stop() if wanted("10") else None

        if done_after("10"):
            return browser.close()

        # 11: the agent, asked from the category view of shot 2
        if wanted("11a") or wanted("11b"):
            d.click(page.locator("#navKb a[data-navbranch=uv]"), 900)
            cat = page.locator('.entry[data-docket="8C_686/2025"] .entry__cat')
            cat.wait_for()
            cam.start("11a") if wanted("11a") else None
            d.wait(600)
            d.click(cat, 800)
            page.wait_for_function("location.hash.includes('cat=unfallbegriff')")
            d.wait(700)
            d.click(page.locator("#agentNew"), 900)
            d.wait(400)
            d.click(page.locator("#agentInput"), 600)
            page.keyboard.type(AGENT_QUESTION, delay=22)
            d.wait(500)
            d.click(page.locator("#agentSend"), 500)
            page.locator(".msg--busy").wait_for()
            d.wait(1800)
            cam.stop() if wanted("11a") else None
            page.locator(".msg--busy").wait_for(state="detached", timeout=agent_timeout_s * 1000)
            answer = page.locator("#agentLog .msg--agent").last
            print("agent answer:\n" + answer.inner_text())
            (out / "agent_answer.txt").write_text(answer.inner_text())
            cam.start("11b") if wanted("11b") else None
            # Scroll only the chat log: scrollIntoView would also scroll the list beside it.
            heading = answer.get_by_text("Relevante Normen").first
            if heading.count():
                heading.evaluate(
                    "e => { const log = document.getElementById('agentLog');"
                    " log.scrollTo({top: log.scrollTop + e.getBoundingClientRect().top"
                    " - log.getBoundingClientRect().top - 12, behavior: 'smooth'}); }"
                )
            d.wait(1200)
            link = answer.locator("a.ref--ruling", has_text="8C_686/2025").first
            if link.count():
                d.point(link, 1000)
            d.wait(3000)
            cam.stop() if wanted("11b") else None

        browser.close()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "out", type=Path, help="output directory (clips/ and frames/ are written there)"
    )
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--only", help="comma-separated parts to record, e.g. 1,2,6a (default: all)")
    ap.add_argument(
        "--agent-timeout", type=float, default=900, help="seconds to wait for the agent"
    )
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    record(args.base_url.rstrip("/"), args.out, only, args.agent_timeout)


if __name__ == "__main__":
    main()
