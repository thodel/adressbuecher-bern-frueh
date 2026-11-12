#!/usr/bin/env python3
"""Lesungen der Häuser-Nummerirung 1882 zu einer Tabelle zusammenführen und zwei Lesungen vergleichen.

  tools/hn1882_table.py --run v1 --second v2
Ergebnis: data/csv/07_hausnummern_1882.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLOURS = {"roth": "rot", "rot": "rot", "weiss": "weiss", "weiß": "weiss", "grün": "grün", "gelb": "gelb", "schwarz": "schwarz"}
COLS = ["part", "district", "quarter", "group", "old", "old_base", "old_suffix", "und", "new", "street", "hand", "note",
        "page", "printed_page", "agree", "second_new", "second_street"]


def norm_no(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("u.", "u. ").replace(" ,", ",")).strip()


def heading_key(h: str) -> tuple[str, str]:
    """Kopfzeile -> (Teil, Quartier/Bezirk)."""
    hl = (h or "").lower()
    for k, v in COLOURS.items():
        if re.search(rf"\b{k}\w*\s+quartier", hl):
            return "innere Stadt", v
    m = re.search(r"stadtbezirk\s+([\wäöü]+)", hl)
    if m:
        return "Stadtbezirke", m.group(1)
    return "", ""


def load(run: str) -> list[dict]:
    rows, part, district = [], "", ""
    for f in sorted((ROOT / "data/raw/hn1882" / run).glob("p*.json")):
        rec = json.loads(f.read_text())
        if not rec.get("ok"):
            print("nicht gelesen:", f.name)
            continue
        obj = rec["parsed"]
        if not obj["rows"]:
            continue
        p, d = heading_key(obj.get("page_heading", ""))
        if d:
            part, district = p, d
        for i, r in enumerate(obj["rows"]):
            old = norm_no(str(r.get("old", "")))
            m = re.match(r"^(\d+)\s*(.*)$", old)
            rows.append({
                "part": part, "district": district,
                "quarter": district if part == "innere Stadt" else "",
                "group": (r.get("group") or "").rstrip(". "),
                "old": old, "old_base": m.group(1) if m else "", "old_suffix": m.group(2).strip() if m else "",
                "und": "ja" if r.get("und") else "", "new": norm_no(str(r.get("new", ""))),
                "street": (r.get("street") or "").strip().rstrip("."), "hand": "ja" if r.get("hand") else "",
                "note": r.get("note") or "", "page": rec["page"], "printed_page": obj.get("printed_page", ""), "_i": i})
    # Neues Quartier mitten auf der Seite («IV. Weisses Quartier» unter dem grünen): die Nummern beginnen
    # wieder bei 1. Reihenfolge im Heft: rot, gelb, grün, weiss, schwarz.
    ORDER = ["rot", "gelb", "grün", "weiss", "schwarz"]
    cur, last, switch_page = "", {}, None
    for r in rows:
        if r["part"] != "innere Stadt":
            continue
        if not cur or ORDER.index(r["quarter"]) > ORDER.index(cur):
            cur = r["quarter"]
            switch_page = None
        if not r["old_base"]:
            r["quarter"] = r["district"] = cur
            continue
        b = int(r["old_base"])
        prev_b = last.get(cur, 0)
        if b <= 2 and prev_b > 40 and cur != "schwarz":
            cur = ORDER[ORDER.index(cur) + 1]
            switch_page = r["page"]
        # rechte Spalte setzt oft noch das vorige Quartier fort (268 nach 267)
        q = cur
        i = ORDER.index(cur)
        if i > 0 and r["page"] == switch_page:
            pq = ORDER[i - 1]
            if pq in last and b >= last[pq] - 3 and (b - last[pq]) < (b - last.get(cur, -999)) and b > 20:
                q = pq
        last[q] = max(last.get(q, 0), b) if b - last.get(q, 0) < 60 or q not in last else last[q]
        r["quarter"] = r["district"] = q
    # Stadtbezirke: das Drittel steht im Zwischentitel
    for r in rows:
        if r["part"] == "Stadtbezirke":
            r["quarter"] = r["group"]
    return rows


ABBR = [(r"\bAeuss(\.\s*|\s+)", "Aeusseres "), (r"(?<=s)g\.?$", "gasse"), (r"g[äe]?c?hn\.?$", "gässchen"), (r"\bInn\.?\s+", "Inneres "), (r"pl\.?$", "platz"), (r"str\.?$", "strasse"),
        (r"gchn\.?$", "gässchen"), (r"gässch\.?$", "gässchen"), (r"Promen\.?$", "Promenade"), (r"w\.?$", "weg")]


def expand(s: str) -> str:
    s = (s or "").strip().rstrip(".")
    for a, b in ABBR:
        s2 = re.sub(a, b, s)
        if s2 != s:
            s = s2
    return re.sub(r"\s+", " ", s).strip()


def nos(new: str) -> frozenset:
    return frozenset(re.findall(r"\d+\s*[a-z]?\b", (new or "").replace(" ", "")))


def same(a: tuple, b: tuple) -> bool:
    return nos(a[0]) == nos(b[0]) and expand(a[1]).lower() == expand(b[1]).lower()


def key(r: dict) -> tuple:
    return (r["district"], r["quarter"], r["old"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v1")
    ap.add_argument("--second", default="v2")
    args = ap.parse_args()
    a = load(args.run)
    b = defaultdict(list)
    for r in a:
        r["street"] = expand(r["street"])
    if args.second:
        for r in load(args.second):
            b[key(r)].append((r["new"], expand(r["street"])))
    stats = defaultdict(int)
    for r in a:
        if not args.second:
            break
        other = b.get(key(r))
        if not other:
            r["agree"] = "ohne_gegenstueck"
        elif any(same((r["new"], r["street"]), o) for o in other):
            r["agree"] = "ja"
            # ausgeschriebener Name der anderen Lesung, wo diese abgekürzt hat
            for o in other:
                if same((r["new"], r["street"]), o) and len(o[1]) > len(r["street"]):
                    r["street"] = o[1]
        else:
            r["agree"] = "nein"
            r["second_new"], r["second_street"] = other[0]
        stats[r["agree"]] += 1
    # Berichtigungen nach Prüfung am Bild (config/hn1882_fix.csv)
    fixes = {(x["quarter"], x["old"], x["und"]): x for x in csv.DictReader((ROOT / "config/hn1882_fix.csv").open(encoding="utf-8"))}
    for r in a:
        x = fixes.get((r["quarter"], r["old"], r["und"]))
        if x:
            r["new"], r["street"] = x["new"], x["street"]
            r["note"] = "; ".join(filter(None, [r["note"], "berichtigt: " + x["note"]]))
            r["agree"] = "berichtigt"
    out = ROOT / "data/csv/07_hausnummern_1882.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS, extrasaction="ignore"); w.writeheader(); w.writerows(a)
    by = defaultdict(int)
    for r in a:
        by[(r["part"], r["district"])] += 1
    print(len(a), "Zeilen", dict(stats)); print(dict(by))


if __name__ == "__main__":
    main()
