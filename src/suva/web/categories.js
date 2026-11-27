// Classification of relevant rulings: insurance branch (UV / IV / ATSG / other), then legal category.
//
// The classification stage (lucas-firstmate, PR in flight) delivers per ruling a `branch` and a
// `category` with German and French labels. This module accepts the shapes that stage may use:
//   branch:   "uv" | "iv" | "atsg" | "other"  or  { id|code, de|label_de, fr|label_fr }
//   category: "<id>"  or  { id|code|key, de|label_de|name_de, fr|label_fr|name_fr }
//             or flat fields category_de / category_fr (category_label_de / category_label_fr)
// Until rulings carry those fields, a provisional keyword classifier on the court's subject line
// (and the triage reasoning) fills in, and the UI says the grouping is provisional.

const pick = (o, ...keys) => { for (const k of keys) if (o && o[k] != null && o[k] !== "") return o[k]; return undefined; };

export const BRANCHES = {
  uv: { de: "Unfallversicherung", fr: "Assurance-accidents", law: { de: "UVG", fr: "LAA" } },
  iv: { de: "Invalidenversicherung", fr: "Assurance-invalidité", law: { de: "IVG", fr: "LAI" } },
  atsg: { de: "Allgemeiner Teil", fr: "Partie générale", law: { de: "ATSG", fr: "LPGA" } },
  other: { de: "Weitere Gebiete", fr: "Autres domaines", law: null },
};
export const BRANCH_ORDER = ["uv", "iv", "atsg", "other"];

// Provisional categories, first match wins (subject line first, then reasoning).
const RULES = [
  ["koordination", "Leistungskoordination und Überentschädigung", "Coordination et surindemnisation",
    /überentschädig|surindemnis|koordination|coordination|sovraindennizz/i],
  ["rueckerstattung", "Rückerstattung und Erlass", "Restitution et remise", /rückerstatt|restitu|remise de l|erlass/i],
  ["hilflosigkeit", "Hilflosenentschädigung", "Allocation pour impotent", /hilflos|impoten|grande invalidit|grande invalidità/i],
  ["invaliditaet", "Invalidenrente und Einkommensvergleich", "Rente d'invalidité et comparaison des revenus",
    /invalidenrente|invaliditätsbemess|invaliditätsgrad|valideneinkommen|invalideneinkommen|rente d.invalidit|revenu (sans invalidit|d.invalide)|rendita d.invalidit|confronto dei redditi|tabellenlohn|versicherte[nr]? verdienst|gain assuré|verwertbarkeit|restarbeitsfähig/i],
  ["integritaet", "Integritätsentschädigung", "Indemnité pour atteinte à l'intégrité", /integrität|intégrité|integrità/i],
  ["psyche", "Psychische Unfallfolgen und Hirnverletzungen", "Troubles psychiques et lésions cérébrales",
    /psychisch|psychique|psichic|schädel-hirn|cranio|schleudertrauma|coup du lapin|whiplash/i],
  ["unfallbegriff", "Unfallbegriff und Listenverletzungen", "Notion d'accident et lésions assimilées",
    /unfallbegriff|notion d.accident|listenverletz|unfallähnlich|lésion.? (corporelle.? )?assimilée|ungewöhnlich/i],
  ["rueckfall", "Rückfall und Spätfolgen", "Rechute et séquelles tardives", /rückfall|rechute|spätfolge|séquelles tardives|ricaduta/i],
  ["kausalitaet", "Kausalzusammenhang", "Lien de causalité", /kausal|causalit|causalità|status quo/i],
  ["heilbehandlung", "Heilbehandlung und Pflege", "Traitement médical et soins", /pflege|heilbehandlung|soins|traitement médical|hilfsmittel|zahn|cure/i],
  ["unterstellung", "Versicherungsunterstellung und Prämien", "Assujettissement et primes",
    /unterstellung|versicherungspflicht|obligation d.assurance|beitragspflicht|beitr[äa]g|prämie|cotisation|primes?\b|selbständig|arbeitnehmerbegriff|tarif|cna/i],
  ["beweis", "Beweiswert medizinischer Berichte", "Valeur probante des rapports médicaux", /gutachten|beweiswert|beweiswürdig|expertise|valeur probante/i],
  ["verfahren", "Verfahren und Fristen", "Procédure et délais",
    /verfahren|procédure|recevabilit|einsprache|opposition|frist|délai|zustellung|notification|eintreten|rechtliches gehör|droit d.être entendu|vollmacht|procedura/i],
];
const OTHER_CAT = ["weitere", "Weitere Rechtsfragen", "Autres questions juridiques"];
export const PROVISIONAL_ORDER = [...RULES.map((r) => r[0]), OTHER_CAT[0]];

const BRANCH_RULES = [
  ["uv", /unfallversicherung|assurance[- ]accidents|infortuni|\bUVG\b|\bLAA\b/i],
  ["iv", /invalidenversicherung|assurance[- ]invalidit|assicurazione per l.invalidit|\bIVG\b|\bLAI\b/i],
  ["atsg", /allgemeiner teil|sozialversicherungsrecht|partie générale|\bATSG\b|\bLPGA\b/i],
];
const subject = (r) => (/^([^(]+)/.exec(r.title || "") || [])[1] || "";

const memo = new WeakMap();

/** { branch: {id, de, fr}, category: {id, de, fr}, provisional } for one ruling. */
export function classify(r) {
  if (memo.has(r)) return memo.get(r);
  const out = fromApi(r) || provisional(r);
  memo.set(r, out);
  return out;
}

function normBranch(raw) {
  if (raw == null || raw === "") return null;
  const id = String(typeof raw === "object" ? pick(raw, "id", "code", "key") ?? "" : raw).toLowerCase();
  const known = BRANCHES[id] || (/(uv|uvg|laa)/.test(id) ? BRANCHES.uv : /(iv|ivg|lai)/.test(id) ? BRANCHES.iv : /(atsg|lpga)/.test(id) ? BRANCHES.atsg : null);
  const key = known ? Object.keys(BRANCHES).find((k) => BRANCHES[k] === known) : "other";
  const base = BRANCHES[key];
  return {
    id: key,
    de: (typeof raw === "object" && pick(raw, "de", "label_de", "name_de")) || base.de,
    fr: (typeof raw === "object" && pick(raw, "fr", "label_fr", "name_fr")) || base.fr,
  };
}

function fromApi(r) {
  let c = pick(r, "category");
  if (!c && Array.isArray(r.categories) && r.categories.length) c = r.categories[0];
  const flatDe = pick(r, "category_de", "category_label_de");
  const flatFr = pick(r, "category_fr", "category_label_fr");
  if (!c && !flatDe) return null;
  const id = String((typeof c === "object" ? pick(c, "id", "code", "key") : c) ?? flatDe);
  const de = (typeof c === "object" && pick(c, "de", "label_de", "name_de", "label", "name")) || flatDe || id;
  const fr = (typeof c === "object" && pick(c, "fr", "label_fr", "name_fr")) || flatFr || de;
  const branch = normBranch(pick(r, "branch", "insurance_branch") ?? (typeof c === "object" ? c.branch : null)) || provisional(r).branch;
  return { branch, category: { id, de, fr }, provisional: false };
}

function provisional(r) {
  const head = subject(r);
  const b = (BRANCH_RULES.find(([, re]) => re.test(head)) || BRANCH_RULES.find(([, re]) => re.test(r.reasoning || "")) || ["other"])[0];
  const paren = (r.title || "").slice(head.length);
  const hit = RULES.find((x) => x[3].test(paren)) || RULES.find((x) => x[3].test(head)) || RULES.find((x) => x[3].test(r.reasoning || ""));
  const [id, de, fr] = hit || OTHER_CAT;
  return { branch: { id: b, de: BRANCHES[b].de, fr: BRANCHES[b].fr }, category: { id, de, fr }, provisional: true };
}

export const label = (o, lang) => (o ? o[lang] || o.de || o.id : "");

/**
 * Build the register: branches in fixed order, each with its categories sorted by size.
 * Returns [{ branch, count, cats: [{ category, count, items }] }].
 */
export function buildRegister(items) {
  const byBranch = new Map();
  for (const r of items) {
    const { branch, category } = classify(r);
    if (!byBranch.has(branch.id)) byBranch.set(branch.id, { branch, count: 0, cats: new Map() });
    const b = byBranch.get(branch.id);
    b.count++;
    if (!b.cats.has(category.id)) b.cats.set(category.id, { category, items: [] });
    b.cats.get(category.id).items.push(r);
  }
  const last = (id) => (id === OTHER_CAT[0] ? 1 : 0);
  return BRANCH_ORDER.filter((id) => byBranch.has(id)).map((id) => {
    const b = byBranch.get(id);
    const cats = [...b.cats.values()]
      .map((c) => ({ ...c, count: c.items.length }))
      .sort((x, y) => last(x.category.id) - last(y.category.id) || y.count - x.count || x.category.de.localeCompare(y.category.de));
    return { branch: b.branch, count: b.count, cats };
  });
}
