// Root view, the knowledge base: the rulings triage marked relevant for Suva, as one list with
// sortable columns (ruling, category, subject); most relevant first until a column is sorted.
// The side navigation picks the insurance branch, a category label in the list the category.
// No search box: searching (and editing) the knowledge base is meant to go through the agent panel.

import { $, API, esc, headlineOf, reasoningOf, state, t } from "./app.js";
import { BRANCH_ORDER, classify, ensureTaxonomy, taxLabel } from "./categories.js";

const cache = { sig: "", items: [] };

// All relevant rulings, every period; shared with the side navigation (branch counts).
let pending = null;
export function loadKnowledgeBase() {
  pending ||= load().then(() => cache.items, (e) => { pending = null; throw e; });
  return pending;
}
async function load() {
  if (cache.sig) return;
  const base = {};
  const items = [];
  for (;;) {
    const res = await API.list({ ...base, label: "relevant", sort: "score", order: "desc", limit: 500, offset: items.length });
    items.push(...(res.items || []));
    if (!res.items?.length || items.length >= res.total) break;
  }
  Object.assign(cache, { sig: "loaded", items });
}

const SORTS = ["docket", "cat", "title"];
function readParams(params) {
  const sort = SORTS.includes(params.get("sort")) ? params.get("sort") : "";
  return { branch: params.get("branch") || "", cat: params.get("cat") || "", sort, dir: sort && params.get("dir") === "desc" ? "desc" : "asc" };
}
function toHash(f) {
  const p = new URLSearchParams();
  for (const k of ["branch", "cat", "sort"]) if (f[k]) p.set(k, f[k]);
  if (f.sort && f.dir === "desc") p.set("dir", "desc");
  const s = p.toString();
  return "#/" + (s ? "?" + s : "");
}

// Most relevant first, newer first on equal score.
const byRelevance = (a, b) => (b.score ?? 0) - (a.score ?? 0) || (b.decision_date || "").localeCompare(a.decision_date || "");

// Ruling numbers sort by year, then court division, then number: 8C_17/2026 after 8C_686/2025.
const docketKey = (d) => {
  const m = /^(\d+[A-Z])_(\d+)\/(\d{4})$/.exec(d || "");
  return m ? `${m[3]} ${m[1]} ${m[2].padStart(5, "0")}` : d || "";
};
const collator = new Intl.Collator("de", { sensitivity: "base", numeric: true });
const SORT_KEYS = {
  docket: (r) => docketKey(r.docket),
  cat: (r) => taxLabel("categories", classify(r).category, true),
  // Across all branches the column reads branch first, so it sorts by branch, then category.
  branchCat: (r) => `${String(BRANCH_ORDER.indexOf(classify(r).branch) + 1 || 9)} ${taxLabel("categories", classify(r).category, true)}`,
  title: (r) => headlineOf(r) || r.title || "",
};
function sorted(items, f) {
  if (!f.sort) return [...items].sort(byRelevance);
  const key = SORT_KEYS[f.sort === "cat" && !f.branch ? "branchCat" : f.sort];
  const sign = f.dir === "desc" ? -1 : 1;
  return [...items].sort((a, b) => sign * collator.compare(key(a), key(b)) || byRelevance(a, b));
}

function headerRow(f) {
  const th = (key, label, cls) => {
    const on = f.sort === key;
    return `<button type="button" class="entries__th ${cls}" data-sort="${key}"${on ? ` aria-sort="${f.dir === "desc" ? "descending" : "ascending"}"` : ""}>
      ${esc(label)} <span class="arrow">${on && f.dir === "desc" ? "▼" : "▲"}</span></button>`;
  };
  return `<div class="entries__head">${th("docket", t("col.docket"), "entries__th--id")}${th("cat", t("f.category"), "")}${th("title", t("col.subject"), "")}</div>`;
}

// ---------------------------------------------------------------- pieces
// Columns: ruling number | insurance branch (only when the list spans all branches) above the
// legal category (e.g. "Natürliche Kausalität"), each linking to its filter | headline, subject
// and reasoning.
function entry(r, f) {
  const reason = reasoningOf(r);
  const c = classify(r);
  return `<li class="entry" data-docket="${esc(r.docket)}" data-branch="${esc(c.branch)}">
    <a class="entry__id docket" href="#/r/${encodeURIComponent(r.docket)}">${esc(r.docket)}</a>
    <div class="entry__class">
      ${f.branch ? "" : `<a class="entry__branch" href="${toHash({ ...f, branch: c.branch, cat: "" })}" title="${esc(taxLabel("branches", c.branch))}">${esc(taxLabel("branches", c.branch, true))}</a>`}
      <a class="entry__cat" href="${toHash({ ...f, branch: c.branch, cat: c.category })}" title="${esc(taxLabel("categories", c.category))}">${esc(taxLabel("categories", c.category, true))}</a>
    </div>
    <div class="entry__body">
      <p class="entry__title">${esc(headlineOf(r) || r.title || "—")}</p>
      ${headlineOf(r) && r.title ? `<p class="entry__subject">${esc(r.title)}</p>` : ""}
      ${reason ? `<p class="entry__reason">${esc(reason)}</p>` : ""}
    </div>
  </li>`;
}

// Heading: the knowledge base, the chosen branch, or a category with a way back to its branch.
function headHtml(f, n) {
  if (!f.branch && !f.cat) return `<header class="kbhead"><h1>${esc(t("rel.title"))}</h1><span class="kbhead__n">${n}</span></header>`;
  const branch = taxLabel("branches", f.branch, true);
  if (!f.cat) return `<header class="kbhead"><h1>${esc(branch)}</h1><span class="kbhead__n">${n}</span></header>`;
  return `<header class="kbhead"><span class="kbhead__crumb"><a href="${toHash({ branch: f.branch, cat: "" })}">${esc(branch)}</a> ›</span>
    <h1>${esc(taxLabel("categories", f.cat, true))}</h1><span class="kbhead__n">${n}</span></header>`;
}

// ---------------------------------------------------------------- view
export async function renderRelevant(params, opts) {
  const f = readParams(params);
  document.title = `${t("rel.title")} – BGer-Monitor`;
  state.lastListHash = toHash(f);
  const app = $("#app");
  app.innerHTML = `
    <div id="relHead"></div>
    <div id="relBody"><div class="skelblock">${'<div class="skel"></div>'.repeat(8)}</div></div>`;

  const paint = () => {
    const pool = cache.items;

    const selected = pool.filter((r) => {
      const c = classify(r);
      return (!f.branch || c.branch === f.branch) && (!f.cat || c.category === f.cat);
    });

    $("#relHead").innerHTML = headHtml(f, selected.length);
    const body = $("#relBody");
    if (!selected.length) {
      body.innerHTML = `<div class="empty"><h2>${esc(t(cache.items.length ? "empty.title" : "kb.empty"))}</h2>
        <p>${esc(cache.items.length ? t("empty.filtered") : t("kb.empty.sub"))}</p>
        ${f.branch || f.cat ? `<p><a class="btn btn--sm" href="${toHash({ branch: "", cat: "" })}">${esc(t("f.reset"))}</a></p>` : ""}</div>`;
      return;
    }
    body.innerHTML = `<div class="kblist">${headerRow(f)}<ol class="entries">${sorted(selected, f).map((r) => entry(r, f)).join("")}</ol></div>`;
  };

  const reload = async () => {
    try {
      await Promise.all([loadKnowledgeBase(), ensureTaxonomy()]);
    } catch (e) {
      $("#relBody").innerHTML = `<div class="empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
      return;
    }
    paint();
  };

  app.addEventListener("click", (e) => {
    // Sorting: ascending first, then descending, then back to most relevant first.
    const th = e.target.closest("[data-sort]");
    if (th) {
      const key = th.dataset.sort;
      if (f.sort !== key) Object.assign(f, { sort: key, dir: "asc" });
      else if (f.dir === "asc") f.dir = "desc";
      else Object.assign(f, { sort: "", dir: "asc" });
      history.replaceState(null, "", toHash(f));
      state.lastListHash = toHash(f);
      paint();
      return;
    }
    const li = e.target.closest(".entry[data-docket]");
    if (li && !e.target.closest("a") && !window.getSelection()?.toString()) location.hash = `#/r/${encodeURIComponent(li.dataset.docket)}`;
  }, opts);

  await reload();
}
