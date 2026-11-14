/* aus scripts/site_nav.py erzeugt */
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
window.FSTX = {"books": "Adressbücher", "entries": "Einträge", "map": "Karte", "search": "Suche nach Feldern", "repo": "Daten und Code", "add": "+ Bedingung", "clear": "alle Bedingungen löschen", "any": "beliebiges Feld", "hint": "Alle Bedingungen müssen zutreffen. Gross-/Kleinschreibung und Akzente zählen nicht.", "ops": {"has": "enthält", "eq": "ist genau", "start": "beginnt mit", "not": "enthält nicht", "empty": "ist leer", "full": "ist nicht leer", "ge": "≥", "le": "≤"}, "remove": "Bedingung entfernen", "value": "Wert", "field": "Feld", "op": "Vergleich", "nav": "Städte", "labels": {"section": "Teil", "line_from": "Zeile", "line_to": "Zeile bis", "entry_type": "Typ", "citizen_flag": "Bürger", "dash_prefix": "Strich (Name wie oben)", "surname_inherited": "Name geerbt", "maiden_name": "Ledigname", "relation": "Beziehung", "origin_raw": "Herkunft", "origin_canton": "Herkunftskanton", "address_seq": "Adresse Nr.", "address_role": "Adressart", "heading": "Rubrik", "parse_method": "Lesung", "residual": "Rest", "municipality": "Gemeinde", "district": "Gebiet", "civil_status": "Stand", "title": "Titel", "maiden": "Ledigname"}};
