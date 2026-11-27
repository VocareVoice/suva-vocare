// Root view, the knowledge base: the rulings triage marked relevant for Suva, grouped by insurance
// branch and legal category. A register on the left lists every category and acts as the filter.

import { $, $$, API, ICONS, PERIODS, esc, fmtDate, highlight, reasoningOf, state, t } from "./app.js";
import { branchLaw, buildRegister, classify, ensureTaxonomy, taxLabel } from "./categories.js";

const cache = { sig: "", items: [] };

async function load(period, q) {
  const p = PERIODS.find((x) => x.id === period) || PERIODS[0];
  const range = {};
  if (p.from) range.from = p.from;
  if (p.to) range.to = p.to;
  const sig = JSON.stringify({ ...range, q });
  if (sig === cache.sig) return;
  const base = { ...range, ...(q ? { q } : {}) };
  const items = [];
  for (;;) {
    const res = await API.list({ ...base, label: "relevant", sort: "score", order: "desc", limit: 500, offset: items.length });
    items.push(...(res.items || []));
    if (!res.items?.length || items.length >= res.total) break;
  }
  Object.assign(cache, { sig, items });
}

function readParams(params) {
  return {
    period: params.get("period") || "all",
    q: params.get("q") || "",
    branch: params.get("branch") || "",
    cat: params.get("cat") || "",
    sum: params.get("sum") || "",
    sort: params.get("sort") === "date" ? "date" : "score",
    view: params.get("view") === "flat" ? "flat" : "groups",
  };
}
function toHash(f) {
  const p = new URLSearchParams();
  if (f.period !== "all") p.set("period", f.period);
  for (const k of ["q", "branch", "cat", "sum"]) if (f[k]) p.set(k, f[k]);
  if (f.sort !== "score") p.set("sort", f.sort);
  if (f.view !== "groups") p.set("view", f.view);
  const s = p.toString();
  return "#/" + (s ? "?" + s : "");
}

const sorter = (sort) => (sort === "date"
  ? (a, b) => (b.decision_date || "").localeCompare(a.decision_date || "") || (b.score ?? 0) - (a.score ?? 0)
  : (a, b) => (b.score ?? 0) - (a.score ?? 0) || (b.decision_date || "").localeCompare(a.decision_date || ""));

// ---------------------------------------------------------------- pieces
function entry(r, terms, showCat) {
  const c = classify(r);
  const reason = reasoningOf(r);
  return `<li class="entry" data-docket="${esc(r.docket)}">
    <a class="entry__id docket" href="#/r/${encodeURIComponent(r.docket)}">${esc(r.docket)}</a>
    <div class="entry__body">
      <div class="entry__head">
        <span class="entry__date">${esc(fmtDate(r.decision_date, "long"))}</span>
        ${r.language ? `<span class="entry__lang">${esc(t(`lang.${r.language}`))}</span>` : ""}
        ${showCat ? `<span class="entry__cat" data-branch="${esc(c.branch)}" title="${esc(taxLabel("categories", c.category))}">${esc(taxLabel("categories", c.category, true))}</span>` : ""}
      </div>
      <p class="entry__title">${terms.length ? highlight(r.title || "—", terms) : esc(r.title || "—")}</p>
      ${reason ? `<p class="entry__reason">${terms.length ? highlight(reason, terms) : esc(reason)}</p>` : ""}
    </div>
    <div class="entry__sum">${r.has_summary
      ? `<span class="sumflag is-yes" title="${esc(t("rel.sum.yes"))}">${ICONS.check}DE FR</span>`
      : `<span class="sumflag" title="${esc(t("rel.sum.no"))}">${esc(t("rel.sum.open"))}</span>`}</div>
  </li>`;
}

function registerHtml(reg, f, total) {
  const link = (patch) => toHash({ ...f, ...patch });
  const cur = (on) => (on ? ' aria-current="true"' : "");
  return `<nav class="register" aria-label="${esc(t("rel.register"))}">
    <h2 class="register__title">${esc(t("rel.register"))}</h2>
    <a class="register__all" href="${link({ branch: "", cat: "" })}"${cur(!f.branch && !f.cat)}>
      <span>${esc(t("rel.all"))}</span><span class="register__n">${total}</span></a>
    ${reg.map((b) => `<section class="register__branch" data-branch="${esc(b.branch)}">
      <a class="register__b" href="${link({ branch: b.branch, cat: "" })}"${cur(f.branch === b.branch && !f.cat)} title="${esc(taxLabel("branches", b.branch))}">
        <span class="register__swatch" aria-hidden="true"></span>
        <span class="register__bname">${esc(taxLabel("branches", b.branch, true))}${branchLaw(b.branch) ? ` <span class="register__law">${esc(branchLaw(b.branch))}</span>` : ""}</span>
        <span class="register__n">${b.count}</span></a>
      <ul>${b.cats.map((c) => `<li><a href="${link({ branch: b.branch, cat: c.category })}"${cur(f.branch === b.branch && f.cat === c.category)} title="${esc(taxLabel("categories", c.category))}">
        <span>${esc(taxLabel("categories", c.category, true))}</span><span class="register__n">${c.count}</span></a></li>`).join("")}</ul>
    </section>`).join("")}
  </nav>`;
}

// ---------------------------------------------------------------- view
export async function renderRelevant(params, opts) {
  const f = readParams(params);
  document.title = `${t("rel.title")} – BGer-Monitor`;
  state.lastListHash = toHash(f);
  const app = $("#app");
  app.innerHTML = `
    <div class="relgrid">
      <aside class="relgrid__side" id="register"><div class="skel"></div><div class="skel"></div><div class="skel" style="width:60%"></div></aside>
      <div class="relgrid__main">
        <div class="filterbar">
          <label class="search">
            <span class="sr-only">${esc(t("rel.search"))}</span>${ICONS.search}
            <input type="search" id="q" value="${esc(f.q)}" placeholder="${esc(t("rel.search"))}" autocomplete="off"><kbd>/</kbd>
          </label>
          <label class="field"><span>${esc(t("f.period"))}</span>
            <select id="period">${PERIODS.filter((p) => p.id !== "custom").map((p) => `<option value="${p.id}"${p.id === f.period ? " selected" : ""}>${esc(p.label())}</option>`).join("")}</select>
          </label>
          <label class="field"><span>${esc(t("f.summary"))}</span>
            <select id="sum">${[["", t("f.summary.all")], ["yes", t("f.summary.yes")], ["no", t("f.summary.no")]].map(([v, l]) => `<option value="${v}"${v === f.sum ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>
          </label>
          <span class="seg" role="group" aria-label="${esc(t("rel.sort"))}">
            <button type="button" data-sort="score" aria-pressed="${f.sort === "score"}">${esc(t("kb.sort.score"))}</button>
            <button type="button" data-sort="date" aria-pressed="${f.sort === "date"}">${esc(t("kb.sort.date"))}</button>
          </span>
          <span class="seg" role="group" aria-label="${esc(t("rel.view"))}">
            <button type="button" data-view="groups" aria-pressed="${f.view === "groups"}">${esc(t("rel.view.groups"))}</button>
            <button type="button" data-view="flat" aria-pressed="${f.view === "flat"}">${esc(t("rel.view.flat"))}</button>
          </span>
        </div>
        <div id="relBody"><div class="skelblock">${'<div class="skel"></div>'.repeat(8)}</div></div>
      </div>
    </div>`;

  const go = (patch, replace = true) => {
    Object.assign(f, patch);
    const h = toHash(f);
    state.lastListHash = h;
    if (replace) history.replaceState(null, "", h);
  };

  const paint = () => {
    const terms = f.q.trim() ? f.q.trim().split(/\s+/) : [];
    const pool = cache.items.filter((r) => !f.sum || r.has_summary === (f.sum === "yes"));
    const reg = buildRegister(pool);
    $("#register").innerHTML = registerHtml(reg, f, pool.length);

    const selected = pool.filter((r) => {
      const c = classify(r);
      return (!f.branch || c.branch === f.branch) && (!f.cat || c.category === f.cat);
    });

    const body = $("#relBody");
    if (!selected.length) {
      body.innerHTML = `<div class="empty"><h2>${esc(t(cache.items.length ? "empty.title" : "kb.empty"))}</h2>
        <p>${esc(cache.items.length ? t("empty.filtered") : t("kb.empty.sub"))}</p>
        ${f.q || f.sum || f.branch || f.cat ? `<p><a class="btn btn--sm" href="${toHash({ ...f, q: "", sum: "", branch: "", cat: "" })}">${esc(t("f.reset"))}</a></p>` : ""}</div>`;
      return;
    }
    const sort = sorter(f.sort);
    if (f.view === "flat") {
      body.innerHTML = `<ol class="entries">${[...selected].sort(sort).map((r) => entry(r, terms, true)).join("")}</ol>`;
      return;
    }
    const groups = reg
      .filter((b) => !f.branch || b.branch === f.branch)
      .flatMap((b) => b.cats.filter((c) => !f.cat || c.category === f.cat).map((c) => ({ b, c })));
    body.innerHTML = groups.map(({ b, c }) => `
      <section class="group" data-branch="${esc(b.branch)}">
        <header class="group__head">
          <h2><a href="${toHash({ ...f, branch: b.branch, cat: c.category })}" title="${esc(taxLabel("categories", c.category))}">${esc(taxLabel("categories", c.category, true))}</a></h2>
          <span class="group__branch">${esc(taxLabel("branches", b.branch, true))}</span>
        </header>
        <ol class="entries">${[...c.items].sort(sort).map((r) => entry(r, terms, false)).join("")}</ol>
      </section>`).join("");
  };

  const reload = async () => {
    try {
      await Promise.all([load(f.period, f.q.trim()), ensureTaxonomy()]);
    } catch (e) {
      $("#relBody").innerHTML = `<div class="empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
      $("#register").innerHTML = "";
      return;
    }
    paint();
  };

  let timer;
  app.addEventListener("input", (e) => {
    if (e.target.id !== "q") return;
    clearTimeout(timer);
    timer = setTimeout(() => { go({ q: e.target.value }); reload(); }, 250);
  }, opts);
  app.addEventListener("change", (e) => {
    if (e.target.id === "period") { go({ period: e.target.value }); reload(); }
    if (e.target.id === "sum") { go({ sum: e.target.value }); paint(); }
  }, opts);
  app.addEventListener("click", (e) => {
    const s = e.target.closest("[data-sort]");
    const v = e.target.closest("[data-view]");
    if (s || v) {
      go(s ? { sort: s.dataset.sort } : { view: v.dataset.view });
      $$(s ? "[data-sort]" : "[data-view]").forEach((x) => x.setAttribute("aria-pressed", x === (s || v)));
      paint();
      return;
    }
    const li = e.target.closest(".entry[data-docket]");
    if (li && !e.target.closest("a") && !window.getSelection()?.toString()) location.hash = `#/r/${encodeURIComponent(li.dataset.docket)}`;
  }, opts);

  await reload();
}
