// Adjustments (#/adjust): every relevance score a legal expert changed, next to the triage's own
// score, and an LLM summary of what the corrections have in common (/api/adjustments). The
// summary is read-only input for the next step of the feedback loop, a better triage prompt;
// nothing here changes the pipeline.

import { $, esc, fmtDate, headlineOf, scoreBadge, t, uiLang } from "./app.js";
import { ensureTaxonomy, taxLabel } from "./categories.js";

async function request(method, path) {
  const res = await fetch(path, { method, headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* keep the status */ }
    throw new Error(detail);
  }
  return res.json();
}

export const loadAdjustments = () => request("GET", `/api/adjustments?lang=${uiLang}`);

// The LLM answers in short Markdown: "## " headings, "- " bullets, paragraphs.
function markdown(text) {
  const out = [];
  let list = [];
  const flush = () => { if (list.length) { out.push(`<ul>${list.join("")}</ul>`); list = []; } };
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  for (const raw of text.split("\n")) {
    // Strip code formatting the model sometimes wraps around a line ("- `- text`").
    const line = raw.trim().replace(/^(-\s+)?`+(?:-\s+)?/, "$1").replace(/`+$/, "").trim();
    if (!line) { flush(); continue; }
    const h = /^#{1,4}\s+(.*)$/.exec(line);
    const li = /^[-*•]\s+(.*)$/.exec(line);
    if (h) { flush(); out.push(`<h3>${inline(h[1])}</h3>`); }
    else if (li) list.push(`<li>${inline(li[1])}</li>`);
    else { flush(); out.push(`<p>${inline(line)}</p>`); }
  }
  flush();
  return out.join("");
}

function statTiles(s) {
  const tile = (n, label) => `<div class="adjstat"><span class="adjstat__n">${n}</span><span class="adjstat__l">${esc(label)}</span></div>`;
  return `<div class="adjstats">
    ${tile(s.total, t("adj.stat.total"))}${tile(s.raised, t("adj.stat.raised"))}${tile(s.lowered, t("adj.stat.lowered"))}
    ${tile(s.added_to_kb, t("adj.stat.added"))}${tile(s.removed_from_kb, t("adj.stat.removed"))}
  </div>`;
}

function summaryCard(data, busy = false, error = "") {
  const s = data.summary;
  const stale = s && (s.adjustment_count !== data.items.length || data.items.some((i) => i.adjusted_at > s.created_at));
  const btn = `<button type="button" class="btn ${s ? "btn--ghost" : "btn--primary"} btn--sm" id="adjRun" ${busy || !data.items.length ? "disabled" : ""}>
    ${esc(t(busy ? "adj.sum.running" : s ? "adj.sum.rerun" : "adj.sum.run"))}</button>`;
  let body;
  if (busy) body = `<div class="skelblock">${'<div class="skel"></div>'.repeat(4)}</div><p class="muted">${esc(t("adj.sum.wait"))}</p>`;
  else if (s) body = `<div class="adjsum__text">${markdown(s.text)}</div>`;
  else body = `<p class="muted">${esc(t(data.items.length ? "adj.sum.none" : "adj.sum.empty"))}</p>`;
  return `<section class="card adjsum" id="adjSummary">
    <div class="card__head"><h2 class="card__title">${esc(t("adj.sum.title"))}</h2>${btn}</div>
    <div class="card__body">
      ${error ? `<div class="alert">${esc(error)}</div>` : ""}
      ${s && stale && !busy ? `<div class="adjsum__stale">${esc(t("adj.sum.stale"))}</div>` : ""}
      ${body}
      ${s && !busy ? `<p class="adjsum__meta">${esc(t("adj.sum.meta", fmtDate(s.created_at.slice(0, 10)), s.adjustment_count, s.model || "LLM"))}</p>` : ""}
      <p class="adjsum__next">${esc(t("adj.sum.next"))}</p>
    </div>
  </section>`;
}

function row(i) {
  const title = headlineOf(i) || i.title || "—";
  const reason = i.comment || "";
  const delta = i.model_score == null ? null : i.expert_score - i.model_score;
  return `<tr data-docket="${esc(i.docket)}">
    <td class="c-docket"><a class="docket" href="#/r/${encodeURIComponent(i.docket)}">${esc(i.docket)}</a>
      <span class="subdocket">${fmtDate(i.decision_date)}</span></td>
    <td class="c-cat">${i.branch ? `<div class="entry__class" data-branch="${esc(i.branch)}">
      <span class="entry__branch">${esc(taxLabel("branches", i.branch, true))}</span>
      <span class="entry__cat">${esc(taxLabel("categories", i.primary_category, true))}</span></div>` : `<span class="muted">—</span>`}</td>
    <td class="c-change"><div class="adjchange">
      ${scoreBadge(i.model_score)}<span class="adjchange__arrow" aria-hidden="true">→</span>${scoreBadge(i.expert_score)}
    </div>${delta != null ? `<span class="adjchange__delta ${delta < 0 ? "is-down" : "is-up"}">${delta > 0 ? "+" : ""}${delta}</span>` : ""}</td>
    <td><div class="ruling-title">${esc(title)}</div>
      ${reason ? `<div class="adjreason">${esc(reason)}</div>` : `<div class="adjreason muted">${esc(t("adj.noreason"))}</div>`}</td>
    <td class="c-date num">${fmtDate(i.adjusted_at.slice(0, 10))}</td>
  </tr>`;
}

function table(items) {
  if (!items.length) {
    return `<div class="empty"><h2>${esc(t("adj.empty.title"))}</h2><p>${esc(t("adj.empty.text"))}</p>
      <p><a class="btn btn--sm" href="#/all">${esc(t("nav.all"))}</a></p></div>`;
  }
  return `<table class="rulings adjtable">
    <thead><tr><th class="c-docket">${esc(t("col.docket"))}</th><th class="c-cat">${esc(t("f.category"))}</th>
      <th class="c-change">${esc(t("adj.col.change"))}</th><th>${esc(t("adj.col.reason"))}</th><th class="c-date">${esc(t("adj.col.date"))}</th></tr></thead>
    <tbody>${items.map(row).join("")}</tbody>
  </table>`;
}

export async function renderAdjustments(opts) {
  const app = $("#app");
  document.title = `${t("nav.adjust")} – Praecedens`;
  app.innerHTML = `<header class="pagehead">
      <h1>${esc(t("nav.adjust"))}</h1>
      <p class="pagehead__lede">${esc(t("adj.intro"))}</p>
    </header>
    <div id="adjBody"><div class="skelblock">${'<div class="skel"></div>'.repeat(6)}</div></div>`;
  let data;
  try {
    [data] = await Promise.all([loadAdjustments(), ensureTaxonomy()]);
  } catch (e) {
    $("#adjBody").innerHTML = `<div class="card empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
    return;
  }
  const paint = (busy = false, error = "") => {
    if (!$("#adjBody")) return; // left the page while the summary was running
    $("#adjBody").innerHTML = `${data.items.length ? statTiles(data.stats) : ""}
      ${summaryCard(data, busy, error)}
      <section class="tablebox">${table(data.items)}</section>`;
  };
  paint();
  app.addEventListener("click", async (e) => {
    if (e.target.closest("#adjRun")) {
      paint(true);
      try {
        data = await request("POST", `/api/adjustments/summary?lang=${uiLang}`);
        paint();
      } catch (err) {
        paint(false, t("adj.sum.err", err.message));
      }
      return;
    }
    const tr = e.target.closest("tr[data-docket]");
    if (tr && !e.target.closest("a")) location.hash = `#/r/${encodeURIComponent(tr.dataset.docket)}`;
  }, opts);
}
