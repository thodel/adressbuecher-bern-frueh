"""site_search.py — Startseite mit Suche über alle Bände, Eintragsseite und Suchindex (gleiche Datei in allen adressbuecher-*).

Die Stadt-Skripte (`89_suche.py`) bringen ihre Einträge in eine gemeinsame Form und rufen `build()` auf:

    site_search.build(Path("_site"), city=CITY, records=records, labels=LABELS)

Geschrieben wird nach `out/`:

- `index.html`   Suche über alle Bände: freie Suche und Felder (Name, Vorname, Beruf, Strasse), offene Facetten
                 (Band, Teil, Gebiet, Strasse, Beruf) mit Zahlen, Zeitstrahl mit zwei Reglern, Treffer als Liste und
                 als Karte (je Strasse ein Kreis). Alter Zustand im URL (`?tab=`, `?vol=`, `?f=`, `?col=`, `#…`) → `korrektur/`.
- `eintrag.html` ein Eintrag (`?id=<entry_id>`): Felder, gelesene Zeile, Seitenbild, Karte, Telefonbuch,
                 Normdaten, dieselbe Person in anderen Bänden, Link in den Korrekturmodus.
- `s/`           der Index, als .gz (Pages liefert .gz unverändert aus, der Browser entpackt mit DecompressionStream):
    - `meta.json`         Stadt, Bände, Teile, Gebiete, Strassen mit Koordinaten, Zahlen je Jahr
    - `occ.json.gz`       Berufe (häufigste Schreibung je Schlüssel; nur Berufe, die mindestens zweimal vorkommen)
    - `c.bin.gz`          je Eintrag Strasse, Beruf, Gebiet (Uint16), Band, Teil (Uint8) — für Facetten und Karte
    - `t/<xy>.json.gz`    Wortindex: «<Feld><Wort>» → Eintragsnummern (Differenzen), Teil = die ersten zwei Buchstaben
    - `r/<n>.json.gz`     Einträge in Blöcken zu BLOCK, nach Name, Vorname, Jahr geordnet
    - `i/<xx>.json.gz`    entry_id → Eintragsnummer (FNV-1a, 64 Teile)

Ein Eintrag (dict) hat mindestens `id`, `vol`, `year`, `part`; dazu nach Bedarf `name`, `forename`, `alliance`,
`occupation`, `street`, `no`, `area`, `origin`, `title`, `text` (gelesene Zeile), `page`, `page_url`, `lat`/`lon`
(Strasse), `point` ([lat, lon] des Hauses, für die Karte der Eintragsseite), `place` (Ort für die Karte, wenn keine Strasse da ist, z. B. die Gemeinde), `fields` (weitere Spalten als [[Spalte, Wert], …], beschriftet über `labels`), `links`
([[Art, Text, URL, Notiz], …]; Art tel, vs, wd, hls, mg, img, ext), `related` ([[Band, Stufe, entry_id], …]).
Helfer für die gemeinsamen Zellformate der Seiten (Telefon, Normdaten, andere Bände): `std_links()`.
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import unicodedata
from array import array
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import site_nav

BLOCK = 400  # Einträge je Datei in s/r/
VS = site_nav.VS
FIELDS = {  # Feldkennung im Wortindex → Schlüssel im Eintrag
    "n": ("name", "alliance", "maiden"),
    "v": ("forename",),
    "b": ("occupation",),
    "s": ("street",),
    "o": ("origin", "area"),
    "t": ("title", "heading"),
}
STOP = {"de", "la", "le", "du", "des", "und", "u", "et", "in", "im", "am", "an", "der", "die", "das", "von", "v", "zum",
        "zur", "bei", "geb", "wwe", "sel", "frau", "hr", "herr", "mme", "mlle", "veuve", "vve"}


def fold(s: str) -> str:
    """Klein, ohne Akzente, ß → ss (wie fold() in suche.js)."""
    s = (s or "").replace("ß", "ss").replace("æ", "ae").replace("œ", "oe").replace("Æ", "ae").replace("Œ", "oe")
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def words(s: str) -> list[str]:
    """Wörter für den Index: mindestens zwei Zeichen, nicht nur Ziffern, ohne Füllwörter."""
    return [w for w in re.findall(r"[a-z0-9]+", fold(s)) if len(w) > 1 and not w.isdigit() and w not in STOP]


def fnv(s: str, mask: int = 0x3F) -> str:
    """FNV-1a 32 über UTF-8 (wie fnv() in suche.js)."""
    h = 0x811C9DC5
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h & mask:02x}"


def occ_key(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", fold(s)))


def std_links(r: dict, vs_entity: bool = True) -> tuple[list, list]:
    """Die gemeinsamen Zellformate der Kontrollseiten → (links, related).

    telefon      «how|Jahr|Name|Strasse|Nummer|entity_id|Bild» (80_telefon.py)
    authority    «QID|HLS|Label|Lebensdaten|Metagrid-JSON» (Aarau, Basel) oder «Stufe|QID|Label|…» erkennt die Stadt selbst
    other_volume «Band|Stufe|entry_id|Text|Belege» durch «;;» getrennt (81_baende.py)
    """
    links, related = [], []
    tel = r.get("telefon", "")
    if tel:
        how, year, name, st, phone, eid, img = (tel.split("|") + [""] * 7)[:7]
        note = ", ".join(x for x in (name, st, f"Nr. {phone}" if phone else "") if x)
        if eid and vs_entity:
            links.append(["tel", f"Telefonbuch {year}", f"{VS}#/e/{eid}", f"{note} · Zuordnung: {how}"])
        else:
            links.append(["tel", f"Telefonbuch {year}", "", f"{note} · Zuordnung: {how}"])
        if img:
            links.append(["img", f"Seite im Telefonbuch {year}", img, "PTT-Archiv"])
    auth = r.get("authority", "")
    if auth and auth.split("|")[0].startswith("Q"):
        parts = auth.split("|")
        qid, hls, label, life = (parts + [""] * 4)[:4]
        mg = "|".join(parts[4:])
        links.append(["wd", label or qid, f"https://www.wikidata.org/wiki/{qid}", f"{life} · Wikidata (ungeprüft)"])
        if hls:
            links.append(["hls", f"HLS {hls}", f"https://hls-dhs-dss.ch/de/articles/{hls}/", "Historisches Lexikon der Schweiz"])
        try:
            extra = json.loads(mg) if mg else {}
        except json.JSONDecodeError:
            extra = {}
        for k, u in list(extra.items())[:8]:
            if not re.match(r"^(HLS|Wikidata|DHS|DSS)$", k, re.I):
                links.append(["mg", k, u, "über Metagrid"])
    for x in filter(None, (r.get("other_volume") or "").split(";;")):
        ov, tier, oid = (x.split("|") + [""] * 3)[:3]
        if oid:
            related.append([ov, tier, oid.split("#")[0]])
    return links, related


def _gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    path.write_bytes(gzip.compress(data, 9, mtime=0))


def build(out: Path, *, city: dict, records: list[dict], labels: dict[str, str] | None = None, block: int = BLOCK) -> None:
    """city: key (wie in site_nav.CITIES), name («Aarau»), span («1833–1913»), title, lead, repo, lang («de»/«fr»),
    center [lat, lon], korr (Vorlage mit {id} {vol} {part}, relativ zur Startseite), nav (weitere Seiten als
    [[href, Label], …], z. B. Karte), parts {Schlüssel: Label}, volumes {Schlüssel: Titel}, note (Hinweis zur Lesung),
    page_note (woher die Seitenbilder kommen), ui (eigene Wörter der Oberfläche, z. B. {"area": "Commune", "area_l": "Commune"}). block = Einträge je Datei in s/r/ (grosse Städte mehr: der Pages-Deploy
    bricht bei rund 3 500 Dateien ab)."""
    out = Path(out)
    s = out / "s"
    if s.exists():
        shutil.rmtree(s)
    recs = [r for r in records if r.get("id")]
    seen = set()
    recs = [r for r in recs if not (r["id"] in seen or seen.add(r["id"]))]
    recs.sort(key=lambda r: (re.sub(r"^[^a-z]+", "", fold(r.get("name", ""))) or "~", fold(r.get("forename", "")), r["year"], r["id"]))
    n = len(recs)

    vols = sorted({(r["year"], r["vol"]) for r in recs})
    vol_ix = {v: i for i, (_, v) in enumerate(vols)}
    vol_n = Counter(r["vol"] for r in recs)
    part_keys = list(dict.fromkeys([*city.get("parts", {}), *sorted({r["part"] for r in recs})]))
    part_n = Counter(r["part"] for r in recs)
    part_keys = [p for p in part_keys if part_n[p]]
    part_ix = {p: i for i, p in enumerate(part_keys)}
    area_n = Counter(r.get("area", "") for r in recs if r.get("area"))
    areas = [a for a, _ in area_n.most_common(65535)]
    area_ix = {a: i + 1 for i, a in enumerate(areas)}

    # Strassen: Schlüssel = gefaltete Schreibung; Anzeige = häufigste Schreibung; Koordinaten aus den Einträgen
    st_cnt, st_lab, st_geo = Counter(), defaultdict(Counter), {}
    loc = lambda r: r.get("street") or r.get("place") or ""  # noqa: E731
    for r in recs:
        if loc(r):
            k = occ_key(loc(r))
            if not k:
                continue
            st_cnt[k] += 1
            st_lab[k][loc(r).strip()] += 1
            if r.get("lat") and k not in st_geo:
                st_geo[k] = (round(float(r["lat"]), 5), round(float(r["lon"]), 5))
    st_keys = [k for k, _ in st_cnt.most_common(65535)]
    st_ix = {k: i + 1 for i, k in enumerate(st_keys)}
    streets = [[st_lab[k].most_common(1)[0][0], *(st_geo.get(k) or (None, None))] for k in st_keys]

    oc_cnt, oc_lab = Counter(), defaultdict(Counter)
    for r in recs:
        k = occ_key(r.get("occupation", ""))
        if k:
            oc_cnt[k] += 1
            oc_lab[k][r["occupation"].strip(" .,;")] += 1
    oc_keys = [k for k, c in oc_cnt.most_common(65535) if c > 1]
    oc_ix = {k: i + 1 for i, k in enumerate(oc_keys)}

    # Spalten (binär): Strasse u16, Beruf u16, Gebiet u16, Band u8, Teil u8
    cs, cb, ca, cv, cp = array("H"), array("H"), array("H"), array("B"), array("B")
    post = defaultdict(list)
    for i, r in enumerate(recs):
        cs.append(st_ix.get(occ_key(loc(r)), 0))
        cb.append(oc_ix.get(occ_key(r.get("occupation", "")), 0))
        cv.append(vol_ix[r["vol"]])
        cp.append(part_ix[r["part"]])
        ca.append(area_ix.get(r.get("area", ""), 0))
        for f, keys in FIELDS.items():
            ws = set()
            for k in keys:
                ws.update(words(r.get(k, "")))
            for w in ws:
                post[f + w].append(i)
    for a in (cs, cb, ca):
        if a.itemsize != 2:
            raise RuntimeError("array('H') ist nicht 16 Bit")
    blob = cs.tobytes() + cb.tobytes() + ca.tobytes() + cv.tobytes() + cp.tobytes()  # little endian auf x86/arm
    _gz(s / "c.bin.gz", blob)

    shards = defaultdict(dict)
    for key, ids in post.items():
        d, prev = [], 0
        for x in ids:
            d.append(x - prev)
            prev = x
        shards[key[1:3]][key] = d
    for sh, obj in shards.items():
        _gz(s / "t" / f"{sh}.json.gz", obj)

    ids = defaultdict(dict)
    for b in range(0, n, block):
        rows = []
        for i in range(b, min(n, b + block)):
            r = recs[i]
            rows.append([r["id"], vol_ix[r["vol"]], part_ix[r["part"]], r.get("name", ""), r.get("forename", ""),
                         r.get("alliance", ""), r.get("occupation", ""), r.get("street", ""), r.get("no", ""),
                         r.get("area", ""), r.get("page", ""), r.get("text", ""), r.get("page_url", ""),
                         [[k, v] for k, v in r.get("fields", []) if v not in ("", None)], r.get("links", []),
                         r.get("related", []), cs[i], r.get("title", ""), r.get("origin", ""),
                         [round(float(x), 6) for x in r["point"]] if r.get("point") else None])
            ids[fnv(r["id"])][r["id"]] = i
        _gz(s / "r" / f"{b // block}.json.gz", rows)
    for sh, obj in ids.items():
        _gz(s / "i" / f"{sh}.json.gz", obj)
    _gz(s / "occ.json.gz", [oc_lab[k].most_common(1)[0][0] for k in oc_keys])

    years = Counter(r["year"] for r in recs)
    meta = {
        "city": {k: city.get(k) for k in ("key", "name", "span", "title", "lead", "repo", "lang", "center", "korr", "note",
                                          "page_note", "nav", "ui")},
        "n": n, "block": block,
        "volumes": [{"k": v, "year": y, "label": city.get("volumes", {}).get(v, str(v)), "n": vol_n[v]} for y, v in vols],
        "parts": [{"k": p, "label": city.get("parts", {}).get(p, p), "n": part_n[p]} for p in part_keys],
        "areas": areas, "streets": streets, "n_occ": len(oc_keys),
        "years": sorted([y, c] for y, c in years.items()),
        "labels": labels or {},
        "built": datetime.now(ZoneInfo("Europe/Zurich")).strftime("%d.%m.%Y"),
    }
    (s / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "assets" / "suche.css").write_text(CSS, encoding="utf-8")
    (out / "assets" / "suche.js").write_text(JS, encoding="utf-8")
    for name, page in (("index.html", "suche"), ("eintrag.html", "eintrag")):
        (out / name).write_text(page_html(city, page), encoding="utf-8")
    fonts = Path(__file__).resolve().parent.parent / "fonts"
    if fonts.is_dir():
        (out / "fonts").mkdir(exist_ok=True)
        for f in fonts.iterdir():
            if f.is_file():
                shutil.copy2(f, out / "fonts" / f.name)
    nfiles = sum(1 for _ in s.rglob("*"))
    size = sum(p.stat().st_size for p in s.rglob("*") if p.is_file())
    print(f"Suche: {n} Einträge, {len(vols)} Bände, {len(st_keys)} Strassen ({len(st_geo)} verortet), "
          f"{len(oc_keys)} Berufe, {len(shards)} Wortteile → {out}/s ({nfiles} Dateien, {size / 1e6:.1f} MB)")


T = {
    "de": {"books": "Adressbücher", "search": "Suche", "korr": "Korrektur", "repo": "Daten und Code", "entry": "Eintrag"},
    "fr": {"books": "Annuaires", "search": "Recherche", "korr": "Correction", "repo": "Données et code", "entry": "Entrée"},
}


def page_html(city: dict, page: str) -> str:
    lang = city.get("lang", "de")
    t = T[lang]
    cities = "".join(f'<a href="{url}"{" aria-current=\"page\"" if key == city["key"] else ""}>{name}</a>'
                     for key, name, url in site_nav.CITIES)
    nav = [("./", t["search"], page == "suche")]
    nav += [(href, label, False) for href, label in city.get("nav", [])]
    nav += [("korrektur/", t["korr"], False)]
    band = "".join(f'<a href="{h}"{" aria-current=\"page\"" if cur else ""}>{lab}</a>' for h, lab, cur in nav)
    band += f'<a href="{city["repo"]}">{t["repo"]} ↗</a><a class="vs" href="{VS}">Vernetzte Schweiz ↗</a>'
    title = city["title"] if page == "suche" else f'{t["entry"]} · {city["title"]}'
    redirect = ("<script>(function(){var p=new URLSearchParams(location.search);"
                "if(p.has('tab')||p.has('vol')||p.has('f')||p.has('flag')||p.has('col')||location.hash.length>1)"
                "location.replace('korrektur/'+location.search+location.hash);})();</script>") if page == "suche" else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{city.get('lead', '')}">
{redirect}
<link rel="stylesheet" href="assets/suche.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
</head>
<body data-page="{page}">
<nav class="cities" aria-label="{t['books']}"><div class="wrap"><span>{t['books']}</span>{cities}</div></nav>
<header class="top">
  <div class="wrap row">
    <a class="brand" href="./">{city['name']} <span class="accent">{city['span']}</span></a>
    <span class="tagline">{city.get('tagline', t['books'])}</span>
  </div>
  <div class="band"><nav class="wrap">{band}</nav></div>
</header>
<main class="wrap" id="app"><p class="muted">…</p></main>
<footer class="foot"><div class="wrap" id="foot"></div></footer>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="assets/suche.js"></script>
</body>
</html>
"""


CSS = r"""/* Gestaltung nach Vernetzte Schweiz (thodel/vernetzte-schweiz, site/assets/style.css): infoclio-Palette,
   Barlow für Titel und Menü, Serife für Lesetext. Aus scripts/site_search.py erzeugt. */
@font-face { font-family: "Barlow Condensed"; font-weight: 600; font-display: swap; src: url("../fonts/barlow-condensed-600-latin.woff2") format("woff2"); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2212; }
@font-face { font-family: "Barlow Condensed"; font-weight: 600; font-display: swap; src: url("../fonts/barlow-condensed-600-latin-ext.woff2") format("woff2"); unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+20A0-20AB, U+20AD-20C0, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: "Barlow Semi Condensed"; font-weight: 400; font-display: swap; src: url("../fonts/barlow-semicondensed-400-latin.woff2") format("woff2"); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2212; }
@font-face { font-family: "Barlow Semi Condensed"; font-weight: 400; font-display: swap; src: url("../fonts/barlow-semicondensed-400-latin-ext.woff2") format("woff2"); unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+20A0-20AB, U+20AD-20C0, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: "Barlow Semi Condensed"; font-weight: 600; font-display: swap; src: url("../fonts/barlow-semicondensed-600-latin.woff2") format("woff2"); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2212; }
@font-face { font-family: "Barlow Semi Condensed"; font-weight: 600; font-display: swap; src: url("../fonts/barlow-semicondensed-600-latin-ext.woff2") format("woff2"); unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+20A0-20AB, U+20AD-20C0, U+2C60-2C7F, U+A720-A7FF; }

:root {
  --bg: #f0f0f0; --panel: #ffffff; --ink: #212529; --heading: #000000;
  --accent: #d21938; --accent-dk: #a81429; --link: #2f6ea5; --muted: #4a4a4a; --border: #c7c7c3; --nav-grey: #b0b0b0;
  --cat-source: #d7b95a; --cat-source-pale: #ebdbad; --cat-source-dk: #7a4e14;
  --cat-ann: #64c8c8; --cat-ann-pale: #d6eeee; --cat-ann-dk: #175b5b;
  --cat-pers: #dc878c; --cat-pers-pale: #eec3c5; --cat-pers-dk: #9e323c;
  --font-head: "Barlow Condensed", "Arial Narrow", Helvetica, sans-serif;
  --font-nav: "Barlow Semi Condensed", "Helvetica Neue", Helvetica, sans-serif;
  --font-serif: "Iowan Old Style", "Palatino", Georgia, serif;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  color-scheme: light;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 var(--font-ui); }
a { color: var(--link); }
a:hover { color: var(--accent-dk); }
.wrap { max-width: 1240px; margin: 0 auto; padding: 0 16px; }
.muted { color: var(--muted); }
[hidden] { display: none !important; }

nav.cities { background: #212529; font: .82rem/1.3 var(--font-nav); }
nav.cities .wrap { display: flex; flex-wrap: wrap; gap: 2px 4px; align-items: center; padding-top: 5px; padding-bottom: 5px; }
nav.cities span { color: #bbb; text-transform: uppercase; letter-spacing: .08em; font-size: .7rem; margin-right: 6px; }
nav.cities a { color: #eee; text-decoration: none; padding: 2px 8px; }
nav.cities a:hover { color: #fff; text-decoration: underline; }
nav.cities a[aria-current="page"] { background: var(--accent); color: #fff; }

.top { background: var(--panel); }
.top .row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; padding-top: 14px; padding-bottom: 10px; }
.brand { font: 600 1.9rem/1 var(--font-head); color: var(--heading); text-decoration: none; }
.brand .accent { color: var(--accent); }
.tagline { font-family: var(--font-nav); color: var(--muted); font-size: .95rem; }
.band { background: var(--nav-grey); }
.band nav { display: flex; flex-wrap: wrap; }
.band a { font-family: var(--font-nav); font-size: 1.02rem; color: #000; text-decoration: none; padding: 9px 16px; }
.band a:first-child { margin-left: -16px; }
.band a:hover { color: var(--accent-dk); background: rgba(255,255,255,.45); }
.band a[aria-current="page"] { background: var(--bg); }
.band a.vs { margin-left: auto; }

h1, h2, h3 { font-family: var(--font-head); font-weight: 600; color: var(--heading); line-height: 1.1; letter-spacing: .01em; }
h1 { font-size: clamp(2rem, 5vw, 3rem); margin: 0 0 10px; }
h2 { font-size: 1.6rem; margin: 0 0 8px; }
h3 { font-size: 1.2rem; margin: 0 0 6px; }
.hero { padding: 30px 0 8px; }
.kicker { font: 600 .8rem/1.4 var(--font-nav); text-transform: uppercase; letter-spacing: .08em; color: var(--accent-dk); margin: 0 0 6px; }
.lead { font-family: var(--font-serif); font-size: 1.12rem; max-width: 48em; margin: 0 0 18px; }
.note { font-family: var(--font-serif); color: var(--muted); max-width: 60em; font-size: .95rem; }

form.searchbar { display: flex; gap: 0; max-width: 760px; }
form.searchbar input { flex: 1 1 auto; min-width: 0; font: 1.05rem var(--font-ui); padding: 11px 14px; border: 1px solid var(--border); border-right: 0; background: var(--panel); }
form.searchbar button, .btn { font: 600 1rem var(--font-nav); background: var(--accent); color: #fff; border: 0; padding: 0 22px; cursor: pointer; }
form.searchbar button:hover, .btn:hover { background: var(--accent-dk); }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; max-width: 760px; margin-top: 8px; }
.fields label { display: flex; flex-direction: column; font: .8rem var(--font-nav); color: var(--muted); }
.fields input { font: .95rem var(--font-ui); padding: 7px 10px; border: 1px solid var(--border); background: var(--panel); }
details.more > summary { cursor: pointer; font: 600 .95rem var(--font-nav); color: var(--link); margin-top: 10px; }
.hint { font-size: .85rem; color: var(--muted); margin: 6px 0 0; max-width: 760px; }

.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0 0; }
.kpis div { background: var(--panel); border: 1px solid var(--border); border-top: 4px solid var(--cat-source); padding: 8px 12px; }
.kpis dt { font: .8rem var(--font-nav); color: var(--muted); }
.kpis dd { margin: 0; font: 600 1.6rem/1.1 var(--font-head); }

.timeline { background: var(--panel); border: 1px solid var(--border); padding: 10px 14px 6px; margin: 18px 0 0; }
.timeline .head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; font: .9rem var(--font-nav); }
.timeline .head b { font: 600 1.1rem var(--font-head); }
.bars { display: flex; align-items: flex-end; gap: 1px; height: 70px; margin-top: 6px; }
.bars span { flex: 1 1 0; background: var(--cat-source); min-height: 1px; position: relative; cursor: pointer; }
.bars span.off { background: #dedbd2; }
.bars span.zero { background: transparent; }
.bars span:hover { background: var(--accent); }
.ticks { display: flex; justify-content: space-between; font: .75rem var(--font-nav); color: var(--muted); }
.range { position: relative; height: 26px; }
.range input { position: absolute; left: 0; right: 0; width: 100%; top: 4px; pointer-events: none; -webkit-appearance: none; appearance: none; background: none; margin: 0; }
.range input::-webkit-slider-thumb { pointer-events: auto; -webkit-appearance: none; width: 16px; height: 16px; border-radius: 50%; background: var(--accent); border: 2px solid #fff; box-shadow: 0 0 0 1px var(--accent-dk); cursor: pointer; }
.range input::-moz-range-thumb { pointer-events: auto; width: 14px; height: 14px; border-radius: 50%; background: var(--accent); border: 2px solid #fff; cursor: pointer; }
.range .track { position: absolute; left: 0; right: 0; top: 11px; height: 3px; background: #dedbd2; }
.range .sel { position: absolute; top: 11px; height: 3px; background: var(--accent); }

.layout { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 18px; margin: 18px 0 30px; align-items: start; }
.fbox > summary { display: none; }
.facets { display: flex; flex-direction: column; gap: 10px; }
.facet { background: var(--panel); border: 1px solid var(--border); padding: 8px 10px; }
.facet h3 { font-size: 1.05rem; display: flex; justify-content: space-between; }
.facet input[type=search] { width: 100%; font: .85rem var(--font-ui); padding: 4px 7px; border: 1px solid var(--border); margin: 2px 0 6px; }
.facet ul { list-style: none; margin: 0; padding: 0; font-size: .88rem; }
.facet li button { all: unset; box-sizing: border-box; display: flex; width: 100%; gap: 6px; justify-content: space-between; padding: 2px 4px; cursor: pointer; }
.facet li button:hover { background: var(--cat-source-pale); }
.facet li button[aria-pressed="true"] { background: var(--cat-source); font-weight: 600; }
.facet li button .c { color: var(--muted); font-variant-numeric: tabular-nums; }
.facet li button[aria-pressed="true"] .c { color: var(--ink); }
.facet .more { all: unset; color: var(--link); cursor: pointer; font-size: .85rem; margin-top: 4px; }
.facet .lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.facet .zero { opacity: .45; }

.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; align-items: center; }
.chip { background: var(--cat-source-pale); border: 1px solid var(--cat-source); padding: 1px 4px 1px 9px; font-size: .85rem; display: inline-flex; gap: 4px; align-items: center; }
.chip button { all: unset; cursor: pointer; padding: 0 4px; font-weight: 700; }
.chips .clear { all: unset; cursor: pointer; color: var(--link); font-size: .85rem; }
.count { font: 600 1.25rem var(--font-head); margin: 0 0 8px; }
.count small { font: .85rem var(--font-ui); color: var(--muted); }
.res { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; align-items: start; }
.res.nomap { grid-template-columns: minmax(0, 1fr); }
.mapbox { position: sticky; top: 10px; }
#map, #emap { height: 520px; background: #e5e3dc; border: 1px solid var(--border); }
#emap { height: 300px; }
.mapnote { font-size: .8rem; color: var(--muted); margin: 4px 0 0; }
ol.hits { list-style: none; margin: 0; padding: 0; background: var(--panel); border: 1px solid var(--border); }
ol.hits li { border-bottom: 1px solid #e6e4de; }
ol.hits li:last-child { border-bottom: 0; }
ol.hits a { display: block; padding: 8px 12px; color: var(--ink); text-decoration: none; }
ol.hits a:hover { background: #faf7ef; }
ol.hits .nm { font-weight: 600; color: var(--link); }
ol.hits .sub { display: block; font-size: .88rem; color: var(--muted); }
ol.hits .tag { font: 600 .72rem/1.4 var(--font-nav); background: var(--cat-source-pale); color: var(--cat-source-dk); padding: 1px 6px; margin-left: 6px; white-space: nowrap; }
ol.hits .tag.p { background: #e9e9e9; color: #333; }
mark { background: #fbe7a4; color: inherit; padding: 0; }
.pager { display: flex; gap: 8px; align-items: center; margin: 10px 0; flex-wrap: wrap; font-size: .9rem; }
.pager button { font: .9rem var(--font-nav); border: 1px solid var(--border); background: var(--panel); padding: 4px 12px; cursor: pointer; }
.pager button:disabled { opacity: .4; cursor: default; }
.loading { color: var(--muted); font-style: italic; }

/* Eintrag */
.entry { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 20px; margin: 10px 0 40px; align-items: start; }
.card { background: var(--panel); border: 1px solid var(--border); border-top: 4px solid var(--cat-source); padding: 12px 16px; margin-bottom: 16px; }
.card.tel { border-top-color: var(--cat-ann); }
.card.pers { border-top-color: var(--cat-pers); }
.card.korr { border-top-color: var(--accent); }
.quote { font-family: var(--font-serif); font-size: 1.1rem; background: #fbf8ef; border-left: 3px solid var(--cat-source); padding: 8px 12px; margin: 8px 0; }
table.kv { border-collapse: collapse; width: 100%; font-size: .92rem; }
table.kv th { text-align: left; font: 600 .85rem var(--font-nav); color: var(--muted); padding: 4px 10px 4px 0; vertical-align: top; width: 34%; }
table.kv td { padding: 4px 0; border-bottom: 1px solid #eeece6; vertical-align: top; word-break: break-word; }
ul.links { list-style: none; padding: 0; margin: 0; }
ul.links li { padding: 4px 0; border-bottom: 1px solid #eeece6; }
ul.links li:last-child { border: 0; }
ul.links small { color: var(--muted); }
.pill { font: 600 .7rem/1.4 var(--font-nav); padding: 1px 6px; background: #e9e9e9; text-transform: uppercase; letter-spacing: .04em; }
.pill.sicher, .pill.wahrscheinlich { background: var(--cat-ann-pale); color: var(--cat-ann-dk); }
.crumbs { font: .9rem var(--font-nav); margin: 18px 0 0; }
.foot { background: var(--panel); border-top: 1px solid var(--border); padding: 14px 0; font-size: .85rem; color: var(--muted); }
.foot p { margin: 4px 0; }
.leaflet-container { font-family: var(--font-ui); }

@media (max-width: 900px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .res { grid-template-columns: minmax(0, 1fr); }
  .mapbox { position: static; order: -1; }
  #map { height: 340px; }
  .entry { grid-template-columns: minmax(0, 1fr); }
  .band a.vs { margin-left: 0; }
  .facets { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: 8px; }
  .fbox > summary { display: list-item; cursor: pointer; font: 600 1rem var(--font-nav); background: var(--panel); border: 1px solid var(--border); padding: 8px 12px; }
}
@media (max-width: 520px) {
  .band a { padding: 8px 10px; font-size: .95rem; }
  .band a:first-child { margin-left: -10px; }
  form.searchbar button { padding: 0 14px; }
}
"""


JS = r"""// Suche und Eintragsseite der Adressbücher; aus scripts/site_search.py erzeugt (gleich in allen adressbuecher-*).
(() => {
'use strict';
const TX = {
  de: { lead_n: 'Einträge', vols: 'Bände', years: 'Jahre', streets: 'Strassen', q_ph: 'Name, Beruf, Strasse … z. B. Meier Bäcker',
        go: 'Suchen', more: 'Nach Feldern suchen', f_n: 'Familien- oder Firmenname', f_v: 'Vorname', f_b: 'Beruf', f_s: 'Strasse',
        hint: 'Gesucht wird in allen Bänden, Wörter vom Anfang her, ohne Akzente («muller» findet «Müller»); alle Wörter müssen vorkommen. Facetten und Zeitstrahl grenzen ein.',
        timeline: 'Zeitstrahl', all_years: 'alle Jahre', vol: 'Band', part: 'Teil', area: 'Gebiet', street: 'Strasse', occ: 'Beruf',
        filters: 'Filter: Band, Teil, Strasse, Beruf', filter: 'filtern …', show_more: 'mehr zeigen', show_less: 'weniger', clear: 'alles zurücksetzen', hits: 'Treffer', of: 'von',
        sorted: 'nach Name geordnet', prev: '← zurück', next: 'weiter →', page: 'Seite', map_note: (a, b) => `${a} von ${b} Treffern an einer verorteten Strasse. Kreis = Strasse, Grösse = Zahl der Treffer; Klick filtert.`,
        no_hits: 'Keine Treffer. Weniger Wörter, kürzere Wortanfänge oder weniger Facetten versuchen.', loading: 'lädt …',
        filter_street: 'nach dieser Strasse filtern', entries_here: 'Einträge', all_entries: 'Alle Einträge aller Bände',
        built: 'Stand', lic: 'Inhalte der Bücher gemeinfrei; Daten CC0 1.0, Code MIT. Maschinell gelesen und zerlegt: Fehler in Namen und Adressen kommen vor.',
        e_source: 'Quelle', e_read: 'Gelesene Zeile', e_fields: 'Alle Angaben', e_links: 'Verknüpfungen', e_other: 'In anderen Bänden',
        e_map: 'Ort', e_korr: 'Korrektur', e_korr_p: 'Lesung oder Zerlegung falsch? Im Korrekturmodus lässt sich der Eintrag markieren (Flag) und als CSV melden, oder direkt ein Issue eröffnen.',
        e_korr_a: 'Im Korrekturmodus öffnen', e_issue: 'Fehler als GitHub-Issue melden', e_page: 'Seitenbild', e_pdf: 'Seite',
        e_zeit: 'Historische Karte (swisstopo Zeitreise)', e_street_all: 'Alle Einträge an dieser Strasse', e_name_all: 'Gleicher Name in allen Bänden',
        e_notfound: 'Eintrag nicht gefunden.', e_back: '← zur Suche', e_nogeo: 'Die Strasse ist nicht verortet.',
        name: 'Name', forename: 'Vorname', alliance: 'Allianzname', occupation: 'Beruf', address: 'Adresse', area_l: 'Gebiet', title: 'Titel', origin: 'Herkunft',
        tiers: { sicher: 'sicher', wahrscheinlich: 'wahrscheinlich', 'möglich': 'möglich' }, other_note: 'automatisch verknüpft, ungeprüft' },
  fr: { lead_n: 'entrées', vols: 'volumes', years: 'années', streets: 'rues', q_ph: 'nom, profession, rue … p. ex. Bovet boulanger',
        go: 'Chercher', more: 'Recherche par champ', f_n: 'nom de famille ou raison sociale', f_v: 'prénom', f_b: 'profession', f_s: 'rue',
        hint: 'La recherche porte sur tous les volumes, mots depuis le début, sans accents («muller» trouve «Müller»); tous les mots doivent figurer. Les facettes et la frise chronologique restreignent.',
        timeline: 'Frise chronologique', all_years: 'toutes les années', vol: 'Volume', part: 'Partie', area: 'Quartier', street: 'Rue', occ: 'Profession',
        filters: 'Filtres: volume, partie, rue, profession', filter: 'filtrer …', show_more: 'plus', show_less: 'moins', clear: 'tout réinitialiser', hits: 'résultats', of: 'sur',
        sorted: 'par ordre alphabétique', prev: '← précédent', next: 'suivant →', page: 'page', map_note: (a, b) => `${a} sur ${b} résultats dans une rue localisée. Cercle = rue, taille = nombre de résultats; un clic filtre.`,
        no_hits: 'Aucun résultat. Essayez moins de mots, des débuts de mots plus courts ou moins de facettes.', loading: 'chargement …',
        filter_street: 'filtrer par cette rue', entries_here: 'entrées', all_entries: 'Toutes les entrées de tous les volumes',
        built: 'État', lic: 'Contenu des annuaires dans le domaine public; données CC0 1.0, code MIT. Lu et découpé automatiquement: des erreurs dans les noms et adresses subsistent.',
        e_source: 'Source', e_read: 'Ligne lue', e_fields: 'Toutes les indications', e_links: 'Liens', e_other: 'Dans d’autres volumes',
        e_map: 'Lieu', e_korr: 'Correction', e_korr_p: 'Lecture ou découpage erronés? Le mode correction permet de signaler l’entrée (flag) et d’exporter un CSV, ou d’ouvrir directement un issue.',
        e_korr_a: 'Ouvrir en mode correction', e_issue: 'Signaler une erreur (issue GitHub)', e_page: 'Image de la page', e_pdf: 'page',
        e_zeit: 'Carte historique (swisstopo Voyage dans le temps)', e_street_all: 'Toutes les entrées de cette rue', e_name_all: 'Même nom dans tous les volumes',
        e_notfound: 'Entrée introuvable.', e_back: '← retour à la recherche', e_nogeo: 'La rue n’est pas localisée.',
        name: 'Nom', forename: 'Prénom', alliance: 'nom d’alliance', occupation: 'Profession', address: 'Adresse', area_l: 'Quartier', title: 'Titre', origin: 'Origine',
        tiers: { sicher: 'sûr', wahrscheinlich: 'probable', 'möglich': 'possible' }, other_note: 'lien automatique, non vérifié' },
};
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fold = s => String(s ?? '').replace(/ß/g, 'ss').replace(/[æÆ]/g, 'ae').replace(/[œŒ]/g, 'oe').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const STOP = new Set(['de','la','le','du','des','und','u','et','in','im','am','an','der','die','das','von','v','zum','zur','bei','geb','wwe','sel','frau','hr','herr','mme','mlle','veuve','vve']);
const words = s => (fold(s).match(/[a-z0-9]+/g) || []).filter(w => w.length > 1 && !/^\d+$/.test(w) && !STOP.has(w));
const fnv = s => { let h = 0x811c9dc5; for (const b of new TextEncoder().encode(s)) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; } return (h & 0x3f).toString(16).padStart(2, '0'); };
const fmt = n => n.toLocaleString('de-CH');
const cache = new Map();
async function gz(path) {
  if (cache.has(path)) return cache.get(path);
  const p = (async () => {
    const r = await fetch(path);
    if (!r.ok) { if (r.status === 404) return null; throw new Error(path + ' ' + r.status); }
    const buf = await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    return path.endsWith('.bin.gz') ? buf : JSON.parse(new TextDecoder().decode(buf));
  })();
  cache.set(path, p);
  return p;
}
let M, T, N, COL = null, OCC = null;
const block = i => gz(`s/r/${Math.floor(i / M.block)}.json.gz`).then(b => b[i % M.block]);
async function loadCols() {
  if (COL) return COL;
  const [buf, occ] = await Promise.all([gz('s/c.bin.gz'), gz('s/occ.json.gz')]);
  OCC = occ;
  COL = { s: new Uint16Array(buf, 0, N), b: new Uint16Array(buf, 2 * N, N), a: new Uint16Array(buf, 4 * N, N), v: new Uint8Array(buf, 6 * N, N), p: new Uint8Array(buf, 7 * N, N) };
  return COL;
}
function rowName(r) { return [r[3], r[5] && r[5] !== r[3] ? r[5] : ''].filter(Boolean).join('-'); }
function addr(r) { return [r[7], r[8]].filter(Boolean).join(' '); }
function korrUrl(r) {
  const v = M.volumes[r[1]], p = M.parts[r[2]];
  return (M.city.korr || 'korrektur/').replace('{id}', encodeURIComponent(r[0].split('#')[0])).replace('{vol}', encodeURIComponent(v.k)).replace('{part}', encodeURIComponent(p.k));
}
function lv95(lat, lon) {
  const p = (lat * 3600 - 169028.66) / 10000, l = (lon * 3600 - 26782.5) / 10000;
  return [Math.round(2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p - 44.54 * l ** 3),
          Math.round(1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p - 194.56 * l * l * p + 119.79 * p ** 3)];
}
function footer() {
  $('foot').innerHTML = `<p>${esc(M.city.note || '')}</p><p>${esc(T.lic)} ${esc(T.built)} ${esc(M.built)} · <a href="${esc(M.city.repo)}">${esc(M.city.repo.replace('https://', ''))}</a></p>`;
}
let leafletReady = () => typeof L !== 'undefined';
function baseMap(el, opts) {
  const map = L.map(el, Object.assign({ scrollWheelZoom: false }, opts || {}));
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende' }).addTo(map);
  return map;
}

/* ───────────── Suche ───────────── */
const FACETS = [['v', 'vol'], ['p', 'part'], ['a', 'area'], ['s', 'street'], ['b', 'occ']];
const PAGE = 50;
const st = { q: '', n: '', vn: '', b: '', s: '', y0: 0, y1: 9999, sel: { v: new Set(), p: new Set(), a: new Set(), s: new Set(), b: new Set() }, page: 0, open: {}, ff: {} };
let hits = null, counts = null, map = null, layer = null, run = 0;

function readUrl() {
  const P = new URLSearchParams(location.search);
  st.q = P.get('q') || ''; st.n = P.get('name') || ''; st.vn = P.get('vorname') || ''; st.b = P.get('beruf') || ''; st.s = P.get('strasse') || '';
  const y = (P.get('jahre') || '').split('-');
  st.y0 = +y[0] || 0; st.y1 = +y[1] || 9999; st.page = Math.max(0, (+P.get('seite') || 1) - 1);
  const lab = { v: M.volumes.map(x => String(x.k)), p: M.parts.map(x => x.k), a: ['', ...M.areas], s: ['', ...M.streets.map(x => x[0])], b: null };
  for (const [k, name] of [['v', 'band'], ['p', 'teil'], ['a', 'gebiet'], ['s', 'str'], ['b', 'ber']]) {
    st.sel[k] = new Set();
    for (const val of P.getAll(name)) {
      if (k === 'b') { st.selB = st.selB || []; st.selB.push(val); continue; }
      const i = lab[k].indexOf(val); if (i >= 0) st.sel[k].add(i);
    }
  }
}
function writeUrl() {
  const P = new URLSearchParams();
  if (st.q) P.set('q', st.q); if (st.n) P.set('name', st.n); if (st.vn) P.set('vorname', st.vn); if (st.b) P.set('beruf', st.b); if (st.s) P.set('strasse', st.s);
  const ys = M.years.map(x => x[0]);
  if (st.y0 > ys[0] || st.y1 < ys[ys.length - 1]) P.set('jahre', `${st.y0}-${st.y1}`);
  for (const i of st.sel.v) P.append('band', M.volumes[i].k);
  for (const i of st.sel.p) P.append('teil', M.parts[i].k);
  for (const i of st.sel.a) P.append('gebiet', M.areas[i - 1]);
  for (const i of st.sel.s) P.append('str', M.streets[i - 1][0]);
  for (const i of st.sel.b) P.append('ber', OCC[i - 1]);
  if (st.page) P.set('seite', st.page + 1);
  const s = P.toString();
  history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
}
// Begriffe → Treffermaske (null = keine Textsuche)
async function textMask() {
  const terms = [];
  for (const w of words(st.q)) terms.push([w, 'nvbsot']);
  for (const [val, f] of [[st.n, 'n'], [st.vn, 'v'], [st.b, 'b'], [st.s, 's']]) for (const w of words(val)) terms.push([w, f]);
  if (!terms.length) return null;
  let mask = null;
  for (const [w, fs] of terms) {
    const sh = await gz(`s/t/${w.slice(0, 2)}.json.gz`);
    const m = new Uint8Array(N);
    if (sh) for (const key in sh) {
      if (!fs.includes(key[0]) || !key.startsWith(w, 1)) continue;
      let x = 0; for (const d of sh[key]) { x += d; m[x] = 1; }
    }
    if (mask) for (let i = 0; i < N; i++) mask[i] &= m[i]; else mask = m;
  }
  return mask;
}
function compute(mask) {
  const C = COL, sel = st.sel, vy = M.volumes.map(v => v.year);
  const nf = { v: new Uint32Array(M.volumes.length), p: new Uint32Array(M.parts.length), a: new Uint32Array(M.areas.length + 1), s: new Uint32Array(M.streets.length + 1), b: new Uint32Array(OCC.length + 1) };
  const yc = new Map(); const out = [];
  const has = { v: sel.v.size > 0, p: sel.p.size > 0, a: sel.a.size > 0, s: sel.s.size > 0, b: sel.b.size > 0 };
  for (let i = 0; i < N; i++) {
    if (mask && !mask[i]) continue;
    const v = C.v[i], y = vy[v];
    const inY = y >= st.y0 && y <= st.y1;
    let fail = 0, which = '';
    if (has.v && !sel.v.has(v)) { fail++; which = 'v'; }
    if (has.p && !sel.p.has(C.p[i])) { fail++; which = 'p'; }
    if (has.a && !sel.a.has(C.a[i])) { fail++; which = 'a'; }
    if (has.s && !sel.s.has(C.s[i])) { fail++; which = 's'; }
    if (has.b && !sel.b.has(C.b[i])) { fail++; which = 'b'; }
    if (fail === 0) { yc.set(y, (yc.get(y) || 0) + 1); }
    if (!inY) continue;
    if (fail === 0) { nf.v[v]++; nf.p[C.p[i]]++; nf.a[C.a[i]]++; nf.s[C.s[i]]++; nf.b[C.b[i]]++; out.push(i); }
    else if (fail === 1) nf[which][which === 'v' ? v : C[which][i]]++;
  }
  return { hits: out, nf, yc };
}
function facetHtml(k, key) {
  const nf = counts.nf[k], sel = st.sel[k], t = T[key];
  let items = [];
  if (k === 'v') items = M.volumes.map((x, i) => [i, x.label, nf[i]]);
  else if (k === 'p') items = M.parts.map((x, i) => [i, x.label, nf[i]]);
  else if (k === 'a') items = M.areas.map((x, i) => [i + 1, x, nf[i + 1]]);
  else if (k === 's') { items = []; for (let i = 1; i < nf.length; i++) if (nf[i] || sel.has(i)) items.push([i, M.streets[i - 1][0], nf[i]]); }
  else if (k === 'b') { items = []; for (let i = 1; i < nf.length; i++) if (nf[i] || sel.has(i)) items.push([i, OCC[i - 1], nf[i]]); }
  if (!items.length || (k === 'a' && !M.areas.length) || (items.length < 2 && !sel.size && (k === 'p' || k === 'a'))) return '';
  const ff = fold(st.ff[k] || '');
  if (ff) items = items.filter(x => fold(x[1]).includes(ff));
  if (k === 's' || k === 'b' || k === 'a') items.sort((a, b) => (sel.has(b[0]) - sel.has(a[0])) || b[2] - a[2] || a[1].localeCompare(b[1]));
  const lim = st.open[k] ? 200 : (k === 'v' ? 40 : 10);
  const searchable = k === 's' || k === 'b' || (k === 'v' && M.volumes.length > 15) || (k === 'a' && M.areas.length > 15);
  const li = items.slice(0, lim).map(([i, lab, c]) => `<li><button type="button" data-f="${k}" data-i="${i}" aria-pressed="${sel.has(i)}" class="${c ? '' : 'zero'}"><span class="lbl" title="${esc(lab)}">${esc(lab)}</span><span class="c">${fmt(c)}</span></button></li>`).join('');
  const more = items.length > lim ? `<button type="button" class="more" data-more="${k}">${esc(T.show_more)} (${fmt(items.length - lim)})</button>` : st.open[k] && items.length > 10 ? `<button type="button" class="more" data-more="${k}">${esc(T.show_less)}</button>` : '';
  return `<section class="facet"><h3>${esc(t)}</h3>${searchable ? `<input type="search" data-ff="${k}" value="${esc(st.ff[k] || '')}" placeholder="${esc(T.filter)}" aria-label="${esc(t)} ${esc(T.filter)}">` : ''}<ul>${li}</ul>${more}</section>`;
}
function renderFacets() {
  const box = $('facets');
  const focus = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.ff : null;
  box.innerHTML = FACETS.map(([k, key]) => facetHtml(k, key)).join('');
  if (focus) { const el = box.querySelector(`[data-ff="${focus}"]`); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }
}
function renderTimeline() {
  const ys = M.years.map(x => x[0]), y0 = ys[0], y1 = ys[ys.length - 1];
  const span = y1 - y0 + 1, max = Math.max(1, ...counts.yc.values());
  let bars = '';
  for (let y = y0; y <= y1; y++) {
    const c = counts.yc.get(y) || 0, has = ys.includes(y);
    const off = y < st.y0 || y > st.y1;
    bars += `<span class="${!has ? 'zero' : off ? 'off' : ''}" data-y="${y}" style="height:${c ? Math.max(3, Math.round(70 * Math.sqrt(c / max))) : has ? 1 : 0}px" title="${y}: ${fmt(c)} ${esc(T.hits)}"></span>`;
  }
  const a = Math.max(st.y0, y0), b = Math.min(st.y1, y1);
  const lab = a === y0 && b === y1 ? T.all_years : `${a}–${b}`;
  $('tl').innerHTML = `<div class="head"><b>${esc(T.timeline)}</b><span>${esc(lab)}</span></div><div class="bars">${bars}</div>
    <div class="range"><div class="track"></div><div class="sel" style="left:${(a - y0) / span * 100}%;width:${(b - a + 1) / span * 100}%"></div>
    <input type="range" id="ya" min="${y0}" max="${y1}" value="${a}" aria-label="von"><input type="range" id="yb" min="${y0}" max="${y1}" value="${b}" aria-label="bis"></div>
    <div class="ticks"><span>${y0}</span><span>${y1}</span></div>`;
}
function chips() {
  const out = [];
  const add = (lab, fn) => out.push([lab, fn]);
  if (st.q) add(`„${st.q}“`, () => { st.q = ''; $('q').value = ''; });
  for (const [k, id, lab] of [['n', 'fn', T.f_n], ['vn', 'fv', T.f_v], ['b', 'fb', T.f_b], ['s', 'fs', T.f_s]]) if (st[k]) add(`${lab}: ${st[k]}`, () => { st[k] = ''; $(id).value = ''; });
  const ys = M.years.map(x => x[0]);
  if (st.y0 > ys[0] || st.y1 < ys[ys.length - 1]) add(`${Math.max(st.y0, ys[0])}–${Math.min(st.y1, ys[ys.length - 1])}`, () => { st.y0 = 0; st.y1 = 9999; });
  const names = { v: i => M.volumes[i].label, p: i => M.parts[i].label, a: i => M.areas[i - 1], s: i => M.streets[i - 1][0], b: i => OCC[i - 1] };
  for (const [k] of FACETS) for (const i of st.sel[k]) add(names[k](i), () => st.sel[k].delete(i));
  if (!out.length) return '';
  window._chips = out;
  return out.map(([lab], j) => `<span class="chip">${esc(lab)}<button type="button" data-chip="${j}" aria-label="entfernen">✕</button></span>`).join('') + `<button type="button" class="clear" data-chip="all">${esc(T.clear)}</button>`;
}
async function renderList() {
  const list = hits, from = st.page * PAGE, part = list.slice(from, from + PAGE);
  const box = $('list');
  const head = `<p class="count">${fmt(list.length)} ${esc(T.hits)} <small>${esc(T.of)} ${fmt(N)} · ${esc(T.sorted)}</small></p>`;
  if (!list.length) { box.innerHTML = head + `<p>${esc(T.no_hits)}</p>`; return; }
  box.innerHTML = head + `<p class="loading">${esc(T.loading)}</p>`;
  const my = run;
  const rows = await Promise.all(part.map(block));
  if (my !== run) return;
  const hl = new Set([...words(st.q), ...words(st.n), ...words(st.vn), ...words(st.b), ...words(st.s)]);
  const mk = s => { if (!hl.size || !s) return esc(s); return String(s).split(/(\s+|[,.;()\-])/).map(t => { const f = fold(t); for (const w of hl) if (f.startsWith(w)) return `<mark>${esc(t)}</mark>`; return esc(t); }).join(''); };
  const pages = Math.ceil(list.length / PAGE);
  const pager = pages > 1 ? `<div class="pager"><button type="button" data-pg="-1" ${st.page ? '' : 'disabled'}>${esc(T.prev)}</button><span>${esc(T.page)} ${st.page + 1} / ${fmt(pages)}</span><button type="button" data-pg="1" ${st.page + 1 < pages ? '' : 'disabled'}>${esc(T.next)}</button></div>` : '';
  box.innerHTML = head + pager + '<ol class="hits">' + rows.map(r => {
    const v = M.volumes[r[1]], p = M.parts[r[2]];
    const nm = [mk(rowName(r)) || '—', r[4] ? mk(r[4]) : ''].filter(Boolean).join(', ');
    const sub = [r[6] ? mk(r[6]) : '', addr(r) ? mk(addr(r)) : '', r[9] ? esc(r[9]) : ''].filter(Boolean).join(' · ');
    return `<li><a href="eintrag.html?id=${encodeURIComponent(r[0])}"><span class="nm">${nm}</span><span class="tag">${esc(v.year)}</span>${M.parts.length > 1 ? `<span class="tag p">${esc(p.label)}</span>` : ''}<span class="sub">${sub || esc(r[11] || '')}</span></a></li>`;
  }).join('') + '</ol>' + pager;
}
function renderMap() {
  if (!leafletReady() || !M.streets.some(x => x[1] != null)) return;
  if (!map) {
    map = baseMap('map', { preferCanvas: true });
    map.setView(M.city.center || [46.8, 8.2], 14);
    layer = L.layerGroup().addTo(map);
  }
  layer.clearLayers();
  const nf = counts.nf.s; let located = 0, max = 1;
  for (let i = 1; i < nf.length; i++) if (nf[i] && M.streets[i - 1][1] != null) { located += nf[i]; max = Math.max(max, nf[i]); }
  // Kreise nur für Strassen mit Treffern, die Kreise der gewählten Strassen gefüllt
  const pts = [];
  for (let i = 1; i < nf.length; i++) {
    const c = nf[i]; const s = M.streets[i - 1];
    if (!c || s[1] == null) continue;
    const on = st.sel.s.has(i);
    const m = L.circleMarker([s[1], s[2]], { radius: 3 + 17 * Math.sqrt(c / max), color: on ? '#a81429' : '#7a4e14', weight: on ? 2 : 1, fillColor: on ? '#d21938' : '#d7b95a', fillOpacity: .7 });
    m.bindTooltip(`${esc(s[0])}: ${fmt(c)}`);
    m.on('click', () => { st.sel.s.has(i) ? st.sel.s.delete(i) : st.sel.s.add(i); st.page = 0; update(); });
    m.addTo(layer); pts.push([s[1], s[2]]);
  }
  if (pts.length && hits.length < N) map.fitBounds(pts, { maxZoom: 16, padding: [20, 20] });
  else if (!pts.length) map.setView(M.city.center || [46.8, 8.2], 14);
  $('mapnote').textContent = T.map_note(fmt(located), fmt(hits.length));
}
async function update(keepPage) {
  const my = ++run;
  if (!keepPage) st.page = 0;
  writeUrl();
  $('chips').innerHTML = chips();
  await loadCols();
  const mask = await textMask();
  if (my !== run) return;
  if (st.selB) { for (const b of st.selB) { const i = OCC.indexOf(b); if (i >= 0) st.sel.b.add(i + 1); } st.selB = null; $('chips').innerHTML = chips(); }
  counts = compute(mask);
  hits = counts.hits;
  renderTimeline(); renderFacets(); renderMap();
  await renderList();
}
function searchPage() {
  const app = $('app');
  const vs = M.volumes.length, ys = M.years.map(x => x[0]);
  app.innerHTML = `<section class="hero">
    <p class="kicker">${esc(M.city.title)}</p>
    <h1>${esc(M.city.name)} ${esc(M.city.span)}</h1>
    <p class="lead">${esc(M.city.lead || '')}</p>
    <form class="searchbar" id="sf" role="search"><input id="q" type="search" placeholder="${esc(T.q_ph)}" aria-label="${esc(T.go)}" autocomplete="off"><button type="submit">${esc(T.go)}</button></form>
    <details class="more" id="more"><summary>${esc(T.more)}</summary><div class="fields">
      <label>${esc(T.f_n)}<input id="fn" type="search" autocomplete="off"></label><label>${esc(T.f_v)}<input id="fv" type="search" autocomplete="off"></label>
      <label>${esc(T.f_b)}<input id="fb" type="search" autocomplete="off"></label><label>${esc(T.f_s)}<input id="fs" type="search" autocomplete="off"></label></div></details>
    <p class="hint">${esc(T.hint)}</p>
    <dl class="kpis"><div><dt>${esc(T.lead_n)}</dt><dd>${fmt(N)}</dd></div><div><dt>${esc(T.vols)}</dt><dd>${fmt(vs)}</dd></div>
      <div><dt>${esc(T.years)}</dt><dd>${ys[0]}–${ys[ys.length - 1]}</dd></div><div><dt>${esc(T.streets)}</dt><dd>${fmt(M.streets.length)}</dd></div></dl>
    <div class="timeline" id="tl"></div>
  </section>
  <div class="layout"><details class="fbox" id="fbox" open><summary>${esc(T.filters)}</summary><aside class="facets" id="facets"></aside></details>
    <section><div class="chips" id="chips"></div>
      <div class="res"><div id="list"><p class="loading">${esc(T.loading)}</p></div><div class="mapbox"><div id="map"></div><p class="mapnote" id="mapnote"></p></div></div>
    </section></div>`;
  if (matchMedia('(max-width: 900px)').matches) $('fbox').open = false;
  if (!M.streets.some(x => x[1] != null)) { document.querySelector('.res').classList.add('nomap'); document.querySelector('.mapbox').hidden = true; }
  readUrl();
  $('q').value = st.q; $('fn').value = st.n; $('fv').value = st.vn; $('fb').value = st.b; $('fs').value = st.s;
  if (st.n || st.vn || st.b || st.s) $('more').open = true;
  let deb;
  const typed = () => { clearTimeout(deb); deb = setTimeout(() => { st.q = $('q').value.trim(); st.n = $('fn').value.trim(); st.vn = $('fv').value.trim(); st.b = $('fb').value.trim(); st.s = $('fs').value.trim(); update(); }, 250); };
  $('sf').addEventListener('submit', e => { e.preventDefault(); typed(); });
  for (const id of ['q', 'fn', 'fv', 'fb', 'fs']) $(id).addEventListener('input', typed);
  $('facets').addEventListener('click', e => {
    const b = e.target.closest('button[data-f]');
    if (b) { const k = b.dataset.f, i = +b.dataset.i; st.sel[k].has(i) ? st.sel[k].delete(i) : st.sel[k].add(i); update(); return; }
    const m = e.target.closest('[data-more]');
    if (m) { st.open[m.dataset.more] = !st.open[m.dataset.more]; renderFacets(); }
  });
  $('facets').addEventListener('input', e => { const k = e.target.dataset.ff; if (k) { st.ff[k] = e.target.value; renderFacets(); } });
  $('chips').addEventListener('click', e => {
    const b = e.target.closest('[data-chip]'); if (!b) return;
    if (b.dataset.chip === 'all') { for (const [, fn] of window._chips) fn(); } else window._chips[+b.dataset.chip][1]();
    update();
  });
  $('list').addEventListener('click', e => { const b = e.target.closest('[data-pg]'); if (!b) return; st.page += +b.dataset.pg; writeUrl(); renderList().then(() => $('list').scrollIntoView({ block: 'start', behavior: 'smooth' })); });
  $('tl').addEventListener('input', e => {
    if (e.target.id !== 'ya' && e.target.id !== 'yb') return;
    let a = +$('ya').value, b = +$('yb').value; if (a > b) [a, b] = [b, a];
    st.y0 = a; st.y1 = b; clearTimeout(deb); deb = setTimeout(() => update(), 150);
  });
  $('tl').addEventListener('click', e => { const s = e.target.closest('[data-y]'); if (!s || s.classList.contains('zero')) return; const y = +s.dataset.y; if (st.y0 === y && st.y1 === y) { st.y0 = 0; st.y1 = 9999; } else { st.y0 = y; st.y1 = y; } update(); });
  update(true);
}

/* ───────────── Eintrag ───────────── */
async function byId(id) {
  const sh = await gz(`s/i/${fnv(id)}.json.gz`);
  if (!sh || sh[id] == null) return null;
  return [sh[id], await block(sh[id])];
}
async function entryPage() {
  const id = new URLSearchParams(location.search).get('id') || '';
  const app = $('app');
  const hit = id ? await byId(id) : null;
  if (!hit) { app.innerHTML = `<p class="crumbs"><a href="./">${esc(T.e_back)}</a></p><h1>${esc(T.e_notfound)}</h1><p>${esc(id)}</p>`; return; }
  const [ix, r] = hit;
  const v = M.volumes[r[1]], p = M.parts[r[2]], s0 = r[16] ? M.streets[r[16] - 1] : null;
  const s = r[19] ? [s0 ? s0[0] : addr(r), r[19][0], r[19][1]] : s0;  // Haus vor Strasse
  const name = rowName(r) || '—';
  document.title = `${name}${r[4] ? ', ' + r[4] : ''} · ${v.year} · ${M.city.name}`;
  const L_ = M.labels || {};
  const kv = [[T.name, name], [T.forename, r[4]], [T.title, r[17]], [T.occupation, r[6]], [T.address, addr(r)], [T.area_l, r[9]], [T.origin, r[18]]].filter(x => x[1]);
  const all = r[13].map(([k, val]) => [L_[k] || k, val]);
  const links = r[14];
  const icon = { tel: '☏', vs: '⟷', wd: 'W', hls: 'H', mg: '↗', img: '▣', ext: '↗' };
  const linkHtml = links.length ? `<ul class="links">${links.map(([k, lab, url, note]) => `<li>${icon[k] || '↗'} ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(lab)}</a>` : esc(lab)}${note ? ` <small>${esc(note)}</small>` : ''}</li>`).join('')}</ul>` : '';
  const pageHtml = r[12] ? `<a href="${esc(r[12])}" target="_blank" rel="noopener">${esc(T.e_page)} ↗</a>` : '';
  const zeit = s && s[1] != null ? (() => { const [e, n] = lv95(s[1], s[2]); return `https://map.geo.admin.ch/#/map?lang=${M.city.lang}&center=${e},${n}&z=11&crosshair=marker&bgLayer=void&layers=ch.swisstopo.zeitreihen@year=${v.year}`; })() : '';
  const issue = `${M.city.repo}/issues/new?title=${encodeURIComponent('Flag ' + r[0])}&labels=review&body=${encodeURIComponent(`ID: ${r[0]}\nBand ${v.label}, ${T.e_pdf} ${r[10]}\n\n${T.e_read}:\n${r[11]}\n\nProblem:\n`)}`;
  const streetQ = r[7] ? `./?str=${encodeURIComponent(s0 ? s0[0] : r[7])}` : '';
  app.innerHTML = `<p class="crumbs"><a href="./" id="back">${esc(T.e_back)}</a></p>
  <section class="hero" style="padding-top:12px"><p class="kicker">${esc(v.label)} · ${esc(p.label)}${r[10] ? ` · ${esc(T.e_pdf)} ${esc(r[10])}` : ''}</p>
    <h1>${esc(name)}${r[4] ? `<span style="font-weight:400">, ${esc(r[4])}</span>` : ''}</h1>
    <p class="lead">${esc([r[6], addr(r)].filter(Boolean).join(' · '))}</p></section>
  <div class="entry"><div>
    <div class="card"><h2>${esc(T.e_read)}</h2><div class="quote">${esc(r[11] || '—')}</div>
      <p class="muted" style="font-size:.9rem">${esc(T.e_source)}: ${esc(v.label)}${r[10] ? `, ${esc(T.e_pdf)} ${esc(r[10])}` : ''}${pageHtml ? ' · ' + pageHtml : ''}${M.city.page_note ? ` <br><small>${esc(M.city.page_note)}</small>` : ''}</p>
      <table class="kv">${kv.map(([k, val]) => `<tr><th>${esc(k)}</th><td>${esc(val)}</td></tr>`).join('')}</table></div>
    ${r[15].length ? `<div class="card"><h2>${esc(T.e_other)}</h2><p class="muted" style="font-size:.85rem;margin-top:0">${esc(T.other_note)}</p><ul class="links" id="rel">${r[15].map(([ov, tier, oid]) => `<li data-oid="${esc(oid)}"><a href="eintrag.html?id=${encodeURIComponent(oid)}">${esc(ov)}</a> <span class="pill ${esc(tier)}">${esc(T.tiers[tier] || tier)}</span> <small class="t"></small></li>`).join('')}</ul></div>` : ''}
    ${all.length ? `<div class="card"><h2>${esc(T.e_fields)}</h2><table class="kv">${all.map(([k, val]) => `<tr><th>${esc(k)}</th><td>${esc(val)}</td></tr>`).join('')}</table></div>` : ''}
  </div><div>
    <div class="card"><h2>${esc(T.e_map)}</h2>${s && s[1] != null ? '<div id="emap"></div>' : `<p class="muted">${esc(T.e_nogeo)}</p>`}
      <ul class="links" style="margin-top:8px">${zeit ? `<li><a href="${esc(zeit)}" target="_blank" rel="noopener">${esc(T.e_zeit)} ${esc(v.year)} ↗</a></li>` : ''}
      ${streetQ ? `<li><a href="${esc(streetQ)}">${esc(T.e_street_all)}: ${esc(s0 ? s0[0] : r[7])}</a></li>` : ''}
      ${r[3] ? `<li><a href="./?name=${encodeURIComponent(r[3])}${r[4] ? '&vorname=' + encodeURIComponent(r[4].split(/[\s,]/)[0]) : ''}">${esc(T.e_name_all)}: ${esc(r[3])}${r[4] ? ' ' + esc(r[4].split(/[\s,]/)[0]) : ''}</a></li>` : ''}</ul></div>
    ${linkHtml ? `<div class="card tel"><h2>${esc(T.e_links)}</h2>${linkHtml}</div>` : ''}
    <div class="card korr"><h2>${esc(T.e_korr)}</h2><p style="font-size:.92rem">${esc(T.e_korr_p)}</p>
      <ul class="links"><li><a href="${esc(korrUrl(r))}">${esc(T.e_korr_a)}</a></li><li><a href="${esc(issue)}" target="_blank" rel="noopener">${esc(T.e_issue)} ↗</a></li></ul>
      <p class="muted" style="font-size:.8rem;margin-bottom:0">ID ${esc(r[0])}</p></div>
  </div></div>`;
  if (document.referrer && new URL(document.referrer).pathname === location.pathname.replace(/eintrag\.html$/, '')) $('back').addEventListener('click', e => { e.preventDefault(); history.back(); });
  if (s && s[1] != null && leafletReady()) {
    const m = baseMap('emap'); m.setView([s[1], s[2]], 16);
    L.circleMarker([s[1], s[2]], { radius: 9, color: '#a81429', fillColor: '#d21938', fillOpacity: .8 }).bindTooltip(esc(s[0])).addTo(m);
  }
  for (const li of document.querySelectorAll('#rel li')) {
    byId(li.dataset.oid).then(h => { if (h) li.querySelector('.t').textContent = [rowName(h[1]), h[1][4], h[1][6], addr(h[1])].filter(Boolean).join(', '); });
  }
}

(async () => {
  M = await fetch('s/meta.json').then(r => r.json());
  T = Object.assign({}, TX[M.city.lang] || TX.de, M.city.ui || {}); N = M.n;
  footer();
  if (document.body.dataset.page === 'eintrag') entryPage(); else searchPage();
})().catch(e => { $('app').innerHTML = `<p>Fehler: ${esc(e.message)}</p>`; console.error(e); });
})();
"""
