// Agent panel docked on the right-hand side: a tab on the edge opens a chat drawer.
// Only the UI exists. There is no agent backend yet: `ask()` is the single place to wire one in
// (e.g. POST /api/agent with { question, docket }), and until then it answers with a notice.

import { $, esc, t } from "./app.js";

const CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
const CLOSE = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';

const log = []; // { role: "user" | "agent" | "note", text } — kept across page changes

/** The ruling the user is looking at, passed to the agent as context. */
function currentDocket() {
  const m = /^#\/r\/([^?]+)/.exec(location.hash);
  return m ? decodeURIComponent(m[1]) : null;
}

async function ask(question, docket) {
  void question; void docket; // no backend yet
  return { role: "note", text: t("agent.soon") };
}

function paintLog() {
  const el = $("#agentLog");
  const msgs = [{ role: "agent", text: t("agent.intro") }, ...log];
  el.innerHTML = msgs.map((m) => `<div class="msg msg--${m.role}">${esc(m.text)}</div>`).join("");
  el.scrollTop = el.scrollHeight;
}

function paintContext() {
  const d = currentDocket();
  const el = $("#agentCtx");
  el.hidden = !d;
  el.textContent = d ? t("agent.context", d) : "";
}

/** (Re)render labels in the UI language; called on boot and on language switch. */
export function paintAgent() {
  $("#agentTab").innerHTML = `${CHAT}<span>${esc(t("agent.tab"))}</span>`;
  $("#agentTitle").innerHTML = `${CHAT}${esc(t("agent.title"))}`;
  $("#agentClose").setAttribute("aria-label", t("agent.close"));
  $("#agentInput").placeholder = t("agent.ph");
  $("#agentSend").textContent = t("agent.send");
  paintContext();
  paintLog();
}

function setOpen(open) {
  document.body.classList.toggle("agent-open", open);
  $("#agentTab").setAttribute("aria-expanded", open);
  $("#agent").setAttribute("aria-hidden", !open);
  localStorage.setItem("agentOpen", open ? "1" : "");
  if (open) $("#agentInput").focus({ preventScroll: true });
}

export function initAgent() {
  document.body.insertAdjacentHTML("beforeend", `
    <button type="button" class="agent-tab" id="agentTab" aria-controls="agent" aria-expanded="false"></button>
    <aside class="agent" id="agent" aria-labelledby="agentTitle" aria-hidden="true">
      <header class="agent__head">
        <h2 id="agentTitle"></h2>
        <button type="button" class="btn btn--ghost btn--sm" id="agentClose">${CLOSE}</button>
      </header>
      <div class="agent__ctx" id="agentCtx" hidden></div>
      <div class="agent__log" id="agentLog" aria-live="polite"></div>
      <form class="agent__form" id="agentForm">
        <textarea id="agentInput" rows="1"></textarea>
        <button type="submit" class="btn btn--primary" id="agentSend"></button>
      </form>
    </aside>`);
  paintAgent();

  $("#agentTab").addEventListener("click", () => setOpen(true));
  $("#agentClose").addEventListener("click", () => { setOpen(false); $("#agentTab").focus(); });
  const input = $("#agentInput");
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${input.scrollHeight}px`; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#agentForm").requestSubmit(); }
    if (e.key === "Escape") { e.stopPropagation(); setOpen(false); $("#agentTab").focus(); }
  });
  $("#agentForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    input.style.height = "auto";
    log.push({ role: "user", text: q });
    paintLog();
    log.push(await ask(q, currentDocket()));
    paintLog();
  });
  window.addEventListener("hashchange", paintContext);
  if (localStorage.getItem("agentOpen")) setOpen(true);
}
