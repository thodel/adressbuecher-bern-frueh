#!/usr/bin/env python3
"""Ortsnamen aus 04_entries.csv mit der Suche von swisstopo (api3.geo.admin.ch) verorten.

Schritt 1 (dieses Skript): für jede Schreibung Kandidaten holen (zwischengespeichert in
data/geo/swisstopo_cache.json), bewerten und mit dem Seitenkontext auswählen.
Ergebnis: config/places.csv (Schreibung -> Ort, Koordinaten, Verfahren); wird bei jedem Lauf neu
geschrieben. Korrekturen von Hand stehen in config/places_hand.csv (heutiger Name zum Nachschlagen).
"""
import csv, json, re, sys, time, unicodedata, urllib.parse, urllib.request
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from math import hypot
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/geo/swisstopo_cache.json"
OUT = ROOT / "config/places.csv"
API = "https://api3.geo.admin.ch/rest/services/api/SearchServer?type=locations&origins=gg25,gazetteer&limit=15&sr=4326&searchText="
COLS = ["place", "name", "kind", "canton", "lat", "lon", "method", "score", "n_entries", "volumes", "source", "note"]

cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}


def search(q: str) -> list[dict]:
    if q not in cache:
        with urllib.request.urlopen(API + urllib.parse.quote(q), timeout=30) as r:
            res = json.load(r).get("results", [])
        cache[q] = [{"origin": x["attrs"]["origin"], "label": re.sub("<[^>]+>", "", x["attrs"]["label"]).replace("\n", " "),
                     "lat": x["attrs"]["lat"], "lon": x["attrs"]["lon"], "id": x["attrs"].get("featureId")} for x in res]
        time.sleep(0.15)
    return cache[q]


def fold(s: str) -> str:
    s = s.lower().replace("ß", "ss").replace("ſ", "s")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z ]", " ", s)
    for a, b in [("th", "t"), ("y", "i"), ("tz", "z"), ("ck", "k"), ("dt", "t"), ("ph", "f")]:
        s = s.replace(a, b)
    s = re.sub(r"(.)\1", r"\1", s)  # Doppelbuchstaben
    s = re.sub(r"^(la|le|les|l) ", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


ART = r"(im|in der|in den|auf dem|auf der|an der|am|beim|bei der|zum|zur|zu|unterm|ob dem|klein|gross|groß)"


def clean(p: str) -> tuple[str, str]:
    """Schreibung -> (Suchname, Bezugsort aus «bei X»/«im Y»)."""
    s = p.strip().rstrip(".").strip()
    s = re.sub(r"\s*=\s*", "-", s)
    near = ""
    m = re.search(r",?\s*\b(bei|bey|b\.|près|prés|pres|Amt)\s+(.+)$", s)
    if m:
        near, s = m.group(2), s[:m.start()]
    m = re.search(r"\s+(im|in)\s+([A-ZÄÖÜ]\w+)$", s)  # «Oberwyl im Simmenthal», «Hallwyl im Aargau»
    if m and not near:
        near, s = m.group(2), s[:m.start()]
    s = re.sub(rf"^{ART}\s+", "", s, flags=re.I)
    s = re.sub(rf",\s*{ART}\.?$", "", s, flags=re.I)
    s = re.sub(r",\s*(Stadt|Vorstadt|auf dem Wasen)$", "", s)
    m = re.match(r"^(.+),\s*(St|La|Le|Les)\.?$", s)
    if m:
        s = f"{m.group(2)}{'.' if m.group(2) == 'St' else ''} {m.group(1)}"
    m = re.match(r"^(.+)\s*\((Groß|Gross|Klein|Ober|Nieder|Unter)-?\)$", s)
    if m:
        s = m.group(2) + m.group(1).strip().lower()
    s = s.replace("I mmier", "Immier")
    return s.strip(" ,"), near.strip(" ,.")


def label_name(label: str) -> tuple[str, str, str]:
    """swisstopo-Label -> (Name, Kanton, Art)."""
    m = re.match(r"^(.*?)\s*\((\w\w)\)", label)
    name, canton = (m.group(1), m.group(2)) if m else (label, "")
    kind = ""
    km = re.match(r"^(Ort|See|Gebiet|Flurname|Huegel|Hügel|Berg|Pass|Tal|Strasse|Haltestelle|Bahnhof|Quartierteil|Quartier|Ortsteil|Weiler|Gebäude|Einzelhaus|Campingplatzareal|Alp)\s+(.*)$", name)
    if km:
        kind, name = km.group(1), km.group(2)
    name = name.split("|")[0]
    return name.strip(), canton, kind


def candidates(name: str) -> list[dict]:
    qs = [name]
    alt = name.replace("ß", "ss")
    alt = re.sub(r"wyl\b", "wil", alt)
    alt = re.sub(r"y", "i", alt)
    alt = re.sub(r"th", "t", alt)
    for a in (alt, re.sub(r"(?<=[aeiouäöü])z", "tz", alt)):
        if a not in qs:
            qs.append(a)
    out, seen = [], set()
    for q in qs:
        for c in search(q):
            key = (c["label"], round(c["lat"], 4))
            if key in seen:
                continue
            seen.add(key)
            nm, canton, kind = label_name(c["label"])
            if c["origin"] == "gazetteer" and kind not in ("Ort", "Weiler", "Quartierteil", "Quartier", "Ortsteil", "Einzelhaus", "Gebäude", ""):
                continue
            sim = SequenceMatcher(None, fold(name), fold(nm)).ratio()
            if fold(nm).startswith(fold(name) + " ") or fold(nm.replace(" b. ", " bei ")).startswith(fold(name) + " "):
                sim = max(sim, 0.9)  # amtlicher Name mit Zusatz: «Langnau im Emmental», «Wangen an der Aare»
            # zweisprachige Namen «Delémont|Delsberg»
            for other in c["label"].split("|")[1:]:
                sim = max(sim, SequenceMatcher(None, fold(name), fold(other.split("(")[0])).ratio())
            out.append({**c, "name": nm, "canton": canton, "kind": "Gemeinde" if c["origin"] == "gg25" else (kind or "Ort"), "sim": sim})
    return out


# Amt Laufen gehörte 1815–1993 zu Bern, die Gemeinden liegen heute in Basel-Landschaft
LAUFENTAL = {"Laufen", "Zwingen", "Dittingen", "Blauen", "Brislach", "Burg im Leimental", "Duggingen", "Grellingen",
             "Liesberg", "Nenzlingen", "Roggenburg", "Röschenz", "Wahlen"}
VOL_CANTONS = {"1795": {"BE", "VD", "AG"}, "1810": {"BE"}, "1822": {"BE"}, "1836": {"BE", "JU"}, "1839": {"BE", "JU"}, "1848": {"BE"}}


def main():
    rows = list(csv.DictReader(open(ROOT / "data/csv/04_entries.csv", encoding="utf-8")))
    uses = defaultdict(list)
    for r in rows:
        if r["place"].strip():
            uses[r["place"].strip()].append((r["volume"], int(r["page"])))
    keep = {}  # Korrekturen gehören in config/places_hand.csv, nicht in places.csv

    hand, hand_pages = {}, []
    for r in csv.DictReader(open(ROOT / "config/places_hand.csv", encoding="utf-8")):
        if r["pages"]:
            hand_pages.append(r)
        else:
            hand[r["place"]] = r
    cands = {}
    for i, p in enumerate(sorted(uses)):
        if p in keep:
            continue
        name, near = clean(p)
        cs = candidates(name) if name else []
        if near:
            nn, _ = clean(near)
            nc = [c for c in candidates(nn) if c["sim"] >= 0.8]
            cands[p] = (name, near, cs, nc[0] if nc else None)
        else:
            cands[p] = (name, near, cs, None)
        if i % 100 == 0:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False))
            print(i, len(uses), file=sys.stderr)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False))

    def allowed(c, p):
        vols = {v for v, _ in uses[p]}
        cs = set()
        for v in vols:
            cs |= VOL_CANTONS[v]
        if c["canton"] == "BL" and c["name"] in LAUFENTAL and vols & {"1836", "1839", "1848"}:
            return True
        return c["canton"] in cs

    # 1. Durchgang: eindeutige Treffer
    res = {}
    for p, (name, near, cs, nc) in cands.items():
        good = [c for c in cs if c["sim"] >= 0.84 and allowed(c, p)]
        for pref in ("BE", "JU"):  # gleichnamige Orte: bernische vor jurassischen vor Laufentaler Orten
            if any(c["canton"] == pref for c in good):
                good = [c for c in good if c["canton"] == pref]
                break
        gem = [c for c in good if c["kind"] == "Gemeinde"]
        named = [c for c in good if near and fold(clean(near)[0])[:6] in fold(c["label"])]
        top = max((c["sim"] for c in gem), default=0)
        tops = [c for c in gem if c["sim"] == top]
        if named:
            res[p] = (max(named, key=lambda c: c["sim"]), "auto_bezug", f"Zusatz {near}")
        elif nc:
            good.sort(key=lambda c: hypot(c["lat"] - nc["lat"], c["lon"] - nc["lon"]))
            if good and hypot(good[0]["lat"] - nc["lat"], good[0]["lon"] - nc["lon"]) < 0.12:
                res[p] = (good[0], "auto_bezug", f"bei {nc['name']}")
            else:
                res[p] = (nc, "bezugsort", f"nur Bezugsort {nc['name']} gefunden")
        elif gem and len({c["id"] for c in tops}) == 1:
            res[p] = (tops[0], "auto", "")
        elif gem:
            pass  # mehrere gleich gute Gemeinden: Seitenkontext entscheidet
        elif len({(round(c["lat"], 2), round(c["lon"], 2)) for c in good}) == 1:
            res[p] = (good[0], "auto", "")
        elif not good:
            out_g = [c for c in cs if c["sim"] >= 0.95 and c["kind"] == "Gemeinde"]
            if len(out_g) == 1:
                res[p] = (out_g[0], "auto", "ausserhalb des damaligen Kantonsgebiets")
    # Handtabelle config/places_hand.csv: heutiger Name zum Nachschlagen, leer = nicht verorten
    skip = {}
    for p, h in hand.items():
        if p not in uses:
            continue
        if not h["query"]:
            skip[p] = h["note"]; res.pop(p, None); continue
        cs = [c for c in candidates(h["query"]) if c["canton"] == h["canton"]]
        cs.sort(key=lambda c: (-SequenceMatcher(None, fold(h["query"]), fold(c["name"])).ratio(), c["kind"] != "Gemeinde"))
        cs = [c for c in cs if SequenceMatcher(None, fold(h["query"]), fold(c["name"])).ratio() >= 0.9]
        if cs:
            res[p] = (cs[0], "hand", h["note"] or f"als {h['query']}")
        else:
            res.pop(p, None)
            print("Handtabelle ohne Treffer:", p, h["query"], file=sys.stderr)
    # Seitenkontext: Mittelpunkt der eindeutig verorteten Orte je Band und Seitenbereich
    ctx = defaultdict(list)
    for p, (c, m, _) in res.items():
        if c["kind"] == "Gemeinde" and p != "Bern":
            for v, pg in uses[p]:
                ctx[(v, pg)].append((c["lat"], c["lon"]))

    def centre(p):
        pts = []
        for v, pg in uses[p]:
            for d in (0, -1, 1):
                pts += ctx.get((v, pg + d), [])
        if not pts:
            return None
        return (sorted(x for x, _ in pts)[len(pts) // 2], sorted(y for _, y in pts)[len(pts) // 2])

    # 2. Durchgang: mehrdeutige mit Kontext
    for p, (name, near, cs, nc) in cands.items():
        if p in res:
            continue
        good = [c for c in cs if c["sim"] >= 0.84 and allowed(c, p)]
        cen = centre(p)
        if good and cen:
            good.sort(key=lambda c: hypot(c["lat"] - cen[0], c["lon"] - cen[1]))
            d = hypot(good[0]["lat"] - cen[0], good[0]["lon"] - cen[1])
            if d < 0.15:
                res[p] = (good[0], "kontext", f"{len(good)} gleichnamige, nächster zu den Orten derselben Seite")

    # 3. Durchgang: unscharfe Namensgleichheit, nur nahe bei den Orten derselben Seite
    for p, (name, near, cs, nc) in cands.items():
        if p in res:
            continue
        good = [c for c in cs if c["sim"] >= 0.75 and allowed(c, p)]
        cen = centre(p)
        if good and cen:
            good.sort(key=lambda c: hypot(c["lat"] - cen[0], c["lon"] - cen[1]))
            if hypot(good[0]["lat"] - cen[0], good[0]["lon"] - cen[1]) < 0.1:
                res[p] = (good[0], "unscharf", f"Name ähnlich ({good[0]['sim']:.2f}), nahe den Orten derselben Seite")

    out = []
    for p in sorted(uses):
        vols = ",".join(sorted({v for v, _ in uses[p]}))
        if p in keep:
            r = keep[p]; r["n_entries"] = len(uses[p]); r["volumes"] = vols; out.append(r); continue
        if p in res:
            c, m, note = res[p]
            out.append({"place": p, "name": c["name"], "kind": c["kind"], "canton": c["canton"], "lat": round(c["lat"], 5),
                        "lon": round(c["lon"], 5), "method": m, "score": round(c.get("sim", 0), 2), "n_entries": len(uses[p]),
                        "volumes": vols, "source": f"swisstopo {c['origin']} {c['id'] or ''}".strip(), "note": note})
        elif p in skip:
            out.append({"place": p, "name": "", "kind": "", "canton": "", "lat": "", "lon": "", "method": "ausgelassen", "score": "",
                        "n_entries": len(uses[p]), "volumes": vols, "source": "", "note": skip[p]})
        else:
            name, near, cs, nc = cands[p]
            best = sorted(cs, key=lambda c: -c["sim"])[:3]
            out.append({"place": p, "name": "", "kind": "", "canton": "", "lat": "", "lon": "", "method": "offen", "score": "",
                        "n_entries": len(uses[p]), "volumes": vols, "source": "",
                        "note": "Kandidaten: " + "; ".join(f"{c['name']} ({c['canton']}, {c['sim']:.2f})" for c in best)})
    # seitenweise Ausnahmen: Schlüssel «Schreibung@Band:Seite»
    for h in hand_pages:
        cs = [c for c in candidates(h["query"]) if c["canton"] == h["canton"]
              and SequenceMatcher(None, fold(h["query"]), fold(c["name"])).ratio() >= 0.9]
        if not cs:
            print("Handtabelle ohne Treffer:", h["place"], h["query"], file=sys.stderr); continue
        c = cs[0]
        for vp in h["pages"].split(";"):
            v, pg = vp.split(":")
            n = sum(1 for u in uses.get(h["place"], []) if u == (v, int(pg)))
            out.append({"place": f"{h['place']}@{v}:{int(pg)}", "name": c["name"], "kind": c["kind"], "canton": c["canton"],
                        "lat": round(c["lat"], 5), "lon": round(c["lon"], 5), "method": "hand", "score": 1.0, "n_entries": n,
                        "volumes": v, "source": f"swisstopo {c['origin']} {c['id'] or ''}".strip(), "note": h["note"]})
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS); w.writeheader(); w.writerows(out)
    cnt = Counter(r["method"] for r in out)
    ent = Counter()
    for r in out:
        ent[r["method"]] += int(r["n_entries"])
    print("Schreibungen", dict(cnt), "Einträge", dict(ent))


if __name__ == "__main__":
    main()
