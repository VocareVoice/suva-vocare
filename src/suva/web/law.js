// Law view: UVG, ATSG and UVV as in force (snapshots from Fedlex, GET /api/law/{code}), every
// article in order under its Title / Chapter / Section headings, with a table of contents and an
// article filter on the left. `#/law/atsg?art=4` opens the ATSG scrolled to Art. 4; `#/law` is the UVG.

import { $, ICONS, esc, fmtDate, t, uiLang } from "./app.js";

const cache = {}; // by "code/lang"
const get = async (path) => {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};
function load(code, lang) {
  cache[`${code}/${lang}`] ||= get(`/api/law/${encodeURIComponent(code)}?lang=${lang}`).catch((e) => { delete cache[`${code}/${lang}`]; throw e; });
  return cache[`${code}/${lang}`];
}
function loadList(lang) {
  cache[`list/${lang}`] ||= get(`/api/laws?lang=${lang}`).catch((e) => { delete cache[`list/${lang}`]; throw e; });
  return cache[`list/${lang}`];
}

const REPEALED = /^(?:Aufgehoben|Abrogé)[^.]*\.?$/;
const artId = (a) => `art-${a.key || a.id}`;

// "1 Text" is a paragraph (Absatz / alinéa), "a. Text" or "1. Text" a list item.
function articleText(text) {
  return String(text || "").split("\n").filter(Boolean).map((line) => {
    let m = /^(\d+[a-z]?(?:bis|ter|quater)?)\s+(\S[\s\S]*)$/.exec(line);
    if (m && !/^\d+\.$/.test(m[1])) return `<p><span class="n">${esc(m[1])}</span>${esc(m[2])}</p>`;
    m = /^([a-z]{1,3}(?:bis|ter|quater|quinquies|sexies)?\.|\d+\.)\s+([\s\S]*)$/.exec(line);
    if (m) return `<p class="lit"><span class="n">${esc(m[1])}</span>${esc(m[2])}</p>`;
    return `<p>${esc(line)}</p>`;
  }).join("");
}

function articleHtml(a, law) {
  const repealed = REPEALED.test(a.text.trim());
  return `<article class="lawart${repealed ? " is-repealed" : ""}" id="${esc(artId(a))}">
    <h3 class="lawart__head" style="margin:0 0 6px">
      <span class="lawart__num">Art. ${esc(a.number)} ${esc(law)}</span>
      ${a.title ? `<span class="lawart__title">${esc(a.title)}</span>` : ""}
      <a class="lawart__ext" href="${esc(a.url)}" target="_blank" rel="noopener" title="Fedlex">Fedlex ↗</a>
    </h3>
    <div class="lawart__text">${articleText(a.text)}</div>
  </article>`;
}

// Articles with the Title/Chapter/Section headings that open whenever the path changes.
function bodyHtml(data, articles) {
  let last = [];
  const out = [];
  articles.forEach((a) => {
    a.path.forEach((h, depth) => {
      if (last[depth] === h && last.slice(0, depth).every((x, i) => x === a.path[i])) return;
      const tag = ["h2", "h3", "h4"][Math.min(depth, 2)];
      out.push(`<${tag} id="sec-${esc(a.key)}-${depth}">${esc(h)}</${tag}>`);
    });
    last = a.path;
    out.push(articleHtml(a, data.law));
  });
  return out.join("") || `<p class="lawempty">${esc(t("law.none"))}</p>`;
}

// Table of contents: Titles and Chapters, each pointing at its first article.
function tocHtml(code, articles) {
  const seen = new Set();
  const items = [];
  for (const a of articles) {
    a.path.slice(0, 2).forEach((h, depth) => {
      const k = a.path.slice(0, depth + 1).join(" / ");
      if (seen.has(k)) return;
      seen.add(k);
      items.push(`<li class="lvl-${depth}"><a href="#/law/${esc(code)}?art=${encodeURIComponent(a.key)}" data-sec="sec-${esc(a.key)}-${depth}">${esc(h)}</a></li>`);
    });
  }
  return `<ol>${items.join("")}</ol>`;
}

function matches(a, q) {
  if (!q) return true;
  const num = q.replace(/^(?:art\.?|artikel|article)\s*/i, "").replace(/\s+/g, "").toLowerCase();
  if (/^\d+[a-z]*$/.test(num)) return a.key === num || a.number.replace(/\s+/g, "").toLowerCase() === num;
  const hay = `${a.title} ${a.text}`.toLowerCase();
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
}

function flash(el) {
  el.scrollIntoView({ block: "start" });
  el.classList.remove("is-flash"); void el.offsetWidth; el.classList.add("is-flash");
}

// Switch between the laws, by their abbreviation in the UI language.
const switcher = (list, code) => `<span class="seg" role="group" aria-label="${esc(t("nav.law"))}">${list
  .map((l) => `<a href="#/law/${esc(l.code)}" title="${esc(l.title)}" aria-pressed="${l.code === code}">${esc(l.law)}</a>`).join("")}</span>`;

export async function renderLaw(code, params, opts) {
  const app = $("#app");
  document.title = `${t("nav.law")} – BGer-Monitor`;
  app.innerHTML = `<header class="lawhead"><div class="skel" style="width:40%;height:28px"></div></header>
    <div class="card card__body" style="display:grid;gap:14px">${'<div class="skel"></div>'.repeat(8)}</div>`;
  let data, list;
  try {
    [data, list] = await Promise.all([load(code, uiLang), loadList(uiLang)]);
  } catch (e) {
    app.innerHTML = `<div class="empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
    return;
  }
  document.title = `${data.law} – BGer-Monitor`;
  app.innerHTML = `
    <header class="lawhead">
      ${switcher(list, data.code)}
      <h1>${esc(data.title)}</h1>
      <p><span>${esc(data.law)} · SR ${esc(data.sr)}</span><span>${esc(t("law.inforce", fmtDate(data.in_force, "long")))}</span>
        <a href="${esc(data.url)}" target="_blank" rel="noopener">${ICONS.ext.replace("<svg", '<svg width="14" height="14" style="vertical-align:-2px;margin-right:4px"')}fedlex.admin.ch</a></p>
    </header>
    <div class="lawgrid">
      <aside class="lawtoc">
        <label class="search">
          <span class="sr-only">${esc(t("law.filter"))}</span>
          ${ICONS.search}
          <input type="search" id="lawQ" placeholder="${esc(t("law.filter"))}" autocomplete="off">
        </label>
        <nav id="lawToc">${tocHtml(data.code, data.articles)}</nav>
      </aside>
      <div class="lawbody" id="lawBody">${bodyHtml(data, data.articles)}</div>
    </div>`;

  const input = $("#lawQ");
  input.addEventListener("input", () => {
    const q = input.value.trim();
    const hits = data.articles.filter((a) => matches(a, q));
    $("#lawBody").innerHTML = bodyHtml(data, hits);
    $("#lawToc").innerHTML = tocHtml(data.code, hits);
  }, opts);
  // TOC links scroll inside the page without leaving a history entry per click.
  $("#lawToc").addEventListener("click", (e) => {
    const a = e.target.closest("[data-sec]");
    if (!a) return;
    e.preventDefault();
    const el = document.getElementById(a.dataset.sec);
    if (el) el.scrollIntoView({ block: "start" });
  }, opts);

  const art = params.get("art");
  if (art) {
    const key = art.toLowerCase().replace(/\s+/g, "");
    const target = data.articles.find((a) => a.key === key) || data.articles.find((a) => a.key.startsWith(key.replace(/[a-z]+$/, "")));
    const el = target && document.getElementById(artId(target));
    if (el) requestAnimationFrame(() => flash(el));
  }
}
