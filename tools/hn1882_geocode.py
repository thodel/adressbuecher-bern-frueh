#!/usr/bin/env python3
"""Die neuen Adressen von 1882 (Strasse + Nummer) mit dem amtlichen Gebäudeadressverzeichnis verorten.

1. Strassenname von 1882 -> heutiger Strassenname (swisstopo-Suche, Schreibvergleich; Ausnahmen in
   config/streets_1882.csv).
2. Alle heutigen Adressen dieser Strasse in Bern (Ebene ch.swisstopo.amtliches-gebaeudeadressverzeichnis).
3. Nummer: genau (mit Buchstabe) -> ohne Buchstabe -> zwischen den Nachbarnummern derselben Strassenseite
   -> Strassenmitte.
Schreibt lat/lon/geo_* in data/csv/07_hausnummern_1882.csv. Antworten zwischengespeichert in data/geo/.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data/csv/07_hausnummern_1882.csv"
CACHE = ROOT / "data/geo/gwr_cache.json"
FIX = ROOT / "config/streets_1882.csv"
SEARCH = "https://api3.geo.admin.ch/rest/services/api/SearchServer?type=locations&origins=address&limit=20&sr=4326&searchText="
FIND = ("https://api3.geo.admin.ch/rest/services/api/MapServer/find?layer=ch.swisstopo.amtliches-gebaeudeadressverzeichnis"
        "&searchField=stn_label&returnGeometry=true&sr=4326&contains=false&searchText=")
cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}


def get(url: str):
    if url not in cache:
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    cache[url] = json.load(r)
                break
            except OSError:
                if attempt == 4:
                    CACHE.write_text(json.dumps(cache))
                    raise
                time.sleep(2 ** attempt)
        time.sleep(0.1)
        if len(cache) % 20 == 0:
            CACHE.write_text(json.dumps(cache))
    return cache[url]


def fold(s: str) -> str:
    s = s.lower().replace("ß", "ss")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.replace("strasse", "str").replace("gässchen", "gasschen").replace("gaesschen", "gasschen")
    for a, b in [("th", "t"), ("y", "i"), ("ie", "i"), ("ck", "k")]:
        s = s.replace(a, b)
    s = re.sub(r"[^a-z]", "", s)
    return re.sub(r"(.)\1", r"\1", s)


def today_street(name: str, fixes: dict) -> tuple[str, str]:
    if name in fixes:
        return fixes[name], "hand"
    res = get(SEARCH + urllib.parse.quote(f"{name} Bern")).get("results", [])
    best, score = "", 0.0
    for r in res:
        lab = re.sub("<[^>]+>", "", r["attrs"]["label"])
        m = re.match(r"^(.*?)\s+\d+\w*\s+(\d{4})\s+(.*)$", lab)
        if not m or "Bern" not in m.group(3):
            continue
        s = SequenceMatcher(None, fold(name), fold(m.group(1))).ratio()
        if s > score:
            best, score = m.group(1), s
    if score >= 0.8:
        return best, f"auto {score:.2f}"
    # anderer Strassentyp: «Brunnhofstrasse» -> «Brunnhofweg»
    m = re.match(r"^(.*?)(strasse|str|weg|gasse|gässchen|platz|rain|halde)$", name, re.I)
    if m and len(m.group(1)) >= 4:
        core = m.group(1)
        for typ in ("strasse", "weg", "gasse", "rain", "platz"):
            for r in get(SEARCH + urllib.parse.quote(f"{core}{typ} Bern")).get("results", []):
                lab = re.sub("<[^>]+>", "", r["attrs"]["label"])
                mm = re.match(r"^(.*?)\s+\d+\w*\s+(\d{4})\s+(.*)$", lab)
                if not mm or "Bern" not in mm.group(3):
                    continue
                c2 = re.match(r"^(.*?)(strasse|weg|gasse|gässchen|platz|rain|halde|quai)?$", mm.group(1), re.I).group(1)
                s2 = SequenceMatcher(None, fold(core), fold(c2)).ratio()
                if s2 >= 0.85 and s2 > score:
                    best, score = mm.group(1), s2
        if score >= 0.85:
            return best, f"anderer Strassentyp {score:.2f}"
    return "", f"nicht gefunden (bestes {best} {score:.2f})"


def addresses(street: str) -> dict[str, tuple[float, float]]:
    d = get(FIND + urllib.parse.quote(street))
    out = {}
    for x in d.get("results", []):
        a = x["attributes"]
        if a.get("com_name") == "Bern" and a.get("stn_label") == street and x.get("geometry"):
            out[a["adr_number"].lower().replace(" ", "")] = (x["geometry"]["y"], x["geometry"]["x"])
    return out


def numbers(new: str) -> list[str]:
    """«15, 15 a u. 15 b» -> ['15', '15a', '15b']; «110 bis 110 e» -> ['110', '110e']."""
    parts = re.split(r",|\bu\.|\bund\b|\bbis\b|\bn\.", new)
    out = []
    for p in parts:
        m = re.match(r"^\s*(\d+)\s*([a-z])?\b", p.strip())
        if m:
            out.append(m.group(1) + (m.group(2) or ""))
    return out


def locate(nos: list[str], adr: dict) -> tuple[float, float, str] | None:
    if not adr:
        return None
    for n in nos:
        if n in adr:
            return (*adr[n], "genau")
    for n in nos:
        base = re.match(r"\d+", n).group(0)
        if base in adr:
            return (*adr[base], "ohne Buchstabe")
        cands = [k for k in adr if re.match(rf"^{base}[a-z]$", k)]
        if cands:
            return (*adr[sorted(cands)[0]], "anderer Buchstabe")
    if nos:
        b = int(re.match(r"\d+", nos[0]).group(0))
        same = sorted((int(re.match(r"\d+", k).group(0)), v) for k, v in adr.items()
                      if re.match(r"\d+", k) and int(re.match(r"\d+", k).group(0)) % 2 == b % 2)
        lo = [v for n, v in same if n < b]
        hi = [v for n, v in same if n > b]
        if lo and hi:
            return ((lo[-1][0] + hi[0][0]) / 2, (lo[-1][1] + hi[0][1]) / 2, "zwischen Nachbarnummern")
        if lo or hi:
            v = (lo or hi)[-1 if lo else 0]
            return (*v, "nächste Nummer derselben Seite")
    ys = [v[0] for v in adr.values()]; xs = [v[1] for v in adr.values()]
    return (sum(ys) / len(ys), sum(xs) / len(xs), "Strassenmitte")


def main() -> None:
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    fixes = {}
    if FIX.exists():
        fixes = {r["street_1882"]: r["street_today"] for r in csv.DictReader(FIX.open(encoding="utf-8"))}
    streets = sorted({r["street"] for r in rows if r["street"]})
    mapping = {}
    for i, s in enumerate(streets):
        mapping[s] = today_street(s, fixes)
        if i % 25 == 0:
            CACHE.parent.mkdir(parents=True, exist_ok=True); CACHE.write_text(json.dumps(cache))
    adr = {t: addresses(t) for t, _ in set(mapping.values()) if t}
    CACHE.write_text(json.dumps(cache))
    stats = {}
    for r in rows:
        t, how = mapping.get(r["street"], ("", ""))
        r["street_today"], r["street_match"] = t, how
        loc = locate(numbers(r["new"]), adr.get(t, {})) if t else None
        r["lat"], r["lon"], r["geo_precision"] = (round(loc[0], 6), round(loc[1], 6), loc[2]) if loc else ("", "", "ohne")
        stats[r["geo_precision"]] = stats.get(r["geo_precision"], 0) + 1
    # Ohne heutige Strasse (abgegangene Gassen): zwischen den nächsten alten Nummern desselben Quartiers
    placed = {}
    for r in rows:
        if r["lat"] and r["old_base"]:
            placed.setdefault((r["quarter"], int(r["old_base"])), []).append((float(r["lat"]), float(r["lon"])))
    for r in rows:
        if r["lat"] or not r["old_base"]:
            continue
        b = int(r["old_base"])
        lo = next((placed[(r["quarter"], b - d)] for d in range(0, 4) if (r["quarter"], b - d) in placed), None)
        hi = next((placed[(r["quarter"], b + d)] for d in range(1, 4) if (r["quarter"], b + d) in placed), None)
        pts = (lo or []) + (hi or [])
        if pts:
            r["lat"] = round(sum(p[0] for p in pts) / len(pts), 6); r["lon"] = round(sum(p[1] for p in pts) / len(pts), 6)
            r["geo_precision"] = "nach alten Nachbarnummern im Quartier"
            stats["ohne"] -= 1; stats[r["geo_precision"]] = stats.get(r["geo_precision"], 0) + 1
    cols = list(rows[0].keys())
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(rows)
    print("Strassen:", len(streets), "ohne heutige Entsprechung:",
          [s for s in streets if not mapping[s][0]], file=sys.stderr)
    print("Verortung:", stats)


if __name__ == "__main__":
    main()
