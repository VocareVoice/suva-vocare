// Classification of rulings: insurance branch (UV / IV / MV / ATSG / other), then legal category.
//
// Every ruling carries `classification: { branch, primary, secondary, outcome, flags }` (PR #6,
// src/suva/classify.py). The closed label lists with DE/FR labels and counts come from
// /api/facets (`classification`). Labels look like "Unfallversicherung (UVG)": the short form
// drops the parenthesis, which for branches holds the statute.

import { uiLang } from "./app.js";

export const BRANCH_ORDER = ["uv", "iv", "mv", "atsg", "other"];
const OTHER_CAT = "andere";

let taxonomy = null;
export async function ensureTaxonomy() {
  if (!taxonomy) {
    const res = await fetch("/api/facets", { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    taxonomy = (await res.json()).classification;
  }
  return taxonomy;
}
export const getTaxonomy = () => taxonomy;

const PAREN = /\s*\(([^)]*)\)\s*$/;
/** Label for a slug of `kind` (branches, categories, outcomes, flags) in the UI language. */
export function taxLabel(kind, slug, short = false) {
  const item = taxonomy?.[kind]?.find((x) => x.value === slug);
  const full = item ? item[uiLang] || item.de : slug || "";
  return short ? full.replace(PAREN, "") : full;
}
/** The statute in a branch label, e.g. "UVG" / "LAA". */
export const branchLaw = (slug) => (PAREN.exec(taxLabel("branches", slug)) || [])[1] || "";

/** { branch, category } slugs for one ruling; unclassified rulings fall under other / andere. */
export function classify(r) {
  const c = r.classification;
  return { branch: c?.branch || "other", category: c?.primary || OTHER_CAT };
}

/**
 * Build the register: branches in fixed order, each with its categories sorted by size
 * ("Andere" last). Returns [{ branch, count, cats: [{ category, count, items }] }].
 */
export function buildRegister(items) {
  const byBranch = new Map();
  for (const r of items) {
    const { branch, category } = classify(r);
    if (!byBranch.has(branch)) byBranch.set(branch, { branch, count: 0, cats: new Map() });
    const b = byBranch.get(branch);
    b.count++;
    if (!b.cats.has(category)) b.cats.set(category, { category, items: [] });
    b.cats.get(category).items.push(r);
  }
  const last = (id) => (id === OTHER_CAT ? 1 : 0);
  const rank = (id) => (BRANCH_ORDER.includes(id) ? BRANCH_ORDER.indexOf(id) : BRANCH_ORDER.length);
  return [...byBranch.values()].sort((x, y) => rank(x.branch) - rank(y.branch)).map((b) => ({
    branch: b.branch,
    count: b.count,
    cats: [...b.cats.values()]
      .map((c) => ({ ...c, count: c.items.length }))
      .sort((x, y) => last(x.category) - last(y.category) || y.count - x.count
        || taxLabel("categories", x.category).localeCompare(taxLabel("categories", y.category))),
  }));
}
