"""89_suche.py — Startseite mit Suche über alle Bände und Eintragsseiten (scripts/site_search.py).

    python scripts/90_site.py && python scripts/89_suche.py --out _site

Liest data/csv/04_entries.csv (Spalten wie COLS in scripts/90_site.py), die Bände aus config/volumes.json, die
e-rara-Seiten aus data/csv/01_pages.csv und die Häuser der Stadt aus data/csv/08_entry_houses.csv (alte
Quartiernummer → Adresse 1882 mit Koordinaten). Die bisherige Seite aus site/ (Suchen und Blättern) liegt im
Korrekturmodus unter korrektur/; Karte, Abdeckung und Methode bleiben an der Wurzel.

Karte der Suche: in der Stadt je Gasse (Koordinaten des gefundenen Hauses), Einträge ohne Gasse und alle im Kanton
je Ort (data/csv/06_entry_places.csv, nur sicher verortete Orte, nicht die «ungefähr» geerbten). Die Eintragsseite
zeigt das Haus (`point`), sonst den Ort. Gebiet = Quartier in der Stadt, sonst der Ort.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import site_nav  # noqa: E402
import site_search  # noqa: E402

S = importlib.import_module("90_site")
ROOT = S.ROOT
REPO = "https://github.com/thodel/adressbuecher-bern-frueh"
TOWN = "Bern"

CITY = {
    "key": "bern-frueh", "name": "Bern", "span": "1795–1848", "lang": "de",
    "title": "Frühe Berner Adressbücher 1795–1848",
    "lead": "Handelshäuser, Einwohner, Einsassen und Berufe aus sechs Berner Verzeichnissen 1795–1848 (Stadt und Kanton), "
            "maschinell gelesen und in Felder zerlegt. Gesucht wird über alle Bände.",
    "tagline": "Adressbücher · Einwohner · Häuser · Berufe",
    "repo": REPO, "center": [46.9480, 7.4474],
    # Korrekturmodus = die bisherige Seite (Zustand im #-Teil); die Feldsuche filtert auf genau diesen Eintrag
    "korr": "korrektur/#v=search&band={vol}&f=entry_id~eq~{id}",
    "nav": [["karte.html", "Karte der Orte"], ["abdeckung.html", "Abdeckung"], ["methoden.html", "Methode und Vorbehalte"]],
    "note": "Quellen: Universitätsbibliothek Bern, digitalisiert auf e-rara.ch. Gelesen mit Google Gemini; "
            "Lesefehler sind möglich – vor dem Zitieren am Seitenbild prüfen.",
    "page_note": "Seitenbilder: e-rara.ch, Universitätsbibliothek Bern. «Seite» ist die gedruckte Seite, sonst die PDF-Seite.",
}
LABELS = {  # wie LABEL in site/app.js
    "entry_id": "Kennung", "volume": "Band", "page": "PDF-Seite", "printed_page": "gedruckte Seite", "section": "Abschnitt",
    "line_from": "Zeile von", "line_to": "Zeile bis", "kind": "Art", "heading": "Rubrik", "place": "Ort",
    "surname": "Nachname", "forename": "Vorname", "title": "Anrede/Titel", "occupation": "Beruf / Gewerbe",
    "address": "Adresse", "quarter": "Quartier", "street": "Gasse", "house_no": "Hausnummer", "origin": "Herkunft",
    "birth_year": "Geburtsjahr", "household": "Haushalt", "note": "Vermerk", "continues": "Seitenwechsel",
    "text": "Wortlaut", "doubt": "Zweite Lesung weicht ab bei", "doubt_detail": "Abweichungen (1. → 2. Lesung)",
    "reader": "Gelesen mit", "run": "Lauf", "house_1882": "Adresse 1882",
}
# schon als Feld des Eintrags gezeigt (oder Verweis auf das Seitenbild)
CORE = {"entry_id", "volume", "printed_page", "section", "surname", "forename", "title", "occupation", "street",
        "house_no", "quarter", "origin", "heading", "text", "erara_url"}


def street_of(e: dict) -> str:
    """Gasse, sonst die Adresse, wenn sie einen Ortsnamen trägt (nicht nur «V, 193», «Q. v. 2.», «Nr. 29 gb. qr.»)."""
    if e["street"].strip():
        return e["street"].strip()
    a = e["address"].strip()
    words = [w for w in re.findall(r"[^\W\d_]+", a) if w.lower() not in {"nr", "qr", "no"}]
    return a if any(len(w) >= 4 for w in words) else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config/volumes.json").read_text(encoding="utf-8"))["volumes"]
    vols = {v["volume"]: v for v in cfg}
    CITY["volumes"] = {v["volume"]: v["short"] for v in sorted(cfg, key=lambda v: (int(v["year"]), v["volume"]))}
    parts: dict[str, str] = {}
    for v in sorted(cfg, key=lambda v: (int(v["year"]), v["volume"])):
        for s in v["sections"]:
            parts.setdefault(s["section"], s["label"])
    CITY["parts"] = parts

    canvas = {(p["volume"], p["page"]): p["erara_canvas"] for p in csv.DictReader((ROOT / "data/csv/01_pages.csv").open(encoding="utf-8"))}
    places = {r["entry_id"]: r for r in csv.DictReader((ROOT / "data/csv/06_entry_places.csv").open(encoding="utf-8"))
              if r["lat"] and r["precision"] == "ort"}
    houses = {}
    hp = ROOT / "data/csv/08_entry_houses.csv"
    if hp.exists():
        for h in csv.DictReader(hp.open(encoding="utf-8")):
            if h["lat"] and h["street_check"] != "passt nicht":
                houses[h["entry_id"]] = h

    with (ROOT / "data/csv/04_entries.csv").open(encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        entries = list(rd)
        cols = S.COLS + site_nav.extra_columns(entries, rd.fieldnames, S.COLS)

    recs = []
    for e in entries:
        v = vols.get(e["volume"])
        if not v:
            continue
        place = e.get("place", "").strip()
        in_town = place in ("", TOWN)
        h = houses.get(e["entry_id"]) if in_town else None
        g = places.get(e["entry_id"])
        street = street_of(e) if in_town else e["street"].strip()  # im Kanton keine Adresse als Gasse («im Dorf»)
        page_url = e.get("erara_url") or (
            f"https://www.e-rara.ch/bes_1/content/pageview/{canvas[(e['volume'], e['page'])]}"
            if canvas.get((e["volume"], e["page"])) else "")
        fields = [(c, e.get(c, "")) for c in cols if c not in CORE]
        if h:
            fields.append(("house_1882", h["new_1882"]))
        if street:  # Punkt der Gasse = ein gefundenes Haus an ihr; im Kanton keine
            lat, lon = (float(h["lat"]), float(h["lon"])) if h else (None, None)
        else:  # Punkt des Ortes (Bern, Thun, …)
            lat, lon = (float(g["lat"]), float(g["lon"])) if g else (None, None)
        point = [float(h["lat"]), float(h["lon"])] if h else ([float(g["lat"]), float(g["lon"])] if g else None)
        recs.append({
            "id": e["entry_id"], "vol": e["volume"], "year": int(v["year"]), "part": e["section"],
            "name": e["surname"], "forename": e["forename"], "title": e["title"], "occupation": e["occupation"],
            "street": street, "no": e["house_no"],
            "place": (g["map_place"] or place) if g and not street else "",
            "area": e["quarter"] if in_town else place,  # in der Stadt das Quartier, im Kanton der Ort
            "origin": e["origin"], "heading": e["heading"], "text": e["text"],
            "page": e["printed_page"] or e["page"], "page_url": page_url,
            "lat": lat, "lon": lon, "point": point, "fields": fields,
        })
    site_search.build(args.out, city=CITY, records=recs, labels={**site_nav.LABELS["de"], **LABELS})


if __name__ == "__main__":
    main()
