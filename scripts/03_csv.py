#!/usr/bin/env python3
"""Stufe 3: Gemini-Antworten eines Laufs in CSV überführen.

  data/csv/00_volumes.csv      Bände
  data/csv/02_lines.csv        Zeilen je Seite (diplomatisch, wie gelesen)
  data/csv/03_page_status.csv  Lesestatus je Seite (ok, Abbruchgrund, Tokens)
  data/csv/04_entries.csv      strukturierte Einträge mit Seiten- und Zeilenherkunft
  data/csv/05_second_reading.csv  Vergleich mit einer zweiten Lesung je Seite (mit --second)

Mit --second <lauf> wird jede Zeile der ersten Lesung mit der zweiten verglichen
(02_lines.csv: text_b, wo sie abweicht) und je Eintrag geprüft, ob die Wörter der
Felder Name, Vorname, Beruf, Strasse, Hausnummer, Herkunft und Geburtsjahr auch in
der zweiten Lesung derselben Zeilen stehen (04_entries.csv: doubt, doubt_detail).

Nur Seiten mit ok=true liefern Zeilen und Einträge; die übrigen stehen mit ihrem
Fehler in 03_page_status.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["surname", "forename", "title", "occupation", "address", "quarter", "street",
          "house_no", "origin", "birth_year", "household", "note"]


def clean(v) -> str:
    if v is None:
        return ""
    return " ".join(str(v).split())


CHECK = ["surname", "forename", "occupation", "street", "house_no", "origin", "birth_year"]
WORD = re.compile(r"[\wß']+")
SKIP = {"ꝛc", "rc", "etc", "c", "&c"}  # Abkürzung «etc.»: verschieden geschrieben, ohne Belang


def fold(t: str) -> str:
    """Für den Vergleich gleichgesetzt: ſ/s, ß/ss, Trenn- und Gedankenstriche, Sperrsatz."""
    t = unicodedata.normalize("NFC", t or "").replace("ſ", "s").replace("ß", "ss")
    t = re.sub(r"[=⸗¬–—]", "-", t)
    t = re.sub(r"\b(\w) (?=\w\b)", r"\1", t)  # g e s p e r r t -> gesperrt
    return t


def norm(t: str) -> str:
    return " ".join(fold(t).split())


def dehyphen(t: str) -> str:
    return re.sub(r"(\w)\s*-\s+(?=\w)", r"\1", t)


def words(t: str) -> set[str]:
    t = fold(t)
    return set(WORD.findall(t)) | set(WORD.findall(dehyphen(t)))


def align(a: list[str], b: list[str]) -> dict[int, str | None]:
    """Index in a -> zugeordnete Zeile aus b (None, wenn keine passt)."""
    out: dict[int, str | None] = {}
    sm = SequenceMatcher(None, [norm(x) for x in a], [norm(x) for x in b], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        for k in range(i2 - i1):
            if tag == "equal":
                out[i1 + k] = b[j1 + k]
            elif tag == "replace" and k < j2 - j1 and SequenceMatcher(None, a[i1 + k], b[j1 + k]).ratio() >= 0.5:
                out[i1 + k] = b[j1 + k]
            else:
                out[i1 + k] = None
    return out


def chardiff(x: str, y: str) -> int:
    return sum(max(i2 - i1, j2 - j1) for t, i1, i2, j1, j2 in
               SequenceMatcher(None, x, y, autojunk=False).get_opcodes() if t != "equal")


RN_FIELDS = ["heading", "place", "surname", "forename", "street", "origin", "household"]


def rn_fix(text: str, other: set[str]) -> tuple[str, list[str]]:
    """Fraktur-R wird oft als N gelesen, kaum umgekehrt. Ein Wort, das mit N beginnt, wird zu R,
    wenn eine andere Lesung derselben Seite genau dieses Wort mit R hat."""
    changed = []

    def sub(m):
        w = m.group(0)
        r = "R" + w[1:]
        if len(w) > 2 and fold(r) in other and fold(w) != fold(r):
            changed.append(f"{w} → {r}")
            return r
        return w
    return re.sub(r"\bN[\wß']+", sub, text or ""), changed


def page_words(run: str, vol: str, page: int) -> set[str]:
    path = ROOT / "data/raw" / run / vol / f"p{page:03d}.json"
    if not path.exists():
        return set()
    rec = json.loads(path.read_text())
    if not rec.get("ok"):
        return set()
    return words(" ".join(l.get("text") or "" for l in rec["parsed"]["lines"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--second", help="zweiter Lauf zum Vergleich, z. B. full-v2")
    ap.add_argument("--prefer", default="", help="Läufe mit Neulesungen einzelner Seiten, die --run ersetzen "
                    "(kommagetrennt, z. B. fix-high); gilt nur für gültige Seiten")
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

    lines_out, status_out, entries_out, compare_out = [], [], [], []
    SALUTATION_HEAD = re.compile(r"^(Herr|Herren|Monsieur|Messieurs)\.?(?=\s*(/|$))")
    last_heading: dict[str, str] = {}  # Band -> letzte Rubrik, für Einträge oben auf der Folgeseite
    for p in pages:
        vol, page = p["volume"], int(p["page"])
        run_used = args.run
        for pr in filter(None, args.prefer.split(",")):
            pp_ = ROOT / "data/raw" / pr / vol / f"p{page:03d}.json"
            if pp_.exists() and json.loads(pp_.read_text()).get("ok"):
                run_used = pr
        path = ROOT / "data/raw" / run_used / vol / f"p{page:03d}.json"
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
            "finished": rec.get("finished"), "run": run_used,
        })
        if not rec.get("ok"):
            continue
        bmap: dict[int, str | None] | None = None
        btext_page = ""
        if args.second:
            bpath = ROOT / "data/raw" / args.second / vol / f"p{page:03d}.json"
            brec = json.loads(bpath.read_text()) if bpath.exists() else {}
            if brec.get("ok"):
                blines = [l.get("text") or "" for l in brec["parsed"]["lines"]]
                alines = [l.get("text") or "" for l in obj["lines"]]
                m_ = align(alines, blines)
                bmap = {obj["lines"][i].get("n"): t for i, t in m_.items()}
                btext_page = " ".join(blines)
                same = sum(1 for i, t in m_.items() if t is not None and norm(t) == norm(alines[i]))
                paired = [(alines[i], t) for i, t in m_.items() if t is not None]
                chars = sum(len(x) for x, _ in paired) or 1
                compare_out.append({"volume": vol, "page": page, "lines_a": len(alines), "lines_b": len(blines),
                                    "lines_same": same, "lines_differ": len(paired) - same,
                                    "lines_unpaired": len(alines) - len(paired),
                                    "chars_differ": sum(chardiff(x, y) for x, y in paired),
                                    "share_chars_differ": round(sum(chardiff(x, y) for x, y in paired) / chars, 4),
                                    "run_b": args.second, "model_b": brec.get("model")})
            else:
                compare_out.append({"volume": vol, "page": page, "run_b": args.second,
                                    "note": "zweite Lesung fehlt oder ungültig"})
        for l in obj["lines"]:
            row = {"volume": vol, "page": page, "line": l.get("n"), "text": l.get("text", "")}
            if args.second:
                bt = bmap.get(l.get("n")) if bmap is not None else None
                row["text_b"] = "" if bt is None or norm(bt) == norm(row["text"]) else bt
                row["agree"] = "" if bmap is None else ("ohne_gegenstueck" if bt is None else
                                                         ("ja" if norm(bt) == norm(row["text"]) else "nein"))
            lines_out.append(row)
        atext = {l.get("n"): l.get("text", "") for l in obj["lines"]}
        other_runs = {args.run, args.second, *filter(None, args.prefer.split(","))} - {run_used, None}
        other_w: set[str] = set().union(*(page_words(r, vol, page) for r in other_runs)) if other_runs else set()
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
            # 1795: «Herr» / «Monsieur» steht als Spaltenkopf über den Namen; das Modell hat ihn
            # teils als Rubrik genommen. Dann gilt die vorige echte Rubrik (Ort bzw. Gewerbe).
            row["heading"], rn_head = rn_fix(row["heading"], other_w)
            m = SALUTATION_HEAD.match(row["heading"] or "") if vol == "1795" else None
            if m:
                rest = row["heading"][m.end():].strip(" /")
                row["heading"] = rest or last_heading.get(vol, "") or row["place"]
                row["note"] = f"Spaltenkopf «{m.group(1)}» nicht als Rubrik übernommen"
            if not row["heading"] and last_heading.get(vol):
                row["heading"] = last_heading[vol]
                row["note"] = "Rubrik von Vorseite"
            if row["heading"]:
                last_heading[vol] = row["heading"]
            inherited = row.pop("note", "")
            row.update({k: clean(e.get(k)) for k in FIELDS})
            if inherited:
                row["note"] = "; ".join(x for x in (row["note"], inherited) if x)
            rn_all = list(rn_head)
            for k in RN_FIELDS[2:]:
                row[k], ch = rn_fix(row[k], other_w)
                rn_all += [c for c in ch if c not in rn_all]
            if rn_all:
                row["note"] = "; ".join(x for x in (row["note"], "R statt N nach anderer Lesung: " + ", ".join(rn_all)) if x)
            if vol == "1848" and row["kind"] == "person" and not row["surname"] and row["heading"]:
                # Haushalt oben auf der Seite: Familienname steht als Zwischentitel auf der Vorseite
                row["surname"] = re.split(r"\s+a\.\s", row["heading"])[0].strip(" .")
                row["note"] = "; ".join(x for x in (row["note"], "Name aus Zwischentitel der Vorseite") if x)
            row.update({"continues": cont, "text": clean(e.get("text")), "erara_url": erara,
                        "reader": rec.get("model"), "run": run_used})
            if args.second:
                row["doubt"], row["doubt_detail"] = "", ""
                if bmap is not None:
                    try:
                        rng = range(int(e.get("line_from")), int(e.get("line_to") or e.get("line_from")) + 1)
                    except (TypeError, ValueError):
                        rng = range(0)
                    a_w = words(" ".join(atext.get(n, "") for n in rng))
                    bl = [bmap.get(n) for n in rng]
                    b_src = " ".join(t for t in bl if t) if bl and all(bl) else btext_page
                    b_w = words(b_src)
                    fields, detail = [], []
                    for k in CHECK:
                        for wd in WORD.findall(fold(row.get(k, ""))):
                            # nur Wörter prüfen, die in der ersten Lesung dieser Zeilen stehen
                            # (übernommene oder aufgelöste Angaben lassen sich nicht vergleichen)
                            if wd in SKIP or len(wd) < 2 and not wd.isdigit() or wd not in a_w or wd in b_w:
                                continue
                            alt = get_close_matches(wd, list(b_w), n=1, cutoff=0.6)
                            if k not in fields:
                                fields.append(k)
                            detail.append(f"{k}: {wd} → {alt[0] if alt else '?'}")
                    row["doubt"] = ";".join(fields)
                    row["doubt_detail"] = "; ".join(detail)
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
    if args.second:
        write("05_second_reading.csv", compare_out)


if __name__ == "__main__":
    main()
