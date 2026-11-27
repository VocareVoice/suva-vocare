// Agent column on the right-hand side: a chat with Apertus about the UVG and the case law.
// The chat lives on the server (/api/chats/{id}); its id is kept in localStorage, so the
// conversation survives reloads until the user starts a new one. A turn streams NDJSON events:
// "user", one "step" per tool call, then "answer" (with links the server has checked) or "error".
// When the agent changes its knowledge (update_memory), the "agent-memory" event tells the
// knowledge page (knowledge.js) to reload it.

import { $, esc, t, uiLang } from "./app.js";

const CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
const CLOSE = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';
const NEW = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>';

const CHAT_KEY = "agentChat";
let chatId = localStorage.getItem(CHAT_KEY) || null;
let messages = []; // as the server returns them: {role: user|tool|assistant, ...}
let busy = false;
let loadedLang = null; // answers are rendered server-side per language (Fedlex DE/FR links)

/** The ruling the user is looking at, passed to the agent as context. */
function currentDocket() {
  const m = /^#\/r\/([^?]+)/.exec(location.hash);
  return m ? decodeURIComponent(m[1]) : null;
}

// ---------------------------------------------------------------- rendering

/** Only links the server produced: Fedlex (new tab) and rulings inside the app. */
function safeHref(href) {
  if (href.startsWith("https://www.fedlex.admin.ch/")) return { href, external: true };
  if (/^#\/r\/[\w%.-]+$/.test(href)) return { href, external: false };
  return null;
}

function inline(text) {
  // Escape first, then re-introduce the two constructs we allow: links and bold.
  let html = esc(text);
  html = html.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (all, label, rawHref) => {
    const link = safeHref(rawHref.replace(/&amp;/g, "&"));
    if (!link) return label;
    const ext = link.external ? ' target="_blank" rel="noopener"' : "";
    return `<a href="${esc(link.href)}"${ext} class="${link.external ? "ref ref--law" : "ref ref--ruling"}">${label}</a>`;
  });
  return html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
}

/** A small, safe Markdown subset: paragraphs, "- " lists, headings as bold lines. */
function markdown(text) {
  const out = [];
  let list = null;
  const flush = () => { if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; } };
  for (const block of text.split(/\n{2,}/)) {
    for (const line of block.split("\n")) {
      const item = /^\s*[-*•]\s+(.*)$/.exec(line);
      if (item) { (list ||= []).push(`<li>${inline(item[1])}</li>`); continue; }
      flush();
      const heading = /^#{1,4}\s+(.*)$/.exec(line);
      if (heading) out.push(`<p><strong>${inline(heading[1])}</strong></p>`);
      else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    }
    flush();
  }
  return out.join("");
}

function stepLabel(m) {
  if (m.tool === "correction") {
    const key = `agent.step.correction.${m.args?.kind}`;
    const label = t(key);
    return label === key ? t("agent.step.correction") : label;
  }
  const key = `agent.step.${m.tool}`;
  const label = t(key, m.args || {});
  return label === key ? t("agent.step.other", m.tool) : label;
}

function proposalCard(p) {
  const status = p.status === "open"
    ? `<div class="prop__actions">
         <button type="button" class="btn btn--primary btn--sm" data-apply="${p.id}">${esc(t("agent.prop.apply"))}</button>
         <button type="button" class="btn btn--ghost btn--sm" data-discard="${p.id}">${esc(t("agent.prop.discard"))}</button>
       </div>`
    : `<div class="prop__status prop__status--${p.status}">${esc(t(`agent.prop.${p.status}`))}</div>`;
  return `<div class="prop" data-prop="${p.id}">
    <div class="prop__head">${esc(t("agent.prop.title", p.docket, p.lang.toUpperCase()))}
      <a class="ref ref--ruling" href="#/r/${encodeURIComponent(p.docket)}">${esc(p.docket)}</a></div>
    ${p.rationale ? `<div class="prop__why">${esc(p.rationale)}</div>` : ""}
    <div class="prop__text">${esc(p.text)}</div>
    <details class="prop__old"><summary>${esc(t("agent.prop.current"))}</summary>
      <div class="prop__text prop__text--old">${p.current ? esc(p.current) : esc(t("agent.prop.none"))}</div></details>
    ${status}
  </div>`;
}

/** One tool call, collapsed to its label; opening it shows the arguments and the result. */
function stepItem(s) {
  const args = s.tool === "correction" ? "" : `<pre class="step__args">${esc(JSON.stringify({ tool: s.tool, args: s.args || {} }, null, 1))}</pre>`;
  const result = s.result ? `<pre class="step__result">${esc(s.result)}</pre>` : "";
  return `<li class="${s.error ? "step step--err" : "step"}"><details>
    <summary>${esc(stepLabel(s))}</summary>${args}${result}</details></li>`;
}

function paintLog() {
  const el = $("#agentLog");
  const parts = [`<div class="msg msg--agent">${markdown(t("agent.intro"))}</div>`];
  let steps = [];
  const flushSteps = () => {
    if (!steps.length) return;
    // The tool calls of one turn: a separate box, not a chat message, collapsed by default.
    const errors = steps.filter((s) => s.error).length;
    parts.push(`<details class="trace"><summary>${esc(t("agent.trace", steps.length, errors))}</summary>
      <ul class="steps">${steps.map(stepItem).join("")}</ul></details>`);
    steps = [];
  };
  for (const m of messages) {
    if (m.role === "tool") { steps.push(m); continue; }
    flushSteps();
    if (m.role === "user") parts.push(`<div class="msg msg--user">${esc(m.text)}</div>`);
    else if (m.role === "assistant") {
      parts.push(`<div class="msg msg--agent">${markdown(m.text || "")}</div>`);
      for (const p of m.proposals || []) parts.push(proposalCard(p));
    } else if (m.role === "note") parts.push(`<div class="msg msg--note">${esc(m.text)}</div>`);
  }
  flushSteps();
  if (busy) parts.push(`<div class="msg msg--note msg--busy">${esc(t("agent.thinking"))}</div>`);
  // Keep the steps the user opened open across repaints (a new step repaints the whole log).
  const open = new Set([...el.querySelectorAll("details[open]")].map((d) => d.dataset.i));
  el.innerHTML = parts.join("");
  el.querySelectorAll(".trace, .step details").forEach((d, i) => { d.dataset.i = i; if (open.has(String(i))) d.open = true; });
  if (!open.size) el.scrollTop = el.scrollHeight;
}

function paintContext() {
  const d = currentDocket();
  const el = $("#agentCtx");
  el.hidden = !d;
  el.textContent = d ? t("agent.context", d) : "";
}

function paintBusy() {
  $("#agentSend").disabled = busy;
  $("#agentNew").disabled = busy;
  $("#agentInput").setAttribute("aria-busy", busy);
}

/** (Re)render labels in the UI language; called on boot and on language switch. */
export function paintAgent() {
  $("#agentTab").innerHTML = `${CHAT}<span>${esc(t("agent.tab"))}</span>`;
  $("#agentTitle").innerHTML = `${CHAT}${esc(t("agent.title"))}`;
  $("#agentClose").setAttribute("aria-label", t("agent.close"));
  $("#agentNew").innerHTML = `${NEW}<span>${esc(t("agent.new"))}</span>`;
  $("#agentNew").title = t("agent.new.title");
  $("#agentInput").placeholder = t("agent.ph");
  $("#agentSend").textContent = t("agent.send");
  paintContext();
  paintLog();
  if (chatId && loadedLang && loadedLang !== uiLang && !busy) loadChat();
}

// ---------------------------------------------------------------- server

async function loadChat() {
  if (!chatId) { messages = []; paintLog(); return; }
  const res = await fetch(`/api/chats/${chatId}?lang=${uiLang}`);
  if (res.status === 404) { forgetChat(); paintLog(); return; }
  if (!res.ok) return;
  messages = (await res.json()).messages;
  loadedLang = uiLang;
  paintLog();
}

function forgetChat() {
  chatId = null;
  messages = [];
  localStorage.removeItem(CHAT_KEY);
}

async function ensureChat() {
  if (chatId) return chatId;
  const res = await fetch("/api/chats", { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  chatId = (await res.json()).id;
  localStorage.setItem(CHAT_KEY, chatId);
  loadedLang = uiLang;
  return chatId;
}

async function newChat() {
  if (busy) return;
  const old = chatId;
  forgetChat();
  paintLog();
  if (old) await fetch(`/api/chats/${old}`, { method: "DELETE" }).catch(() => {});
  $("#agentInput").focus();
}

function handle(event) {
  if (event.type === "user") messages.push(event.message);
  else if (event.type === "step") {
    messages.push({ role: "tool", tool: event.tool, args: event.args, error: event.error, result: event.result });
    if (event.tool === "update_memory" && !event.error) window.dispatchEvent(new Event("agent-memory"));
  }
  else if (event.type === "answer") messages.push(event.message);
  else if (event.type === "error") messages.push({ role: "note", text: t("agent.error", event.error) });
  paintLog();
}

async function send(text) {
  busy = true;
  paintBusy();
  paintLog();
  try {
    const id = await ensureChat();
    let res = await fetch(`/api/chats/${id}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, docket: currentDocket(), lang: uiLang }),
    });
    if (res.status === 404) { // the chat was deleted elsewhere: start a fresh one
      forgetChat();
      const fresh = await ensureChat();
      res = await fetch(`/api/chats/${fresh}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, docket: currentDocket(), lang: uiLang }),
      });
    }
    if (!res.ok) throw new Error(res.status === 409 ? t("agent.busy") : `HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) handle(JSON.parse(line));
      }
    }
    if (buffer.trim()) handle(JSON.parse(buffer));
  } catch (err) {
    messages.push({ role: "note", text: t("agent.error", err.message) });
  } finally {
    busy = false;
    paintBusy();
    paintLog();
  }
}

async function decide(id, action) {
  const res = await fetch(`/api/proposals/${id}/${action}`, { method: "POST" });
  if (!res.ok) { messages.push({ role: "note", text: t("agent.error", `HTTP ${res.status}`) }); paintLog(); return; }
  const { proposal } = await res.json();
  for (const m of messages) {
    if (m.proposals) m.proposals = m.proposals.map((p) => (p.id === proposal.id ? proposal : p));
  }
  paintLog();
  // The ruling page shows the summary: re-render it when it is the one that changed.
  if (action === "apply" && currentDocket() === proposal.docket) window.dispatchEvent(new HashChangeEvent("hashchange"));
}

// ---------------------------------------------------------------- shell

/** Open the chat with `text` in the input, for the user to complete and send. */
export function askAgent(text) {
  setOpen(true);
  const input = $("#agentInput");
  input.value = text;
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight}px`;
  input.focus();
  input.setSelectionRange(text.length, text.length);
}

function setOpen(open) {
  document.body.classList.toggle("agent-open", open);
  $("#agentTab").setAttribute("aria-expanded", open);
  $("#agent").setAttribute("aria-hidden", !open);
  localStorage.setItem("agentOpen", open ? "1" : "0");
  if (open) $("#agentInput").focus({ preventScroll: true });
}

export function initAgent() {
  document.body.insertAdjacentHTML("beforeend", `
    <button type="button" class="agent-tab" id="agentTab" aria-controls="agent" aria-expanded="false"></button>
    <aside class="agent" id="agent" aria-labelledby="agentTitle" aria-hidden="true">
      <header class="agent__head">
        <h2 id="agentTitle"></h2>
        <span class="agent__tools">
          <button type="button" class="btn btn--ghost btn--sm agent__new" id="agentNew"></button>
          <button type="button" class="btn btn--ghost btn--sm" id="agentClose">${CLOSE}</button>
        </span>
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
  $("#agentNew").addEventListener("click", newChat);
  $("#agentLog").addEventListener("click", (e) => {
    const apply = e.target.closest("[data-apply]");
    const discard = e.target.closest("[data-discard]");
    if (apply) { apply.disabled = true; decide(apply.dataset.apply, "apply"); }
    if (discard) { discard.disabled = true; decide(discard.dataset.discard, "discard"); }
  });
  const input = $("#agentInput");
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${input.scrollHeight}px`; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#agentForm").requestSubmit(); }
    if (e.key === "Escape") { e.stopPropagation(); setOpen(false); $("#agentTab").focus(); }
  });
  $("#agentForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q || busy) return;
    input.value = "";
    input.style.height = "auto";
    send(q);
  });
  window.addEventListener("hashchange", paintContext);
  setOpen(localStorage.getItem("agentOpen") !== "0");
  loadChat();
}
