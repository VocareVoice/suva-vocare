// Knowledge base views: funnel overview, topic map / topic tiles, and the page of one topic.
// Rulings reach the knowledge base when triage marks them relevant for Suva; they are then
// grouped by legal topic so a lawyer can go straight to the rulings on the question at hand.

import { $, $$, API, ICONS, PERIODS, band, esc, fmtDate, highlight, scoreBadge, state, t, uiLang } from "./app.js";

// ---------------------------------------------------------------- categories
// The categorisation stage delivers `categories` (array of strings or {label|name|id}) or a single
// `category` per ruling. Until it does, rulings are grouped by the legal area the court names at
// the start of the title ("Unfallversicherung (…)", "Assurance-invalidité (…)"), merged across
// German, French and Italian.
const TITLE_RE = /^([^(]+?)\s*(?:\(|$)/;
const AREAS = [
  ["uv", /unfallversicherung|assurance[- ]accidents|infortuni/i],
  ["iv", /invalidenversicherung|assurance[- ]invalidit|per l.invalidit/i],
  ["ahv", /alters- und hinterlassenen|assurance[- ]vieillesse|vecchiaia/i],
  ["el", /erg[äa]nzungsleistung|prestations? compl[ée]mentaire|prestazion[ei] complementar/i],
  ["bvg", /berufliche vorsorge|pr[ée]voyance professionnelle|previdenza professionale/i],
  ["kv", /krankenversicherung|assurance[- ]maladie|assicurazione malattie/i],
  ["alv", /arbeitslosenversicherung|assurance[- ]ch[ôo]mage|disoccupazione/i],
  ["sv", /sozialversicherung|assurances? sociales?|assicurazioni sociali/i],
];

export function categoriesOf(r) {
  if (Array.isArray(r.categories) && r.categories.length) {
    const names = r.categories.filter(Boolean).map((c) => (typeof c === "string" ? c : c.label || c.name || c.id));
    if (names.some(Boolean)) return [...new Set(names.filter(Boolean))];
  }
  if (r.category) return [typeof r.category === "string" ? r.category : r.category.label || r.category.name];
  return [areaOf(r) || t("kb.uncat")];
}

export function areaOf(r) {
  if (r.area || r.domain) return r.area || r.domain;
  const head = (TITLE_RE.exec(r.title || "") || [])[1] || "";
  const hit = AREAS.find(([, re]) => re.test(head));
  return hit ? t(`area.${hit[0]}`) : head.trim();
}

const catHref = (name) => `#/c/${encodeURIComponent(name)}`;

// ---------------------------------------------------------------- data
const kb = { sig: "", items: [], corpus: 0, period: "all" };

async function loadKb(period) {
  const p = PERIODS.find((x) => x.id === period) || PERIODS[0];
  const range = {};
  if (p.from) range.from = p.from;
  if (p.to) range.to = p.to;
  const sig = JSON.stringify(range);
  if (sig === kb.sig && kb.items.length) return;
  const items = [];
  for (;;) {
    const res = await API.list({ ...range, label: "relevant", sort: "score", limit: 500, offset: items.length });
    items.push(...(res.items || []));
    if (!res.items?.length || items.length >= res.total) break;
  }
  const all = await API.list({ ...range, limit: 1 });
  Object.assign(kb, { sig, items, corpus: all.total ?? 0, period });
}

function groupByCategory(items) {
  const groups = new Map();
  for (const r of items) {
    for (const c of categoriesOf(r)) {
      if (!groups.has(c)) groups.set(c, []);
      groups.get(c).push(r);
    }
  }
  return [...groups.entries()]
    .map(([name, rs]) => ({
      name,
      items: rs.sort((a, b) => (b.score ?? 0) - (a.score ?? 0)),
      avg: Math.round(rs.reduce((s, r) => s + (r.score ?? 0), 0) / rs.length),
    }))
    .sort((a, b) => b.items.length - a.items.length || b.avg - a.avg);
}

// ---------------------------------------------------------------- funnel
function funnel(st) {
  const pct = (a, b) => (b ? `${((a / b) * 100).toLocaleString(uiLang === "fr" ? "fr-CH" : "de-CH", { maximumFractionDigits: 1 })} %` : "");
  const steps = [
    { n: st.corpus, label: t("kb.f.corpus"), sub: t("kb.f.corpus.sub"), href: "#/all" },
    { n: st.relevant, label: t("kb.f.relevant"), sub: pct(st.relevant, st.corpus), href: "#/all?label=relevant" },
    { n: st.cats, label: t("kb.f.cats"), sub: t("kb.f.cats.sub", st.relevant) },
    { n: st.summaries, label: t("kb.f.sum"), sub: pct(st.summaries, st.relevant) },
  ];
  const max = Math.max(1, st.corpus);
  // Bar widths on a log scale: the corpus is ~100x the relevant set.
  const w = (n) => (n ? Math.max(6, (Math.log10(n + 1) / Math.log10(max + 1)) * 100) : 0);
  return `<ol class="funnel">${steps
    .map((s, i) => {
      const inner = `<span class="funnel__step">${i + 1}</span>
        <span class="funnel__n num">${(s.n ?? 0).toLocaleString("de-CH")}</span>
        <span class="funnel__label">${esc(s.label)}</span>
        <span class="funnel__sub">${esc(s.sub || "")}</span>
        <span class="funnel__bar"><i style="width:${i === 2 ? 100 : w(s.n)}%"></i></span>`;
      return `<li class="funnel__item">${s.href ? `<a href="${s.href}">${inner}</a>` : `<div>${inner}</div>`}</li>`;
    })
    .join("")}</ol>`;
}

// ---------------------------------------------------------------- topic map (SVG)
// Each topic is a circle sized by its number of rulings; each ruling is a dot inside it, placed on a
// sunflower spiral (strongest score in the middle). A ruling filed under several topics appears in
// each of them; hovering one draws the links to its other occurrences.
const DOT = 5.5, STEP = 7.6, PAD = 16, LABEL = 34;

const labelText = (name) => (name.length > 30 ? name.slice(0, 29) + "…" : name);

function packCircles(groups) {
  // Footprint = box around the circle and the two label lines under it.
  const placed = [];
  const overlaps = (a, b) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 + 14 && Math.abs(a.y - b.y) < (a.h + b.h) / 2 + 14;
  for (const g of groups) {
    const rc = STEP * Math.sqrt(g.items.length) + PAD;
    const w = Math.max(2 * rc, labelText(g.name).length * 7 + 8);
    const h = 2 * rc + LABEL;
    const box = { x: 0, y: 0, w, h };
    if (placed.length) {
      // Walk outwards on a slightly wide spiral (the canvas is landscape) until it fits.
      for (let a = 0, d = 0; ; a += 0.3, d += 1.2) {
        box.x = Math.cos(a) * d * 1.5;
        box.y = Math.sin(a) * d;
        if (!placed.some((p) => overlaps(p, box))) break;
      }
    }
    placed.push({ ...g, ...box, rc, r: Math.max(w, h) / 2 });
  }
  return placed;
}

function mapSvg(groups) {
  const circles = packCircles(groups);
  const minX = Math.min(...circles.map((c) => c.x - c.w / 2)) - 10, maxX = Math.max(...circles.map((c) => c.x + c.w / 2)) + 10;
  const minY = Math.min(...circles.map((c) => c.y - c.h / 2)) - 10, maxY = Math.max(...circles.map((c) => c.y + c.h / 2)) + 10;
  const golden = Math.PI * (3 - Math.sqrt(5));
  const dots = [];
  const parts = circles.map((c, ci) => {
    const cy = c.y - LABEL / 2; // circle centre, leaving room for the label below
    c.items.forEach((r, i) => {
      const d = STEP * Math.sqrt(i + 0.5) * 0.95;
      dots.push({ r, ci, x: c.x + Math.cos(i * golden) * d, y: cy + Math.sin(i * golden) * d });
    });
    const label = labelText(c.name);
    return `<g class="topic" data-cat="${esc(c.name)}">
      <circle class="topic__bg" cx="${c.x.toFixed(1)}" cy="${cy.toFixed(1)}" r="${c.rc.toFixed(1)}"/>
      <title>${esc(c.name)}</title>
      <text class="topic__label" x="${c.x.toFixed(1)}" y="${(cy + c.rc + 16).toFixed(1)}" text-anchor="middle">${esc(label)}</text>
      <text class="topic__count" x="${c.x.toFixed(1)}" y="${(cy + c.rc + 30).toFixed(1)}" text-anchor="middle">${t("kb.n", c.items.length)}</text>
    </g>`;
  });
  const dotSvg = dots
    .map((d, i) => `<circle class="dot dot--${band(d.r.score)}${d.r.has_summary ? "" : " dot--open"}" data-i="${i}" data-docket="${esc(d.r.docket)}" cx="${d.x.toFixed(1)}" cy="${d.y.toFixed(1)}" r="${DOT}"/>`)
    .join("");
  return {
    dots,
    // Never zoom in beyond 1.6x, so a map with few topics keeps readable dot and label sizes.
    html: `<svg class="kbmap__svg" style="max-width:${((maxX - minX) * 1.6).toFixed(0)}px" viewBox="${minX.toFixed(0)} ${minY.toFixed(0)} ${(maxX - minX).toFixed(0)} ${(maxY - minY).toFixed(0)}" role="img" aria-label="${esc(t("kb.map.aria"))}">
      ${parts.join("")}<g class="links"></g>${dotSvg}</svg>`,
  };
}

function tilesHtml(groups) {
  return `<div class="tiles">${groups
    .map((g) => `<a class="card tile" href="${catHref(g.name)}">
      <div class="tile__head"><h3>${esc(g.name)}</h3><span class="tile__n num">${g.items.length}</span></div>
      <div class="tile__bar" title="${esc(t("kb.avg", g.avg))}"><i class="score--${band(g.avg)}" style="width:${g.avg}%"></i></div>
      <ul class="tile__list">${g.items.slice(0, 3).map((r) => `<li><span class="docket">${esc(r.docket)}</span> <span class="muted">${esc(fmtDate(r.decision_date))}</span></li>`).join("")}</ul>
      ${g.items.length > 3 ? `<span class="tile__more">${esc(t("kb.more", g.items.length - 3))}</span>` : ""}
    </a>`)
    .join("")}</div>`;
}

// ---------------------------------------------------------------- overview page
let view = localStorage.getItem("kbView") || "map";

export async function renderHome(params, opts) {
  document.title = `${t("kb.title")} · BGer-Monitor`;
  state.lastListHash = location.hash || "#/";
  const period = params.get("period") || "all";
  const q = params.get("q") || "";
  const app = $("#app");
  app.innerHTML = `
    <div class="pagehead"><div><h1>${esc(t("kb.title"))}</h1><p>${esc(t("kb.sub"))}</p></div></div>
    <section id="funnel">${funnel({ corpus: 0, relevant: 0, cats: 0, summaries: 0 })}</section>
    <section class="card toolbar">
      <div class="toolbar__row">
        <label class="search"><span class="sr-only">${esc(t("kb.search"))}</span>${ICONS.search}
          <input type="search" id="q" value="${esc(q)}" placeholder="${esc(t("kb.search"))}" autocomplete="off"><kbd>/</kbd></label>
        <span class="field">${esc(t("f.period"))}
          <select id="period">${PERIODS.filter((p) => p.id !== "custom").map((p) => `<option value="${p.id}"${p.id === period ? " selected" : ""}>${esc(p.label())}</option>`).join("")}</select></span>
        <span class="tabs" role="tablist">
          <button type="button" role="tab" data-kbview="map" aria-selected="${view === "map"}">${esc(t("kb.view.map"))}</button>
          <button type="button" role="tab" data-kbview="tiles" aria-selected="${view === "tiles"}">${esc(t("kb.view.tiles"))}</button>
        </span>
      </div>
    </section>
    <section id="kbBody"><div class="card card__body" style="display:grid;gap:14px">${'<div class="skel"></div>'.repeat(6)}</div></section>`;

  try {
    await loadKb(period);
  } catch (e) {
    $("#kbBody").innerHTML = `<div class="card empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
    return;
  }

  const paint = () => {
    const needle = $("#q").value.trim().toLowerCase();
    const items = needle
      ? kb.items.filter((r) => `${r.docket} ${r.title || ""} ${categoriesOf(r).join(" ")}`.toLowerCase().includes(needle))
      : kb.items;
    const groups = groupByCategory(items);
    $("#funnel").innerHTML = funnel({
      corpus: kb.corpus,
      relevant: kb.items.length,
      cats: groupByCategory(kb.items).length,
      summaries: kb.items.filter((r) => r.has_summary).length,
    });
    const body = $("#kbBody");
    if (!groups.length) {
      body.innerHTML = `<div class="card empty"><h2>${esc(t("kb.empty"))}</h2><p>${esc(kb.items.length ? t("empty.filtered") : t("kb.empty.sub"))}</p></div>`;
      return;
    }
    if (view === "tiles") {
      body.innerHTML = tilesHtml(groups);
      return;
    }
    const { html, dots } = mapSvg(groups);
    body.innerHTML = `<div class="card kbmap">
      <div class="kbmap__canvas">${html}<div class="kbmap__tip" id="tip" hidden></div></div>
      <div class="kbmap__legend">
        <span><i class="dot-key dot--high"></i>${esc(t("kb.lg.high"))}</span>
        <span><i class="dot-key dot--mid"></i>${esc(t("kb.lg.mid"))}</span>
        <span><i class="dot-key dot--open"></i>${esc(t("kb.lg.open"))}</span>
        <span class="muted">${esc(t("kb.lg.hint"))}</span>
      </div>
    </div>`;
    bindMap(dots);
  };

  const replace = () => {
    const p = new URLSearchParams();
    if ($("#period").value !== "all") p.set("period", $("#period").value);
    if ($("#q").value.trim()) p.set("q", $("#q").value.trim());
    const h = "#/" + (p.toString() ? "?" + p : "");
    history.replaceState(null, "", h);
    state.lastListHash = h;
  };
  let timer;
  app.addEventListener("input", (e) => {
    if (e.target.id !== "q") return;
    clearTimeout(timer);
    timer = setTimeout(() => { replace(); paint(); }, 150);
  }, opts);
  app.addEventListener("change", async (e) => {
    if (e.target.id !== "period") return;
    replace();
    await loadKb(e.target.value);
    paint();
  }, opts);
  app.addEventListener("click", (e) => {
    const b = e.target.closest("[data-kbview]");
    if (!b) return;
    view = b.dataset.kbview;
    localStorage.setItem("kbView", view);
    $$("[data-kbview]").forEach((x) => x.setAttribute("aria-selected", x === b));
    paint();
  }, opts);
  paint();
}

function bindMap(dots) {
  const svg = $(".kbmap__svg");
  const tip = $("#tip");
  const links = $(".links", svg);
  const canvas = $(".kbmap__canvas");
  const clear = () => {
    tip.hidden = true;
    links.innerHTML = "";
    $$(".dot.is-hot", svg).forEach((d) => d.classList.remove("is-hot"));
    svg.classList.remove("is-focus");
  };
  svg.addEventListener("mouseover", (e) => {
    const el = e.target.closest(".dot");
    if (!el) return;
    const d = dots[+el.dataset.i];
    const same = dots.filter((x) => x.r.docket === d.r.docket);
    svg.classList.add("is-focus");
    $$(`.dot[data-docket="${CSS.escape(d.r.docket)}"]`, svg).forEach((x) => x.classList.add("is-hot"));
    links.innerHTML = same.filter((x) => x !== d)
      .map((x) => `<line x1="${d.x.toFixed(1)}" y1="${d.y.toFixed(1)}" x2="${x.x.toFixed(1)}" y2="${x.y.toFixed(1)}"/>`).join("");
    const cats = categoriesOf(d.r);
    tip.innerHTML = `<div class="tip__head">${scoreBadge(d.r.score)}<div><strong>${esc(d.r.docket)}</strong>
        <div class="muted">${esc(fmtDate(d.r.decision_date))}${d.r.language ? ` · ${esc(d.r.language.toUpperCase())}` : ""}</div></div></div>
      <div class="tip__title">${esc(d.r.title || "")}</div>
      ${cats.length > 1 ? `<div class="tip__cats">${cats.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div>` : ""}
      <div class="tip__foot">${esc(d.r.has_summary ? t("kb.tip.sum") : t("kb.tip.nosum"))}</div>`;
    tip.hidden = false;
    const box = canvas.getBoundingClientRect(), r = el.getBoundingClientRect();
    const left = r.left - box.left + r.width / 2, top = r.top - box.top;
    tip.style.left = `${Math.min(Math.max(left, 150), box.width - 150)}px`;
    tip.style.top = `${top}px`;
    tip.classList.toggle("is-below", top < 170);
  });
  svg.addEventListener("mouseout", (e) => { if (e.target.closest(".dot")) clear(); });
  svg.addEventListener("click", (e) => {
    const dot = e.target.closest(".dot");
    if (dot) { location.hash = `#/r/${encodeURIComponent(dot.dataset.docket)}`; return; }
    const g = e.target.closest(".topic");
    if (g) location.hash = catHref(g.dataset.cat);
  });
}

// ---------------------------------------------------------------- topic page
function excerpt(text, max = 420) {
  const s = String(text || "").replace(/\s+/g, " ").trim();
  if (s.length <= max) return s;
  const cut = s.slice(0, max);
  return cut.slice(0, cut.lastIndexOf(" ")) + " …";
}

export async function renderCategory(name, params) {
  document.title = `${name} · BGer-Monitor`;
  state.lastListHash = location.hash;
  const app = $("#app");
  app.innerHTML = `<nav class="crumbs"><a href="#/">${ICONS.back} ${esc(t("kb.title"))}</a></nav>
    <div class="card card__body" style="display:grid;gap:14px">${'<div class="skel"></div>'.repeat(6)}</div>`;
  try {
    await loadKb(params.get("period") || kb.period);
  } catch (e) {
    app.innerHTML += `<div class="card empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
    return;
  }
  const items = kb.items.filter((r) => categoriesOf(r).includes(name));
  if (!items.length) {
    location.replace("#/");
    return;
  }
  const sort = params.get("sort") === "date" ? "date" : "score";
  items.sort(sort === "date"
    ? (a, b) => (b.decision_date || "").localeCompare(a.decision_date || "")
    : (a, b) => (b.score ?? 0) - (a.score ?? 0));
  const related = new Map();
  for (const r of items) for (const c of categoriesOf(r)) if (c !== name) related.set(c, (related.get(c) || 0) + 1);
  const areas = [...new Set(items.map(areaOf).filter(Boolean))];

  app.innerHTML = `
    <nav class="crumbs"><a href="#/">${ICONS.back} ${esc(t("kb.title"))}</a></nav>
    <header class="dhead">
      <div>
        <div class="dhead__kicker">${areas.map((a) => `<span class="chip">${esc(a)}</span>`).join("")}</div>
        <h1>${esc(name)}</h1>
        <p class="dhead__title">${esc(t("kb.cat.sub", items.length))}</p>
      </div>
      <div class="dhead__actions">
        <span class="tabs" role="tablist">
          <a role="tab" href="${catHref(name)}" aria-selected="${sort === "score"}">${esc(t("kb.sort.score"))}</a>
          <a role="tab" href="${catHref(name)}?sort=date" aria-selected="${sort === "date"}">${esc(t("kb.sort.date"))}</a>
        </span>
      </div>
    </header>
    ${related.size ? `<div class="related"><span class="muted">${esc(t("kb.related"))}</span>${[...related.entries()].sort((a, b) => b[1] - a[1])
      .map(([c, n]) => `<a class="chip" href="${catHref(c)}">${esc(c)} <span class="muted">${n}</span></a>`).join("")}</div>` : ""}
    ${items.length ? `<div class="entries">${items.map((r) => `
      <article class="card entry" data-docket="${esc(r.docket)}">
        <div class="entry__score">${scoreBadge(r.score)}</div>
        <div class="entry__main">
          <div class="entry__head">
            <a class="docket" href="#/r/${encodeURIComponent(r.docket)}">${esc(r.docket)}</a>
            <span class="muted">${esc(fmtDate(r.decision_date, "long"))}</span>
            ${r.language ? `<span class="lang">${esc(r.language)}</span>` : ""}
          </div>
          <div class="ruling-title">${esc(r.title || "")}</div>
          <div class="entry__summary" data-sum>${r.has_summary ? '<div class="skel"></div><div class="skel" style="width:70%"></div>' : `<span class="muted">${esc(t("kb.nosum"))}</span>`}</div>
        </div>
        <a class="btn btn--sm entry__open" href="#/r/${encodeURIComponent(r.docket)}">${esc(t("kb.open"))}</a>
      </article>`).join("")}</div>`
      : `<div class="card empty"><h2>${esc(t("kb.empty"))}</h2></div>`}`;

  // Summary excerpts in the interface language, fetched for the rulings that have one.
  await Promise.all(items.filter((r) => r.has_summary).map(async (r) => {
    const slot = $(`.entry[data-docket="${CSS.escape(r.docket)}"] [data-sum]`);
    try {
      const d = await API.detail(r.docket);
      const s = d.summaries?.[uiLang] || d.summaries?.de || d.summaries?.fr;
      if (slot) slot.innerHTML = s ? `<p>${highlight(excerpt(s.text))}</p>` : `<span class="muted">${esc(t("kb.nosum"))}</span>`;
    } catch {
      if (slot) slot.innerHTML = "";
    }
  }));
}
