#!/usr/bin/env python3
"""Stufe 1: Seitenliste und Seitenbilder.

Liest config/volumes.json, holt die IIIF-Manifeste von e-rara (gecacht unter
data/erara/), lädt die Seitenbilder der gewählten PDF-Seiten in voller e-rara-
Auflösung nach data/pages/<band>/p<NNN>.jpg (nicht im Repo, siehe .gitignore)
und schreibt data/csv/01_pages.csv.

Seitenschlüssel ist überall die PDF-Seite (1-basiert) der Datei in
~/Documents/adressbücher_bern/. e-rara-Canvas k (1-basiert) = PDF-Seite k+1,
weil e-rara dem PDF ein Deckblatt voranstellt. Das Skript prüft das an der
Seitenzahl beider Quellen (PDF minus 1 == Canvas-Zahl).
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = Path.home() / "Documents" / "adressbücher_bern"


def get(url: str, dest: Path, tries: int = 4) -> None:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "adressbuecher-bern-frueh/0.1"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return
        except Exception as exc:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {url}: {exc}", file=sys.stderr)
            time.sleep(3 * (i + 1))


def main() -> None:
    import pymupdf

    cfg = json.loads((ROOT / "config" / "volumes.json").read_text())
    rows = []
    for v in cfg["volumes"]:
        vol = v["volume"]
        mid = v["iiif_manifest"].split("/")[-2]
        mpath = ROOT / "data" / "erara" / f"manifest_{mid}.json"
        if not mpath.exists():
            get(v["iiif_manifest"], mpath)
        canvases = json.loads(mpath.read_text())["sequences"][0]["canvases"]
        npdf = len(pymupdf.open(PDF_DIR / v["pdf"]))
        if npdf - 1 != len(canvases):
            sys.exit(f"{vol}: PDF {npdf} Seiten, e-rara {len(canvases)} Canvases — Zuordnung unsicher")
        for sec in v["sections"]:
            for page in range(sec["from"], sec["to"] + 1):
                c = canvases[page - 2]
                canvas_id = c["@id"].rstrip("/").split("/")[-1]
                svc = c["images"][0]["resource"]["service"]["@id"]
                img = ROOT / "data" / "pages" / vol / f"p{page:03d}.jpg"
                if not img.exists():
                    get(f"{svc}/full/full/0/default.jpg", img)
                rows.append({
                    "volume": vol, "page": page, "section": sec["section"],
                    "erara_canvas": canvas_id, "erara_label": c.get("label", ""),
                    "width": c.get("width", ""), "height": c.get("height", ""),
                    "image": f"{vol}/p{page:03d}.jpg",
                    "iiif_image": svc,
                })
        print(f"{vol}: {sum(1 for r in rows if r['volume'] == vol)} Seiten")
    out = ROOT / "data" / "csv" / "01_pages.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} Seiten -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
