// BGer-Monitor UI — vanilla ES module, no build step, no external dependencies.
// Talks to the FastAPI JSON API in src/suva/api.py. The root view (relevant rulings by category)
// lives in relevant.js, the branch/category taxonomy in categories.js, the agent panel in agent.js,
// the agent's knowledge page in knowledge.js.

import { askAgent, initAgent, paintAgent } from "./agent.js";
import { branchLaw, buildRegister, ensureTaxonomy, getTaxonomy, taxLabel } from "./categories.js";
import { renderKnowledge } from "./knowledge.js";
import { renderLaw } from "./law.js";
import { invalidateKnowledgeBase, loadKnowledgeBase, renderRelevant } from "./relevant.js";
import { loadAdjustments, renderAdjustments } from "./adjustments.js";

// ---------------------------------------------------------------- i18n
const I18N = {
  de: {
    "nav.rel": "Wissensbasis",
    "nav.all": "Alle Urteile",
    "nav.law": "Gesetze",
    "nav.agent": "Agent-Wissen",
    "nav.adjust": "Anpassungen",
    "adj.intro": "Hier sind alle Relevanz-Scores erfasst, die Fachpersonen angepasst haben, jeweils neben dem Score der KI-Triage. Die KI-Auswertung fasst zusammen, wo die Triage danebenliegt. Sie ändert die Triage nicht: Diese Erkenntnisse in den Triage-Prompt zurückzuführen, ist der nächste Schritt.",
    "adj.stat.total": "Anpassungen",
    "adj.stat.raised": "höher bewertet",
    "adj.stat.lowered": "tiefer bewertet",
    "adj.stat.added": "neu in der Wissensbasis",
    "adj.stat.removed": "aus der Wissensbasis entfernt",
    "adj.sum.title": "KI-Auswertung",
    "adj.sum.run": "Auswerten",
    "adj.sum.rerun": "Neu auswerten",
    "adj.sum.running": "Wird ausgewertet …",
    "adj.sum.wait": "Apertus liest die Anpassungen. Das kann eine Minute dauern.",
    "adj.sum.none": "Noch keine Auswertung. Apertus fasst zusammen, was die Anpassungen gemeinsam haben und was das für den Triage-Prompt heisst.",
    "adj.sum.empty": "Sobald Fachpersonen Scores anpassen, lässt sich hier auswerten, was die Korrekturen gemeinsam haben.",
    "adj.sum.stale": "Seit dieser Auswertung haben sich die Anpassungen geändert.",
    "adj.sum.meta": (d, n, m) => `Erstellt am ${d} aus ${n} ${n === 1 ? "Anpassung" : "Anpassungen"} · ${m}`,
    "adj.sum.next": "Nächster Schritt (noch nicht umgesetzt): Die Vorschläge fliessen geprüft in den Triage-Prompt ein, und die Triage wird mit den angepassten Urteilen als Referenz neu evaluiert.",
    "adj.sum.err": (m) => `Die Auswertung ist fehlgeschlagen: ${m}`,
    "adj.col.change": "KI → Fachperson",
    "adj.col.reason": "Gegenstand und Begründung der Fachperson",
    "adj.col.date": "Angepasst",
    "adj.noreason": "Keine Begründung angegeben",
    "adj.empty.title": "Noch keine Anpassungen",
    "adj.empty.text": "Öffnen Sie ein Urteil unter «Alle Urteile» und passen Sie im Feld «Relevanz» den Score an.",
    "mem.intro": "Dieser Text gilt für jede Antwort des Agenten, vor allem für Zusammenfassungen. Er geht bei jeder Frage mit, halten Sie ihn deshalb kurz. Standardmässig enthält er die wichtigsten Stilregeln der Suva-Zusammenfassungen; Sie können ihn frei ändern und jederzeit auf den Standard zurücksetzen. Bitten Sie den Agenten im Chat, sich etwas zu merken, ergänzt er den Text selbst.",
    "mem.save": "Speichern",
    "mem.undo": "Änderungen verwerfen",
    "mem.reset": "Standard wiederherstellen",
    "mem.saved": "Gespeichert",
    "mem.status.default": "Standard",
    "mem.status.dirty": "Nicht gespeicherte Änderungen",
    "mem.by.agent": "Zuletzt vom Agenten geändert",
    "mem.by.user": "Zuletzt von Hand geändert",
    "mem.chars": (n, max) => `${n} von ${max} Zeichen`,
    "law.inforce": (d) => `Stand ${d}`,
    "law.filter": "Artikel oder Stichwort, z. B. 6 oder Heilbehandlung",
    "law.none": "Kein Artikel gefunden.",
    "rel.title": "Wissensbasis",
    "rel.register": "Register",
    "rel.all": "Alle Rechtsfragen",
    "rel.sum.yes": "Zusammenfassung DE und FR vorhanden",
    "rel.sum.no": "Noch keine Zusammenfassung",
    "rel.sum.open": "Offen",
    "agent.tab": "Agent",
    "agent.title": "Agent",
    "agent.close": "Agent schliessen",
    "agent.intro": "Schildern Sie einen Fall oder stellen Sie eine Frage. Ich suche die einschlägigen UVG-Artikel und Bundesgerichtsurteile aus der Wissensbasis und verlinke sie. Auf Wunsch schlage ich auch eine überarbeitete Zusammenfassung eines Urteils vor.",
    "agent.ph": "Fall schildern oder Frage stellen …",
    "agent.send": "Senden",
    "agent.new": "Neuer Chat",
    "agent.new.title": "Diesen Chat löschen und neu beginnen",
    "agent.thinking": "Der Agent recherchiert …",
    "agent.busy": "Der Agent beantwortet noch die vorige Nachricht.",
    "agent.error": (e) => `Fehler: ${e}`,
    "agent.context": (d) => `Kontext: ${d}`,
    "agent.step.read_uvg_article": (a) => `Art. ${a.art ?? ""} UVG gelesen`,
    "agent.step.read_article": (a) => `Art. ${a.art ?? ""} ${({ LAA: "UVG", LPGA: "ATSG", OLAA: "UVV" })[(a.law || "UVG").toUpperCase()] || (a.law || "UVG").toUpperCase()} gelesen`,
    "agent.step.list_rulings": (a) => a.category ? `Wissensbasis durchsucht (Kategorie ${a.category})` : a.query ? `Wissensbasis durchsucht: «${a.query}»` : "Wissensbasis durchgesehen",
    "agent.step.search_rulings": (a) => `Volltextsuche: «${a.query ?? ""}»`,
    "agent.step.read_ruling": (a) => `Urteil ${a.docket ?? ""} gelesen${a.offset ? " (Fortsetzung)" : ""}`,
    "agent.step.propose_summary": (a) => `Zusammenfassung ${a.docket ?? ""} (${(a.lang || "").toUpperCase()}) entworfen`,
    "agent.step.other": (name) => `Werkzeug ${name}`,
    "agent.step.correction": "Antwort zurückgewiesen",
    "agent.trace": (n, err) => `${n} Tool-Aufruf${n === 1 ? "" : "e"}${err ? ` · ${err} mit Fehler` : ""}`,
    "agent.step.correction.format": "Tool-Aufruf ungültig, zurückgewiesen",
    "agent.step.correction.json": "Antwort als JSON, zurückgewiesen",
    "agent.step.correction.unseen": "Ungeprüfte Geschäftsnummern, zurückgewiesen",
    "agent.step.correction.notool": "Kein Tool aufgerufen, zurückgewiesen",
    "agent.prop.title": (d, l) => `Vorschlag: neue Zusammenfassung ${l} für`,
    "agent.prop.apply": "Übernehmen",
    "agent.prop.discard": "Verwerfen",
    "agent.prop.applied": "Übernommen – die bisherige Zusammenfassung wurde ersetzt.",
    "agent.prop.discarded": "Verworfen.",
    "agent.prop.current": "Bisherige Zusammenfassung",
    "agent.prop.none": "Noch keine Zusammenfassung.",
    "agent.step.update_memory": (a) => `Agent-Wissen ${a.mode === "replace" ? "neu geschrieben" : "ergänzt"}`,
    "kb.empty": "Keine Urteile in der Wissensbasis",
    "kb.empty.sub": "Sobald die Triage Urteile als relevant bewertet, erscheinen sie hier.",
    "brand.sub": "Rechtsprechung Unfallversicherung",
    "nav.rulings": "Urteile",
    "list.title": "Bundesgerichtsurteile",
    "list.sub": "Alle publizierten Urteile mit Relevanzbewertung für die Suva",
    "add.btn": "Urteil hinzufügen",
    "add.label": "Urteilsnummer des Bundesgerichts",
    "add.ph": "z. B. 8C_129/2025",
    "add.hint": "Das Urteil wird von entscheidsuche.ch geladen, klassifiziert und auf seine Relevanz für die Suva bewertet.",
    "add.submit": "Hinzufügen",
    "add.cancel": "Abbrechen",
    "add.running": (d) => `${d} wird hinzugefügt …`,
    "add.s1": "Urteil auf entscheidsuche.ch suchen und laden",
    "add.s2": "Versicherungszweig und Kategorie bestimmen",
    "add.s3": "Relevanz für die Suva bewerten",
    "add.elapsed": (s) => `Laufzeit ${fmtElapsed(s)} · dauert meist unter einer Minute`,
    "add.invalid": "Bitte eine Urteilsnummer wie 8C_129/2025 eingeben.",
    "add.err": "Das Urteil konnte nicht hinzugefügt werden",
    "add.notfound": (d) => `${d} ist auf entscheidsuche.ch nicht zu finden. Ist die Nummer richtig?`,
    "add.done": (d) => `${d} hinzugefügt`,
    "add.exists": (d) => `${d} ist bereits in der Datenbank`,
    "add.partial": (d) => `${d} hinzugefügt, aber nicht vollständig bewertet`,
    "search.ph": "Volltextsuche in Urteilen – z. B. «Kausalzusammenhang», «Art. 6 UVG», 8C_129/2025",
    "f.period": "Zeitraum",
    "f.period.all": "Alle",
    "f.custom": "Benutzerdefiniert",
    "f.period.eval": "Evaluation",
    "gen.eval": "Dieses Urteil liegt im Evaluationszeitraum (Q4 2025 – Q1 2026). Er diente zum Vergleich mit den Zusammenfassungen der Suva, deshalb wurden hier keine Zusammenfassungen im Voraus erstellt.",
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
    "f.advanced": "Erweitert",
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
    "d.edit": "Bearbeiten",
    "d.write": "Verfassen",
    "d.writeOwn": "Selbst verfassen",
    "d.edit.save": "Speichern",
    "d.edit.cancel": "Abbrechen",
    "d.edit.hint": "Absätze mit einer Leerzeile trennen.",
    "d.edit.saved": "Zusammenfassung gespeichert",
    "d.edit.err": "Speichern fehlgeschlagen",
    "d.manual": "Von Hand bearbeitet",
    "d.agentEdited": "Mit dem Agenten überarbeitet",
    "d.askAgent": "Mit Agent überarbeiten",
    "d.askAgent.prompt": (d) => `Überarbeite die Zusammenfassung von ${d} (DE und FR): `,
    "gen.title": "Noch keine Zusammenfassung",
    "gen.text": "Erstellen Sie eine deutsche und eine französische Zusammenfassung im Suva-Stil. Beide Fassungen werden eigenständig verfasst, nicht übersetzt.",
    "gen.btn": "Zusammenfassen",
    "gen.running": "Zusammenfassung wird erstellt …",
    "gen.s1": "Urteilstext analysieren",
    "gen.s2": "Kernaussagen und Normen extrahieren",
    "gen.s3": "Deutsche Fassung verfassen",
    "gen.s4": "Französische Fassung verfassen",
    "gen.elapsed": (s) => `Laufzeit ${fmtElapsed(s)} · kann einige Minuten dauern`,
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
    "r.adjust": "Anpassen",
    "r.expert": "Von Fachperson angepasst",
    "r.model": (s) => `KI-Score ${s}`,
    "r.reset": "Auf KI-Score zurücksetzen",
    "r.edit.kb": "Erscheint in der Wissensbasis",
    "r.edit.nokb": "Erscheint nicht in der Wissensbasis",
    "r.edit.comment": "Begründung (optional)",
    "r.edit.placeholder": "Warum ist das Urteil für die Suva mehr oder weniger relevant?",
    "r.edit.saved": "Score gespeichert",
    "r.edit.reset": "Wieder der KI-Score",
    "r.edit.err": "Der Score konnte nicht gespeichert werden",
    "st.title": "Zitierte Normen",
    "st.none": "Keine Normen erkannt.",
    "st.para": "Abs.",
    "st.let": "lit.",
    "pr.title": "Zitierte Leitentscheide",
    "pr.prefix": "BGE",
    "pr.open": "Auf bger.ch öffnen",
    "m.title": "Angaben",
    "m.docket": "Urteil",
    "m.subject": "Gegenstand",
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
    "nav.law": "Lois",
    "nav.agent": "Savoir de l'agent",
    "nav.adjust": "Ajustements",
    "adj.intro": "Tous les scores de pertinence ajustés par des spécialistes, à côté du score du triage IA. L'analyse IA résume où le triage se trompe. Elle ne modifie pas le triage : réintégrer ces enseignements dans le prompt de triage est la prochaine étape.",
    "adj.stat.total": "ajustements",
    "adj.stat.raised": "relevés",
    "adj.stat.lowered": "abaissés",
    "adj.stat.added": "ajoutés à la base",
    "adj.stat.removed": "retirés de la base",
    "adj.sum.title": "Analyse IA",
    "adj.sum.run": "Analyser",
    "adj.sum.rerun": "Analyser à nouveau",
    "adj.sum.running": "Analyse en cours …",
    "adj.sum.wait": "Apertus lit les ajustements. Cela peut prendre une minute.",
    "adj.sum.none": "Pas encore d'analyse. Apertus résume ce que les ajustements ont en commun et ce que cela implique pour le prompt de triage.",
    "adj.sum.empty": "Dès que des spécialistes ajustent des scores, vous pourrez analyser ici ce que les corrections ont en commun.",
    "adj.sum.stale": "Les ajustements ont changé depuis cette analyse.",
    "adj.sum.meta": (d, n, m) => `Créée le ${d} à partir de ${n} ajustement${n === 1 ? "" : "s"} · ${m}`,
    "adj.sum.next": "Prochaine étape (pas encore réalisée) : les propositions, une fois vérifiées, sont intégrées au prompt de triage, et le triage est réévalué avec les arrêts ajustés comme référence.",
    "adj.sum.err": (m) => `L'analyse a échoué : ${m}`,
    "adj.col.change": "IA → spécialiste",
    "adj.col.reason": "Objet et motivation du ou de la spécialiste",
    "adj.col.date": "Ajusté",
    "adj.noreason": "Aucune motivation indiquée",
    "adj.empty.title": "Pas encore d'ajustements",
    "adj.empty.text": "Ouvrez un arrêt sous « Tous les arrêts » et ajustez le score dans le champ « Pertinence ».",
    "mem.intro": "Ce texte vaut pour chaque réponse de l'agent, en particulier pour les résumés. Il accompagne chaque question, gardez-le donc court. Par défaut, il contient l'essentiel des règles de style des résumés de la Suva ; vous pouvez le modifier librement et le rétablir en tout temps. Si vous demandez à l'agent dans le chat de retenir quelque chose, il complète lui-même le texte.",
    "mem.save": "Enregistrer",
    "mem.undo": "Annuler les modifications",
    "mem.reset": "Rétablir le standard",
    "mem.saved": "Enregistré",
    "mem.status.default": "Standard",
    "mem.status.dirty": "Modifications non enregistrées",
    "mem.by.agent": "Modifié en dernier par l'agent",
    "mem.by.user": "Modifié en dernier à la main",
    "mem.chars": (n, max) => `${n} sur ${max} caractères`,
    "law.inforce": (d) => `État le ${d}`,
    "law.filter": "Article ou mot-clé, p. ex. 6 ou traitement",
    "law.none": "Aucun article trouvé.",
    "rel.title": "Base de connaissances",
    "rel.register": "Registre",
    "rel.all": "Toutes les questions",
    "rel.sum.yes": "Résumé DE et FR disponible",
    "rel.sum.no": "Pas encore de résumé",
    "rel.sum.open": "Ouvert",
    "agent.tab": "Agent",
    "agent.title": "Agent",
    "agent.close": "Fermer l'agent",
    "agent.intro": "Décrivez un cas ou posez une question. Je cherche les articles pertinents de la LAA et les arrêts du Tribunal fédéral de la base de connaissances, avec des liens. Sur demande, je propose aussi un résumé révisé d'un arrêt.",
    "agent.ph": "Décrire un cas ou poser une question …",
    "agent.send": "Envoyer",
    "agent.new": "Nouveau chat",
    "agent.new.title": "Supprimer ce chat et recommencer",
    "agent.thinking": "L'agent fait ses recherches …",
    "agent.busy": "L'agent répond encore au message précédent.",
    "agent.error": (e) => `Erreur : ${e}`,
    "agent.context": (d) => `Contexte : ${d}`,
    "agent.step.read_uvg_article": (a) => `Art. ${a.art ?? ""} LAA lu`,
    "agent.step.read_article": (a) => `Art. ${a.art ?? ""} ${({ UVG: "LAA", ATSG: "LPGA", UVV: "OLAA" })[(a.law || "UVG").toUpperCase()] || (a.law || "UVG").toUpperCase()} lu`,
    "agent.step.list_rulings": (a) => a.category ? `Base de connaissances parcourue (catégorie ${a.category})` : a.query ? `Base de connaissances : « ${a.query} »` : "Base de connaissances parcourue",
    "agent.step.search_rulings": (a) => `Recherche plein texte : « ${a.query ?? ""} »`,
    "agent.step.read_ruling": (a) => `Arrêt ${a.docket ?? ""} lu${a.offset ? " (suite)" : ""}`,
    "agent.step.propose_summary": (a) => `Résumé ${a.docket ?? ""} (${(a.lang || "").toUpperCase()}) rédigé`,
    "agent.step.other": (name) => `Outil ${name}`,
    "agent.step.correction": "Réponse renvoyée",
    "agent.trace": (n, err) => `${n} appel${n === 1 ? "" : "s"} d'outil${err ? ` · ${err} en erreur` : ""}`,
    "agent.step.correction.format": "Appel d'outil invalide, renvoyé",
    "agent.step.correction.json": "Réponse en JSON, renvoyée",
    "agent.step.correction.unseen": "Numéros de dossier non vérifiés, renvoyée",
    "agent.step.correction.notool": "Aucun outil appelé, renvoyée",
    "agent.prop.title": (d, l) => `Proposition : nouveau résumé ${l} pour`,
    "agent.prop.apply": "Appliquer",
    "agent.prop.discard": "Rejeter",
    "agent.prop.applied": "Appliqué – l'ancien résumé a été remplacé.",
    "agent.prop.discarded": "Rejeté.",
    "agent.prop.current": "Résumé actuel",
    "agent.prop.none": "Pas encore de résumé.",
    "agent.step.update_memory": (a) => `Savoir de l'agent ${a.mode === "replace" ? "réécrit" : "complété"}`,
    "kb.empty": "Aucun arrêt dans la base de connaissances",
    "kb.empty.sub": "Les arrêts apparaissent ici dès que le triage les juge pertinents.",
    "brand.sub": "Jurisprudence assurance-accidents",
    "nav.rulings": "Arrêts",
    "list.title": "Arrêts du Tribunal fédéral",
    "list.sub": "Tous les arrêts publiés avec leur évaluation de pertinence pour la Suva",
    "add.btn": "Ajouter un arrêt",
    "add.label": "Numéro de l'arrêt du Tribunal fédéral",
    "add.ph": "p. ex. 8C_129/2025",
    "add.hint": "L'arrêt est chargé depuis entscheidsuche.ch, classé et évalué quant à sa pertinence pour la Suva.",
    "add.submit": "Ajouter",
    "add.cancel": "Annuler",
    "add.running": (d) => `Ajout de ${d} …`,
    "add.s1": "Rechercher et charger l'arrêt sur entscheidsuche.ch",
    "add.s2": "Déterminer la branche d'assurance et la catégorie",
    "add.s3": "Évaluer la pertinence pour la Suva",
    "add.elapsed": (s) => `Durée ${fmtElapsed(s)} · en général moins d'une minute`,
    "add.invalid": "Veuillez saisir un numéro d'arrêt comme 8C_129/2025.",
    "add.err": "L'arrêt n'a pas pu être ajouté",
    "add.notfound": (d) => `${d} est introuvable sur entscheidsuche.ch. Le numéro est-il correct ?`,
    "add.done": (d) => `${d} ajouté`,
    "add.exists": (d) => `${d} figure déjà dans la base de données`,
    "add.partial": (d) => `${d} ajouté, mais pas entièrement évalué`,
    "search.ph": "Recherche plein texte – p. ex. « causalité adéquate », « art. 6 LAA », 8C_129/2025",
    "f.period": "Période",
    "f.period.all": "Toutes",
    "f.custom": "Personnalisée",
    "f.period.eval": "évaluation",
    "gen.eval": "Cet arrêt se situe dans la période d'évaluation (T4 2025 – T1 2026). Elle a servi à la comparaison avec les résumés de la Suva ; aucun résumé n'y a donc été rédigé à l'avance.",
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
    "f.advanced": "Avancé",
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
    "d.edit": "Modifier",
    "d.write": "Rédiger",
    "d.writeOwn": "Rédiger soi-même",
    "d.edit.save": "Enregistrer",
    "d.edit.cancel": "Annuler",
    "d.edit.hint": "Séparer les paragraphes par une ligne vide.",
    "d.edit.saved": "Résumé enregistré",
    "d.edit.err": "L'enregistrement a échoué",
    "d.manual": "Modifié à la main",
    "d.agentEdited": "Révisé avec l'agent",
    "d.askAgent": "Réviser avec l'agent",
    "d.askAgent.prompt": (d) => `Révise le résumé de ${d} (DE et FR) : `,
    "gen.title": "Pas encore de résumé",
    "gen.text": "Générez un résumé en allemand et en français dans le style de la Suva. Les deux versions sont rédigées séparément, et non traduites.",
    "gen.btn": "Résumer",
    "gen.running": "Résumé en cours de rédaction …",
    "gen.s1": "Analyser le texte de l'arrêt",
    "gen.s2": "Extraire les considérants et les normes",
    "gen.s3": "Rédiger la version allemande",
    "gen.s4": "Rédiger la version française",
    "gen.elapsed": (s) => `Durée ${fmtElapsed(s)} · peut prendre quelques minutes`,
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
    "r.adjust": "Ajuster",
    "r.expert": "Ajusté par un·e spécialiste",
    "r.model": (s) => `Score IA ${s}`,
    "r.reset": "Revenir au score IA",
    "r.edit.kb": "Figure dans la base de connaissances",
    "r.edit.nokb": "Ne figure pas dans la base de connaissances",
    "r.edit.comment": "Motivation (facultatif)",
    "r.edit.placeholder": "Pourquoi l'arrêt est-il plus ou moins pertinent pour la Suva ?",
    "r.edit.saved": "Score enregistré",
    "r.edit.reset": "Score IA rétabli",
    "r.edit.err": "Le score n'a pas pu être enregistré",
    "st.title": "Normes citées",
    "st.none": "Aucune norme détectée.",
    "st.para": "al.",
    "st.let": "let.",
    "pr.title": "Arrêts de principe cités",
    "pr.prefix": "ATF",
    "pr.open": "Ouvrir sur bger.ch",
    "m.title": "Informations",
    "m.docket": "Arrêt",
    "m.subject": "Objet",
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

// 75 -> "1:15 min", 42 -> "42 s"
const fmtElapsed = (s) => (s < 60 ? `${s} s` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} min`);

export let uiLang =localStorage.getItem("uiLang") === "fr" ? "fr" : "de";
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
  de: {
    1: "I. öffentlich-rechtliche Abteilung", 2: "II. öffentlich-rechtliche Abteilung",
    9: "III. öffentlich-rechtliche Abteilung", 8: "IV. öffentlich-rechtliche Abteilung",
    4: "I. zivilrechtliche Abteilung", 5: "II. zivilrechtliche Abteilung",
    6: "I. strafrechtliche Abteilung", 7: "II. strafrechtliche Abteilung",
  },
  fr: {
    1: "Ire Cour de droit public", 2: "IIe Cour de droit public",
    9: "IIIe Cour de droit public", 8: "IVe Cour de droit public",
    4: "Ire Cour de droit civil", 5: "IIe Cour de droit civil",
    6: "Ire Cour de droit pénal", 7: "IIe Cour de droit pénal",
  },
};
const COMMON_DIVISIONS = ["8C", "9C", "1C", "2C", "4A", "5A", "6B", "7B"];
function divisionName(code) { return ABTEILUNG[uiLang][(code || "")[0]] || ""; }
// The stored `division` is the court's German name; the docket prefix gives it in the UI language.
function rulingDivision(r) {
  const code = divisionCode(r.docket);
  return divisionName(code) || r.division || code;
}
const divisionCode = (docket) => (/^(\d[A-Z])_/.exec(docket || "") || [])[1] || "";

// Triage explanation in the UI language (reasoning_de / reasoning_fr); older results only have
// the German one or the single `reasoning` field.
export const reasoningOf = (o) => (o && (o[`reasoning_${uiLang}`] || o.reasoning_de || o.reasoning || o.reason)) || "";

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
  chevron: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
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
  add: (docket) => api("/api/rulings", { method: "POST", body: JSON.stringify({ docket }) }),
  summarize: (docket) => api(`/api/rulings/${docketPath(docket)}/summarize`, { method: "POST" }),
  setScore: (docket, score, comment) => api(`/api/rulings/${docketPath(docket)}/score`, { method: "PUT", body: JSON.stringify({ score, comment }) }),
  resetScore: (docket) => api(`/api/rulings/${docketPath(docket)}/score`, { method: "DELETE" }),
  saveSummary: (docket, lang, text) => api(`/api/rulings/${docketPath(docket)}/summaries/${lang}`, { method: "PUT", body: JSON.stringify({ text }) }),
};

// ---------------------------------------------------------------- statutes
// The cited statutes and precedents come with the classification (`classification.statutes`,
// `classification.precedents`). This pattern only marks citations in the text, so a statute chip
// can jump to its first occurrence: "Art. 73 lit. b UVV", "art. 6 al. 1 LAA", "Art. 16 ATSG".
const LAWS = ["UVG", "LAA", "UVV", "OLAA", "ATSG", "LPGA", "ATSV", "OPGA", "IVG", "LAI", "IVV", "RAI", "AHVG", "LAVS",
  "BVG", "LPP", "KVG", "LAMal", "MVG", "LAM", "VVG", "LCA", "OR", "CO", "ZGB", "CC", "BV", "Cst\\.", "BGG", "LTF", "VwVG", "PA", "EMRK", "CEDH", "SVG", "LCR"];
const LAW_PAIRS = { LAA: "UVG", OLAA: "UVV", LPGA: "ATSG", OPGA: "ATSV", LAI: "IVG", RAI: "IVV", LAVS: "AHVG", LPP: "BVG",
  LAMal: "KVG", LAM: "MVG", LCA: "VVG", CO: "OR", CC: "ZGB", "Cst.": "BV", LTF: "BGG", PA: "VwVG", CEDH: "EMRK", LCR: "SVG" };
const LAW_FR = Object.fromEntries(Object.entries(LAW_PAIRS).map(([fr, de]) => [de, fr]));
// A statute's abbreviation in the UI language: "UVG" reads "LAA" in the French UI.
const lawAbbr = (law) => (uiLang === "fr" ? LAW_FR[LAW_PAIRS[law] || law] || law : LAW_PAIRS[law] || law);
const CITE_RE = new RegExp(
  String.raw`\b[Aa]rt(?:\.|ikel)\s*(\d+[a-z]?(?:\s*(?:bis|ter|quater))?)` +
  String.raw`((?:\s*(?:Abs\.|al\.|para\.)\s*\d+[a-z]?)?(?:\s*(?:lit\.|let\.|Bst\.|Ziff\.|ch\.)\s*[a-z0-9]+)?)` +
  String.raw`\s+(?:des\s+|de\s+la\s+|du\s+|de\s+l')?(${LAWS.join("|")})(?![\wÀ-ÿ])`,
  "g",
);
// Escape text, then mark statute citations and search terms.
export function highlight(text, terms = []) {
  // "13 %" stays on one line.
  let html = esc(text).replace(/(\d) %/g, "$1 %");
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
// Summaries were written ahead of time only for Q2 2026; Q4 2025 – Q1 2026 is the evaluation
// period (compared against Suva's own summaries), so the list opens on Q2 2026.
const DEFAULT_PERIOD = "2026q2";
const EVAL_END = "2026-03-31";

export const state = {
  // list filters (mirrored in the URL hash)
  q: "", period: DEFAULT_PERIOD, from: "", to: "", label: "", min: 0, div: "", lang: "", sum: "",
  branch: "", cat: "",
  sort: "score", dir: "desc",
  // cache of last list response
  items: [], total: 0, sig: "", loaded: false, shown: 0,
  lastListHash: "#/",
  advOpen: null, // "Erweitert" filters shown; null: open only when one of them is set
};

export const PERIODS = [
  { id: "all", label: () => t("f.period.all"), from: "", to: "" },
  { id: "2026q2", label: () => "Q2 2026", from: "2026-04-01", to: "2026-06-30" },
  { id: "2026q1", label: () => `Q1 2026 (${t("f.period.eval")})`, from: "2026-01-01", to: "2026-03-31" },
  { id: "2025q4", label: () => `Q4 2025 (${t("f.period.eval")})`, from: "2025-10-01", to: "2025-12-31" },
  { id: "2025q4-2026q1", label: () => `Q4 2025 – Q1 2026 (${t("f.period.eval")})`, from: "2025-10-01", to: "2026-03-31" },
  { id: "custom", label: () => t("f.custom") },
];

function readHash() {
  const raw = location.hash.slice(1) || "/";
  const [path, query = ""] = raw.split("?");
  return { path, params: new URLSearchParams(query) };
}
function listHash() {
  const p = new URLSearchParams();
  for (const k of ["q", "period", "from", "to", "label", "div", "lang", "sum", "branch", "cat"]) if (state[k] && !(k === "period" && state[k] === DEFAULT_PERIOD)) p.set(k, state[k]);
  if (state.min) p.set("min", state.min);
  if (state.sort !== "score" || state.dir !== "desc") { p.set("sort", state.sort); p.set("dir", state.dir); }
  const s = p.toString();
  return "#/all" + (s ? "?" + s : "");
}

// ---------------------------------------------------------------- side navigation
// Knowledge base with its insurance branches (no categories), all rulings, the law. On a ruling
// page the section it was opened from stays marked.
async function paintNav() {
  const ul = $("#navKb");
  if (!ul.children.length) ul.innerHTML = '<li><div class="skel"></div></li><li><div class="skel" style="width:70%"></div></li>';
  let items;
  try {
    [items] = await Promise.all([loadKnowledgeBase(), ensureTaxonomy()]);
  } catch {
    ul.innerHTML = "";
    return;
  }
  $("#kbCount").textContent = items.length || "";
  loadAdjustments().then((d) => { $("#adjCount").textContent = d.items.length || ""; }, () => {});
  ul.innerHTML = buildRegister(items).map((b) => `<li data-branch="${esc(b.branch)}">
    <a href="#/?branch=${encodeURIComponent(b.branch)}" data-navbranch="${esc(b.branch)}" title="${esc(taxLabel("branches", b.branch))}">
      <span class="navsub__swatch" aria-hidden="true"></span>
      <span class="navsub__name">${esc(taxLabel("branches", b.branch, true))}${branchLaw(b.branch) ? `<span class="navsub__law">${esc(branchLaw(b.branch))}</span>` : ""}</span>
      <span class="navlink__n">${b.count}</span></a></li>`).join("");
  markNav();
}

function markNav() {
  const { path, params } = readHash();
  const onDetail = path.startsWith("/r/");
  const [refPath, refQuery = ""] = (onDetail ? state.lastListHash.slice(1) : `${path}?${params}`).split("?");
  const section = refPath.startsWith("/all") ? "all" : refPath === "/adjust" ? "adjust" : refPath.startsWith("/law") ? "law" : refPath === "/agent" ? "agent" : "kb";
  const branch = section === "kb" ? new URLSearchParams(refQuery).get("branch") || "" : "";
  $$("[data-nav]").forEach((a) => {
    const on = a.dataset.nav === section && !(section === "kb" && branch) && !onDetail;
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  $$("[data-navbranch]").forEach((a) => {
    if (a.dataset.navbranch === branch) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
  });
}

async function route() {
  const { path, params } = readHash();
  const m = /^\/r\/(.+)$/.exec(path);
  window.scrollTo(0, 0);
  markNav();
  if (m) {
    await renderDetail(decodeURIComponent(m[1]), params);
  } else if (path === "/adjust") {
    state.lastListHash = location.hash;
    await renderAdjustments(resetListeners());
  } else if (path === "/agent") {
    state.lastListHash = location.hash;
    await renderKnowledge(resetListeners());
  } else if (path.startsWith("/law")) {
    state.lastListHash = location.hash;
    await renderLaw(path.split("/")[2] || "uvg", params, resetListeners());
  } else if (!path.startsWith("/all")) {
    if (path !== "/" && path !== "") { location.replace("#/"); return; } // old #/c/<topic> links
    await renderRelevant(params, resetListeners());
  } else {
    for (const k of ["q", "period", "from", "to", "label", "div", "lang", "sum", "branch", "cat"]) state[k] = params.get(k) || (k === "period" ? DEFAULT_PERIOD : "");
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
// Filters behind "Erweitert": score threshold, division, language, summary.
const advancedCount = () => [state.min > 0, state.div, state.lang, state.sum].filter(Boolean).length;

function listShell() {
  const advN = advancedCount();
  const advOpen = state.advOpen ?? advN > 0;
  const sel = (name, opts, val) =>
    `<select data-f="${name}">${opts.map(([v, l]) => `<option value="${esc(v)}"${v === val ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  return `
  <header class="pagehead pagehead--action">
    <div>
      <h1>${esc(t("list.title"))}</h1>
      <p class="pagehead__lede" id="stats">${esc(t("list.sub"))}</p>
    </div>
    <button type="button" class="btn btn--sm" id="addBtn" aria-expanded="false" aria-controls="addForm">${ICONS.plus}${esc(t("add.btn"))}</button>
  </header>
  <form class="addform" id="addForm" hidden novalidate>
    <label for="addDocket">${esc(t("add.label"))}</label>
    <div class="addform__row">
      <input id="addDocket" name="docket" autocomplete="off" spellcheck="false" placeholder="${esc(t("add.ph"))}">
      <button type="submit" class="btn btn--primary btn--sm">${esc(t("add.submit"))}</button>
      <button type="button" class="btn btn--ghost btn--sm" id="addCancel">${esc(t("add.cancel"))}</button>
    </div>
    <p class="addform__hint">${esc(t("add.hint"))}</p>
    <div id="addStatus" aria-live="polite"></div>
  </form>
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
      <span class="field">${esc(t("f.branch"))} <span id="branchSel"></span></span>
      <span class="field">${esc(t("f.category"))} <span id="catSel"></span></span>
      <span class="toolbar__spacer"></span>
      <span class="toolbar__actions">
      <button type="button" class="btn btn--ghost btn--sm advtoggle" id="advToggle" aria-expanded="${advOpen}" aria-controls="advRow">
        ${esc(t("f.advanced"))}<span class="advtoggle__n" id="advCount"${advN ? "" : " hidden"}>${advN}</span>${ICONS.chevron}
      </button>
      <button type="button" class="btn btn--ghost btn--sm" id="reset">${esc(t("f.reset"))}</button>
      </span>
    </div>
    <div class="toolbar__row toolbar__row--adv" id="advRow"${advOpen ? "" : " hidden"}>
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

// Branch above the legal category, as in the knowledge base; each one filters the list.
function classCell(c) {
  if (!c) return `<span class="muted">—</span>`;
  return `<div class="entry__class" data-branch="${esc(c.branch)}">
    <button type="button" class="entry__branch" data-filter-branch="${esc(c.branch)}" title="${esc(taxLabel("branches", c.branch))}">${esc(taxLabel("branches", c.branch, true))}</button>
    <button type="button" class="entry__cat" data-filter-branch="${esc(c.branch)}" data-filter-cat="${esc(c.primary)}" title="${esc(taxLabel("categories", c.primary))}">${esc(taxLabel("categories", c.primary, true))}</button>
  </div>`;
}

function renderTable() {
  const items = state.items;
  const wrap = $("#tableWrap");
  const filtered = state.q || state.label || state.min || state.div || state.lang || state.sum || state.branch || state.cat || state.period !== DEFAULT_PERIOD;
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
      <td class="c-score">${scoreBadge(r.score)}${r.expert_score ? `<span class="score__expert" title="${esc(t("r.expert"))}">${PENCIL}</span>` : ""}</td>
      <td class="c-docket"><a class="docket" href="#/r/${encodeURIComponent(r.docket)}">${esc(r.docket)}</a>
        <span class="subdocket" title="${esc(rulingDivision(r))}">${esc(div)}${r.score == null ? " " + esc(t("untriaged")) : ""}</span></td>
      <td class="c-date num">${fmtDate(r.decision_date)}</td>
      <td class="c-cat">${classCell(r.classification)}</td>
      <td><div class="ruling-title">${terms.length ? highlight(r.title || "—", terms) : esc(r.title || "—")}</div>
        ${reason ? `<div class="ruling-reason">${esc(reason)}</div>` : ""}</td>
    </tr>`;
  }).join("");
  wrap.innerHTML = `<table class="rulings">
    <thead><tr>
      ${th("score", t("col.score"), "c-score")}${th("docket", t("col.docket"), "c-docket")}${th("date", t("col.date"), "c-date")}
      ${th("category", t("f.category"), "c-cat")}${th("title", t("col.subject"), "")}
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
    const n = advancedCount();
    const badge = $("#advCount");
    if (badge) { badge.textContent = n; badge.hidden = !n; }
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
    const cls = e.target.closest("[data-filter-branch]");
    if (cls) {
      state.branch = cls.dataset.filterBranch;
      state.cat = cls.dataset.filterCat || "";
      reload();
      return;
    }
    const s = e.target.closest("[data-sort]");
    if (s) {
      const key = s.dataset.sort;
      if (state.sort === key) state.dir = state.dir === "asc" ? "desc" : "asc";
      else { state.sort = key; state.dir = ["docket", "title", "category"].includes(key) ? "asc" : "desc"; }
      reload();
      return;
    }
    const adv = e.target.closest("#advToggle");
    if (adv) {
      state.advOpen = adv.getAttribute("aria-expanded") !== "true";
      adv.setAttribute("aria-expanded", state.advOpen);
      $("#advRow").hidden = !state.advOpen;
      return;
    }
    if (e.target.id === "more") {
      state.shown += SHOW_STEP;
      reload(false);
      return;
    }
    if (e.target.id === "reset") {
      Object.assign(state, { q: "", period: DEFAULT_PERIOD, from: "", to: "", label: "", min: 0, div: "", lang: "", sum: "", branch: "", cat: "", sort: "score", dir: "desc" });
      renderList();
      return;
    }
    const tr = e.target.closest("tr[data-docket]");
    if (tr && !e.target.closest("a")) location.hash = `#/r/${encodeURIComponent(tr.dataset.docket)}`;
  }, opts);
  bindAddRuling(opts);

  await reload();
}

// "Add ruling": fetch one ruling by its number, classify and triage it (POST /api/rulings),
// then open it. Same normalisation as the server (suva/ingest.py), so typos show up at once.
const DOCKET_INPUT_RE = /^\s*(\d{1,2}[A-Z]{1,2})[\s_.-]*(\d{1,5})\s*[/-]\s*(\d{4})\s*$/i;
const normaliseDocket = (raw) => {
  const m = DOCKET_INPUT_RE.exec(raw);
  return m ? `${m[1].toUpperCase()}_${+m[2]}/${m[3]}` : null;
};

function bindAddRuling(opts) {
  const form = $("#addForm");
  const btn = $("#addBtn");
  const input = $("#addDocket");
  const status = $("#addStatus");
  let busy = false;
  const toggle = (open) => {
    if (busy) return;
    form.hidden = !open;
    btn.setAttribute("aria-expanded", open);
    status.innerHTML = "";
    if (open) input.focus();
    else btn.focus();
  };
  btn.addEventListener("click", () => toggle(form.hidden), opts);
  $("#addCancel").addEventListener("click", () => toggle(false), opts);
  form.addEventListener("keydown", (e) => { if (e.key === "Escape") toggle(false); }, opts);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const docket = normaliseDocket(input.value);
    if (!docket) {
      status.innerHTML = `<div class="alert">${esc(t("add.invalid"))}</div>`;
      input.focus();
      return;
    }
    busy = true;
    form.classList.add("is-busy");
    $$("input, button", form).forEach((el) => { el.disabled = true; });
    // One blocking call; as for summaries, the steps are an estimate that follows the clock.
    const steps = [t("add.s1"), t("add.s2"), t("add.s3")];
    const started = Date.now();
    status.innerHTML = `<div class="progress"><strong>${esc(t("add.running", docket))}</strong>
      <div class="progress__bar"><i></i></div>
      <ol class="progress__steps">${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      <div class="progress__time" id="addTime"></div></div>`;
    const bar = $(".progress__bar i", status);
    const tick = () => {
      const s = Math.floor((Date.now() - started) / 1000);
      const p = 0.9 * (1 - Math.exp(-s / 30));
      bar.style.width = `${(p * 100).toFixed(1)}%`;
      const idx = s < 3 ? 0 : Math.min(steps.length - 1, 1 + Math.floor(s / 20));
      $$(".progress__steps li", status).forEach((li, i) => { li.className = i < idx ? "is-done" : i === idx ? "is-now" : ""; });
      const tm = $("#addTime"); if (tm) tm.textContent = t("add.elapsed", s);
    };
    tick();
    const timer = setInterval(tick, 500);
    try {
      const res = await API.add(docket);
      clearInterval(timer);
      busy = false;
      if (res.created) scoreChanged(); // new row in the list, maybe in the knowledge base
      toast(t(res.errors?.length ? "add.partial" : res.created ? "add.done" : "add.exists", res.docket));
      location.hash = `#/r/${encodeURIComponent(res.docket)}`;
    } catch (err) {
      clearInterval(timer);
      busy = false;
      form.classList.remove("is-busy");
      $$("input, button", form).forEach((el) => { el.disabled = false; });
      const msg = err.status === 404 ? t("add.notfound", docket) : err.message;
      status.innerHTML = `<div class="alert"><strong>${esc(t("add.err"))}</strong><br>${esc(msg)}</div>`;
      input.focus();
    }
  }, opts);
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

const PENCIL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>';

/** Who wrote the summary: the pipeline, the user by hand, or the user with the agent. */
function originChip(sum) {
  const icon = (svg) => svg.replace("<svg", '<svg width="13" height="13"');
  if (sum.model === "manual") return `<span class="chip">${icon(PENCIL)}${esc(t("d.manual"))}</span>`;
  if (sum.model === "agent") return `<span class="chip chip--accent">${icon(ICONS.spark)}${esc(t("d.agentEdited"))}</span>`;
  return `<span class="chip chip--accent">${icon(ICONS.spark)}${esc(t("d.ai"))}</span>`;
}

function summaryBlock(r, writeOwn = false) {
  const s = r.summaries || {};
  const has = s.de || s.fr || writeOwn;
  if (!has) {
    return `<section class="card" id="summaryCard">
      <div class="card__head"><h2 class="card__title">${esc(t("d.summary"))}</h2></div>
      <div class="generate" id="generate">
        <h3>${esc(t("gen.title"))}</h3>
        <p>${esc(t("gen.text"))}</p>
        ${r.decision_date && r.decision_date <= EVAL_END ? `<p class="muted">${esc(t("gen.eval"))}</p>` : ""}
        <p style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
          <button type="button" class="btn btn--primary" id="genBtn">${ICONS.spark}${esc(t("gen.btn"))}</button>
          <button type="button" class="btn" id="writeOwnBtn">${PENCIL}${esc(t("d.writeOwn"))}</button>
        </p>
      </div>
    </section>`;
  }
  const one = (lang) => {
    const sum = s[lang];
    return `<article class="summary" lang="${lang}">
      <div class="summary__lang">
        <h3>${esc(t(`d.text.${lang}`))}</h3>
        <span class="summary__tools">
          <button type="button" class="btn btn--ghost btn--sm" data-edit="${lang}">${PENCIL}${esc(t(sum ? "d.edit" : "d.write"))}</button>
          ${sum ? `<button type="button" class="btn btn--ghost btn--sm" data-copy="${lang}" title="${esc(t("d.copy"))}">${ICONS.copy}${esc(t("d.copy"))}</button>` : ""}
        </span>
      </div>
      ${sum
        ? `<div class="summary__text">${sum.text.split(/\n\s*\n/).map((p) => `<p>${highlight(p.trim())}</p>`).join("")}</div>
           <div class="summary__meta">${originChip(sum)}
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
        <button type="button" class="btn btn--sm" id="askAgentBtn">${ICONS.spark}${esc(t("d.askAgent"))}</button>
        <button type="button" class="btn btn--ghost btn--sm" id="regenBtn">${ICONS.spark}${esc(t("d.regen"))}</button>
      </span>
    </div>
  </section>`;
}

// Rulings at or above this score are relevant and appear in the knowledge base
// (triage.RELEVANCE_THRESHOLD on the server).
const RELEVANCE_THRESHOLD = 50;

function relevanceCard(r) {
  const tr = r.triage;
  const head = `<div class="card__head"><h2 class="card__title">${esc(t("r.title"))}</h2>
    <button type="button" class="btn btn--ghost btn--sm" id="scoreEdit">${PENCIL}${esc(t("r.adjust"))}</button></div>`;
  if (!tr) {
    return `<section class="card relevance" id="relevanceCard">${head}
      <div class="card__body"><div class="score-lg">${scoreRing(null)}<p class="muted" style="margin:0">${esc(t("r.none"))}</p></div></div></section>`;
  }
  const rel = tr.label === "relevant";
  const expert = tr.model === "expert";
  return `<section class="card relevance" id="relevanceCard">${head}
    <div class="card__body">
      <div class="score-lg">
        ${scoreRing(tr.score)}
        <div>
          <div class="relevance__label ${rel ? "is-rel" : "is-not"}">${esc(rel ? t("r.rel") : t("r.not"))}</div>
          ${expert ? `<div class="relevance__expert">${esc(t("r.expert"))}</div>
            ${r.model_triage ? `<div class="relevance__hint">${esc(t("r.model", r.model_triage.score))}</div>` : ""}
            <button type="button" class="linkbtn" id="scoreReset">${esc(t("r.reset"))}</button>`
          : `<div class="relevance__hint">${esc(t("r.hint"))}</div>`}
        </div>
      </div>
      <div>
        <h3 class="card__title" style="margin-bottom:6px">${esc(t("r.reason"))}</h3>
        <p class="reasoning">${highlight(reasoningOf(tr))}</p>
      </div>
    </div>
  </section>`;
}

/** The expert's editor in place of the relevance card's body: score slider and a reason. */
function editScore(r, terms) {
  const card = $("#relevanceCard");
  if (!card) return;
  const tr = r.triage;
  const start = tr?.score ?? RELEVANCE_THRESHOLD;
  // The expert's own reason, not the model's that stands in when they gave none.
  const comment = tr?.model === "expert" && tr.reasoning_de !== r.model_triage?.reasoning_de ? tr.reasoning_de : "";
  $("#scoreEdit", card)?.remove();
  $(".card__body", card).innerHTML = `
    <div class="score-lg">
      <div data-ring>${scoreRing(start)}</div>
      <div>
        <div class="relevance__label" data-score-label></div>
        <div class="relevance__hint" data-score-kb></div>
      </div>
    </div>
    <div class="scoreedit__row">
      <input type="range" min="0" max="100" step="1" value="${start}" aria-label="Score" data-score-range>
      <input type="number" min="0" max="100" step="1" value="${start}" class="scoreedit__num" aria-label="Score" data-score-num>
    </div>
    <label class="scoreedit__label">${esc(t("r.edit.comment"))}
      <textarea class="summary__edit scoreedit__comment" rows="3" placeholder="${esc(t("r.edit.placeholder"))}" data-score-comment>${esc(comment)}</textarea></label>
    <div class="summary__editbar" style="justify-content:flex-end">
      <span style="display:flex;gap:8px">
        <button type="button" class="btn btn--ghost btn--sm" data-score-cancel>${esc(t("d.edit.cancel"))}</button>
        <button type="button" class="btn btn--primary btn--sm" data-score-save>${esc(t("d.edit.save"))}</button>
      </span>
    </div>`;
  const range = $("[data-score-range]", card), num = $("[data-score-num]", card);
  const clamp = (v) => Math.max(0, Math.min(100, Math.round(+v || 0)));
  const show = (v) => {
    const rel = v >= RELEVANCE_THRESHOLD;
    $("[data-ring]", card).innerHTML = scoreRing(v);
    const label = $("[data-score-label]", card);
    label.className = `relevance__label ${rel ? "is-rel" : "is-not"}`;
    label.textContent = t(rel ? "r.rel" : "r.not");
    $("[data-score-kb]", card).textContent = t(v >= RELEVANCE_THRESHOLD ? "r.edit.kb" : "r.edit.nokb");
  };
  show(start);
  range.addEventListener("input", () => { num.value = range.value; show(+range.value); });
  num.addEventListener("input", () => { if (num.value !== "") { range.value = clamp(num.value); show(clamp(num.value)); } });
  num.addEventListener("change", () => { num.value = clamp(num.value); });
  range.focus();
  $("[data-score-cancel]", card).addEventListener("click", () => repaintRelevance(r, terms));
  $("[data-score-save]", card).addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    try {
      const text = $("[data-score-comment]", card).value.trim();
      Object.assign(r, await API.setScore(r.docket, clamp(num.value), text || null));
      scoreChanged();
      toast(t("r.edit.saved"));
      repaintRelevance(r, terms);
    } catch (err) {
      e.currentTarget.disabled = false;
      toast(`${t("r.edit.err")}: ${err.message}`);
    }
  });
}

function repaintRelevance(r, terms) {
  $("#relevanceCard").outerHTML = relevanceCard(r);
  bindRelevance(r, terms);
}
function bindRelevance(r, terms) {
  $("#scoreEdit")?.addEventListener("click", () => editScore(r, terms));
  $("#scoreReset")?.addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    try {
      Object.assign(r, await API.resetScore(r.docket));
      scoreChanged();
      toast(t("r.edit.reset"));
      repaintRelevance(r, terms);
    } catch (err) {
      e.currentTarget.disabled = false;
      toast(`${t("r.edit.err")}: ${err.message}`);
    }
  });
}
/** A changed score moves the ruling in the list and in or out of the knowledge base. */
function scoreChanged() {
  state.sig = "";
  invalidateKnowledgeBase();
  paintNav(); // branch counts in the side navigation
}

// One-line headline of what the court decided (`headline_de` / `headline_fr`, written by Apertus;
// null until generated, see lucas-firstmate on agent-comms). It is the ruling's heading next to
// the docket. Without one, the court's subject line is the heading and the classification's
// one-sentence explanation (German only, so only in the German UI) stands in below it. Never the
// headline of the other language: a French heading in the German UI reads as a bug.
export function headlineOf(r) {
  return r[`headline_${uiLang}`] || "";
}
const rationaleOf = (c) => (uiLang === "de" && c?.rationale) || "";
const headlineIsRationale = (r) => !headlineOf(r) && !!rationaleOf(r.classification);

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
      ${rationaleOf(c) && !hideRationale ? `<p class="reasoning">${esc(rationaleOf(c))}</p>` : ""}
    </div>
  </section>`;
}

// Statutes as the classification lists them, in its order (UVG, UVV, ATSG first):
// {law, art, count, details?: [{para, let, count}]}. The paragraphs and letters go in the tooltip.
const times = (n) => (n > 1 ? ` ×${n}` : "");
function statuteDetail(d) {
  return [d.para && `${t("st.para")} ${d.para}`, d.let && `${t("st.let")} ${d.let}`].filter(Boolean).join(" ") + times(d.count);
}
function statutesCard(statutes) {
  return `<section class="card">
    <div class="card__head"><h2 class="card__title">${esc(t("st.title"))}</h2></div>
    <div class="card__body">${statutes.length
      ? `<div class="statutes">${statutes.map((s) => {
        const title = [`Art. ${s.art} ${lawAbbr(s.law)}`, ...(s.details || []).map(statuteDetail)].join("\n");
        return `<button type="button" class="chip" data-goto="${esc((LAW_PAIRS[s.law] || s.law) + " " + String(s.art).replace(/\s+/g, ""))}" title="${esc(title)}">Art. ${esc(s.art)} ${esc(lawAbbr(s.law))}${s.count > 1 ? ` <span class="muted">×${s.count}</span>` : ""}</button>`;
      }).join("")}</div>`
      : `<p class="muted" style="margin:0">${esc(t("st.none"))}</p>`}</div>
  </section>`;
}

// Cited leading decisions (BGE / ATF), e.g. {ref: "134 V 109", count: 2}; each opens on bger.ch.
function bgeUrl(ref) {
  const lang = uiLang === "fr" ? "fr" : "de";
  return `https://search.bger.ch/ext/eurospider/live/${lang}/php/clir/http/index.php?highlight_docid=atf%3A%2F%2F${encodeURIComponent(ref.trim().replace(/\s+/g, "-"))}%3A${lang}&lang=${lang}&type=show_document`;
}
function precedentsCard(precedents) {
  if (!precedents?.length) return "";
  return `<section class="card">
    <div class="card__head"><h2 class="card__title">${esc(t("pr.title"))}</h2></div>
    <div class="card__body"><div class="statutes">${precedents.map((p) =>
      `<a class="chip" href="${esc(bgeUrl(p.ref))}" target="_blank" rel="noopener" title="${esc(t("pr.open"))}">${esc(t("pr.prefix"))} ${esc(p.ref)}${p.count > 1 ? ` <span class="muted">×${p.count}</span>` : ""}</a>`).join("")}</div></div>
  </section>`;
}

function metaCard(r) {
  const div = divisionCode(r.docket);
  const rows = [
    [t("m.docket"), r.docket],
    ...(r.title ? [[t("m.subject"), r.title]] : []),
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

// The relevance score and its reasoning matter when screening every ruling ("Alle Urteile");
// in the knowledge base every ruling is relevant already, so the box is left out there.
const fromAllRulings = () => /^#\/(all|adjust)/.test(state.lastListHash);

function paintDetail(r, terms) {
  document.title = `${r.docket} – BGer-Monitor`;
  app.innerHTML = `
    <header class="dhead">
      <div class="dhead__id">
        ${backBtn()}
        <div class="dhead__text">
          <h1><span class="dhead__docket">${esc(r.docket)}</span>${headlineOf(r) || r.title ? `<span class="dhead__name">${esc(headlineOf(r) || r.title)}</span>` : ""}</h1>
          ${headlineIsRationale(r) ? `<p class="dhead__headline">${esc(r.classification.rationale)}</p>` : ""}
        </div>
      </div>
    </header>
    <div class="dgrid">
      <div class="dmain">
        ${summaryBlock(r)}
        ${originalCard(r, terms)}
      </div>
      <aside class="daside">
        <div class="dactions">
          ${r.url ? `<a class="btn" href="${esc(r.url)}" target="_blank" rel="noopener">${ICONS.ext}${esc(t("d.original"))}</a>` : ""}
          <button type="button" class="btn" id="printBtn">${ICONS.print}${esc(t("d.print"))}</button>
        </div>
        ${fromAllRulings() ? relevanceCard(r) : ""}
        ${metaCard(r)}
        ${classificationCard(r.classification, headlineIsRationale(r))}
        ${statutesCard(r.classification?.statutes || [])}
        ${precedentsCard(r.classification?.precedents)}
      </aside>
    </div>`;
  bindDetail(r, terms);
  bindRelevance(r, terms);
}

/** Open the editor for the summary in `lang`, in place of its text. */
function editSummary(r, lang, terms) {
  const art = $(`#summaryCard .summary[lang="${lang}"]`);
  if (!art) return;
  const current = r.summaries?.[lang]?.text || "";
  art.innerHTML = `<div class="summary__lang"><h3>${esc(t(`d.text.${lang}`))}</h3></div>
    <textarea class="summary__edit" spellcheck="true" lang="${lang}">${esc(current)}</textarea>
    <div class="summary__editbar">
      <span class="muted" data-words>${esc(t("d.words", wordCount(current)))} · ${esc(t("d.edit.hint"))}</span>
      <span style="display:flex;gap:8px">
        <button type="button" class="btn btn--ghost btn--sm" data-edit-cancel>${esc(t("d.edit.cancel"))}</button>
        <button type="button" class="btn btn--primary btn--sm" data-edit-save>${esc(t("d.edit.save"))}</button>
      </span>
    </div>`;
  const ta = $("textarea", art);
  const fit = () => { ta.style.height = "auto"; ta.style.height = `${ta.scrollHeight + 2}px`; };
  fit();
  ta.focus();
  ta.addEventListener("input", () => {
    fit();
    $("[data-words]", art).textContent = `${t("d.words", wordCount(ta.value))} · ${t("d.edit.hint")}`;
  });
  $("[data-edit-cancel]", art).addEventListener("click", () => repaintSummary(r, terms));
  $("[data-edit-save]", art).addEventListener("click", async (e) => {
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    e.currentTarget.disabled = true;
    try {
      const updated = await API.saveSummary(r.docket, lang, text);
      toast(t("d.edit.saved"));
      Object.assign(r, updated);
      repaintSummary(r, terms);
    } catch (err) {
      e.currentTarget.disabled = false;
      toast(`${t("d.edit.err")}: ${err.message}`);
    }
  });
}

function repaintSummary(r, terms, writeOwn = false) {
  $("#summaryCard").outerHTML = summaryBlock(r, writeOwn);
  bindSummary(r, terms);
}

/** Listeners inside the summary card, which is re-rendered on its own. */
function bindSummary(r, terms) {
  const on = (id, fn) => { const el = $(id); if (el) el.addEventListener("click", fn); };
  const card = $("#summaryCard");

  // Summary tabs
  $$("[data-view]", card).forEach((b) => b.addEventListener("click", () => {
    summaryView = b.dataset.view;
    localStorage.setItem("summaryView", summaryView);
    repaintSummary(r, terms);
  }));
  $$("[data-copy]", card).forEach((b) => b.addEventListener("click", () => {
    const l = b.dataset.copy;
    copyText(l === "all" ? plainExport(r) : r.summaries[l].text);
  }));
  $$("[data-edit]", card).forEach((b) => b.addEventListener("click", () => editSummary(r, b.dataset.edit, terms)));
  on("#writeOwnBtn", () => {
    const lang = r.language === "fr" ? "fr" : "de";
    if (summaryView !== "both") summaryView = lang;
    repaintSummary(r, terms, true);
    editSummary(r, lang, terms);
  });
  on("#askAgentBtn", () => askAgent(t("d.askAgent.prompt", r.docket)));
  on("#exportBtn", () => download(`${r.docket.replace("/", "_")}_Zusammenfassung.html`, suvaExport(r)));

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
    // The API is a single blocking call that takes from one to many minutes on the shared
    // gateway, so the progress is an estimate: the bar creeps towards 90 % and never goes back,
    // the steps follow it, and the last step stays open (pulsing) until the call returns.
    const bar = $(".progress__bar i", gen);
    const tick = () => {
      const s = Math.floor((Date.now() - started) / 1000);
      const p = 0.9 * (1 - Math.exp(-s / 150));
      bar.style.width = `${(p * 100).toFixed(1)}%`;
      const idx = Math.min(steps.length - 1, Math.floor((p / 0.9) * steps.length * 1.15));
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
}

function bindDetail(r, terms) {
  const on = (id, fn) => { const el = $(id); if (el) el.addEventListener("click", fn); };
  bindSummary(r, terms);
  on("#printBtn", () => {
    const body = $("#origBody");
    body?.classList.remove("original__collapsed");
    window.print();
  });

  // Original text toggle
  on("#origToggle", (e) => {
    const body = $("#origBody");
    const collapsed = body.classList.toggle("original__collapsed");
    e.currentTarget.textContent = collapsed ? t("o.more") : t("o.less");
    if (collapsed) $("#original").scrollIntoView({ behavior: "smooth" });
  });

  // Statute chips jump to first citation in the original text. A statute the text marker does not
  // recognise (a law outside LAWS, an unusual citation form) has nowhere to jump to.
  const citeFor = (key) => $$(`#original .cite`).find((c) => c.dataset.cite === key) || $$(".cite").find((c) => c.dataset.cite === key);
  $$("[data-goto]").forEach((b) => {
    if (!citeFor(b.dataset.goto)) b.classList.add("chip--static");
  });
  $$("[data-goto]").forEach((b) => b.addEventListener("click", () => {
    const target = citeFor(b.dataset.goto);
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
  paintNav();
  route();
}));

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    const q = $("#q");
    if (q) { e.preventDefault(); q.focus(); q.select(); }
  }
  if (e.key === "Escape" && location.hash.startsWith("#/r/") && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) location.hash = state.lastListHash;
});

window.addEventListener("hashchange", route);
initAgent();
applyLang();
paintNav();
route();
