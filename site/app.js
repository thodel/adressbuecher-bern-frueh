(function () {
  "use strict";
  const META = window.BERN_META, RAW = window.BERN_ENTRIES || [], LINES = window.BERN_LINES || {};
  const C = Object.fromEntries(META.entry_cols.map((c, i) => [c, i]));
  const VOL = Object.fromEntries(META.volumes.map(v => [v.volume, v]));
  const PAGE = {};
  for (const [vol, page, section, canvas, iiif, printed, status] of META.pages)
    PAGE[vol + "|" + page] = { vol, page, section, canvas, iiif, printed, status };
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const eraraUrl = (vol, page) => { const p = PAGE[vol + "|" + page]; return p ? "https://www.e-rara.ch/bes_1/content/pageview/" + p.canvas : "#"; };

  // Suche: Kleinschreibung, Diakritika weg, optionale Schreibvarianten angleichen
  function fold(s, fuzzy) {
    s = String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    if (fuzzy) s = s.replace(/ß/g, "ss").replace(/th/g, "t").replace(/y/g, "i").replace(/ae/g, "a").replace(/oe/g, "o").replace(/ue/g, "u").replace(/ck/g, "k").replace(/(.)\1/g, "$1");
    return s;
  }
  const SEARCH_FIELDS = ["surname", "forename", "title", "occupation", "address", "street", "place", "origin", "heading", "text", "household", "note"];
  const idx = { 0: [], 1: [] };
  for (const r of RAW) {
    for (const fz of [0, 1]) {
      const o = {};
      for (const f of SEARCH_FIELDS) o[f] = fold(r[C[f]], fz);
      o._all = SEARCH_FIELDS.map(f => o[f]).join(" | ");
      idx[fz].push(o);
    }
  }

  // Bandauswahl
  for (const v of META.volumes) {
    $("vol").insertAdjacentHTML("beforeend", `<option value="${v.volume}">${esc(v.short)}</option>`);
    $("bvol").insertAdjacentHTML("beforeend", `<option value="${v.volume}">${esc(v.short)}</option>`);
  }

  let hits = [], shown = 0;
  function run() {
    const fz = $("fuzzy").checked ? 1 : 0;
    const terms = fold($("q").value, fz).split(/\s+/).filter(Boolean);
    const vol = $("vol").value, field = $("field").value;
    hits = [];
    for (let i = 0; i < RAW.length; i++) {
      if (vol && RAW[i][C.volume] !== vol) continue;
      const hay = field ? idx[fz][i][field] : idx[fz][i]._all;
      if (terms.every(t => hay.includes(t))) hits.push(i);
    }
    shown = 0; $("rows").innerHTML = ""; more();
    $("count").textContent = hits.length.toLocaleString("de-CH") + " von " + RAW.length.toLocaleString("de-CH") + " Einträgen";
    writeHash();
  }
  function hl(s) {
    const raw = $("q").value.trim();
    if (!raw) return esc(s);
    let out = esc(s);
    for (const t of raw.split(/\s+/).filter(x => x.length > 1)) {
      const re = new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
      out = out.replace(re, "<mark>$1</mark>");
    }
    return out;
  }
  function more() {
    const chunk = hits.slice(shown, shown + 200);
    const html = chunk.map(i => {
      const r = RAW[i];
      const addr = r[C.address] || [r[C.quarter], r[C.street], r[C.house_no]].filter(Boolean).join(" ");
      const where = [r[C.place] && r[C.place] !== "Bern" ? r[C.place] : "", r[C.origin] ? "von " + r[C.origin] : ""].filter(Boolean).join("; ");
      return `<tr data-i="${i}"><td class="num">${r[C.volume]}</td><td class="num"><a href="${eraraUrl(r[C.volume], r[C.page])}" target="_blank" rel="noopener" title="Seite auf e-rara">${r[C.page]}</a></td>` +
        `<td>${hl(r[C.surname])}</td><td>${hl(r[C.forename])}</td><td>${hl(r[C.occupation])}</td><td>${hl(addr)}</td><td>${hl(where)}</td><td>${hl(r[C.heading])}</td><td class="wt">${hl(r[C.text])}</td></tr>`;
    }).join("");
    $("rows").insertAdjacentHTML("beforeend", html);
    shown += chunk.length;
    $("more").hidden = shown >= hits.length;
  }
  $("more").onclick = more;
  let timer;
  for (const id of ["q", "vol", "field", "fuzzy"]) $(id).addEventListener(id === "q" ? "input" : "change", () => { clearTimeout(timer); timer = setTimeout(run, 150); });

  const LABEL = { entry_id: "Kennung", volume: "Band", page: "PDF-Seite", printed_page: "gedruckte Seite", section: "Abschnitt", line_from: "Zeile von", line_to: "Zeile bis", kind: "Art", heading: "Rubrik", place: "Ort", surname: "Nachname", forename: "Vorname", title: "Anrede/Titel", occupation: "Beruf / Gewerbe", address: "Adresse", quarter: "Quartier", street: "Gasse", house_no: "Hausnummer", origin: "Herkunft", birth_year: "Geburtsjahr", household: "Haushalt", note: "Vermerk", continues: "Seitenwechsel", text: "Wortlaut" };
  function detail(i) {
    const r = RAW[i];
    let h = "<dl>";
    for (const c of META.entry_cols) if (r[C[c]] !== "" && r[C[c]] != null) h += `<dt>${LABEL[c] || c}</dt><dd>${esc(r[C[c]])}</dd>`;
    h += "</dl>";
    h += `<p><a href="${eraraUrl(r[C.volume], r[C.page])}" target="_blank" rel="noopener">Seite auf e-rara öffnen ↗</a> · <a href="#" data-browse="${r[C.volume]}|${r[C.page]}">hier blättern</a></p>`;
    $("dbody").innerHTML = h;
    $("detail").showModal();
  }
  $("rows").addEventListener("click", e => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr[data-i]");
    if (tr) detail(+tr.dataset.i);
  });
  $("dbody").addEventListener("click", e => {
    const a = e.target.closest("[data-browse]");
    if (!a) return;
    e.preventDefault();
    const [v, p] = a.dataset.browse.split("|");
    $("detail").close();
    show("browse"); $("bvol").value = v; fillPages(); $("bpage").value = p; renderPage();
  });

  // Blättern
  function volPages(v) { return META.pages.filter(p => p[0] === v).map(p => p[1]); }
  function fillPages() {
    const v = $("bvol").value;
    $("bpage").innerHTML = volPages(v).map(p => {
      const pp = PAGE[v + "|" + p];
      return `<option value="${p}">PDF ${p}${pp.printed ? " · S. " + esc(pp.printed) : ""}${pp.status !== "ok" ? " (nicht gelesen)" : ""}</option>`;
    }).join("");
  }
  function renderPage() {
    const v = $("bvol").value, p = +$("bpage").value, pp = PAGE[v + "|" + p];
    if (!pp) return;
    $("bimg").src = pp.iiif + "/full/!1400,2000/0/default.jpg";
    $("bimg").alt = "Seitenbild " + VOL[v].short + ", PDF-Seite " + p;
    $("bcap").innerHTML = `${esc(VOL[v].short)}, PDF-Seite ${p}${pp.printed ? ", gedruckte Seite " + esc(pp.printed) : ""}. Bild: e-rara.ch / UB Bern, ${esc(VOL[v].shelfmark)}.`;
    $("bext").href = eraraUrl(v, p);
    const es = [];
    RAW.forEach((r, i) => { if (r[C.volume] === v && +r[C.page] === p) es.push(i); });
    $("bstat").textContent = es.length + " Einträge auf dieser Seite";
    $("bentries").innerHTML = es.length ? es.map(i => {
      const r = RAW[i];
      const f = ["surname", "forename", "title", "occupation", "address", "place", "origin", "birth_year", "household", "note"].filter(c => r[C[c]]);
      return `<div class="ent"><div class="h">Z. ${r[C.line_from]}${r[C.line_to] !== r[C.line_from] ? "–" + r[C.line_to] : ""} · ${esc(r[C.kind])}${r[C.heading] ? " · " + esc(r[C.heading]) : ""}</div><dl>${f.map(c => `<dt>${LABEL[c]}</dt><dd>${esc(r[C[c]])}</dd>`).join("")}</dl><div class="t">${esc(r[C.text])}</div></div>`;
    }).join("") : "<p class='legend'>Keine Einträge (Seite nicht gelesen oder ohne Einträge).</p>";
    const ls = LINES[v + "|" + p] || [];
    $("blines").innerHTML = ls.map(([n, t]) => `<li value="${n}">${esc(t)}</li>`).join("");
    writeHash();
  }
  $("bvol").onchange = () => { fillPages(); renderPage(); };
  $("bpage").onchange = renderPage;
  $("prev").onclick = () => { const s = $("bpage"); if (s.selectedIndex > 0) { s.selectedIndex--; renderPage(); } };
  $("next").onclick = () => { const s = $("bpage"); if (s.selectedIndex < s.options.length - 1) { s.selectedIndex++; renderPage(); } };

  // Bände
  $("vols").innerHTML = META.volumes.map(v => `<article class="vol"><h2>${esc(v.short)}</h2>
    <p>${esc(v.title)}</p><p>${esc(v.publisher)} · ${esc(v.shelfmark)} · <a href="https://doi.org/${esc(v.doi)}" target="_blank" rel="noopener">doi:${esc(v.doi)}</a></p>
    <p><span class="n">${v.n_entries.toLocaleString("de-CH")}</span> Einträge aus <span class="n">${v.n_ok}</span> von ${v.n_pages} Seiten</p>
    <ul>${v.sections.map(s => `<li>${esc(s.label)}: PDF-Seiten ${s.from}–${s.to}</li>`).join("")}</ul>
    <p class="legend">${esc(v.notes)}</p>
    <p><a href="#" data-goto="${v.volume}">durchblättern</a> · <a href="#" data-search="${v.volume}">durchsuchen</a></p></article>`).join("");
  $("vols").addEventListener("click", e => {
    const a = e.target.closest("[data-goto],[data-search]");
    if (!a) return;
    e.preventDefault();
    if (a.dataset.goto) { show("browse"); $("bvol").value = a.dataset.goto; fillPages(); renderPage(); }
    else { show("search"); $("vol").value = a.dataset.search; run(); }
  });

  // Reiter und Adresszeile
  let current = "search";
  function show(which) {
    current = which;
    for (const w of ["search", "browse", "volumes"]) {
      $("view-" + w).hidden = w !== which;
      $("tab-" + w).setAttribute("aria-selected", String(w === which));
    }
    if (which === "browse" && !$("bpage").options.length) { fillPages(); renderPage(); }
    writeHash();
  }
  for (const w of ["search", "browse", "volumes"]) $("tab-" + w).onclick = () => show(w);
  function writeHash() {
    const p = new URLSearchParams();
    p.set("v", current);
    if (current === "search") { if ($("q").value) p.set("q", $("q").value); if ($("vol").value) p.set("band", $("vol").value); if ($("field").value) p.set("feld", $("field").value); }
    if (current === "browse") { p.set("band", $("bvol").value); p.set("s", $("bpage").value); }
    history.replaceState(null, "", "#" + p.toString());
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    const v = p.get("v") || "search";
    if (v === "browse") { $("bvol").value = p.get("band") || META.volumes[0].volume; fillPages(); if (p.get("s")) $("bpage").value = p.get("s"); show("browse"); renderPage(); }
    else { $("q").value = p.get("q") || ""; $("vol").value = p.get("band") || ""; $("field").value = p.get("feld") || ""; show(v); run(); }
  }
  $("foot").innerHTML = `Stand der Daten: ${esc(META.built)} (MESZ/MEZ). Daten als CSV im Repository (<code>data/csv/</code>). Seitenbilder: e-rara.ch, Universitätsbibliothek Bern.`;
  window.addEventListener("hashchange", readHash);  // replaceState löst das nicht aus, nur echte Links
  readHash();
})();
