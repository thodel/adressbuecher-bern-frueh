#!/usr/bin/env python3
"""Stadtberner Einträge über Quartier + alte Hausnummer den Häusern von 1882 zuordnen.

Quartiere: 1810 v./j./r./bl./n. (vert, jaune, rouge, blanc, noir), 1836/1839 gn./gb./r./w./s. Qr. bzw.
Drittel ausserhalb, 1822 nur Gasse + Nummer (Quartier aus den Gassen der Konkordanz), 1848 römische
Quartiernummern (Zuordnung zu den Farben aus den Daten bestimmt, siehe --roman).

Prüfung: Wo der Eintrag die Gasse nennt (1822, 1836, 1839), muss sie zu der Gasse passen, unter der die
Konkordanz von 1882 die alte Nummer führt.
Ergebnis: data/csv/08_entry_houses.csv
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from math import cos, hypot, radians
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Q1810 = {"v": "grün", "j": "gelb", "r": "rot", "bl": "weiss", "b": "weiss", "n": "schwarz"}
Q1836 = {"gn": "grün", "gr": "grün", "gb": "gelb", "r": "rot", "w": "weiss", "s": "schwarz"}


def fold(s: str) -> str:
    s = (s or "").lower().replace("ß", "ss").replace("ſ", "s")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    for a, b in [("th", "t"), ("y", "i"), ("ck", "k"), ("dt", "t")]:
        s = s.replace(a, b)
    s = re.sub(r"[^a-z]", "", s)
    s = re.sub(r"(.)\1", r"\1", s)
    for a, b in [("gaslein", "gasli"), ("gasschen", "gasli"), ("gaschen", "gasli"), ("gase", "g"), ("gas", "g"),
                 ("strase", "str"), ("drital", "drit"), ("dritel", "drit")]:
        s = s.replace(a, b)
    return s


ALIASES = [(fold(r["old_name"]), fold(r["name_1881"]))
           for r in csv.DictReader((ROOT / "config/street_aliases.csv").open(encoding="utf-8"))]


def street_ok(entry_street: str, group: str) -> bool | None:
    """Abgekürzte Gasse des Eintrags («Kramg.», «Metzgerngaße») gegen den Zwischentitel der Konkordanz;
    umbenannte Gassen nach config/street_aliases.csv."""
    a, b = fold(entry_street), fold(group)
    if not a or not b:
        return None
    if b.startswith(a) or a.startswith(b) or SequenceMatcher(None, a, b).ratio() >= 0.75:
        return True
    for o, n in ALIASES:
        if (o.startswith(a) or a.startswith(o)) and (n.startswith(b) or b.startswith(n)):
            return True
    return False


def base_no(s: str) -> str:
    m = re.search(r"(\d+)", s or "")
    return m.group(1) if m else ""


def quarter_of(e: dict) -> str:
    v, q = e["volume"], fold(e["quarter"])
    if v == "1810":
        q = re.sub(r"^q", "", q) if q not in ("") else q
        return Q1810.get(q, "")
    if v in ("1836", "1839"):
        q2 = re.sub(r"(qr|q)$", "", q)
        if q2 in Q1836:
            return Q1836[q2]
        for src in (e["quarter"], e["street"]):
            if "drit" in fold(src):
                return "D:" + fold(src).split("drit")[0]
    return ""


def main() -> None:
    conc = [r for r in csv.DictReader((ROOT / "data/csv/07_hausnummern_1882.csv").open(encoding="utf-8"))]
    idx = defaultdict(list)  # (quarter, base) -> rows
    for r in conc:
        q = r["quarter"] if r["part"] == "innere Stadt" else "D:" + fold(r["quarter"]).split("drit")[0]
        idx[(q, r["old_base"])].append(r)
    groups_by_quarter = defaultdict(set)
    for r in conc:
        if r["part"] == "innere Stadt":
            groups_by_quarter[r["quarter"]].add(r["group"])

    entries = [e for e in csv.DictReader((ROOT / "data/csv/04_entries.csv").open(encoding="utf-8"))
               if e["place"] in ("Bern", "") and e["house_no"] and e["volume"] in ("1810", "1822", "1836", "1839", "1848")]

    def place(rows: list[dict]) -> tuple | None:
        pts = [(float(r["lat"]), float(r["lon"])) for r in rows if r.get("lat")]
        if not pts:
            return None
        la = sum(p[0] for p in pts) / len(pts); lo = sum(p[1] for p in pts) / len(pts)
        spread = max(hypot((p[0] - la) * 111000, (p[1] - lo) * 111000 * cos(radians(la))) for p in pts)
        return la, lo, round(spread)

    # 1848: römische Nummer -> Farbe über Personen, die 1839 mit Farbe und Nummer stehen
    # gleicher Familienname und gleiche Hausnummer in 1810/1836/1839 (Familien bleiben im Haus)
    ref = defaultdict(set)
    for e in entries:
        q = quarter_of(e)
        if e["volume"] in ("1810", "1836", "1839") and q and not q.startswith("D:"):
            ref[(fold(e["surname"]), base_no(e["house_no"]))].add(q)
    votes = defaultdict(Counter)
    for e in entries:
        if e["volume"] == "1848":
            for q in ref.get((fold(e["surname"]), base_no(e["house_no"])), ()):
                votes[e["quarter"].strip().upper()][q] += 1
    roman = {}
    for rn, c in votes.items():
        col, n = c.most_common(1)[0]
        if n >= 5 and n >= 0.6 * sum(c.values()):
            roman[rn] = col
    print("1848 römisch -> Farbe:", {k: dict(v) for k, v in sorted(votes.items())}, "=>", roman, file=sys.stderr)

    out, stats = [], Counter()
    check = defaultdict(Counter)
    for e in entries:
        v, no = e["volume"], base_no(e["house_no"])
        q = roman.get(e["quarter"].strip().upper(), "") if v == "1848" else quarter_of(e)
        rows, how = [], ""
        if v == "1822" and e["street"]:
            # Quartier aus der Gasse: Zeilen mit dieser Nummer, deren Zwischentitel zur Gasse passt
            rows = [r for (qq, b), rs in idx.items() if b == no and not qq.startswith("D:") for r in rs
                    if street_ok(e["street"], r["group"])]
            qs = {r["quarter"] for r in rows}
            if len(qs) == 1:
                q, how = qs.pop(), "Gasse"
            elif len(qs) > 1:
                rows, how = [], "mehrdeutig"
        elif q:
            rows = idx.get((q, no), [])
        ok = None
        if rows and e["street"] and v in ("1836", "1839"):
            ok = any(street_ok(e["street"], r["group"]) for r in rows)
            check[v]["passt" if ok else "passt nicht"] += 1
        loc = place(rows)
        if how == "mehrdeutig":
            status = "mehrdeutig"
        elif rows:
            status = "gefunden" if loc else "ohne Verortung"
        elif not q:
            status = "ohne Quartier"
        else:
            status = "Nummer nicht in der Konkordanz"
        stats[(v, status)] += 1
        out.append({"entry_id": e["entry_id"], "volume": v, "address": e["address"], "quarter": q, "old_no": no,
                    "status": status, "n_rows": len(rows),
                    "group_1881": "; ".join(sorted({r["group"] for r in rows})),
                    "new_1882": "; ".join(sorted({f"{r['street']} {r['new']}" for r in rows if r["new"]})),
                    "street_check": "" if ok is None else ("passt" if ok else "passt nicht"),
                    "lat": round(loc[0], 6) if loc else "", "lon": round(loc[1], 6) if loc else "",
                    "spread_m": loc[2] if loc else ""})
    with (ROOT / "data/csv/08_entry_houses.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(out[0])); w.writeheader(); w.writerows(out)
    for v in ("1810", "1822", "1836", "1839", "1848"):
        print(v, {s: n for (vv, s), n in stats.items() if vv == v}, dict(check.get(v, {})))
    json.dump({"roman": roman, "votes": {k: dict(v) for k, v in votes.items()}},
              (ROOT / "data/geo/roman_1848.json").open("w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
