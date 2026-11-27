// BGer-Monitor UI — vanilla ES module, no build step, no external dependencies.
// Talks to the FastAPI JSON API in src/suva/api.py. The root view (relevant rulings by category)
// lives in relevant.js, the branch/category taxonomy in categories.js, the agent panel in agent.js.

import { initAgent, paintAgent } from "./agent.js";
import { ensureTaxonomy, getTaxonomy, taxLabel } from "./categories.js";
import { renderRelevant } from "./relevant.js";

// ---------------------------------------------------------------- i18n
const I18N = {
  de: {
    "nav.rel": "Wissensbasis",
    "nav.all": "Alle Urteile",
    "rel.title": "Wissensbasis",
    "rel.register": "Register",
    "rel.all": "Alle Rechtsfragen",
    "rel.sum.yes": "Zusammenfassung DE und FR vorhanden",
    "rel.sum.no": "Noch keine Zusammenfassung",
    "rel.sum.open": "Offen",
    "agent.tab": "Agent",
    "agent.title": "Agent",
    "agent.close": "Agent schliessen",
    "agent.intro": "Hier können Sie bald mit einem Agenten über die Rechtsprechung sprechen, z. B. «Welche Urteile 2026 betreffen die adäquate Kausalität bei Schleudertrauma?».",
    "agent.ph": "Frage an den Agenten …",
    "agent.send": "Senden",
    "agent.soon": "Der Agent ist noch nicht angebunden. Ihre Frage wurde nicht übermittelt.",
    "agent.context": (d) => `Kontext: ${d}`,
    "kb.empty": "Keine Urteile in der Wissensbasis",
    "kb.empty.sub": "Sobald die Triage Urteile als relevant bewertet, erscheinen sie hier.",
    "brand.sub": "Rechtsprechung Unfallversicherung",
    "nav.rulings": "Urteile",
    "list.title": "Bundesgerichtsurteile",
    "list.sub": "Alle publizierten Urteile mit Relevanzbewertung für die Suva",
    "search.ph": "Volltextsuche in Urteilen – z. B. «Kausalzusammenhang», «Art. 6 UVG», 8C_129/2025",
    "f.period": "Zeitraum",
    "f.period.all": "Alle",
    "f.custom": "Benutzerdefiniert",
    "f.label": "Triage",
    "f.label.all": "Alle",
    "f.label.rel": "Relevant",
    "f.label.not": "Nicht relevant",
    "f.minscore": "Score ab",
    "f.division": "Abteilung",
    "f.division.all": "Alle",
    "f.lang": "Sprache",
    "f.lang.all": "Alle",
    "f.summary": "Zusammenfassung",
    "f.summary.all": "Alle",
    "f.summary.yes": "Vorhanden",
    "f.summary.no": "Fehlt",
    "f.reset": "Filter zurücksetzen",
    "results": (n, t) => (n === t ? `${n.toLocaleString("de-CH")} Urteile` : `${n.toLocaleString("de-CH")} von ${t.toLocaleString("de-CH")} Urteilen`),
    "more": "Weitere anzeigen",
    "loading": "Lädt …",
    "col.score": "Score",
    "col.docket": "Urteil",
    "col.date": "Datum",
    "col.subject": "Gegenstand und Begründung",
    "col.lang": "Spr.",
    "col.summary": "Zusammenf.",
    "sum.yes": "DE FR",
    "sum.no": "—",
    "untriaged": "nicht bewertet",
    "empty.title": "Keine Urteile gefunden",
    "empty.filtered": "Passen Sie Suche oder Filter an.",
    "empty.db": "Die Datenbank ist leer. Laden Sie Urteile mit",
    "err.load": "Daten konnten nicht geladen werden",
    "back": "Zurück zur Übersicht",
    "d.original": "Original auf bger.ch",
    "d.copy": "Kopieren",
    "d.copyAll": "DE + FR kopieren",
    "d.export": "Export (Suva-Format)",
    "d.print": "Drucken",
    "d.summary": "Zusammenfassung",
    "d.both": "DE | FR",
    "d.text.de": "Text DE",
    "d.text.fr": "Text FR",
    "d.ai": "KI-generiert",
    "d.ai.hint": "Vor Verwendung juristisch prüfen",
    "d.words": (n) => `${n} Wörter`,
    "d.missing.lang": "Für diese Sprache liegt noch keine Zusammenfassung vor.",
    "d.regen": "Neu generieren",
    "gen.title": "Noch keine Zusammenfassung",
    "gen.text": "Erstellen Sie eine deutsche und eine französische Zusammenfassung im Suva-Stil. Beide Fassungen werden eigenständig verfasst, nicht übersetzt.",
    "gen.btn": "Zusammenfassen",
    "gen.running": "Zusammenfassung wird erstellt …",
    "gen.s1": "Urteilstext analysieren",
    "gen.s2": "Kernaussagen und Normen extrahieren",
    "gen.s3": "Deutsche Fassung verfassen",
    "gen.s4": "Französische Fassung verfassen",
    "gen.elapsed": (s) => `Laufzeit ${s} s, dauert in der Regel 30–90 s`,
    "gen.err": "Die Zusammenfassung konnte nicht erstellt werden",
    "gen.notimpl": "Der Zusammenfassungs-Dienst ist noch nicht verfügbar.",
    "gen.done": "Zusammenfassung erstellt",
    "o.title": "Urteilstext",
    "o.more": "Ganzen Urteilstext anzeigen",
    "o.less": "Urteilstext einklappen",
    "o.empty": "Kein Volltext gespeichert. Öffnen Sie das Original auf bger.ch.",
    "o.hits": (n) => `${n} Treffer`,
    "r.title": "Relevanz",
    "r.rel": "Relevant",
    "r.not": "Nicht relevant",
    "r.hint": "Score 0–100 für die Bedeutung für die Unfallversicherung",
    "r.none": "Dieses Urteil wurde noch nicht bewertet.",
    "r.reason": "Begründung",
    "st.title": "Zitierte Normen",
    "st.none": "Keine Normen erkannt.",
    "m.title": "Angaben",
    "m.docket": "Urteil",
    "m.decision": "Entscheid",
    "m.published": "Publiziert",
    "m.division": "Abteilung",
    "m.language": "Sprache",
    "m.source": "Quelle",
    "copied": "In die Zwischenablage kopiert",
    "lang.de": "Deutsch",
    "lang.fr": "Französisch",
    "lang.it": "Italienisch",
    "notfound": "Urteil nicht gefunden",
    "f.branch": "Versicherungszweig",
    "f.branch.all": "Alle",
    "f.category": "Kategorie",
    "f.category.all": "Alle",
    "c.title": "Rechtsgebiet",
    "c.secondary": "Weitere Fragen",
    "c.outcome": "Ausgang",
  },
  fr: {
    "nav.rel": "Base de connaissances",
    "nav.all": "Tous les arrêts",
    "rel.title": "Base de connaissances",
    "rel.register": "Registre",
    "rel.all": "Toutes les questions",
    "rel.sum.yes": "Résumé DE et FR disponible",
    "rel.sum.no": "Pas encore de résumé",
    "rel.sum.open": "Ouvert",
    "agent.tab": "Agent",
    "agent.title": "Agent",
    "agent.close": "Fermer l'agent",
    "agent.intro": "Vous pourrez bientôt discuter ici de la jurisprudence avec un agent, p. ex. « Quels arrêts de 2026 portent sur la causalité adéquate en cas de coup du lapin ? ».",
    "agent.ph": "Question à l'agent …",
    "agent.send": "Envoyer",
    "agent.soon": "L'agent n'est pas encore connecté. Votre question n'a pas été transmise.",
    "agent.context": (d) => `Contexte : ${d}`,
    "kb.empty": "Aucun arrêt dans la base de connaissances",
    "kb.empty.sub": "Les arrêts apparaissent ici dès que le triage les juge pertinents.",
    "brand.sub": "Jurisprudence assurance-accidents",
    "nav.rulings": "Arrêts",
    "list.title": "Arrêts du Tribunal fédéral",
    "list.sub": "Tous les arrêts publiés avec leur évaluation de pertinence pour la Suva",
    "search.ph": "Recherche plein texte – p. ex. « causalité adéquate », « art. 6 LAA », 8C_129/2025",
    "f.period": "Période",
    "f.period.all": "Toutes",
    "f.custom": "Personnalisée",
    "f.label": "Triage",
    "f.label.all": "Tous",
    "f.label.rel": "Pertinents",
    "f.label.not": "Non pertinents",
    "f.minscore": "Score dès",
    "f.division": "Cour",
    "f.division.all": "Toutes",
    "f.lang": "Langue",
    "f.lang.all": "Toutes",
    "f.summary": "Résumé",
    "f.summary.all": "Tous",
    "f.summary.yes": "Disponible",
    "f.summary.no": "Manquant",
    "f.reset": "Réinitialiser",
    "results": (n, t) => (n === t ? `${n.toLocaleString("fr-CH")} arrêts` : `${n.toLocaleString("fr-CH")} sur ${t.toLocaleString("fr-CH")} arrêts`),
    "more": "Afficher plus",
    "loading": "Chargement …",
    "col.score": "Score",
    "col.docket": "Arrêt",
    "col.date": "Date",
    "col.subject": "Objet et motivation",
    "col.lang": "Lang.",
    "col.summary": "Résumé",
    "sum.yes": "DE FR",
    "sum.no": "—",
    "untriaged": "non évalué",
    "empty.title": "Aucun arrêt trouvé",
    "empty.filtered": "Modifiez la recherche ou les filtres.",
    "empty.db": "La base de données est vide. Chargez des arrêts avec",
    "err.load": "Impossible de charger les données",
    "back": "Retour à la vue d'ensemble",
    "d.original": "Original sur bger.ch",
    "d.copy": "Copier",
    "d.copyAll": "Copier DE + FR",
    "d.export": "Export (format Suva)",
    "d.print": "Imprimer",
    "d.summary": "Résumé",
    "d.both": "DE | FR",
    "d.text.de": "Texte DE",
    "d.text.fr": "Texte FR",
    "d.ai": "Généré par IA",
    "d.ai.hint": "À vérifier juridiquement avant utilisation",
    "d.words": (n) => `${n} mots`,
    "d.missing.lang": "Aucun résumé n'est encore disponible dans cette langue.",
    "d.regen": "Régénérer",
    "gen.title": "Pas encore de résumé",
    "gen.text": "Générez un résumé en allemand et en français dans le style de la Suva. Les deux versions sont rédigées séparément, et non traduites.",
    "gen.btn": "Résumer",
    "gen.running": "Résumé en cours de rédaction …",
    "gen.s1": "Analyser le texte de l'arrêt",
    "gen.s2": "Extraire les considérants et les normes",
    "gen.s3": "Rédiger la version allemande",
    "gen.s4": "Rédiger la version française",
    "gen.elapsed": (s) => `Durée ${s} s, prend en général 30–90 s`,
    "gen.err": "Le résumé n'a pas pu être généré",
    "gen.notimpl": "Le service de résumé n'est pas encore disponible.",
    "gen.done": "Résumé généré",
    "o.title": "Texte de l'arrêt",
    "o.more": "Afficher l'arrêt complet",
    "o.less": "Réduire le texte",
    "o.empty": "Aucun texte intégral enregistré. Ouvrez l'original sur bger.ch.",
    "o.hits": (n) => `${n} occurrences`,
    "r.title": "Pertinence",
    "r.rel": "Pertinent",
    "r.not": "Non pertinent",
    "r.hint": "Score 0–100 pour l'importance en assurance-accidents",
    "r.none": "Cet arrêt n'a pas encore été évalué.",
    "r.reason": "Motivation",
    "st.title": "Normes citées",
    "st.none": "Aucune norme détectée.",
    "m.title": "Informations",
    "m.docket": "Arrêt",
    "m.decision": "Décision",
    "m.published": "Publication",
    "m.division": "Cour",
    "m.language": "Langue",
    "m.source": "Source",
    "copied": "Copié dans le presse-papiers",
    "lang.de": "Allemand",
    "lang.fr": "Français",
    "lang.it": "Italien",
    "notfound": "Arrêt introuvable",
    "f.branch": "Branche d'assurance",
    "f.branch.all": "Toutes",
    "f.category": "Catégorie",
    "f.category.all": "Toutes",
    "c.title": "Domaine juridique",
    "c.secondary": "Autres questions",
    "c.outcome": "Issue",
  },
};

export let uiLang = localStorage.getItem("uiLang") === "fr" ? "fr" : "de";
export function t(key, ...args) {
  const v = I18N[uiLang][key] ?? I18N.de[key] ?? key;
  return typeof v === "function" ? v(...args) : v;
}

// ---------------------------------------------------------------- helpers
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
function parseDate(iso) {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}
export function fmtDate(iso, style = "short") {
  const d = parseDate(iso);
  if (!d) return "—";
  const loc = uiLang === "fr" ? "fr-CH" : "de-CH";
  return style === "long"
    ? d.toLocaleDateString(loc, { day: "numeric", month: "long", year: "numeric" })
    : d.toLocaleDateString(loc, { day: "2-digit", month: "2-digit", year: "numeric" });
}
// Suva's title convention follows the language of the ruling:
//   de "BGer-Urteil 8C_313/2024 vom 13. November 2025"
//   fr "Arrêt du TF 8C_129/2025 du 11 novembre 2025"
//   it "Sentenza del TF 8C_135/2025 del 21 agosto 2025"
const MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
const MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
function suvaTitle(r) {
  const d = parseDate(r.decision_date);
  if (r.language === "fr") return `Arrêt du TF ${r.docket}` + (d ? ` du ${d.getDate() === 1 ? "1er" : d.getDate()} ${MONTHS_FR[d.getMonth()]} ${d.getFullYear()}` : "");
  if (r.language === "it") return `Sentenza del TF ${r.docket}` + (d ? ` del ${d.getDate() === 1 ? "1°" : d.getDate()} ${MONTHS_IT[d.getMonth()]} ${d.getFullYear()}` : "");
  return `BGer-Urteil ${r.docket}` + (d ? ` vom ${d.getDate()}. ${MONTHS_DE[d.getMonth()]} ${d.getFullYear()}` : "");
}

// Court division from the docket prefix (8C_129/2025 -> "8C"); the digit names the Abteilung,
// the letter the procedure (C/A/B = ordinary appeal, D = subsidiary constitutional appeal, F = revision).
const ABTEILUNG = {
  1: "I. öffentlich-rechtliche Abteilung", 2: "II. öffentlich-rechtliche Abteilung",
  9: "III. öffentlich-rechtliche Abteilung", 8: "IV. öffentlich-rechtliche Abteilung",
  4: "I. zivilrechtliche Abteilung", 5: "II. zivilrechtliche Abteilung",
  6: "I. strafrechtliche Abteilung", 7: "II. strafrechtliche Abteilung",
};
const COMMON_DIVISIONS = ["8C", "9C", "1C", "2C", "4A", "5A", "6B", "7B"];
function divisionName(code) { return ABTEILUNG[(code || "")[0]] || ""; }
function rulingDivision(r) {
  const code = divisionCode(r.docket);
  return r.division && r.division.length > 3 ? r.division : divisionName(code) || r.division || code;
}
const divisionCode = (docket) => (/^(\d[A-Z])_/.exec(docket || "") || [])[1] || "";

// Triage reasoning in the interface language (reasoning_de / reasoning_fr), else the single field.
export const reasoningOf = (o) => (o && (o[`reasoning_${uiLang}`] || o.reasoning || o.reason)) || "";

export function band(score) {
  if (score == null) return "none";
  return score >= 70 ? "high" : score >= 40 ? "mid" : "low";
}
export function scoreBadge(score) {
  const b = band(score);
  return `<span class="score score--${b}" title="${score == null ? esc(t("untriaged")) : `Score ${score}/100`}">
    <span class="score__num">${score == null ? "–" : score}</span>
    <span class="score__bar"><i style="width:${score ?? 0}%"></i></span>
  </span>`;
}
function scoreRing(score) {
  const b = band(score);
  return `<div class="score-ring score--${b}" style="--p:${score ?? 0}">
    <svg viewBox="0 0 36 36" aria-hidden="true"><circle class="track" cx="18" cy="18" r="15.9155" pathLength="100"/><circle class="val" cx="18" cy="18" r="15.9155" pathLength="100"/></svg>
    <div class="score-ring__num"><span>${score ?? "–"}<small>/ 100</small></span></div>
  </div>`;
}

export const ICONS = {
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/></svg>',
  print: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 9V4h10v5M7 17H5a1 1 0 0 1-1-1v-5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5a1 1 0 0 1-1 1h-2"/><rect x="7" y="14" width="10" height="6" rx="1"/></svg>',
  up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v10H4V10zM7 10l4-7a2 2 0 0 1 3 2l-1 5h6a2 2 0 0 1 2 2.3l-1.3 6A2 2 0 0 1 17.7 20H7"/></svg>',
  downv: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V4h3v10zM17 14l-4 7a2 2 0 0 1-3-2l1-5H5a2 2 0 0 1-2-2.3l1.3-6A2 2 0 0 1 6.3 4H17"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  back: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>',
};

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("is-on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-on"), 2400);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback for non-secure contexts (http on an intranet host).
    const ta = Object.assign(document.createElement("textarea"), { value: text });
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  toast(t("copied"));
}

function download(filename, content, type = "text/html") {
  const url = URL.createObjectURL(new Blob([content], { type: `${type};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------- API
class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; }
}
async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { Accept: "application/json", ...(opts.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail; } catch { /* not json */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}
// Dockets contain a slash (8C_129/2025); the API accepts it as a path segment.
const docketPath = (docket) => docket.split("/").map(encodeURIComponent).join("/");
export const API = {
  list: (params) => api(`/api/rulings?${new URLSearchParams(params)}`),
  detail: (docket) => api(`/api/rulings/${docketPath(docket)}`),
  summarize: (docket) => api(`/api/rulings/${docketPath(docket)}/summarize`, { method: "POST" }),
};

// ---------------------------------------------------------------- classification
// Closed label lists (branch, category, outcome, flag) with DE/FR labels, from /api/facets.
function classChips(c, size = "chip--sm") {
  if (!c) return "";
  return `<span class="chip ${size}" title="${esc(taxLabel("branches", c.branch))}">${esc(taxLabel("branches", c.branch, true))}</span>` +
    `<span class="chip ${size} chip--accent" title="${esc(taxLabel("categories", c.primary))}">${esc(taxLabel("categories", c.primary, true))}</span>`;
}

// ---------------------------------------------------------------- statutes
// Recognise citations such as "Art. 73 lit. b UVV", "art. 6 al. 1 LAA", "Art. 16 ATSG".
const LAWS = ["UVG", "LAA", "UVV", "OLAA", "ATSG", "LPGA", "ATSV", "OPGA", "IVG", "LAI", "IVV", "RAI", "AHVG", "LAVS",
  "BVG", "LPP", "KVG", "LAMal", "MVG", "LAM", "VVG", "LCA", "OR", "CO", "ZGB", "CC", "BV", "Cst\\.", "BGG", "LTF", "VwVG", "PA", "EMRK", "CEDH", "SVG", "LCR"];
const LAW_PAIRS = { LAA: "UVG", OLAA: "UVV", LPGA: "ATSG", OPGA: "ATSV", LAI: "IVG", RAI: "IVV", LAVS: "AHVG", LPP: "BVG",
  LAMal: "KVG", LAM: "MVG", LCA: "VVG", CO: "OR", CC: "ZGB", "Cst.": "BV", LTF: "BGG", PA: "VwVG", CEDH: "EMRK", LCR: "SVG" };
const CITE_RE = new RegExp(
  String.raw`\b[Aa]rt(?:\.|ikel)\s*(\d+[a-z]?(?:\s*(?:bis|ter|quater))?)` +
  String.raw`((?:\s*(?:Abs\.|al\.|para\.)\s*\d+[a-z]?)?(?:\s*(?:lit\.|let\.|Bst\.|Ziff\.|ch\.)\s*[a-z0-9]+)?)` +
  String.raw`\s+(?:des\s+|de\s+la\s+|du\s+|de\s+l')?(${LAWS.join("|")})(?![\wÀ-ÿ])`,
  "g",
);
function extractStatutes(...texts) {
  const found = new Map();
  for (const text of texts) {
    if (!text) continue;
    for (const m of text.matchAll(CITE_RE)) {
      const law = m[3];
      const canon = LAW_PAIRS[law] || law;
      const key = `${canon} ${m[1].replace(/\s+/g, "")}`;
      const e = found.get(key) || { law: canon, art: m[1].replace(/\s+/g, " "), forms: new Set(), count: 0 };
      e.forms.add(m[0]); e.count++;
      found.set(key, e);
    }
  }
  const order = ["UVG", "UVV", "ATSG", "ATSV", "IVG", "IVV"];
  return [...found.values()].sort((a, b) => {
    const la = order.indexOf(a.law), lb = order.indexOf(b.law);
    if (a.law !== b.law) return (la < 0 ? 99 : la) - (lb < 0 ? 99 : lb) || a.law.localeCompare(b.law);
    return parseInt(a.art) - parseInt(b.art);
  });
}

// Escape text, then mark statute citations and search terms.
export function highlight(text, terms = []) {
  let html = esc(text);
  html = html.replace(new RegExp(CITE_RE.source.replace("des\\s+|de\\s+la\\s+|du\\s+|de\\s+l')", "des\\s+|de\\s+la\\s+|du\\s+|de\\s+l&#39;)"), "g"),
    (m, art, _sub, law) => `<span class="cite" data-cite="${esc((LAW_PAIRS[law] || law) + " " + art.replace(/\s+/g, ""))}">${m}</span>`);
  const words = terms.filter((w) => w.length > 1);
  if (words.length) {
    // Only replace outside of tags.
    const re = new RegExp(`(${words.map((w) => escRe(esc(w))).join("|")})`, "gi");
    html = html.replace(/(<[^>]+>)|([^<]+)/g, (all, tag, txt) => tag || txt.replace(re, "<mark>$1</mark>"));
  }
  return html;
}

const HEADING_RE = /(Sachverhalt|Erwägung|Faits|Considérant|Fatti|Diritto|Ritenuto|erkennt|Par ces motifs|Per questi motivi|prononce|pronuncia)/i;
const LABEL_RE = /^(?:\d{1,2}|[A-Z])(?:\.(?:\d{1,2}|[a-z]))*\.$/; // "A.", "A.a.", "3.", "3.2."
const LEAD_RE = /^((?:\d{1,2}|[A-Z])(?:\.(?:\d{1,2}|[a-z]))*\.)\s+(\D[\s\S]*)$/;

function paragraphs(text, terms) {
  const blocks = String(text || "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const out = [];
  let label = "";
  for (const p of blocks) {
    if (LABEL_RE.test(p)) { label += (label ? " " : "") + p; continue; }
    const tag = label ? `<span class="erw">${esc(label)}</span>` : "";
    label = "";
    if (p.length < 90 && /:\s*$/.test(p) && HEADING_RE.test(p)) { out.push(`<p class="is-heading">${tag}${esc(p)}</p>`); continue; }
    const lead = LEAD_RE.exec(p);
    if (lead && !tag) out.push(`<p><span class="erw">${esc(lead[1])}</span>${highlight(lead[2], terms)}</p>`);
    else out.push(`<p>${tag}${highlight(p, terms)}</p>`);
  }
  if (label) out.push(`<p><span class="erw">${esc(label)}</span></p>`);
  return out.join("");
}

// ---------------------------------------------------------------- router
export const state = {
  // list filters (mirrored in the URL hash)
  q: "", period: "all", from: "", to: "", label: "", min: 0, div: "", lang: "", sum: "",
  branch: "", cat: "",
  sort: "score", dir: "desc",
  // cache of last list response
  items: [], total: 0, sig: "", loaded: false, shown: 0,
  lastListHash: "#/",
};

export const PERIODS = [
  { id: "all", label: () => t("f.period.all"), from: "", to: "" },
  { id: "2026q2", label: () => "Q2 2026", from: "2026-04-01", to: "2026-06-30" },
  { id: "2026q1", label: () => "Q1 2026", from: "2026-01-01", to: "2026-03-31" },
  { id: "2025q4", label: () => "Q4 2025", from: "2025-10-01", to: "2025-12-31" },
  { id: "2025q4-2026q1", label: () => "Q4 2025 – Q1 2026", from: "2025-10-01", to: "2026-03-31" },
  { id: "custom", label: () => t("f.custom") },
];

function readHash() {
  const raw = location.hash.slice(1) || "/";
  const [path, query = ""] = raw.split("?");
  return { path, params: new URLSearchParams(query) };
}
function listHash() {
  const p = new URLSearchParams();
  for (const k of ["q", "period", "from", "to", "label", "div", "lang", "sum", "branch", "cat"]) if (state[k] && !(k === "period" && state[k] === "all")) p.set(k, state[k]);
  if (state.min) p.set("min", state.min);
  if (state.sort !== "score" || state.dir !== "desc") { p.set("sort", state.sort); p.set("dir", state.dir); }
  const s = p.toString();
  return "#/all" + (s ? "?" + s : "");
}

async function route() {
  const { path, params } = readHash();
  const m = /^\/r\/(.+)$/.exec(path);
  window.scrollTo(0, 0);
  const section = path.startsWith("/all") ? "#/all" : m ? "" : "#/";
  $$(".pillnav a").forEach((a) => {
    if (a.getAttribute("href") === section) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (m) {
    await renderDetail(decodeURIComponent(m[1]), params);
  } else if (!path.startsWith("/all")) {
    if (path !== "/" && path !== "") { location.replace("#/"); return; } // old #/c/<topic> links
    await renderRelevant(params, resetListeners());
  } else {
    for (const k of ["q", "period", "from", "to", "label", "div", "lang", "sum", "branch", "cat"]) state[k] = params.get(k) || (k === "period" ? "all" : "");
    state.min = +params.get("min") || 0;
    state.sort = params.get("sort") || "score";
    state.dir = params.get("dir") || "desc";
    await renderList();
  }
}

// ---------------------------------------------------------------- list view
function periodRange() {
  if (state.period === "custom") return { from: state.from, to: state.to };
  const p = PERIODS.find((x) => x.id === state.period) || PERIODS[0];
  return { from: p.from, to: p.to };
}

const PAGE = 500;      // API maximum per request
const SHOW_STEP = 200; // rows rendered per "show more"

function serverParams() {
  const { from, to } = periodRange();
  const params = { sort: state.sort === "lang" ? "language" : state.sort, order: state.dir };
  if (state.q.trim()) params.q = state.q.trim();
  if (from) params.from = from;
  if (to) params.to = to;
  if (state.label) params.label = state.label;
  if (state.min) params.min_score = state.min;
  if (state.div) params.division = state.div;
  if (state.lang) params.language = state.lang;
  if (state.sum) params.has_summary = state.sum === "yes";
  if (state.branch) params.branch = state.branch;
  if (state.cat) params.category = state.cat;
  return params;
}

async function ensureItems() {
  const params = serverParams();
  const sig = JSON.stringify(params);
  if (sig !== state.sig) { state.sig = sig; state.items = []; state.total = 0; state.loaded = false; }
  while (!state.loaded && state.items.length < state.shown) {
    const res = await API.list({ ...params, limit: PAGE, offset: state.items.length });
    if (state.sig !== sig) return; // a newer request took over
    state.items.push(...(res.items || []));
    state.total = res.total ?? state.items.length;
    if (!res.items?.length || state.items.length >= state.total) state.loaded = true;
  }
}

// Stats describe the period and search, independent of the triage/score filters.
function listShell() {
  const sel = (name, opts, val) =>
    `<select data-f="${name}">${opts.map(([v, l]) => `<option value="${esc(v)}"${v === val ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  return `
  <header class="pagehead">
    <h1>${esc(t("list.title"))}</h1>
    <p class="pagehead__lede" id="stats">${esc(t("list.sub"))}</p>
  </header>
  <section class="toolbar">
    <div class="toolbar__row">
      <label class="search">
        <span class="sr-only">${esc(t("search.ph"))}</span>
        ${ICONS.search}
        <input type="search" id="q" value="${esc(state.q)}" placeholder="${esc(t("search.ph"))}" autocomplete="off">
        <kbd>/</kbd>
      </label>
    </div>
    <div class="toolbar__row">
      <span class="field">${esc(t("f.period"))}
        ${sel("period", PERIODS.map((p) => [p.id, p.label()]), state.period)}
      </span>
      <span class="field" id="customRange" ${state.period === "custom" ? "" : "hidden"}>
        <input type="date" data-f="from" value="${esc(state.from)}"> – <input type="date" data-f="to" value="${esc(state.to)}">
      </span>
      <span class="field">${esc(t("f.label"))}
        <span class="seg" role="group">
          ${[["", t("f.label.all")], ["relevant", t("f.label.rel")], ["not_relevant", t("f.label.not")]]
            .map(([v, l]) => `<button type="button" data-label="${v}" aria-pressed="${state.label === v}">${esc(l)}</button>`).join("")}
        </span>
      </span>
      <span class="field">${esc(t("f.minscore"))}
        <input type="range" min="0" max="100" step="5" data-f="min" value="${state.min}">
        <output class="num" id="minOut">${state.min}</output>
      </span>
      <span class="field">${esc(t("f.division"))} <span id="divSel"></span></span>
      <span class="field">${esc(t("f.lang"))}
        ${sel("lang", [["", t("f.lang.all")], ["de", "DE"], ["fr", "FR"], ["it", "IT"]], state.lang)}
      </span>
      <span class="field">${esc(t("f.summary"))}
        ${sel("sum", [["", t("f.summary.all")], ["yes", t("f.summary.yes")], ["no", t("f.summary.no")]], state.sum)}
      </span>
      <span class="field">${esc(t("f.branch"))} <span id="branchSel"></span></span>
      <span class="field">${esc(t("f.category"))} <span id="catSel"></span></span>
      <span class="toolbar__spacer"></span>
      <button type="button" class="btn btn--ghost btn--sm" id="reset">${esc(t("f.reset"))}</button>
    </div>
  </section>
  <section class="tablebox">
    <div class="table-wrap" id="tableWrap"></div>
  </section>`;
}

function renderStats() {
  const divs = [...new Set([...COMMON_DIVISIONS, ...state.items.map((r) => divisionCode(r.docket)).filter(Boolean)])].sort();
  if (state.div && !divs.includes(state.div)) divs.push(state.div);
  $("#divSel").innerHTML = `<select data-f="div"><option value="">${esc(t("f.division.all"))}</option>${divs
    .map((d) => `<option value="${d}"${d === state.div ? " selected" : ""}>${d}${divisionName(d) ? " – " + esc(divisionName(d)) : ""}</option>`).join("")}</select>`;
  renderClassFilters();
}

// Branch first; the category list then shows the categories that branch allows, with counts.
function renderClassFilters() {
  const taxonomy = getTaxonomy();
  if (!taxonomy) return;
  const opt = (v, l, n, on) => `<option value="${esc(v)}"${on ? " selected" : ""}>${esc(l)}${n != null ? ` (${n.toLocaleString("de-CH")})` : ""}</option>`;
  $("#branchSel").innerHTML = `<select data-f="branch">${opt("", t("f.branch.all"), null, !state.branch)}${taxonomy.branches
    .filter((b) => b.count || b.value === state.branch)
    .map((b) => opt(b.value, taxLabel("branches", b.value, true), b.count, b.value === state.branch)).join("")}</select>`;
  const count = (c) => (state.branch ? c.counts[state.branch] || 0 : Object.values(c.counts).reduce((a, n) => a + n, 0));
  $("#catSel").innerHTML = `<select data-f="cat">${opt("", t("f.category.all"), null, !state.cat)}${taxonomy.categories
    .filter((c) => (!state.branch || c.branches.includes(state.branch)) && (count(c) || c.value === state.cat))
    .map((c) => opt(c.value, taxLabel("categories", c.value, true), count(c), c.value === state.cat)).join("")}</select>`;
}

function renderTable() {
  const items = state.items;
  const wrap = $("#tableWrap");
  const filtered = state.q || state.label || state.min || state.div || state.lang || state.sum || state.branch || state.cat || state.period !== "all";
  if (!items.length) {
    wrap.innerHTML = `<div class="empty"><h2>${esc(t("empty.title"))}</h2>${
      !filtered ? `<p>${esc(t("empty.db"))} <code>make load</code></p>` : `<p>${esc(t("empty.filtered"))}</p>`}</div>`;
    return;
  }
  const th = (key, label, cls) => {
    const active = state.sort === key;
    return `<th class="${cls}" ${active ? `aria-sort="${state.dir === "asc" ? "ascending" : "descending"}"` : ""}>
      <button type="button" data-sort="${key}">${esc(label)} <span class="arrow">${active && state.dir === "asc" ? "▲" : "▼"}</span></button></th>`;
  };
  const terms = state.q.trim() ? state.q.trim().split(/\s+/) : [];
  const rows = items.slice(0, state.shown).map((r) => {
    const reason = reasoningOf(r);
    const div = divisionCode(r.docket);
    return `<tr data-docket="${esc(r.docket)}" class="${band(r.score) === "low" ? "is-low" : ""}">
      <td class="c-score">${scoreBadge(r.score)}</td>
      <td class="c-docket"><a class="docket" href="#/r/${encodeURIComponent(r.docket)}">${esc(r.docket)}</a>
        <span class="subdocket" title="${esc(rulingDivision(r))}">${esc(div)}${r.score == null ? " " + esc(t("untriaged")) : ""}</span></td>
      <td class="c-date num">${fmtDate(r.decision_date)}</td>
      <td><div class="ruling-title">${terms.length ? highlight(r.title || "—", terms) : esc(r.title || "—")}</div>${r.classification ? `<div class="ruling-tags">${classChips(r.classification)}</div>` : ""}
        ${reason ? `<div class="ruling-reason">${esc(reason)}</div>` : ""}</td>
      <td class="c-lang">${r.language ? `<span class="lang">${esc(r.language)}</span>` : ""}</td>
      <td class="c-sum">${r.has_summary ? `<span class="sumflag is-yes">${ICONS.check}${esc(t("sum.yes"))}</span>` : `<span class="muted">${t("sum.no")}</span>`}</td>
    </tr>`;
  }).join("");
  wrap.innerHTML = `<table class="rulings">
    <thead><tr>
      ${th("score", t("col.score"), "c-score")}${th("docket", t("col.docket"), "c-docket")}${th("date", t("col.date"), "c-date")}
      ${th("title", t("col.subject"), "")}${th("lang", t("col.lang"), "c-lang")}${th("summary", t("col.summary"), "c-sum")}
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>
  <div class="summary__foot">
    <span class="resultcount" id="resultcount">${esc(t("results", Math.min(state.shown, items.length), state.total))}</span>
    ${state.shown < state.total ? `<button type="button" class="btn btn--sm" id="more">${esc(t("more"))}</button>` : ""}
  </div>`;
}

let searchTimer;
let viewListeners = new AbortController();
function resetListeners() {
  viewListeners.abort();
  viewListeners = new AbortController();
  return { signal: viewListeners.signal };
}

async function renderList() {
  document.title = `${t("list.title")} – BGer-Monitor`;
  const opts = resetListeners();
  app.innerHTML = listShell();
  $("#tableWrap").innerHTML = `<div class="skelblock">${'<div class="skel"></div>'.repeat(8)}</div>`;

  let loadingTimer;
  const reload = async (resetShown = true) => {
    history.replaceState(null, "", listHash());
    state.lastListHash = listHash();
    if (resetShown) state.shown = SHOW_STEP;
    clearTimeout(loadingTimer);
    loadingTimer = setTimeout(() => { const c = $("#resultcount"); if (c) c.textContent = t("loading"); }, 300);
    try {
      await Promise.all([ensureItems().then(renderStats), ensureTaxonomy().then(renderClassFilters)]);
    } catch (e) {
      clearTimeout(loadingTimer);
      $("#tableWrap").innerHTML = `<div class="empty"><h2>${esc(t("err.load"))}</h2><p>${esc(e.message)}</p></div>`;
      return;
    }
    clearTimeout(loadingTimer);
    renderStats();
    renderTable();
  };

  app.addEventListener("input", (e) => {
    const el = e.target;
    if (el.id === "q") {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { state.q = el.value; reload(); }, 250);
    } else if (el.dataset.f === "min") {
      $("#minOut").textContent = el.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { state.min = +el.value; reload(); }, 200);
    }
  }, opts);
  app.addEventListener("change", (e) => {
    const f = e.target.dataset.f;
    if (!f || f === "min") return;
    state[f] = e.target.value;
    if (f === "period") $("#customRange").hidden = state.period !== "custom";
    if (f === "branch" && state.branch && !getTaxonomy()?.categories.find((c) => c.value === state.cat)?.branches.includes(state.branch)) state.cat = "";
    reload();
  }, opts);
  app.addEventListener("click", (e) => {
    const lbl = e.target.closest("[data-label]");
    if (lbl) {
      state.label = lbl.dataset.label;
      $$("[data-label]").forEach((b) => b.setAttribute("aria-pressed", b === lbl));
      reload();
      return;
    }
    const s = e.target.closest("[data-sort]");
    if (s) {
      const key = s.dataset.sort;
      if (state.sort === key) state.dir = state.dir === "asc" ? "desc" : "asc";
      else { state.sort = key; state.dir = ["docket", "title", "lang"].includes(key) ? "asc" : "desc"; }
      reload();
      return;
    }
    if (e.target.id === "more") {
      state.shown += SHOW_STEP;
      reload(false);
      return;
    }
    if (e.target.id === "reset") {
      Object.assign(state, { q: "", period: "all", from: "", to: "", label: "", min: 0, div: "", lang: "", sum: "", branch: "", cat: "", sort: "score", dir: "desc" });
      renderList();
      return;
    }
    const tr = e.target.closest("tr[data-docket]");
    if (tr && !e.target.closest("a")) location.hash = `#/r/${encodeURIComponent(tr.dataset.docket)}`;
  }, opts);

  await reload();
}

// ---------------------------------------------------------------- detail view
function wordCount(s) { return (String(s || "").match(/\S+/g) || []).length; }

function suvaExport(r) {
  const de = r.summaries?.de?.text || "";
  const fr = r.summaries?.fr?.text || "";
  const title = suvaTitle(r);
  const p = (s) => s.split(/\n\s*\n/).map((x) => `<p>${esc(x.trim())}</p>`).join("");
  return `<!DOCTYPE html><html lang="${esc(r.language || "de")}"><head><meta charset="UTF-8"><title>${esc(title)}</title></head><body><hr>` +
    `<h1>${esc(title)}</h1><h2>Text DE</h2>${p(de)}<h2>Text FR</h2>${p(fr)}` +
    `<h2>Link zum Urteil</h2><p><a href="${esc(r.url || "")}">${esc(r.docket)} ${esc(fmtDate(r.decision_date))} - Schweizerisches Bundesgericht</a></p>` +
    `<h2>Autor</h2><p>${esc(t("d.ai"))}</p></body></html>`;
}
function plainExport(r) {
  return `${suvaTitle(r)}\n\nText DE\n${r.summaries?.de?.text || ""}\n\nText FR\n${r.summaries?.fr?.text || ""}\n\nLink zum Urteil\n${r.url || ""}`;
}

let summaryView = localStorage.getItem("summaryView") || "both";

function summaryBlock(r) {
  const s = r.summaries || {};
  const has = s.de || s.fr;
  if (!has) {
    return `<section class="card" id="summaryCard">
      <div class="card__head"><h2 class="card__title">${esc(t("d.summary"))}</h2></div>
      <div class="generate" id="generate">
        <h3>${esc(t("gen.title"))}</h3>
        <p>${esc(t("gen.text"))}</p>
        <button type="button" class="btn btn--primary" id="genBtn">${ICONS.spark}${esc(t("gen.btn"))}</button>
      </div>
    </section>`;
  }
  const one = (lang) => {
    const sum = s[lang];
    return `<article class="summary" lang="${lang}">
      <div class="summary__lang">
        <h3>${esc(t(`d.text.${lang}`))}</h3>
        ${sum ? `<button type="button" class="btn btn--ghost btn--sm" data-copy="${lang}" title="${esc(t("d.copy"))}">${ICONS.copy}${esc(t("d.copy"))}</button>` : ""}
      </div>
      ${sum
        ? `<div class="summary__text">${sum.text.split(/\n\s*\n/).map((p) => `<p>${highlight(p.trim())}</p>`).join("")}</div>
           <div class="summary__meta"><span class="chip chip--accent">${ICONS.spark.replace("<svg", '<svg width="13" height="13"')}${esc(t("d.ai"))}</span>
             <span>${esc(t("d.words", wordCount(sum.text)))}</span></div>`
        : `<p class="summary--missing">${esc(t("d.missing.lang"))}</p>`}
    </article>`;
  };
  const view = summaryView;
  const tabs = [["both", t("d.both")], ["de", "DE"], ["fr", "FR"]];
  return `<section class="card" id="summaryCard">
    <div class="card__head">
      <h2 class="card__title">${esc(t("d.summary"))}</h2>
      <div class="tabs" role="tablist">${tabs.map(([v, l]) => `<button type="button" role="tab" data-view="${v}" aria-selected="${view === v}">${esc(l)}</button>`).join("")}</div>
    </div>
    <div class="summaries ${view === "both" ? "is-both" : ""}">
      ${view === "both" ? one("de") + one("fr") : one(view)}
    </div>
    <div class="summary__foot">
      <span class="muted" style="font-size:12.5px">${esc(t("d.ai.hint"))}</span>
      <span style="display:flex;gap:8px;flex-wrap:wrap">
        <button type="button" class="btn btn--sm" data-copy="all">${ICONS.copy}${esc(t("d.copyAll"))}</button>
        <button type="button" class="btn btn--sm" id="exportBtn">${ICONS.down}${esc(t("d.export"))}</button>
        <button type="button" class="btn btn--ghost btn--sm" id="regenBtn">${ICONS.spark}${esc(t("d.regen"))}</button>
      </span>
    </div>
  </section>`;
}

function relevanceCard(r) {
  const tr = r.triage;
  if (!tr) {
    return `<section class="card relevance"><div class="card__head"><h2 class="card__title">${esc(t("r.title"))}</h2></div>
      <div class="card__body"><div class="score-lg">${scoreRing(null)}<p class="muted" style="margin:0">${esc(t("r.none"))}</p></div></div></section>`;
  }
  const rel = tr.label === "relevant";
  return `<section class="card relevance">
    <div class="card__head"><h2 class="card__title">${esc(t("r.title"))}</h2></div>
    <div class="card__body">
      <div class="score-lg">
        ${scoreRing(tr.score)}
        <div>
          <div class="relevance__label ${rel ? "is-rel" : "is-not"}">${esc(rel ? t("r.rel") : t("r.not"))}</div>
          <div class="relevance__hint">${esc(t("r.hint"))}</div>
        </div>
      </div>
      <div>
        <h3 class="card__title" style="margin-bottom:6px">${esc(t("r.reason"))}</h3>
        <p class="reasoning">${highlight(reasoningOf(tr))}</p>
      </div>
    </div>
  </section>`;
}

// One-line headline of what the court decided, shown under the ruling number. Reads
// `headline_de` / `headline_fr` (or `headline`) once the backend provides them; until then the
// classification's one-sentence explanation stands in (German only).
function headlineOf(r) {
  return r[`headline_${uiLang}`] || r.headline || r.classification?.rationale || "";
}
const headlineIsRationale = (r) => !r[`headline_${uiLang}`] && !r.headline && !!r.classification?.rationale;

function classificationCard(c, hideRationale = false) {
  if (!c) return "";
  const rows = [
    [t("f.branch"), taxLabel("branches", c.branch)],
    [t("f.category"), taxLabel("categories", c.primary)],
    ...(c.secondary.length ? [[t("c.secondary"), c.secondary.map((s) => taxLabel("categories", s)).join(" · ")]] : []),
    ...(c.outcome ? [[t("c.outcome"), taxLabel("outcomes", c.outcome)]] : []),
  ];
  return `<section class="card">
    <div class="card__head"><h2 class="card__title">${esc(t("c.title"))}</h2></div>
    <div class="card__body" style="display:grid;gap:12px">
      <dl class="dl">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
      ${c.flags.length ? `<div class="statutes">${c.flags.map((f) => `<span class="chip chip--accent">${esc(taxLabel("flags", f))}</span>`).join("")}</div>` : ""}
      ${c.rationale && !hideRationale ? `<p class="reasoning">${esc(c.rationale)}</p>` : ""}
    </div>
  </section>`;
}

function statutesCard(statutes) {
  return `<section class="card">
    <div class="card__head"><h2 class="card__title">${esc(t("st.title"))}</h2></div>
    <div class="card__body">${statutes.length
      ? `<div class="statutes">${statutes.map((s) => `<button type="button" class="chip" data-goto="${esc(s.law + " " + s.art.replace(/\s+/g, ""))}" title="${esc([...s.forms].join(", "))}">Art. ${esc(s.art)} ${esc(s.law)}${s.count > 1 ? ` <span class="muted">×${s.count}</span>` : ""}</button>`).join("")}</div>`
      : `<p class="muted" style="margin:0">${esc(t("st.none"))}</p>`}</div>
  </section>`;
}

function metaCard(r) {
  const div = divisionCode(r.docket);
  const rows = [
    [t("m.docket"), r.docket],
    [t("m.decision"), fmtDate(r.decision_date, "long")],
    ...(r.publication_date ? [[t("m.published"), fmtDate(r.publication_date, "long")]] : []),
    [t("m.division"), `${div} ${rulingDivision(r)}`],
    [t("m.language"), r.language ? t(`lang.${r.language}`) : "—"],
    [t("m.source"), r.source || "bger.ch"],
  ];
  return `<section class="card">
    <div class="card__head"><h2 class="card__title">${esc(t("m.title"))}</h2></div>
    <div class="card__body"><dl class="dl">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v || "—")}</dd>`).join("")}</dl></div>
  </section>`;
}

function originalCard(r, terms) {
  const text = r.text || "";
  const long = text.length > 4000;
  const hits = terms.length ? (text.match(new RegExp(terms.filter((w) => w.length > 1).map(escRe).join("|") || "$^", "gi")) || []).length : 0;
  return `<section class="card original" id="original">
    <div class="card__head">
      <h2 class="card__title">${esc(t("o.title"))}</h2>
      <div class="original__tools">
        ${hits ? `<span class="chip"><mark style="padding:0 4px">${esc(terms.join(" "))}</mark> ${esc(t("o.hits", hits))}</span>` : ""}
        ${r.language ? `<span class="lang">${esc(r.language)}</span>` : ""}
        ${r.url ? `<a class="btn btn--ghost btn--sm" href="${esc(r.url)}" target="_blank" rel="noopener">${ICONS.ext}bger.ch</a>` : ""}
      </div>
    </div>
    ${text.trim()
      ? `<div class="original__body ${long ? "original__collapsed" : ""}" id="origBody"><div class="original__text" lang="${esc(r.language || "de")}">${paragraphs(text, terms)}</div></div>
         ${long ? `<div class="original__more"><button type="button" class="btn btn--sm" id="origToggle">${esc(t("o.more"))}</button></div>` : ""}`
      : `<div class="card__body muted">${esc(t("o.empty"))}</div>`}
  </section>`;
}

// Round back button left of the ruling number; returns to the last list view.
const backBtn = () => `<a class="dback" href="${esc(state.lastListHash)}" title="${esc(t("back"))}" aria-label="${esc(t("back"))}">${ICONS.back}</a>`;

async function renderDetail(docket, params) {
  resetListeners();
  app.innerHTML = `<header class="dhead"><div class="dhead__id">${backBtn()}<h1><span class="dhead__docket">${esc(docket)}</span></h1></div></header>
    <div class="card card__body" style="display:grid;gap:14px">${'<div class="skel"></div>'.repeat(6)}</div>`;
  let r;
  try {
    [r] = await Promise.all([API.detail(docket), ensureTaxonomy()]);
  } catch (e) {
    app.innerHTML = `<header class="dhead"><div class="dhead__id">${backBtn()}<h1><span class="dhead__docket">${esc(docket)}</span></h1></div></header>
      <div class="card empty"><h2>${esc(e.status === 404 ? t("notfound") : t("err.load"))}</h2><p>${esc(docket)} · ${esc(e.message)}</p></div>`;
    return;
  }
  const terms = (params.get("q") || new URLSearchParams(state.lastListHash.split("?")[1] || "").get("q") || "").trim().split(/\s+/).filter(Boolean);
  paintDetail(r, terms);
}

function paintDetail(r, terms) {
  document.title = `${r.docket} – BGer-Monitor`;
  const statutes = extractStatutes(r.summaries?.de?.text, r.summaries?.fr?.text, reasoningOf(r.triage), r.text);
  app.innerHTML = `
    <header class="dhead">
      <div class="dhead__id">
        ${backBtn()}
        <div class="dhead__text">
          <h1><span class="dhead__docket">${esc(r.docket)}</span>${r.title ? `<span class="dhead__name">${esc(r.title)}</span>` : ""}</h1>
          ${headlineOf(r) ? `<p class="dhead__headline">${esc(headlineOf(r))}</p>` : ""}
        </div>
      </div>
      <div class="dhead__actions">
        ${r.url ? `<a class="btn" href="${esc(r.url)}" target="_blank" rel="noopener">${ICONS.ext}${esc(t("d.original"))}</a>` : ""}
        <button type="button" class="btn btn--ghost" id="printBtn">${ICONS.print}${esc(t("d.print"))}</button>
      </div>
    </header>
    <div class="dgrid">
      <div class="dmain">
        ${summaryBlock(r)}
        ${originalCard(r, terms)}
      </div>
      <aside class="daside">
        ${relevanceCard(r)}
        ${metaCard(r)}
        ${classificationCard(r.classification, headlineIsRationale(r))}
        ${statutesCard(statutes)}
      </aside>
    </div>`;
  bindDetail(r, terms);
}

function bindDetail(r, terms) {
  const on = (id, fn) => { const el = $(id); if (el) el.addEventListener("click", fn); };

  // Summary tabs
  $$("[data-view]").forEach((b) => b.addEventListener("click", () => {
    summaryView = b.dataset.view;
    localStorage.setItem("summaryView", summaryView);
    $("#summaryCard").outerHTML = summaryBlock(r);
    bindDetail(r, terms);
  }));
  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => {
    const l = b.dataset.copy;
    copyText(l === "all" ? plainExport(r) : r.summaries[l].text);
  }));
  on("#exportBtn", () => download(`${r.docket.replace("/", "_")}_Zusammenfassung.html`, suvaExport(r)));
  on("#printBtn", () => {
    const body = $("#origBody");
    body?.classList.remove("original__collapsed");
    window.print();
  });

  // Summarise on demand
  const runSummarize = async () => {
    let gen = $("#generate");
    if (!gen) {
      $("#summaryCard .summaries").outerHTML = `<div class="generate" id="generate"></div>`;
      $("#summaryCard .summary__foot")?.remove();
      gen = $("#generate");
    }
    const steps = [t("gen.s1"), t("gen.s2"), t("gen.s3"), t("gen.s4")];
    const started = Date.now();
    gen.innerHTML = `<h3>${esc(t("gen.running"))}</h3>
      <div class="progress"><div class="progress__bar"><i></i></div>
      <ol class="progress__steps">${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      <div class="progress__time" id="genTime"></div></div>`;
    // The API is a single blocking call; the steps are paced by elapsed time to show progress.
    const tick = () => {
      const s = Math.floor((Date.now() - started) / 1000);
      const idx = Math.min(steps.length - 1, Math.floor(s / 12));
      $$(".progress__steps li", gen).forEach((li, i) => { li.className = i < idx ? "is-done" : i === idx ? "is-now" : ""; });
      const tm = $("#genTime"); if (tm) tm.textContent = t("gen.elapsed", s);
    };
    tick();
    const timer = setInterval(tick, 500);
    try {
      const updated = await API.summarize(r.docket);
      clearInterval(timer);
      toast(t("gen.done"));
      summaryView = "both";
      paintDetail(updated, terms);
    } catch (e) {
      clearInterval(timer);
      gen.innerHTML = `<h3>${esc(t("gen.err"))}</h3>
        <div class="alert">${esc(e.status === 501 ? t("gen.notimpl") : e.message)}</div>
        <p style="margin-top:16px"><button type="button" class="btn btn--primary" id="genBtn">${ICONS.spark}${esc(t("gen.btn"))}</button></p>`;
      on("#genBtn", runSummarize);
    }
  };
  on("#genBtn", runSummarize);
  on("#regenBtn", runSummarize);

  // Original text toggle
  on("#origToggle", (e) => {
    const body = $("#origBody");
    const collapsed = body.classList.toggle("original__collapsed");
    e.currentTarget.textContent = collapsed ? t("o.more") : t("o.less");
    if (collapsed) $("#original").scrollIntoView({ behavior: "smooth" });
  });

  // Statute chips jump to first citation in the original text
  $$("[data-goto]").forEach((b) => b.addEventListener("click", () => {
    const key = b.dataset.goto;
    const target = $$(`#original .cite`).find((c) => c.dataset.cite === key) || $$(".cite").find((c) => c.dataset.cite === key);
    if (!target) return;
    $("#origBody")?.classList.remove("original__collapsed");
    const tg = $("#origToggle"); if (tg) tg.textContent = t("o.less");
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.remove("is-flash"); void target.offsetWidth; target.classList.add("is-flash");
  }));
}

// ---------------------------------------------------------------- boot
function applyLang() {
  document.documentElement.lang = uiLang;
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$(".langswitch button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === uiLang));
  if ($("#agentTab")) paintAgent();
}
$$(".langswitch button").forEach((b) => b.addEventListener("click", () => {
  if (uiLang === b.dataset.lang) return;
  uiLang = b.dataset.lang;
  localStorage.setItem("uiLang", uiLang);
  applyLang();
  route();
}));

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    const q = $("#q");
    if (q) { e.preventDefault(); q.focus(); q.select(); }
  }
  if (e.key === "Escape" && location.hash.startsWith("#/r/") && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) location.hash = state.lastListHash;
});

// Sticky table headers sit right below the sticky top bar, whatever its rendered height.
const syncTopbar = () => document.documentElement.style.setProperty("--topbar-h", `${$(".topbar").offsetHeight}px`);
new ResizeObserver(syncTopbar).observe($(".topbar"));
syncTopbar();

window.addEventListener("hashchange", route);
initAgent();
applyLang();
route();
