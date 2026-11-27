// Agent knowledge (#/agent): one free text from /api/memory that goes into every system prompt of
// the side-panel agent. The default is the summary pipeline's style instructions; users edit it
// here or reset it, and the agent adds to it with its update_memory tool (agent.js then fires
// "agent-memory", and the page reloads the text unless the user has unsaved changes).

import { $, esc, t, uiLang } from "./app.js";

let saved = null; // the text as last loaded or saved: {content, default, updated_by, updated_at}

const onPage = () => location.hash.startsWith("#/agent");

function status(k) {
  if (k.default) return t("mem.status.default");
  const who = t(k.updated_by === "agent" ? "mem.by.agent" : "mem.by.user");
  return `${who}${k.updated_at ? ` · ${k.updated_at.slice(0, 16)}` : ""}`;
}

function paintState() {
  const ta = $("#memText");
  if (!ta || !saved) return;
  const dirty = ta.value !== saved.content;
  $("#memSave").disabled = !dirty || !ta.value.trim();
  $("#memUndo").hidden = !dirty;
  $("#memReset").hidden = saved.default && !dirty;
  $("#memStatus").textContent = dirty ? t("mem.status.dirty") : status(saved);
  const fmt = (n) => n.toLocaleString(uiLang === "fr" ? "fr-CH" : "de-CH");
  $("#memCount").textContent = t("mem.chars", fmt(ta.value.length), fmt(saved.max_length));
}

function show(knowledge) {
  saved = knowledge;
  $("#memText").value = knowledge.content;
  $("#memText").maxLength = knowledge.max_length;
  $("#memText").disabled = false;
  paintState();
}

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function run(button, method, path, body) {
  button.disabled = true;
  $("#memError").hidden = true;
  try {
    show(await request(method, path, body));
    if (method !== "GET") $("#memStatus").textContent = t("mem.saved");
  } catch (err) {
    $("#memError").textContent = t("agent.error", err.message);
    $("#memError").hidden = false;
    paintState();
  }
}

export async function renderKnowledge(opts) {
  const app = $("#app");
  document.title = `${t("nav.agent")} – Praecedens`;
  saved = null;
  app.innerHTML = `<header class="pagehead">
      <h1>${esc(t("nav.agent"))}</h1>
      <p class="pagehead__lede">${esc(t("mem.intro"))}</p>
    </header>
    <section class="card know">
      <textarea class="know__text" id="memText" spellcheck="false" disabled aria-label="${esc(t("nav.agent"))}"></textarea>
      <div class="know__bar">
        <span class="know__status"><span id="memStatus"></span> · <span id="memCount"></span></span>
        <span class="know__actions">
          <button type="button" class="btn btn--ghost btn--sm" id="memReset" hidden>${esc(t("mem.reset"))}</button>
          <button type="button" class="btn btn--ghost btn--sm" id="memUndo" hidden>${esc(t("mem.undo"))}</button>
          <button type="button" class="btn btn--primary btn--sm" id="memSave" disabled>${esc(t("mem.save"))}</button>
        </span>
      </div>
      <div class="alert" id="memError" hidden></div>
    </section>`;
  const ta = $("#memText");
  ta.addEventListener("input", paintState, opts);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "s" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!$("#memSave").disabled) $("#memSave").click(); }
  }, opts);
  $("#memSave").addEventListener("click", (e) => run(e.currentTarget, "PUT", "/api/memory", { content: ta.value }), opts);
  $("#memReset").addEventListener("click", (e) => run(e.currentTarget, "POST", "/api/memory/reset"), opts);
  $("#memUndo").addEventListener("click", () => show(saved), opts);
  await run($("#memSave"), "GET", "/api/memory");
}

// The agent changed its knowledge in the chat: show the new text, unless the user is editing.
window.addEventListener("agent-memory", async () => {
  const ta = $("#memText");
  if (!onPage() || !ta || !saved || ta.value !== saved.content) return;
  try { show(await request("GET", "/api/memory")); } catch { /* keep the text shown */ }
});
