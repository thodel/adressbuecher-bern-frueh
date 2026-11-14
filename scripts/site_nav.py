"""site_nav.py — gemeinsame Navigation und Feldsuche aller Adressbuch-Seiten.

Dieselbe Datei liegt in jedem Repo adressbuecher-* (Aarau, Baden, Basel, Bern, Lausanne, Zürich); Änderungen in
allen Repos gleich nachziehen.

- `city_bar(current, lang)`: oberste Leiste mit den Städten (eigene Zeile, aktuelle Stadt hervorgehoben).
- `city_nav(city, links, lang)`: zweite Zeile, nur innerhalb der Stadt: Einträge · Karte · Suche · Repo.
- `CSS`: Stil für beide Leisten und das Suchfeld; in den <style>-Block der Seite.
- `FIELD_SEARCH_JS`: Feldsuche (`FS.init({params})` liest die Bedingungen aus params statt aus location.search) über alle Spalten der CSV («Name enthält Meier», «Hausnummer = 12», «Allianzname
  nicht leer» …), mehrere Bedingungen mit UND, in der URL (`f=Spalte~Operator~Wert`). Die Seite ruft
  `FS.init({...})` auf, prüft je Zeile `FS.test(row, cols)` und schreibt in syncUrl `FS.toParams(params)`.
- `search_panel(lang)`: das HTML des Suchfelds (<details id="suche">).
- `extra_columns(rows, fieldnames, shown)`: weitere CSV-Spalten mit mindestens zwei verschiedenen Werten, damit die
  Feldsuche *alle* Angaben der CSV erreicht; in der Tabelle bleiben sie verborgen (`hide`).
"""
from __future__ import annotations

CITIES = [  # (Schlüssel, Name, URL)
    ("aarau", "Aarau 1884–1899", "https://thodel.github.io/adressbuecher-aarau/"),
    ("baden", "Baden 1900/1910", "https://thodel.github.io/adressbuecher-baden/"),
    ("basel", "Basel 1841–1862", "https://thodel.github.io/adressbuecher-basel/"),
    ("bern-frueh", "Bern 1795–1848", "https://thodel.github.io/adressbuecher-bern-frueh/"),
    ("bern", "Bern 1883–1900", "https://thodel.github.io/adressbuecher-bern/"),
    ("lausanne", "Lausanne 1896–1907", "https://thodel.github.io/adressbuecher-lausanne/"),
    ("zuerich", "Zürich 1859–1914", "https://thodel.github.io/adressbuecher-zuerich/"),
]
VS = "https://thodel.github.io/vernetzte-schweiz/"

T = {
    "de": {"books": "Adressbücher", "entries": "Einträge", "map": "Karte", "search": "Suche nach Feldern",
           "repo": "Daten und Code", "add": "+ Bedingung", "clear": "alle Bedingungen löschen",
           "any": "beliebiges Feld", "hint": "Alle Bedingungen müssen zutreffen. Gross-/Kleinschreibung und Akzente zählen nicht.",
           "ops": {"has": "enthält", "eq": "ist genau", "start": "beginnt mit", "not": "enthält nicht",
                   "empty": "ist leer", "full": "ist nicht leer", "ge": "≥", "le": "≤"},
           "remove": "Bedingung entfernen", "value": "Wert", "field": "Feld", "op": "Vergleich", "nav": "Städte"},
    "fr": {"books": "Annuaires", "entries": "Entrées", "map": "Carte", "search": "Recherche par champ",
           "repo": "Données et code", "add": "+ condition", "clear": "effacer les conditions",
           "any": "n’importe quel champ", "hint": "Toutes les conditions doivent être remplies. Majuscules et accents ne comptent pas.",
           "ops": {"has": "contient", "eq": "est exactement", "start": "commence par", "not": "ne contient pas",
                   "empty": "est vide", "full": "n’est pas vide", "ge": "≥", "le": "≤"},
           "remove": "supprimer la condition", "value": "valeur", "field": "champ", "op": "comparaison", "nav": "Villes"},
}

# Bezeichnungen der CSV-Spalten, die nicht schon auf der Seite benannt sind
LABELS = {
    "de": {"section": "Teil", "line_from": "Zeile", "line_to": "Zeile bis", "entry_type": "Typ", "citizen_flag": "Bürger",
           "dash_prefix": "Strich (Name wie oben)", "surname_inherited": "Name geerbt", "maiden_name": "Ledigname",
           "relation": "Beziehung", "origin_raw": "Herkunft", "origin_canton": "Herkunftskanton",
           "address_seq": "Adresse Nr.", "address_role": "Adressart", "heading": "Rubrik", "parse_method": "Lesung",
           "residual": "Rest", "municipality": "Gemeinde", "district": "Gebiet", "civil_status": "Stand",
           "title": "Titel", "maiden": "Ledigname"},
    "fr": {"section": "partie", "line_from": "ligne", "line_to": "ligne fin", "entry_type": "type", "citizen_flag": "bourgeois",
           "dash_prefix": "tiret (nom ci-dessus)", "surname_inherited": "nom hérité", "maiden_name": "nom de jeune fille",
           "relation": "relation", "origin_raw": "origine", "origin_canton": "canton d’origine",
           "address_seq": "adresse n°", "address_role": "type d’adresse", "heading": "rubrique", "parse_method": "lecture",
           "residual": "reste", "municipality": "commune", "district": "quartier", "civil_status": "état civil",
           "title": "titre"},
}


def city_bar(current: str, lang: str = "de") -> str:
    t = T[lang]
    items = "".join(f'<a href="{url}"{" aria-current=\"page\"" if key == current else ""}>{name}</a>'
                    for key, name, url in CITIES)
    return (f'<nav class="cities" aria-label="{t["nav"]}"><span class="cities-label">{t["books"]}</span>{items}'
            f'<a class="vs" href="{VS}">Vernetzte Schweiz ↗</a></nav>')


def city_nav(city: str, repo: str, page: str, lang: str = "de", map_href: str = "karte.html", map_label: str | None = None,
             extra: list[tuple[str, str, str]] | None = None) -> str:
    """page = «entries», «map» oder ein Schlüssel aus extra; ausserhalb der Einträge führt «Suche» auf die
    Einträge-Seite. extra = weitere Seiten der Stadt als (Schlüssel, href, Label), vor «Daten und Code»."""
    t = T[lang]
    search = "#suche" if page == "entries" else "./#suche"
    cur = lambda p: ' aria-current="page"' if p == page else ""
    more = "".join(f'<a href="{href}"{cur(k)}>{lab}</a>' for k, href, lab in (extra or []))
    return (f'<nav class="citynav" aria-label="{city}"><b>{city}</b>'
            f'<a href="./"{cur("entries")}>{t["entries"]}</a>'
            f'<a href="{map_href}"{cur("map")}>{map_label or t["map"]}</a>'
            f'<a href="{search}" data-open-search>{t["search"]}</a>{more}'
            f'<a href="{repo}">{t["repo"]} ↗</a></nav>')


CSS = r"""
nav.cities { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 2px; margin: -16px calc(-1 * max(16px, env(safe-area-inset-left, 0px))) 0;
  padding: 6px max(16px, env(safe-area-inset-left, 0px)); background: var(--fg); color: var(--bg); font-size: 0.85rem; }
nav.cities a { color: var(--bg); text-decoration: none; padding: 2px 8px; border-radius: 999px; opacity: 0.85; }
nav.cities a:hover, nav.cities a:focus-visible { opacity: 1; text-decoration: underline; }
nav.cities a[aria-current="page"] { background: var(--bg); color: var(--fg); opacity: 1; font-weight: 700; }
nav.cities .cities-label { font-weight: 700; margin-right: 6px; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.72rem; }
nav.cities .vs { margin-left: auto; }
nav.citynav { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; font-size: 0.92rem; }
nav.citynav b { font-size: 1rem; }
nav.citynav a { color: var(--accent); font-weight: 600; text-decoration: none; }
nav.citynav a:hover, nav.citynav a:focus-visible { text-decoration: underline; }
nav.citynav a[aria-current="page"] { color: var(--fg); border-bottom: 2px solid var(--accent); }
details#suche { border: 1px solid var(--line); border-radius: 8px; background: var(--paper); padding: 6px 12px; }
details#suche > summary { cursor: pointer; font-weight: 600; color: var(--accent); }
details#suche > summary .n { color: var(--muted); font-weight: 400; }
.fs-rows { display: flex; flex-direction: column; gap: 6px; margin: 8px 0 6px; }
.fs-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.fs-row select, .fs-row input { font: inherit; padding: 4px 8px; border: 1px solid var(--line); border-radius: 6px; background: var(--paper); color: var(--fg); min-width: 0; max-width: 100%; }
.fs-row input { flex: 1 1 160px; }
.fs-row button, .fs-bar button { font: inherit; border: 1px solid var(--line); background: var(--paper); color: var(--fg); border-radius: 6px; padding: 3px 9px; cursor: pointer; }
.fs-bar { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; font-size: 0.85rem; color: var(--muted); }
@media (max-width: 600px) { nav.cities .vs { margin-left: 0; } .fs-row select { flex: 1 1 40%; } }
"""


def search_panel(lang: str = "de") -> str:
    t = T[lang]
    return (f'<details id="suche"><summary>{t["search"]} <span class="n" id="fs-n"></span></summary>'
            f'<div class="fs-rows" id="fs-rows"></div>'
            f'<div class="fs-bar"><button type="button" id="fs-add">{t["add"]}</button>'
            f'<button type="button" id="fs-clear">{t["clear"]}</button><span>{t["hint"]}</span></div></details>')


def fs_texts(lang: str = "de") -> dict:
    return {**T[lang], "labels": LABELS[lang]}


FIELD_SEARCH_JS = r"""
const FS = (() => {
  let conds = [], opts = {};
  const fold = s => String(s ?? '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const num = s => { const m = String(s ?? '').match(/-?\d+(?:[.,]\d+)?/); return m ? parseFloat(m[0].replace(',', '.')) : NaN; };
  function label(c) { return (opts.labels && opts.labels[c]) || (opts.tx.labels && opts.tx.labels[c]) || c; }
  function fields() { return (opts.cols() || []).filter(c => !(opts.skip || []).includes(c)); }
  function ok(v, op, w) {
    const a = fold(v), b = fold(w);
    switch (op) {
      case 'has': return !b || a.includes(b);
      case 'not': return !b || !a.includes(b);
      case 'eq': return a === b;
      case 'start': return a.startsWith(b);
      case 'empty': return !a;
      case 'full': return !!a;
      case 'ge': return !isNaN(num(v)) && num(v) >= num(w);
      case 'le': return !isNaN(num(v)) && num(v) <= num(w);
    }
    return true;
  }
  function test(row, cols) {
    for (const c of conds) {
      if (!['empty', 'full'].includes(c.op) && c.v === '') continue;
      if (c.f === '*') { if (!row.some(x => ok(x, c.op, c.v)) && c.op !== 'not') return false; if (c.op === 'not' && row.some(x => !ok(x, 'not', c.v))) return false; continue; }
      const i = cols.indexOf(c.f);
      if (i < 0) { if (['empty', 'not'].includes(c.op)) continue; return false; }
      if (!ok(row[i], c.op, c.v)) return false;
    }
    return true;
  }
  function active() { return conds.filter(c => ['empty', 'full'].includes(c.op) || c.v !== ''); }
  function draw() {
    const box = document.getElementById('fs-rows'), fs = fields(), t = opts.tx;
    box.innerHTML = conds.map((c, k) => `<div class="fs-row">
      <select data-k="${k}" data-p="f" aria-label="${esc(t.field)}"><option value="*">${esc(t.any)}</option>${fs.map(f => `<option value="${esc(f)}" ${f === c.f ? 'selected' : ''}>${esc(label(f))}</option>`).join('')}</select>
      <select data-k="${k}" data-p="op" aria-label="${esc(t.op)}">${Object.entries(t.ops).map(([o, l]) => `<option value="${o}" ${o === c.op ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
      <input type="search" data-k="${k}" data-p="v" value="${esc(c.v)}" placeholder="${esc(t.value)}" aria-label="${esc(t.value)}" ${['empty', 'full'].includes(c.op) ? 'hidden' : ''}>
      <button type="button" data-k="${k}" data-del aria-label="${esc(t.remove)}">✕</button></div>`).join('');
    const n = active().length;
    document.getElementById('fs-n').textContent = n ? `(${n})` : '';
  }
  function changed(redraw) { if (redraw) draw(); else document.getElementById('fs-n').textContent = active().length ? `(${active().length})` : ''; opts.onChange(); }
  function init(o) {
    opts = o;
    const P = o.params || new URLSearchParams(location.search);  // Seiten mit Zustand im #-Teil geben ihn mit
    conds = P.getAll('f').map(s => { const [f, op, ...v] = s.split('~'); return { f: f || '*', op: op || 'has', v: v.join('~') }; });
    if (!conds.length) conds = [{ f: o.first || '*', op: 'has', v: '' }];
    const box = document.getElementById('fs-rows'), det = document.getElementById('suche');
    if (P.getAll('f').length || location.hash === '#suche') det.open = true;
    box.addEventListener('input', e => { const el = e.target, k = +el.dataset.k; if (el.dataset.p === 'v') { conds[k].v = el.value; changed(false); } });
    box.addEventListener('change', e => { const el = e.target, k = +el.dataset.k; if (el.dataset.p && el.dataset.p !== 'v') { conds[k][el.dataset.p] = el.value; changed(true); } });
    box.addEventListener('click', e => { const b = e.target.closest('[data-del]'); if (!b) return; conds.splice(+b.dataset.k, 1); if (!conds.length) conds.push({ f: '*', op: 'has', v: '' }); changed(true); });
    document.getElementById('fs-add').onclick = () => { conds.push({ f: o.first || '*', op: 'has', v: '' }); draw(); box.lastElementChild.querySelector('input').focus(); };
    document.getElementById('fs-clear').onclick = () => { conds = [{ f: o.first || '*', op: 'has', v: '' }]; changed(true); };
    for (const a of document.querySelectorAll('[data-open-search]')) a.addEventListener('click', ev => { if (a.getAttribute('href') === '#suche') { ev.preventDefault(); det.open = true; det.scrollIntoView({ block: 'nearest' }); const i = box.querySelector('input:not([hidden])'); if (i) i.focus(); } });
    draw();
  }
  function toParams(p) { for (const c of active()) p.append('f', `${c.f}~${c.op}~${c.v}`); }
  function refresh() { draw(); }
  return { init, test, toParams, refresh, active };
})();
"""


def extra_columns(rows: list[dict], fieldnames: list[str], shown: list[str]) -> list[str]:
    """CSV-Spalten, die nicht schon gezeigt werden und mindestens zwei verschiedene Werte haben."""
    out = []
    for f in fieldnames:
        if f in shown:
            continue
        vals = set()
        for r in rows:
            vals.add(r.get(f, ""))
            if len(vals) > 1:
                out.append(f)
                break
    return out
