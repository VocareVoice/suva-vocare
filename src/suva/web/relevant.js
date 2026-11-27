// Root view, the knowledge base: the rulings triage marked relevant for Suva, grouped by insurance
// branch and legal category. A register on the left lists every category and acts as the filter.
// No search box: searching (and editing) the knowledge base is meant to go through the agent panel.

import { $, API, ICONS, esc, fmtDate, reasoningOf, state, t } from "./app.js";
import { branchLaw, buildRegister, classify, ensureTaxonomy, taxLabel } from "./categories.js";

const cache = { sig: "", items: [] };

// All relevant rulings, every period.
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

function readParams(params) {
  return { branch: params.get("branch") || "", cat: params.get("cat") || "" };
}
function toHash(f) {
  const p = new URLSearchParams();
  for (const k of ["branch", "cat"]) if (f[k]) p.set(k, f[k]);
  const s = p.toString();
  return "#/" + (s ? "?" + s : "");
}

// Most relevant first, newer first on equal score.
const byRelevance = (a, b) => (b.score ?? 0) - (a.score ?? 0) || (b.decision_date || "").localeCompare(a.decision_date || "");

// ---------------------------------------------------------------- pieces
function entry(r) {
  const reason = reasoningOf(r);
  return `<li class="entry" data-docket="${esc(r.docket)}">
    <a class="entry__id docket" href="#/r/${encodeURIComponent(r.docket)}">${esc(r.docket)}</a>
    <div class="entry__body">
      <div class="entry__head">
        <span class="entry__date">${esc(fmtDate(r.decision_date, "long"))}</span>
        ${r.language ? `<span class="entry__lang">${esc(t(`lang.${r.language}`))}</span>` : ""}
      </div>
      <p class="entry__title">${esc(r.title || "—")}</p>
      ${reason ? `<p class="entry__reason">${esc(reason)}</p>` : ""}
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
        <div id="relBody"><div class="skelblock">${'<div class="skel"></div>'.repeat(8)}</div></div>
      </div>
    </div>`;

  const paint = () => {
    const pool = cache.items;
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
        ${f.branch || f.cat ? `<p><a class="btn btn--sm" href="${toHash({ branch: "", cat: "" })}">${esc(t("f.reset"))}</a></p>` : ""}</div>`;
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
        <ol class="entries">${[...c.items].sort(byRelevance).map((r) => entry(r)).join("")}</ol>
      </section>`).join("");
  };

  const reload = async () => {
    try {
      await Promise.all([load(), ensureTaxonomy()]);
    } catch (e) {
      $("#relBody").innerHTML = `<div class="empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
      $("#register").innerHTML = "";
      return;
    }
    paint();
  };

  app.addEventListener("click", (e) => {
    const li = e.target.closest(".entry[data-docket]");
    if (li && !e.target.closest("a") && !window.getSelection()?.toString()) location.hash = `#/r/${encodeURIComponent(li.dataset.docket)}`;
  }, opts);

  await reload();
}
