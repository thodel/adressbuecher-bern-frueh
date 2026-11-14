#!/usr/bin/env python3
"""Stufe 9: statische Seite aus den CSV bauen.

  site/index.html       Suchen (alle Bände oder ein Band) und Blättern (Seite für Seite,
                        Seitenbild von e-rara neben den gelesenen Zeilen und Einträgen)
  site/methoden.html    Methode und Vorbehalte
  site/data/*.js        Daten als JS (lädt auch über file://)

Die Seitenbilder werden nicht im Repo gehalten; sie kommen über IIIF direkt von
e-rara (Universitätsbibliothek Bern).
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys

sys.path.insert(0, str(Path(__file__).parent))
import site_nav  # noqa: E402  gemeinsame Navigation und Feldsuche aller Adressbuch-Seiten

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

COLS = ["entry_id", "volume", "page", "printed_page", "section", "line_from", "line_to", "kind",
        "heading", "place", "surname", "forename", "title", "occupation", "address", "quarter",
        "street", "house_no", "origin", "birth_year", "household", "note", "continues", "text",
        "doubt", "doubt_detail"]


def main() -> None:
    cfg = json.loads((ROOT / "config/volumes.json").read_text())["volumes"]
    pages = list(csv.DictReader((ROOT / "data/csv/01_pages.csv").open()))
    with (ROOT / "data/csv/04_entries.csv").open() as fh:
        rd = csv.DictReader(fh)
        entries = list(rd)
    cols = COLS + site_nav.extra_columns(entries, rd.fieldnames, COLS)  # alle CSV-Angaben für die Feldsuche
    lines = list(csv.DictReader((ROOT / "data/csv/02_lines.csv").open()))
    status = {(r["volume"], int(r["page"])): r for r in csv.DictReader((ROOT / "data/csv/03_page_status.csv").open())}

    vols = []
    for v in cfg:
        vp = [p for p in pages if p["volume"] == v["volume"]]
        vols.append({
            "volume": v["volume"], "short": v["short"], "title": v["title"], "year": v["year"],
            "publisher": v["publisher"], "doi": v["doi"], "shelfmark": v["shelfmark"],
            "sections": v["sections"], "notes": v["notes"],
            "n_pages": len(vp),
            "n_ok": sum(1 for p in vp if status.get((v["volume"], int(p["page"])), {}).get("status") == "ok"),
            "n_entries": sum(1 for e in entries if e["volume"] == v["volume"]),
        })
    page_rows = [[p["volume"], int(p["page"]), p["section"], p["erara_canvas"], p["iiif_image"],
                  status.get((p["volume"], int(p["page"])), {}).get("printed_page", ""),
                  status.get((p["volume"], int(p["page"])), {}).get("status", "fehlt")] for p in pages]
    ent_rows = [[e.get(c, "") for c in cols] for e in entries]
    by_page = defaultdict(list)
    for l in lines:
        row = [int(l["line"] or 0), l["text"]]
        if l.get("text_b"):
            row.append(l["text_b"])
        by_page[f"{l['volume']}|{l['page']}"].append(row)

    (SITE / "data").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%d.%m.%Y, %H:%M")
    (SITE / "data/meta.js").write_text(
        "window.BERN_META=" + json.dumps({"volumes": vols, "pages": page_rows, "built": stamp,
                                          "entry_cols": cols}, ensure_ascii=False) + ";\n")
    (SITE / "data/entries.js").write_text("window.BERN_ENTRIES=" + json.dumps(ent_rows, ensure_ascii=False, separators=(",", ":")) + ";\n")
    (SITE / "data/lines.js").write_text("window.BERN_LINES=" + json.dumps(by_page, ensure_ascii=False, separators=(",", ":")) + ";\n")

    write_nav()
    write_places(entries)
    write_houses(entries)

    kinds = Counter(e["kind"] for e in entries)
    print(f"site/data: {len(ent_rows)} Einträge, {len(lines)} Zeilen, {len(page_rows)} Seiten; Arten {dict(kinds)}")


NAV_PAGES = {"index.html": "entries", "karte.html": "map", "methoden.html": "methoden"}


def write_nav() -> None:
    """Städteleiste, Stadtnavigation und Feldsuche (scripts/site_nav.py, in allen Adressbuch-Repos gleich):
    site/nav.css, site/fieldsearch.js und das Markup zwischen den Markierungen <!-- site_nav:… --> der Seiten."""
    (SITE / "nav.css").write_text("/* aus scripts/site_nav.py erzeugt */" + site_nav.CSS)
    (SITE / "fieldsearch.js").write_text("/* aus scripts/site_nav.py erzeugt */" + site_nav.FIELD_SEARCH_JS
                                         + "window.FSTX = " + json.dumps(site_nav.fs_texts(), ensure_ascii=False) + ";\n")
    for name, page in NAV_PAGES.items():
        p = SITE / name
        html = p.read_text()
        parts = {"cities": site_nav.city_bar("bern-frueh"),
                 "city": site_nav.city_nav("Bern 1795–1848", "https://github.com/thodel/adressbuecher-bern-frueh", page,
                                           map_label="Karte der Orte",
                                           extra=[("methoden", "methoden.html", "Methode und Vorbehalte")]),
                 "search": site_nav.search_panel()}
        for k, v in parts.items():
            html = re.sub(rf"<!-- site_nav:{k} -->.*?<!-- /site_nav -->", lambda m: f"<!-- site_nav:{k} -->{v}<!-- /site_nav -->",
                          html, flags=re.S)
        p.write_text(html)


def write_places(entries: list[dict]) -> None:
    """Orte für die Karte: config/places.csv (Schreibung -> Ort) auf die Einträge anwenden.

    Einträge ohne verorteten Ort erben den Ort des vorangehenden verorteten Eintrags
    desselben Bandes (höchstens eine Seite zurück) und gelten als «ungefähr».
    Ergebnis: data/csv/06_entry_places.csv und site/data/places.js.
    """
    gaz = {r["place"]: r for r in csv.DictReader((ROOT / "config/places.csv").open(encoding="utf-8"))}
    order = sorted(entries, key=lambda e: (e["volume"], int(e["page"]), int(e["line_from"] or 0)))
    out, last = [], {}
    for e in order:
        sp = e["place"].strip()
        g = gaz.get(f"{sp}@{e['volume']}:{int(e['page'])}") or gaz.get(sp)
        how = ""
        if g and g["lat"]:
            how = "ort"
            last[e["volume"]] = (g, sp, int(e["page"]))
        elif g and g["method"] == "ausgelassen":
            g = None
        else:
            prev = last.get(e["volume"])
            if prev and int(e["page"]) - prev[2] <= 1:
                g, how = prev[0], "ungefähr"
            else:
                g = None
        out.append({"entry_id": e["entry_id"], "volume": e["volume"], "place": sp,
                    "map_place": g["name"] if g else "", "canton": g["canton"] if g else "",
                    "lat": g["lat"] if g else "", "lon": g["lon"] if g else "",
                    "method": (g["method"] if how == "ort" else how) if g else "", "precision": how,
                    "source": g["source"] if g else ""})
    with (ROOT / "data/csv/06_entry_places.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(out[0])); w.writeheader(); w.writerows(out)

    places: dict[tuple, dict] = {}
    for o in out:
        if not o["lat"]:
            continue
        # dieselbe Gemeinde unter deutschem und französischem Namen (Thun/Thoune) zusammenfassen
        key = o["source"] if "gg25" in o["source"] else (round(float(o["lat"]), 3), round(float(o["lon"]), 3))
        p = places.setdefault(key, {"names": Counter(), "c": o["canton"], "lat": float(o["lat"]), "lon": float(o["lon"]),
                                    "m": set(), "sp": {}, "v": Counter(), "a": Counter()})
        p["names"][(o["map_place"], o["canton"])] += 1
        (p["v"] if o["precision"] == "ort" else p["a"])[o["volume"]] += 1
        if o["precision"] == "ort":
            p["m"].add(o["method"])
            p["sp"].setdefault(o["place"], Counter())[o["volume"]] += 1
    notes = {}
    for r in gaz.values():
        if r["note"] and r["lat"] and r["method"] in ("hand", "kontext", "unscharf", "bezugsort"):
            notes.setdefault((r["name"], r["canton"]), set()).add(r["note"])
    rows = []
    for p in places.values():
        p["n"] = p["names"].most_common(1)[0][0][0]
        rows.append({"n": p["n"], "c": p["c"], "lat": p["lat"], "lon": p["lon"], "m": sorted(p["m"]),
                     "sp": {k: dict(v) for k, v in p["sp"].items()}, "v": dict(p["v"]), "a": dict(p["a"]),
                     "note": "; ".join(sorted(set().union(*(notes.get(k, set()) for k in p["names"])))) })
    rows.sort(key=lambda r: -sum(r["v"].values()))
    (SITE / "data/places.js").write_text("window.BERN_PLACES=" + json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + ";\n")
    pc = Counter(o["precision"] or "ohne" for o in out)
    print(f"Karte: {len(rows)} Orte; Einträge {dict(pc)}")


def write_houses(entries: list[dict]) -> None:
    """Häuser in der Stadt Bern (tools/hn1882_match.py -> data/csv/08_entry_houses.csv) für die Karte."""
    path = ROOT / "data/csv/08_entry_houses.csv"
    if not path.exists():
        return
    by_id = {e["entry_id"]: e for e in entries}
    houses: dict[tuple, dict] = {}
    for h in csv.DictReader(path.open(encoding="utf-8")):
        if not h["lat"]:
            continue
        e = by_id.get(h["entry_id"])
        if not e:
            continue
        k = (h["lat"], h["lon"])
        d = houses.setdefault(k, {"lat": float(h["lat"]), "lon": float(h["lon"]), "a": h["new_1882"], "o": set(),
                                  "s": int(h["spread_m"] or 0), "e": []})
        d["o"].add(f"{h['quarter']} {h['old_no']}")
        name = " ".join(x for x in (e["forename"], e["surname"]) if x) or e["text"][:40]
        d["e"].append([e["volume"], name, e["occupation"][:40], e["address"], e["entry_id"],
                       1 if h["street_check"] == "passt nicht" else 0])
    rows = []
    for d in houses.values():
        d["o"] = sorted(d["o"])
        d["e"].sort()
        rows.append(d)
    (SITE / "data/houses.js").write_text("window.BERN_HOUSES=" + json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"Karte: {len(rows)} Häuser mit {sum(len(d['e']) for d in rows)} Einträgen")


if __name__ == "__main__":
    main()
