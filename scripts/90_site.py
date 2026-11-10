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
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

COLS = ["entry_id", "volume", "page", "printed_page", "section", "line_from", "line_to", "kind",
        "heading", "place", "surname", "forename", "title", "occupation", "address", "quarter",
        "street", "house_no", "origin", "birth_year", "household", "note", "continues", "text"]


def main() -> None:
    cfg = json.loads((ROOT / "config/volumes.json").read_text())["volumes"]
    pages = list(csv.DictReader((ROOT / "data/csv/01_pages.csv").open()))
    entries = list(csv.DictReader((ROOT / "data/csv/04_entries.csv").open()))
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
    ent_rows = [[e.get(c, "") for c in COLS] for e in entries]
    by_page = defaultdict(list)
    for l in lines:
        by_page[f"{l['volume']}|{l['page']}"].append([int(l["line"] or 0), l["text"]])

    (SITE / "data").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%d.%m.%Y, %H:%M")
    (SITE / "data/meta.js").write_text(
        "window.BERN_META=" + json.dumps({"volumes": vols, "pages": page_rows, "built": stamp,
                                          "entry_cols": COLS}, ensure_ascii=False) + ";\n")
    (SITE / "data/entries.js").write_text("window.BERN_ENTRIES=" + json.dumps(ent_rows, ensure_ascii=False, separators=(",", ":")) + ";\n")
    (SITE / "data/lines.js").write_text("window.BERN_LINES=" + json.dumps(by_page, ensure_ascii=False, separators=(",", ":")) + ";\n")

    kinds = Counter(e["kind"] for e in entries)
    print(f"site/data: {len(ent_rows)} Einträge, {len(lines)} Zeilen, {len(page_rows)} Seiten; Arten {dict(kinds)}")


if __name__ == "__main__":
    main()
