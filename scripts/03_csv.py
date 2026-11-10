#!/usr/bin/env python3
"""Stufe 3: Gemini-Antworten eines Laufs in CSV überführen.

  data/csv/00_volumes.csv      Bände
  data/csv/02_lines.csv        Zeilen je Seite (diplomatisch, wie gelesen)
  data/csv/03_page_status.csv  Lesestatus je Seite (ok, Abbruchgrund, Tokens)
  data/csv/04_entries.csv      strukturierte Einträge mit Seiten- und Zeilenherkunft

Nur Seiten mit ok=true liefern Zeilen und Einträge; die übrigen stehen mit ihrem
Fehler in 03_page_status.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["surname", "forename", "title", "occupation", "address", "quarter", "street",
          "house_no", "origin", "birth_year", "household", "note"]


def clean(v) -> str:
    if v is None:
        return ""
    return " ".join(str(v).split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config/volumes.json").read_text())["volumes"]
    pages = list(csv.DictReader((ROOT / "data/csv/01_pages.csv").open()))
    csvdir = ROOT / "data/csv"

    with (csvdir / "00_volumes.csv").open("w", newline="") as f:
        cols = ["volume", "year", "short", "title", "publisher", "language", "doi", "shelfmark",
                "iiif_manifest", "pdf", "sections", "notes"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for v in cfg:
            row = {k: v.get(k, "") for k in cols}
            row["sections"] = "; ".join(f"{s['section']} PDF {s['from']}–{s['to']}" for s in v["sections"])
            w.writerow(row)

    lines_out, status_out, entries_out = [], [], []
    last_heading: dict[str, str] = {}  # Band -> letzte Rubrik, für Einträge oben auf der Folgeseite
    for p in pages:
        vol, page = p["volume"], int(p["page"])
        path = ROOT / "data/raw" / args.run / vol / f"p{page:03d}.json"
        erara = f"https://www.e-rara.ch/bes_1/content/pageview/{p['erara_canvas']}"
        if not path.exists():
            status_out.append({"volume": vol, "page": page, "section": p["section"], "status": "fehlt"})
            continue
        rec = json.loads(path.read_text())
        obj = rec.get("parsed") or {}
        u = rec.get("usage") or {}
        status_out.append({
            "volume": vol, "page": page, "section": p["section"],
            "status": "ok" if rec.get("ok") else "fehler",
            "problems": " | ".join(rec.get("problems") or []),
            "finish_reason": rec.get("finish_reason", ""),
            "printed_page": clean(obj.get("printed_page")),
            "running_head": clean(obj.get("running_head")),
            "n_lines": len(obj.get("lines") or []), "n_entries": len(obj.get("entries") or []),
            "first_entry_continues": obj.get("first_entry_continues", ""),
            "last_entry_continues": obj.get("last_entry_continues", ""),
            "model": rec.get("model"), "prompt_sha": rec.get("prompt_sha"),
            "tokens_in": u.get("prompt"), "tokens_out": u.get("output"), "tokens_thought": u.get("thoughts"),
            "finished": rec.get("finished"),
        })
        if not rec.get("ok"):
            continue
        for l in obj["lines"]:
            lines_out.append({"volume": vol, "page": page, "line": l.get("n"), "text": l.get("text", "")})
        seen: dict[str, int] = {}
        for i, e in enumerate(obj["entries"]):
            base = f"{vol}-p{page:03d}-L{int(e.get('line_from') or 0):03d}"
            seen[base] = seen.get(base, 0) + 1
            eid = base if seen[base] == 1 else f"{base}-{seen[base]}"
            cont = ""
            if i == 0 and obj.get("first_entry_continues"):
                cont = "von_vorseite"
            if i == len(obj["entries"]) - 1 and obj.get("last_entry_continues"):
                cont = (cont + ";" if cont else "") + "auf_folgeseite"
            row = {"entry_id": eid, "volume": vol, "page": page, "printed_page": clean(obj.get("printed_page")),
                   "section": p["section"], "line_from": e.get("line_from"), "line_to": e.get("line_to"),
                   "kind": clean(e.get("kind")), "heading": clean(e.get("heading")), "place": clean(e.get("place"))}
            if not row["heading"] and last_heading.get(vol):
                row["heading"] = last_heading[vol]
                row["note"] = "Rubrik von Vorseite"
            if row["heading"]:
                last_heading[vol] = row["heading"]
            inherited = row.pop("note", "")
            row.update({k: clean(e.get(k)) for k in FIELDS})
            if inherited:
                row["note"] = "; ".join(x for x in (row["note"], inherited) if x)
            row.update({"continues": cont, "text": clean(e.get("text")), "erara_url": erara,
                        "reader": rec.get("model"), "run": args.run})
            entries_out.append(row)

    def write(name, rows):
        if not rows:
            return
        cols = list(rows[0])
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        with (csvdir / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {len(rows)} Zeilen")

    write("02_lines.csv", lines_out)
    write("03_page_status.csv", status_out)
    write("04_entries.csv", entries_out)


if __name__ == "__main__":
    main()
