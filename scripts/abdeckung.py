#!/usr/bin/env python3
"""abdeckung.py — Abdeckung der frühen Berner Adressbücher, gemessen an BERNHIST.

Zwei Schritte:

1. `python3 scripts/abdeckung.py referenz --bernhist PFAD` (oder Umgebungsvariable BERNHIST_SQLITE)
   liest aus dem lokalen BERNHIST-Dump (SQLite, Tabellen data_entry, location, topic, type) nur die
   Werte, die hier gebraucht werden, und schreibt
     data/ref/bernhist_werte.csv   verwendete Einzelwerte mit Ort, Thema, Jahr, Wert, Quelle
     data/ref/bernhist_orte.csv    Orte der Kantonsteile 1836/1839 -> BERNHIST-Ort, Kirchgemeinde, Amtsbezirk
   Rohdaten von BERNHIST kommen nicht ins Repo (Nutzungsrechte ungeklärt).

2. `python3 scripts/abdeckung.py rechnen` rechnet nur aus den Dateien im Repo:
     data/abdeckung/baende.csv            Kennzahlen je Band (Zähler, Nenner, Quote, Grundlage des Nenners)
     data/abdeckung/berufsgruppen.csv     Berufsgruppen je Band
     data/abdeckung/amtsbezirke.csv       Einträge je 1000 Einwohner je Amtsbezirk (1836, 1839)
     data/abdeckung/orte_offen.csv        Orte ohne Zuordnung zu einem Amtsbezirk
     data/abdeckung/berufe_stichprobe.csv Stichprobe zur Berufszuordnung (Urteile von Hand bleiben erhalten)
     site/abdeckung.html                  Unterseite der statischen Seite
     docs/abdeckung.md                    Tabellen zwischen den Markierungen <!-- abdeckung:tabellen -->

`python3 scripts/abdeckung.py alles --bernhist PFAD` macht beides. Nur Standardbibliothek.
"""
from __future__ import annotations

import argparse
import csv
import html
import math
import os
import random
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data/csv"
REF = ROOT / "data/ref"
OUT = ROOT / "data/abdeckung"
QUELLE = ("BERNHIST, Historisch-Statistische Datenbank des Kantons Bern (Projekt Ch. Pfister, Universität Bern; "
          "UB Bern), Dump github.com/ub-unibe-ch/bernhist, Stand 22.03.2024")

STADT = 457       # Einwohnergemeinde Bern (vor 1920 ohne Bümpliz)
KANTON = 16
AMT_BERN = 19

# BERNHIST-Themen, die gebraucht werden: Schlüssel -> topic_id
THEMEN = {
    "bev": 990, "haushalte": 543, "frauen": 362, "f_ledig": 356, "f_verwitwet": 360,
    "burger_m": 239, "burger_f": 276, "burger": 259,
    "bern_niedergelassene": 257, "kantone_niedergelassene": 252, "ausl_niedergelassene": 179,
    "sektor1": 305, "sektor2": 314, "sektor3": 327, "selbstaendige": 341, "erwerbstaetige": 342,
    "unselbstaendige": 348, "dienstboten": 344, "tagloehner": 347, "aerzte": 1713,
    "hausbesitzer": 180, "wohnhaeuser": 437,
}
STADT_JAHRE = (1764, 1856)

BAENDE = ["1795", "1810", "1822", "1836", "1839", "1848"]
# Was der Band verzeichnet (aus Titel, README, config/volumes.json und den Einträgen selbst)
BAND_INHALT = {
    "1795": ("Handelshäuser, Fabrikanten, Künstler und «ansehnliche» Gewerbetreibende der alten Republik "
             "(Hauptstadt, Landstädte, Waadt, Aargau)", "Auswahl Handel und Gewerbe; Stadt = Einträge unter «Bern»"),
    "1810": ("Livre d'adresses: «principales maisons de commerce et manufactures», dazu Notare, Advokaten, Ärzte, "
             "Künstler; Stadt und Kanton", "Auswahl Handel, Gewerbe, freie Berufe; Stadt = Teil A und Additions"),
    "1822": ("Adressbuch der Stadt Bern nach Berufen: Advokaten, Ärzte, Handlungen, Handwerker", "Gewerbe und "
             "Berufe der Stadt; eine Person steht unter jedem ihrer Gewerbe"),
    "1836": ("Verzeichnis der Einwohnerschaft zu Bern (alphabetisch, mit Kennbuchstaben B. = Burger, H. = "
             "Hauseigentümer) und Gewerbetreibende der Amtsbezirke", "Stadt: Einwohner mit Beruf oder Stand, "
             "Burger und Nichtburger; Kanton: Gewerbe je Ort"),
    "1839": ("Ergänzungsheft: neue Namen und veränderte Wohnungen in der Stadt, Veränderungen in den Amtsbezirken",
             "nur Nachträge zu 1836, keine vollständige Liste"),
    "1848": ("Einsassen der Stadt Bern: Niedergelassene ohne Burgerrecht, je Haushalt mit Ehefrau und Kindern",
             "nur Nichtburger mit Einsassenrecht; Haushalte mit Kopfzahl"),
}

# ---------------------------------------------------------------------------------------------------------------
# Reine Rechenlogik (getestet in tests/test_abdeckung.py)
# ---------------------------------------------------------------------------------------------------------------

def interpoliere(reihe: dict[int, float], jahr: int) -> dict:
    """Wert einer Reihe {Stichjahr: Wert} im Jahr `jahr`.

    Liegt das Jahr zwischen zwei Stichjahren, wird linear interpoliert; ausserhalb wird NICHT extrapoliert,
    sondern das nächste Stichjahr unverändert genommen. Rückgabe: wert, art (exakt / interpoliert /
    naechstes_stichjahr), jahre (die verwendeten Stichjahre)."""
    if not reihe:
        raise ValueError("leere Reihe")
    jahre = sorted(reihe)
    if jahr in reihe:
        return {"wert": float(reihe[jahr]), "art": "exakt", "jahre": (jahr,)}
    davor = [j for j in jahre if j < jahr]
    danach = [j for j in jahre if j > jahr]
    if davor and danach:
        a, b = davor[-1], danach[0]
        w = reihe[a] + (reihe[b] - reihe[a]) * (jahr - a) / (b - a)
        return {"wert": w, "art": "interpoliert", "jahre": (a, b)}
    j = davor[-1] if davor else danach[0]
    return {"wert": float(reihe[j]), "art": "naechstes_stichjahr", "jahre": (j,)}


def skaliere(wert: float, jahr_ref: int, bev: dict[int, float], jahr: int) -> float:
    """Überträgt einen Wert aus dem Stichjahr `jahr_ref` auf `jahr` unter der Annahme, dass sein Anteil an der
    Wohnbevölkerung gleich bleibt: wert × Bevölkerung(jahr) / Bevölkerung(jahr_ref), beide interpoliert."""
    return wert * interpoliere(bev, jahr)["wert"] / interpoliere(bev, jahr_ref)["wert"]


def quote(zaehler: float, nenner: float | None, je: int = 100) -> float | None:
    if nenner is None or not nenner:
        return None
    return je * zaehler / nenner


def falte(s: str) -> str:
    """Kleinschreibung, ß -> ss, Akzente und Umlautpunkte weg (ä -> a), Rest unverändert."""
    s = (s or "").lower().replace("ß", "ss").replace("ſ", "s")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def ort_schluessel(name: str) -> str:
    """Vergleichsform eines Ortsnamens: gefaltet, ohne Klammerzusätze («Bargen (BE)»), ohne Kantonskürzel,
    St./Saint/Sankt gleich, nur Buchstaben und Ziffern."""
    s = re.sub(r"\([^)]*\)", " ", name or "")
    s = falte(s)
    s = re.sub(r"\b(be|bl|ju)\b", " ", s)
    s = re.sub(r"\b(st|saint|sankt)\b\.?[ -]?", "st ", s)
    s = re.sub(r"\bthal\b", "tal", re.sub(r"thal\b", "tal", s))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def ort_varianten(name: str) -> set[str]:
    """Alle Vergleichsformen eines BERNHIST-Ortsnamens: «Grossaffoltern / Affoltern» -> beide Teile,
    «Neuveville, La» -> «la neuveville» und «neuveville», «Bolligen (mit Ittigen, Ostermundigen)» -> «bolligen»."""
    ohne = re.sub(r"\([^)]*\)", " ", name or "").strip()
    out = set()
    m = re.match(r"^(.*), (La|Le|Les)$", ohne)
    if m:
        out.add(ort_schluessel(f"{m.group(2)} {m.group(1)}"))
        out.add(ort_schluessel(m.group(1)))
        return out
    for teil in re.split(r"\s*/\s*|,\s*", ohne):
        if teil.strip():
            out.add(ort_schluessel(teil))
    out.discard("")
    return out


def ort_kurz(schluessel: str) -> str:
    """Ohne Lagezusatz: «buren an der aare» -> «buren», «bangerten b dieterswil» -> «bangerten»."""
    return re.sub(r" (b|bei|im|in|an der|am|ob|sur|pres|les) .*$", "", schluessel)


GRUPPEN = ["landwirtschaft", "handwerk", "arbeiter", "handel", "gastgewerbe", "verkehr", "gesundheit", "recht",
           "verwaltung", "militaer", "bildung_kirche", "kunst", "angestellte", "dienste", "dienstboten",
           "tagloehner", "ohne_erwerb", "unbestimmt"]
SEKTOR = {"landwirtschaft": "1", "handwerk": "2", "arbeiter": "2", "handel": "3", "gastgewerbe": "3",
          "verkehr": "3", "gesundheit": "3", "recht": "3", "verwaltung": "3", "militaer": "3",
          "bildung_kirche": "3", "kunst": "3", "angestellte": "3", "dienste": "3",
          "dienstboten": "Dienstboten", "tagloehner": "Taglöhner", "ohne_erwerb": "ohne Erwerb",
          "unbestimmt": "unbestimmt"}
# Näherung für «Selbständige»: Gruppen, deren Angehörige im Adressbuch in der Regel auf eigene Rechnung arbeiten
SELBSTAENDIG = {"landwirtschaft", "handwerk", "handel", "gastgewerbe", "verkehr", "gesundheit", "recht", "kunst",
                "dienste"}
GRUPPEN_LABEL = {"landwirtschaft": "Land- und Forstwirtschaft, Gartenbau", "handwerk": "Handwerk und Gewerbe",
                 "arbeiter": "Arbeiter, Gesellen", "handel": "Handel", "gastgewerbe": "Gastgewerbe",
                 "verkehr": "Verkehr", "gesundheit": "Gesundheit", "recht": "Recht, Geschäftsbüros",
                 "verwaltung": "Verwaltung, Ämter", "militaer": "Offiziere", "bildung_kirche": "Bildung, Kirche",
                 "kunst": "Kunst, Architektur", "angestellte": "Schreiber, Angestellte",
                 "dienste": "persönliche Dienste", "dienstboten": "Dienstboten", "tagloehner": "Taglöhner",
                 "ohne_erwerb": "ohne Erwerb (Rentner, Besitzer)", "unbestimmt": "unbestimmt"}


def lade_regeln(pfad: Path | None = None) -> list[tuple[str, re.Pattern]]:
    with open(pfad or ROOT / "config/berufe_regeln.csv", newline="") as f:
        return [(r["gruppe"], re.compile(r["muster"])) for r in csv.DictReader(f)]


_ANGEHOERIGE = re.compile(r"\bdes \S+ (frau|wittwe|witwe|sohn|sohne|tochter|tochtern)\b,?")


def beruf_gruppe(text: str, regeln: list[tuple[str, re.Pattern]]) -> str:
    """Ordnet eine Berufsangabe einer Gruppe zu.

    Die Angabe wird gefaltet und an Leerzeichen, Komma, Strichpunkt und Schrägstrich in Wörter zerlegt.
    Es zählt das erste Wort, auf das eine Regel passt (die erstgenannte Tätigkeit). Passen in diesem Wort
    mehrere Regeln, gewinnt der Treffer, der am weitesten hinten endet (im Deutschen steht das Grundwort
    hinten: Tabak-fabrikant, Wein-händler), bei gleichem Ende der längere. «des Taglöhners Frau» und
    ähnliche Angaben zum Angehörigen werden vorher entfernt. Ohne Treffer: «unbestimmt»."""
    s = _ANGEHOERIGE.sub(" ", falte(text))
    for wort in re.split(r"[\s,;/]+", s):
        wort = wort.strip(".:()«»\"'")
        if not wort:
            continue
        best = None
        for gruppe, muster in regeln:
            for m in muster.finditer(wort):
                key = (m.end(), -m.start())
                if best is None or key > best[0]:
                    best = (key, gruppe)
        if best:
            return best[1]
    return "unbestimmt"


_ARZT = re.compile(r"(?<![a-z])(arzt|aerzte|arzte|medecins?|docteur en med\w*)\b|\bmed\b\.? ?dr|\bdr\b\.? ?med|doktor der medi")
_WUNDARZT = re.compile(r"wundarzt|wundarzte|chirurg|operateur")


def arzt_art(text: str) -> str:
    """«arzt» = Arzt, Médecin, Med. Dr. (ohne Tier-, Zahn-, Vieharzt); «wundarzt» = Wundarzt, Chirurg,
    Opérateur ohne Arzt; sonst leer. «Arzt und Wundarzt» zählt als Arzt."""
    s = falte(text)
    if _ARZT.search(s):
        return "arzt"
    if _WUNDARZT.search(s):
        return "wundarzt"
    return ""


_KENN_TEIL = re.compile(r"^(landesabwesend\.?\s*)?((h|g|b)\.?)(\s*(u\.?|und|,)?\s*(h|g|b)\.?)*\.?$", re.I)


def kennbuchstaben(*felder: str) -> set[str]:
    """Kennbuchstaben des Adressenbuchs 1836/1839: B. = Burger von Bern, H. = Hauseigentümer,
    G. = Grundeigentümer. Sie stehen als eigener Teil («B.», «H. u. B.», «H und B.», «Hu.») in Vermerk,
    Herkunft oder Haushalt; Teile werden an «;» getrennt."""
    out: set[str] = set()
    for feld in felder:
        for teil in (feld or "").split(";"):
            t = teil.strip()
            if t.lower() in ("hu.", "hu"):
                out.add("H")
            elif t and _KENN_TEIL.match(t):
                t = re.sub(r"(?i)landesabwesend\.?|\bund\b|u\.", " ", t)
                out.update(c.upper() for c in re.findall(r"[hgbHGB]", t))
    return out


FRAUENNAMEN = set("""anna maria marie elisabetha elisabeth elise elis elisab lisabeth elsbeth marg margaretha
margaritha margar margarita magdalena magd barbara barb rosina rosine ros susanna susanne sus katharina kathar
kath catharina catherine verena sophie sophia louise luise nanette nannette julie julia rosette lisette christina
christine charlotte henriette johanna marianne mariane adele adelheid karoline caroline emilie emilia salome
ursula regina lina bertha pauline josephine friederike wilhelmine jeanne jeannette madeleine marguerite francoise
esther judith dorothea veronika agnes eva cacilie cecile babette fanny amalie amalia mathilde sara sarah rahel
therese theresia franziska antoinette albertine gertrud helene ida klara clara lydia martha louisa rosa rosalie
emma maria-anna annamaria anne zelie victoire suzanne elisa lucie lucia""".split())
_FRAU = re.compile(r"\b(frau|fr|wittwe|witwe|wittib|wittwen|wwe|jungfer|jungfern|jgfr|jfr|igfr|demoiselles?|dem|dlle|"
                   r"mlle|mad|madame|mme|veuve|vve|schwestern|schwester|tochter|tochtern|toechter|soeurs|"
                   r"geborne|geb)\b")
_BERUF_FRAU = re.compile(r"\w+(er|ler|th|ant|ist|arzt|ier)inn?(en)?\b|\b\w*(magd|frau|hebamme|modiste|kochin|"
                         r"marchande|rentiere|ouvriere|couturiere|lingere|blanchisseuse|institutrice|maitresse|"
                         r"sage.femme|accoucheuse)\b")
_WITWE = re.compile(r"\b(wittwe|witwe|wittib|wittwen|wittw|wwe|veuve|vve|verw)\b|\w+wittwe\b")
_WITWE_1848 = re.compile(r"(^|[ ,])w\.")
_JUNGFER = re.compile(r"\b(jungfer|jungfern|jgfr|jfr|igfr|demoiselles?|dem|dlle|mlle)\b")


def ist_frau(r: dict) -> bool:
    """Frau, wenn Anrede/Stand (Frau, Wittwe, Jungfer, Madame, Veuve, Schwestern, geb. …), ein weiblicher
    erster Vorname oder eine weibliche Berufsform (Schneiderin, Wirthin, Hebamme, Marchande) dasteht.
    «des Taglöhners Frau» im Stand zählt; die Ehefrau im Feld `household` (1848) zählt nicht."""
    titel = falte(r.get("title", ""))
    if _FRAU.search(titel) and not re.search(r"\bund frau\b|& frau\b|et femme", titel):
        return True
    vor = falte(r.get("forename", "")).replace(".", " ").split()
    if vor and vor[0] in FRAUENNAMEN:
        return True
    beruf = _ANGEHOERIGE.sub(" frau ", falte(r.get("occupation", "")))
    erstes = re.split(r"[,;/]| und | u\. | et ", beruf)[0]
    return bool(_BERUF_FRAU.search(erstes))


def ist_witwe(r: dict) -> bool:
    s = falte(r.get("title", "")) + " | " + falte(r.get("occupation", ""))
    if _WITWE.search(s):
        return True
    return r.get("volume") == "1848" and bool(_WITWE_1848.search(falte(r.get("title", ""))))


def ist_jungfer(r: dict) -> bool:
    return bool(_JUNGFER.search(falte(r.get("title", ""))))


_KINDER = re.compile(r"(\d+)\s*(K|S|T)\.")
_EHEFRAU = re.compile(r"(^|[\s.(])Fr\.")


def haushalt_1848(household: str) -> tuple[int, int]:
    """Aus dem Feld `household` des Einsassenverzeichnisses: (Ehefrau 0/1, Zahl der Kinder).
    «813 Fr. - Christina Zbinden. 5 T. - 833 Anna Maria …» -> (1, 5); «2 K.», «1 S.», «3 T.» werden addiert."""
    h = household or ""
    frau = 1 if _EHEFRAU.search(h) else 0
    kinder = sum(int(m.group(1)) for m in _KINDER.finditer(h) if int(m.group(1)) < 20)
    return frau, kinder


ALPHABETISCH = {("1836", "einwohner"), ("1836", "einwohner_nachtrag"), ("1839", "einwohner"), ("1848", "einsassen"),
                ("1848", "veraenderungen"), ("1848", "neue_einsassen"), ("1848", "beamte")}
_UNTERSCHEIDER = re.compile(r"\b(vater|sohn|sohne|alter|junger|pere|fils|aine|cadet|wittwe|witwe|veuve|frau|madame|"
                            r"jungfer|gebruder|freres|schwestern|soeurs|erben)\b")


def personen_schluessel(r: dict) -> tuple:
    """Näherung für «dieselbe Person im selben Band».

    In den alphabetischen Verzeichnissen (Einwohner 1836/1839, Einsassen 1848) steht jede Person bzw. jeder
    Haushalt einmal: jeder Eintrag zählt für sich. In den nach Gewerben oder Orten gegliederten Teilen steht
    eine Person unter jedem ihrer Gewerbe: dort gelten Einträge mit gleichem Familiennamen, Vornamen und
    Unterscheider (Vater/Sohn, älter/jünger, Wittwe, Gebrüder …) als eine Person; fehlt der Vorname, zählen
    zusätzlich Ort und Adresse. Firmen zählen wie Personen."""
    if (r.get("volume"), r.get("section")) in ALPHABETISCH:
        return ("#", r.get("entry_id"))
    name = re.sub(r"[^a-z]+", " ", falte(r.get("surname", ""))).strip()
    vor = re.sub(r"[^a-z]+", " ", falte(r.get("forename", ""))).strip()
    zusatz = " ".join(sorted(set(_UNTERSCHEIDER.findall(falte(r.get("title", ""))))))
    if vor:
        return (name, vor, zusatz, falte(r.get("place", "")))
    return (name, "", zusatz, falte(r.get("place", "")), re.sub(r"[^a-z0-9]+", "", falte(r.get("address", ""))))


def stadt_bereich(r: dict, ort: dict) -> str:
    """In welchem städtischen Teil des Bandes ein Eintrag steht («» = nicht Stadt Bern).
    1848 nach PDF-Seiten, weil die Abschnittsgrenzen in config/volumes.json dort nicht stimmen:
    S. 14–199 Einsassen (198–199 Nachtrag), 200–201 Veränderungen, 202 neue Einsassen."""
    v, sec, seite = r["volume"], r["section"], int(r["page"])
    if v == "1795":
        return "stadt" if ort.get("map_place") == "Bern" else ""
    if v == "1810":
        return "stadt" if sec in ("ville", "additions") else ""
    if v == "1822":
        return "stadt"
    if v == "1836":
        return {"einwohner": "stadt", "einwohner_nachtrag": "stadt_nachtrag"}.get(sec, "")
    if v == "1839":
        return "stadt" if sec == "einwohner" else ""
    if v == "1848":
        return "stadt" if seite <= 199 else ("veraenderungen" if seite <= 201 else "neue_einsassen")
    return ""


def berufsangabe(r: dict) -> str:
    """Text, aus dem der Beruf gelesen wird: das Feld `occupation`; wo der Band nach Gewerben gegliedert ist
    (1795, 1810, 1822, Kantonsteile 1836/1839), ersatzweise die Rubrik, wenn `occupation` leer ist oder
    keine Regel passt. In den alphabetischen Verzeichnissen ist die Rubrik ein Buchstabe oder Familienname."""
    return (r.get("occupation") or "").strip()


def gruppe_eintrag(r: dict, regeln) -> str:
    g = beruf_gruppe(berufsangabe(r), regeln)
    if g == "unbestimmt" and (r["volume"] in ("1795", "1810", "1822") or r["section"].startswith("kanton")):
        g = beruf_gruppe(r.get("heading", ""), regeln)
    return g


def ziehe_stichprobe(eintraege: list[dict], je_band: int = 10, seed: int = 1848) -> list[dict]:
    """Geschichtete Zufallsstichprobe: je Band `je_band` Einträge (Person oder Firma) mit Berufsangabe oder Rubrik,
    fester Startwert, damit sie reproduzierbar ist."""
    rng = random.Random(seed)
    out = []
    for band in BAENDE:
        pool = sorted((r for r in eintraege if r["volume"] == band and r["kind"] in ("person", "firma")
                       and (r["occupation"].strip() or r["heading"].strip())), key=lambda r: r["entry_id"])
        out += rng.sample(pool, min(je_band, len(pool)))
    return out


def mehrheit(werte: list) -> object | None:
    werte = [w for w in werte if w]
    return Counter(werte).most_common(1)[0][0] if werte else None


def distanz_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------------------------------------------
# Schritt 1: Referenzwerte und Ortsbindung aus dem BERNHIST-Dump
# ---------------------------------------------------------------------------------------------------------------

def lies_csv(pfad: Path) -> list[dict]:
    with open(pfad, newline="") as f:
        return list(csv.DictReader(f))


def schreibe_csv(pfad: Path, zeilen: list[dict], felder: list[str] | None = None) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", newline="") as f:
        w = csv.DictWriter(f, felder or list(zeilen[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(zeilen)


def kantonseintraege() -> list[tuple[dict, dict]]:
    orte = {r["entry_id"]: r for r in lies_csv(CSV_DIR / "06_entry_places.csv")}
    return [(r, orte[r["entry_id"]]) for r in lies_csv(CSV_DIR / "04_entries.csv")
            if ist_kantonsteil(r) and r["kind"] in ("person", "firma")]


def ist_kantonsteil(r: dict) -> bool:
    """Kantonsteile: 1810 Teil B (nach Préfectures), 1836 und 1839 die Amtsbezirke mit Nachträgen."""
    return ((r["volume"] == "1810" and r["section"] == "canton")
            or (r["volume"] in ("1836", "1839") and r["section"].startswith("kanton")))


# Préfectures des Livre d'adresses 1810 -> Amtsbezirk in BERNHIST (zur Prüfung der Ortsbindung)
PRAEFEKTUREN_1810 = {"thoune": "Thun", "berthoud": "Burgdorf", "signau": "Signau", "gessenay": "Saanen",
                     "oberhasle": "Oberhasli", "froutigen": "Frutigen", "bas simmenthal": "Niedersimmental",
                     "haut simmenthal": "Obersimmental", "wangen": "Wangen", "trachselwald": "Trachselwald",
                     "buren": "Büren", "cerlier": "Erlach", "schwarzenbourg": "Schwarzenburg", "seftigen": "Seftigen",
                     "berne": "Bern", "nydau": "Nidau", "aarberg": "Aarberg", "aarwangen": "Aarwangen",
                     "fraubrunnen": "Fraubrunnen", "konolfingen": "Konolfingen", "laupen": "Laupen",
                     "interlaken": "Interlaken", "interlacken": "Interlaken"}


# 1810 gehörten Biel und das ehemalige Fürstbistum (Courtelary, Laufen, Moutier, Neuveville) zu Frankreich
BERNISCH_1810 = set(PRAEFEKTUREN_1810.values())


def praefektur_1810(rubrik: str) -> str | None:
    """«Préfecture de Thoune. Thoune» -> «Thun»; None, wenn die Rubrik keine Préfecture nennt."""
    m = re.match(r"pr[eé]fecture (?:de |du |d'|des )?([^./]+)", falte(rubrik).replace("é", "e"))
    if not m:
        return None
    return PRAEFEKTUREN_1810.get(re.sub(r"[^a-z]+", " ", m.group(1)).strip(), "?")


def ort_key(o: dict) -> str:
    return f'{o["map_place"]}|{o["lat"]}|{o["lon"]}'


def referenz(db_pfad: str) -> None:
    db = sqlite3.connect(f"file:{db_pfad}?mode=ro", uri=True)
    loc = {r[0]: {"id": r[0], "parent": r[1], "typ": r[2], "name": r[3]}
           for r in db.execute("select id, parent_id, type_id, name from location")}
    typ = dict(db.execute("select id, name from type"))
    top = {r[0]: {"parent": r[1], "name": r[2], "einheit": typ.get(r[3], "")}
           for r in db.execute("select id, parent_id, name, type_id from topic")}

    def pfad(tid: int) -> str:
        teile = []
        while tid in top:
            teile.append(top[tid]["name"])
            tid = top[tid]["parent"]
        return " > ".join(reversed(teile[:-1] if teile and teile[-1] == "Alles" else teile))

    def hinauf(i: int, t: int) -> int | None:
        while i in loc and loc[i]["typ"] != t:
            i = loc[i]["parent"]
        return i if i in loc else None

    # --- Werte ---------------------------------------------------------------------------------------------
    werte = []

    def nimm(ort: int, tid: int, j0: int, j1: int) -> None:
        q = ("select distinct year_from, year_to, value from data_entry where location_id=? and topic_id=? "
             "and year_from between ? and ? and value > 0 order by year_from, value")
        for jv, jb, w in db.execute(q, (ort, tid, j0, j1)):
            werte.append({"ort_id": ort, "ort": loc[ort]["name"], "ortstyp": typ[loc[ort]["typ"]],
                          "thema_id": tid, "thema": pfad(tid), "jahr_von": jv, "jahr_bis": jb,
                          "wert": int(w) if float(w).is_integer() else w, "einheit": top[tid]["einheit"],
                          "quelle": QUELLE})

    for tid in sorted(set(THEMEN.values())):
        nimm(STADT, tid, *STADT_JAHRE)
    aemter = sorted(i for i in loc if loc[i]["typ"] == 3)
    for ort in [KANTON] + aemter:
        nimm(ort, THEMEN["bev"], 1798, 1837)
    schreibe_csv(REF / "bernhist_werte.csv", werte)

    # --- Orte der Kantonsteile 1836/1839 an BERNHIST binden --------------------------------------------------
    index: dict[str, set[int]] = defaultdict(set)
    for i, l in loc.items():
        if l["typ"] in (5, 6):
            for v in ort_varianten(l["name"]):
                index[v].add(i)
    name_zu_id = {l["name"]: i for i, l in loc.items() if l["typ"] in (5, 6)}
    hand = {ort_schluessel(r["ort"]): r["bernhist_ort"] for r in lies_csv(ROOT / "config/bernhist_orte_hand.csv")}

    def kandidaten(name: str) -> list[int]:
        """BERNHIST-Orte zu einem Namen: Handtabelle, sonst Einwohnergemeinden, sonst Kirchgemeinden."""
        s = ort_schluessel(name)
        if s in hand:
            return [name_zu_id[hand[s]]]
        for form in (s, ort_kurz(s)):
            ids = index.get(form, set())
            for t in (6, 5):
                c = sorted(i for i in ids if loc[i]["typ"] == t)
                if c:
                    return c
        return []

    import json
    cache = json.loads((ROOT / "data/geo/swisstopo_cache.json").read_text())
    gemeinde_bei = {}
    for treffer in cache.values():
        for h in treffer:
            if " - " in h["label"]:
                gemeinde_bei[(round(h["lat"], 5), round(h["lon"], 5))] = h["label"].rsplit(" - ", 1)[1]

    paare = kantonseintraege()
    anzahl = Counter(ort_key(o) for _, o in paare)
    erster = {}
    seiten = defaultdict(list)          # Ort -> (Band, Seite) der Einträge
    for r, o in paare:
        erster.setdefault(ort_key(o), o)
        seiten[ort_key(o)].append((r["volume"], int(r["page"])))

    bind: dict[str, dict] = {}
    offen_mehrdeutig: dict[str, list[int]] = {}
    for key, o in erster.items():
        z = {"ort": o["map_place"], "lat": o["lat"], "lon": o["lon"], "kanton_heute": o["canton"],
             "eintraege": anzahl[key], "bernhist_id": "", "bernhist_ort": "", "bernhist_typ": "",
             "kirchgemeinde": "", "amtsbezirk": "", "methode": "", "bemerkung": ""}
        bind[key] = z
        if not o["map_place"]:
            z["methode"] = "ohne_ort"
            continue
        if o["canton"] == "JU":
            # Moutier gehört seit 2026 zum Kanton Jura, BERNHIST führt es im Amtsbezirk Moutier
            g = gemeinde_bei.get((round(float(o["lat"]), 5), round(float(o["lon"]), 5)), "")
            c = [i for n in (o["map_place"], g) for i in kandidaten(n) if loc[hinauf(i, 3)]["name"] == "Moutier"]
            if c:
                setze(z, c[0], "name" if ort_schluessel(o["map_place"]) == "moutier" else "gemeinde_heute", loc, typ, hinauf)
                z["bemerkung"] = "seit 2026 Kanton Jura, in BERNHIST Amtsbezirk Moutier"
                continue
            z["methode"] = "kanton_jura"
            z["bemerkung"] = "heute Kanton Jura; BERNHIST führt dafür keine Bevölkerung"
            continue
        if o["canton"] not in ("BE", "BL"):
            z["methode"] = "ausserhalb"
            continue
        c, methode = kandidaten(o["map_place"]), "name"
        if not c:
            g = gemeinde_bei.get((round(float(o["lat"]), 5), round(float(o["lon"]), 5)))
            if g:
                c, methode = kandidaten(g), "gemeinde_heute"
                z["bemerkung"] = f"liegt heute in {g}"
        if len({hinauf(i, 3) for i in c}) > 1:
            offen_mehrdeutig[key] = c
            z["methode"] = methode
            continue
        if c:
            setze(z, c[0], methode, loc, typ, hinauf)

    # mehrdeutige Namen (gleicher Name in zwei Amtsbezirken): Amtsbezirk der Nachbarn im Buch entscheidet
    def amt_der_seiten(key: str) -> str | None:
        ziel = set()
        for band, s in seiten[key]:
            ziel.update((band, s + d) for d in (-1, 0, 1))
        nachbarn = []
        for k2, z2 in bind.items():
            if k2 != key and z2["amtsbezirk"]:
                nachbarn += [z2["amtsbezirk"]] * sum(1 for bs in seiten[k2] if bs in ziel)
        return mehrheit(nachbarn)

    for key, c in offen_mehrdeutig.items():
        amt = amt_der_seiten(key)
        passend = [i for i in c if loc[hinauf(i, 3)]["name"] == amt]
        if passend:
            setze(bind[key], passend[0], bind[key]["methode"] + "_seitenkontext", loc, typ, hinauf)
            bind[key]["bemerkung"] = (bind[key]["bemerkung"] + "; " if bind[key]["bemerkung"] else "") + \
                "gleichnamige Orte in BERNHIST, gewählt nach dem Amtsbezirk der Nachbareinträge"
        else:
            bind[key]["methode"] = ""

    # Rest: nächste gebundene Gemeinde (höchstens 6 km), nur für den Amtsbezirk verlässlich
    fest = [(float(z["lat"]), float(z["lon"]), z) for z in bind.values()
            if z["methode"] in ("name", "name_seitenkontext") and z["bernhist_typ"] == "Einwohnergemeinde"]
    for z in bind.values():
        if z["methode"] or not z["lat"]:
            continue
        d, n = min(((distanz_km(float(z["lat"]), float(z["lon"]), la, lo), zz) for la, lo, zz in fest),
                   key=lambda t: t[0])
        if d <= 6:
            for f in ("bernhist_id", "bernhist_ort", "bernhist_typ", "kirchgemeinde", "amtsbezirk"):
                z[f] = n[f]
            z["methode"] = "naechste_gemeinde"
            z["bemerkung"] = f"nächste gebundene Gemeinde, {d:.1f} km; nur der Amtsbezirk ist verlässlich"
        else:
            z["methode"] = "offen"
    for z in bind.values():
        z["methode"] = z["methode"] or "offen"
    zeilen = sorted(bind.values(), key=lambda z: (z["amtsbezirk"] or "~", z["ort"], z["lat"]))
    schreibe_csv(REF / "bernhist_orte.csv", zeilen)
    print(f"referenz: {len(werte)} Werte, {len(zeilen)} Orte ->", REF)


def setze(z: dict, i: int, methode: str, loc, typ, hinauf) -> None:
    z["bernhist_id"], z["bernhist_ort"], z["bernhist_typ"] = i, loc[i]["name"], typ[loc[i]["typ"]]
    k, a = hinauf(i, 5), hinauf(i, 3)
    z["kirchgemeinde"] = loc[k]["name"] if k else ""
    z["amtsbezirk"] = loc[a]["name"] if a else ""
    z["methode"] = methode


# ---------------------------------------------------------------------------------------------------------------
# Schritt 2: rechnen
# ---------------------------------------------------------------------------------------------------------------

class Nenner:
    """Nenner für die Stadt Bern aus data/ref/bernhist_werte.csv, mit Angabe, wie sie zustande kommen."""

    def __init__(self, werte: list[dict]):
        self.reihen: dict[tuple[int, int], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
        for w in werte:
            self.reihen[(int(w["ort_id"]), int(w["thema_id"]))][int(w["jahr_von"])].append(float(w["wert"]))
        self.bev = self.reihe("bev")

    def reihe(self, schluessel: str, ort: int = STADT, wahl=min) -> dict[int, float]:
        """Reihe eines Themas; führt BERNHIST für ein Jahr zwei verschiedene Werte, entscheidet `wahl`."""
        return {j: wahl(v) for j, v in self.reihen[(ort, THEMEN[schluessel])].items()}

    def wert(self, schluessel: str, jahr: int) -> float:
        return self.reihe(schluessel)[jahr]

    # --- einzelne Nenner: Rückgabe (Wert, Grundlage) ---
    def einwohner(self, jahr: int) -> tuple[float, str]:
        i = interpoliere(self.bev, jahr)
        return i["wert"], grundlage(i, "Wohnbevölkerung")

    def haushalte(self, jahr: int) -> tuple[float, str]:
        h = {j: v for j, v in self.reihe("haushalte").items() if j <= 1856}
        if min(h) <= jahr <= max(h):
            i = interpoliere(h, jahr)
            return i["wert"], grundlage(i, "Haushalte")
        ref = min(h)
        return (skaliere(h[ref], ref, self.bev, jahr),
                f"geschätzt: Haushalte {ref} ({h[ref]:.0f}) × Wohnbevölkerung {jahr} / {ref} (beide interpoliert)")

    def anteilig(self, wert: float, jahr_ref: int, jahr: int, was: str) -> tuple[float, str]:
        if jahr == jahr_ref:
            return wert, f"{was} {jahr_ref}"
        return (skaliere(wert, jahr_ref, self.bev, jahr),
                f"{was} {jahr_ref} ({wert:.0f}), mit der Wohnbevölkerung auf {jahr} umgerechnet (gleicher Anteil angenommen)")

    def zwischen(self, a: float, ja: int, b: float, jb: int, jahr: int, was: str) -> tuple[float, str]:
        """Zwischen zwei Stichjahren interpoliert, davor anteilig vom ersten Stichjahr."""
        if ja <= jahr <= jb:
            i = interpoliere({ja: a, jb: b}, jahr)
            return i["wert"], grundlage(i, was)
        return self.anteilig(a, ja, jahr, was)

    def frauen(self, jahr: int) -> tuple[float, str]:
        return self.zwischen(self.wert("frauen", 1846), 1846, self.wert("frauen", 1856), 1856, jahr, "Frauen")

    def burger(self, jahr: int) -> tuple[float, str]:
        b46 = self.wert("burger_m", 1846) + self.wert("burger_f", 1846)
        b56 = self.wert("burger", 1856)
        if 1846 <= jahr <= 1856:
            i = interpoliere({1846: b46, 1856: b56}, jahr)
            return i["wert"], grundlage(i, "Burger der Stadt (Männer und Frauen)")
        return b46, f"Burger der Stadt 1846 ({b46:.0f}), unverändert übernommen (geschlossene Körperschaft)"

    def nichtburger(self, jahr: int) -> tuple[float, str]:
        n46 = self.bev[1846] - self.wert("burger_m", 1846) - self.wert("burger_f", 1846)
        n56 = self.bev[1856] - self.wert("burger", 1856)
        return self.zwischen(n46, 1846, n56, 1856, jahr, "Wohnbevölkerung ohne Burger der Stadt")


def grundlage(i: dict, was: str) -> str:
    if i["art"] == "exakt":
        return f"{was} {i['jahre'][0]}"
    if i["art"] == "interpoliert":
        return f"{was}, linear interpoliert zwischen {i['jahre'][0]} und {i['jahre'][1]}"
    return f"{was} {i['jahre'][0]} (nächstes Stichjahr, nicht umgerechnet)"


def rechnen() -> dict:
    eintraege = lies_csv(CSV_DIR / "04_entries.csv")
    orte = {r["entry_id"]: r for r in lies_csv(CSV_DIR / "06_entry_places.csv")}
    N = Nenner(lies_csv(REF / "bernhist_werte.csv"))
    regeln = lade_regeln()
    namen = [r for r in eintraege if r["kind"] in ("person", "firma")]

    zeilen: list[dict] = []

    def z(band, bereich, kennzahl, zaehler, nenner=None, basis="", je=100, anm=""):
        q = quote(zaehler, nenner, je)
        zeilen.append({"band": band, "bereich": bereich, "kennzahl": kennzahl, "zaehler": runde(zaehler),
                       "nenner": "" if nenner is None else runde(round(nenner, 1)),
                       "quote": "" if q is None else round(q, 2),
                       "einheit": "" if q is None else f"je {je}", "nenner_grundlage": basis, "anmerkung": anm})

    gruppen_zeilen = []
    stadt_je_band = {}
    for band in BAENDE:
        jahr = int(band)
        alle = [r for r in namen if r["volume"] == band]
        stadt = [r for r in alle if stadt_bereich(r, orte[r["entry_id"]]) == "stadt"]
        stadt_je_band[band] = stadt
        personen = {personen_schluessel(r) for r in stadt}
        bev, bev_g = N.einwohner(jahr)
        hh, hh_g = N.haushalte(jahr)
        z(band, "ganzer Band", "Einträge (Personen und Firmen)", len(alle))
        z(band, "ganzer Band", "verschiedene Personen (Näherung)", len({personen_schluessel(r) for r in alle}))
        z(band, "Stadt Bern", "Einträge", len(stadt), bev, bev_g)
        z(band, "Stadt Bern", "verschiedene Personen (Näherung)", len(personen), bev, bev_g)
        z(band, "Stadt Bern", "verschiedene Personen je Haushalt", len(personen), hh, hh_g)

        def pers(liste):
            return len({personen_schluessel(r) for r in liste})

        frauen = [r for r in stadt if ist_frau(r)]
        witwen = [r for r in stadt if ist_witwe(r)]
        jungfern = [r for r in stadt if ist_jungfer(r)]
        z(band, "Stadt Bern", "Frauen: Anteil an den Personen", pers(frauen), len(personen),
          "verschiedene Personen des Bandes in der Stadt")
        f, f_g = N.frauen(jahr)
        z(band, "Stadt Bern", "Frauen je Einwohnerin", pers(frauen), f, f_g,
          anm="Nenner zählt alle Frauen und Mädchen")
        w, w_g = N.anteilig(N.wert("f_verwitwet", 1846), 1846, jahr, "verwitwete Frauen")
        z(band, "Stadt Bern", "Witwen je verwitwete Frau", pers(witwen), w, w_g)
        z(band, "Stadt Bern", "Jungfern (Anrede Jungfer, Demoiselle)", pers(jungfern),
          anm="kein passender Nenner: «ledige Frauen» (1846: %d) schliesst Kinder ein" % N.wert("f_ledig", 1846))

        if band in ("1836", "1839"):
            kb = {r["entry_id"]: kennbuchstaben(r["note"], r["origin"], r["household"]) for r in stadt}
            burger = [r for r in stadt if "B" in kb[r["entry_id"]]]
            haus = [r for r in stadt if "H" in kb[r["entry_id"]]]
            b, b_g = N.burger(jahr)
            z(band, "Stadt Bern", "Burger (Kennbuchstabe B.): Anteil an den Personen", pers(burger), len(personen),
              "verschiedene Personen des Bandes in der Stadt")
            z(band, "Stadt Bern", "Burger (B.) je Burger und Burgerin", pers(burger), b, b_g,
              anm="Nenner zählt Köpfe (Frauen und Kinder eingeschlossen)")
            z(band, "Stadt Bern", "Burger (B.) je männlichen Burger", pers([r for r in burger if not ist_frau(r)]),
              N.wert("burger_m", 1846), "männliche Burger 1846 (alle Alter), unverändert übernommen")
            nb, nb_g = N.nichtburger(jahr)
            z(band, "Stadt Bern", "Nichtburger (ohne B.) je Einwohner ohne Burgerrecht", len(personen) - pers(burger),
              nb, nb_g)
            z(band, "Stadt Bern", "Hauseigentümer (Kennbuchstabe H.) je Hausbesitzer", pers(haus),
              N.wert("hausbesitzer", 1856), "in der Stadt wohnhafte Hausbesitzer 1856, unverändert übernommen")
            z(band, "Stadt Bern", "Hauseigentümer (H.) je Wohnhaus", pers(haus), N.wert("wohnhaeuser", 1856),
              "ausschliessliche Wohnhäuser 1856, unverändert übernommen")
        if band == "1848":
            koepfe = sum(1 + sum(haushalt_1848(r["household"])) for r in stadt)
            ehefrauen = sum(haushalt_1848(r["household"])[0] for r in stadt)
            kinder = sum(haushalt_1848(r["household"])[1] for r in stadt)
            nb, nb_g = N.nichtburger(jahr)
            z(band, "Stadt Bern", "Einsassen-Haushalte je Haushalt der Stadt", len(stadt), hh, hh_g,
              anm="Zähler nur Nichtburger, Nenner alle Haushalte")
            z(band, "Stadt Bern", "Köpfe in Einsassen-Haushalten (Vorstand, Ehefrau, Kinder) je Einwohner ohne Burgerrecht",
              koepfe, nb, nb_g, anm=f"{len(stadt)} Vorstände, {ehefrauen} Ehefrauen, {kinder} Kinder")
            nied = sum(N.wert(k, 1856) for k in ("bern_niedergelassene", "kantone_niedergelassene", "ausl_niedergelassene"))
            z(band, "Stadt Bern", "Köpfe in Einsassen-Haushalten je Niedergelassenen von 1856", koepfe, nied,
              "Niedergelassene ohne Burgerrecht 1856 (Berner, andere Kantone, Ausländer), unverändert übernommen")
            z(band, "Stadt Bern", "Köpfe in Einsassen-Haushalten je Einwohner", koepfe, bev, bev_g)
            bereich = Counter(stadt_bereich(r, orte[r["entry_id"]]) for r in alle)
            z(band, "Stadt Bern", "Einträge unter «Veränderungen» (nicht mitgezählt)", bereich["veraenderungen"])
            z(band, "Stadt Bern", "neue Einsassen Jan./Feb. 1848 (nicht mitgezählt)", bereich["neue_einsassen"])

        # Berufsgruppen: je Person die Gruppe ihres ersten Eintrags mit bestimmbarem Beruf
        gruppe_person: dict[tuple, str] = {}
        arzt_person: dict[tuple, str] = {}
        for r in stadt:
            k = personen_schluessel(r)
            g = gruppe_eintrag(r, regeln)
            if gruppe_person.get(k, "unbestimmt") == "unbestimmt":
                gruppe_person[k] = g
            a = arzt_art(berufsangabe(r) + " | " + (r["heading"] if band in ("1795", "1810", "1822") else "")
                         + " | " + r["title"])
            if a == "arzt" or (a and k not in arzt_person):
                arzt_person[k] = a
        cg = Counter(gruppe_person.values())
        for g in GRUPPEN:
            gruppen_zeilen.append({"band": band, "bereich": "Stadt Bern", "gruppe": g, "bezeichnung": GRUPPEN_LABEL[g],
                                   "sektor": SEKTOR[g], "personen": cg[g],
                                   "anteil_prozent": round(100 * cg[g] / max(1, len(personen)), 1)})
        bestimmt = len(personen) - cg["unbestimmt"]
        z(band, "Stadt Bern", "Personen mit bestimmbarer Berufsgruppe", bestimmt, len(personen),
          "verschiedene Personen des Bandes in der Stadt")

        def n56(schl, was):
            return N.anteilig(N.wert(schl, 1856), 1856, jahr, was)

        sek = Counter(SEKTOR[g] for g in gruppe_person.values())
        erwerb = sek["1"] + sek["2"] + sek["3"] + sek["Dienstboten"] + sek["Taglöhner"]
        n, g_ = N.anteilig(min(N.reihen[(STADT, THEMEN["erwerbstaetige"])][1856]), 1856, jahr, "Erwerbstätige")
        z(band, "Stadt Bern", "Personen mit Erwerb je Erwerbstätigen", erwerb, n, g_)
        for s, schl, was in (("1", "sektor1", "Erwerbstätige 1. Sektor"), ("2", "sektor2", "Erwerbstätige 2. Sektor"),
                             ("3", "sektor3", "Erwerbstätige 3. Sektor")):
            n, g_ = n56(schl, was)
            z(band, "Stadt Bern", f"{s}. Sektor je Erwerbstätigen des Sektors", sek[s], n, g_,
              anm="BERNHIST zählt 1856 vermutlich Dienstboten und Taglöhner zum 1. Sektor" if s == "1" else "")
        n, g_ = n56("selbstaendige", "Selbständige")
        z(band, "Stadt Bern", "Selbständige (Näherung) je Selbständigen", sum(cg[g] for g in SELBSTAENDIG), n, g_,
          anm="Zähler: Handwerk, Handel, Gastgewerbe, Verkehr, Gesundheit, Recht, Kunst, Dienste, Landwirtschaft")
        n, g_ = n56("sektor2", "Erwerbstätige 2. Sektor")
        z(band, "Stadt Bern", "Handwerk und Gewerbe je Erwerbstätigen im 2. Sektor", cg["handwerk"], n, g_)
        n, g_ = n56("dienstboten", "Dienstboten")
        z(band, "Stadt Bern", "Dienstboten je Dienstboten", cg["dienstboten"], n, g_)
        n, g_ = n56("tagloehner", "Taglöhner")
        z(band, "Stadt Bern", "Taglöhner je Taglöhner", cg["tagloehner"], n, g_)
        n, g_ = n56("aerzte", "Ärzte")
        ca = Counter(arzt_person.values())
        z(band, "Stadt Bern", "Ärzte (Arzt, Médecin, Med. Dr.) je Arzt", ca["arzt"], n, g_)
        z(band, "Stadt Bern", "Ärzte und Wundärzte je Arzt", ca["arzt"] + ca["wundarzt"], n, g_,
          anm="Zähler mit Wundärzten, Chirurgen, Opérateurs; Nenner vermutlich nur Ärzte")

    # --- 1836 Nachtrag der Stadt -------------------------------------------------------------------------------
    nt = [r for r in namen if r["volume"] == "1836" and r["section"] == "einwohner_nachtrag"]
    z("1836", "Stadt Bern", "Einträge im Nachtrag «Adressenberichtigungen» (nicht mitgezählt)", len(nt),
      anm="Berichtigungen zu bestehenden Einträgen und Nachzügler, nicht trennbar")

    # --- Amtsbezirke -------------------------------------------------------------------------------------------
    bind = {f'{o["ort"]}|{o["lat"]}|{o["lon"]}': o for o in lies_csv(REF / "bernhist_orte.csv")}
    reihe_amt: dict[str, dict[int, float]] = defaultdict(dict)
    for w in lies_csv(REF / "bernhist_werte.csv"):
        if int(w["thema_id"]) == THEMEN["bev"] and w["ortstyp"] in ("Amtsbezirk", "Kanton"):
            reihe_amt[w["ort"] if w["ortstyp"] == "Amtsbezirk" else "Kanton Bern"][int(w["jahr_von"])] = float(w["wert"])
    bev37 = {a: r[1837] for a, r in reihe_amt.items()}
    bev10 = {a: interpoliere(r, 1810)["wert"] for a, r in reihe_amt.items()}
    praef_ok = praef_n = 0
    zaehl = defaultdict(Counter)
    seiten_amt = defaultdict(list)
    kant = []
    for r in namen:
        if ist_kantonsteil(r):
            o = orte[r["entry_id"]]
            b = bind.get(ort_key(o), {"amtsbezirk": "", "methode": "offen"})
            amt = b["amtsbezirk"] or {"kanton_jura": "(heute Kanton Jura, nicht in BERNHIST)",
                                      "ausserhalb": "(ausserhalb des Kantons)", "ohne_ort": "(ohne Ort)"}.get(
                                          b["methode"], "(Ort nicht zugeordnet)")
            spalte = {"1810": "e1810", "1839": "e1839"}.get(r["volume"]) or \
                {"kanton": "e1836", "kanton_nachtrag": "e1836_nachtrag"}[r["section"]]
            praef = praefektur_1810(r["heading"]) if r["volume"] == "1810" else None   # nur wo die Rubrik sie nennt
            if b["amtsbezirk"] and praef and praef != "?":
                praef_n += 1
                praef_ok += b["amtsbezirk"] == praef
            zaehl[amt][spalte] += 1
            if o["precision"] == "ungefähr":
                zaehl[amt]["ungefaehr"] += 1
            zaehl[amt]["m_" + b["methode"]] += 1
            kant.append((r, amt, b))
            if b["amtsbezirk"]:
                seiten_amt[(r["volume"], r["section"], int(r["page"]))].append(amt)
    # Prüfung: weicht der Amtsbezirk eines Eintrags von der Mehrheit seiner Seite ab?
    abweichend = sum(1 for r, amt, b in kant if b["amtsbezirk"]
                     and amt != mehrheit(seiten_amt[(r["volume"], r["section"], int(r["page"]))]))
    zugeordnet = sum(1 for _, _, b in kant if b["amtsbezirk"])
    amt_zeilen = []
    stadt36 = len({personen_schluessel(r) for r in stadt_je_band["1836"]})
    for amt in sorted(zaehl, key=lambda a: (a.startswith("("), a)):
        c, bev = zaehl[amt], bev37.get(amt)
        anm = ""
        if amt == "Bern":
            anm = (f"ohne das Einwohnerverzeichnis der Stadt ({stadt36} Personen); Amt ohne Stadt: "
                   f"{bev - N.bev[1837]:.0f} Einwohner, {1000 * c['e1836'] / (bev - N.bev[1837]):.1f} je 1000")
        b10 = bev10.get(amt) if amt in BERNISCH_1810 else None
        amt_zeilen.append({"amtsbezirk": amt, "einwohner_1810": "" if b10 is None else round(b10),
                           "eintraege_1810": c["e1810"],
                           "je_1000_einwohner_1810": "" if b10 is None else round(1000 * c["e1810"] / b10, 2),
                           "einwohner_1837": "" if bev is None else round(bev),
                           "eintraege_1836": c["e1836"], "je_1000_einwohner": "" if bev is None else round(1000 * c["e1836"] / bev, 1),
                           "eintraege_1836_nachtrag": c["e1836_nachtrag"], "eintraege_1839": c["e1839"],
                           "davon_ort_ungefaehr": c["ungefaehr"],
                           "davon_ueber_naechste_gemeinde": c["m_naechste_gemeinde"], "anmerkung": anm})
    summe = sum(a["eintraege_1836"] for a in amt_zeilen if a["einwohner_1837"] != "")
    s10 = sum(a["eintraege_1810"] for a in amt_zeilen if a["einwohner_1837"] != "")
    bev10_kanton = sum(v for a, v in bev10.items() if a in BERNISCH_1810)
    amt_zeilen.append({"amtsbezirk": "Kanton Bern (27 Amtsbezirke von BERNHIST)",
                       "einwohner_1810": round(bev10_kanton), "eintraege_1810": s10,
                       "je_1000_einwohner_1810": round(1000 * s10 / bev10_kanton, 2),
                       "einwohner_1837": round(bev37["Kanton Bern"]),
                       "eintraege_1836": summe, "je_1000_einwohner": round(1000 * summe / bev37["Kanton Bern"], 1),
                       "eintraege_1836_nachtrag": sum(a["eintraege_1836_nachtrag"] for a in amt_zeilen if a["einwohner_1837"] != ""),
                       "eintraege_1839": sum(a["eintraege_1839"] for a in amt_zeilen if a["einwohner_1837"] != ""),
                       "davon_ort_ungefaehr": "", "davon_ueber_naechste_gemeinde": "",
                       "anmerkung": "ohne das Einwohnerverzeichnis der Stadt Bern bzw. Teil A von 1810; "
                                    "1810: Bevölkerung interpoliert zwischen 1798 und 1818, nur die 22 damals bernischen Amtsbezirke "
                                    "(ohne Biel, Courtelary, Laufen, Moutier, Neuveville: 1810 französisch)"})
    offen = [o for o in bind.values() if not o["amtsbezirk"]]

    # --- Stichprobe zur Berufszuordnung --------------------------------------------------------------------------
    sp_pfad = OUT / "berufe_stichprobe.csv"
    alt = {r["entry_id"]: r for r in lies_csv(sp_pfad)} if sp_pfad.exists() else {}
    sp = []
    for r in ziehe_stichprobe(eintraege):
        g = gruppe_eintrag(r, regeln)
        a = alt.get(r["entry_id"], {})
        gilt = a.get("gruppe") == g          # ein Urteil gilt nur für die Zuordnung, zu der es gefällt wurde
        sp.append({"entry_id": r["entry_id"], "band": r["volume"], "rubrik": r["heading"], "beruf": r["occupation"],
                   "wortlaut": r["text"][:160], "gruppe": g, "sektor": SEKTOR[g],
                   "urteil": a.get("urteil", "") if gilt else "", "soll_gruppe": a.get("soll_gruppe", "") if gilt else "",
                   "bemerkung": a.get("bemerkung", "") if gilt else ""})
    schreibe_csv(sp_pfad, sp)
    beurteilt = [s for s in sp if s["urteil"]]
    treffer = {
        "n": len(sp), "beurteilt": len(beurteilt),
        "gruppe_richtig": sum(1 for s in beurteilt if s["urteil"] == "richtig"),
        "sektor_richtig": sum(1 for s in beurteilt if s["urteil"] == "richtig"
                              or SEKTOR.get(s["soll_gruppe"]) == s["sektor"]),
    }

    schreibe_csv(OUT / "baende.csv", zeilen)
    schreibe_csv(OUT / "berufsgruppen.csv", gruppen_zeilen)
    schreibe_csv(OUT / "amtsbezirke.csv", amt_zeilen)
    felder_offen = ["ort", "kanton_heute", "eintraege", "methode", "bemerkung", "lat", "lon"]
    schreibe_csv(OUT / "orte_offen.csv", [{f: o[f] for f in felder_offen} for o in
                                          sorted(offen, key=lambda o: (o["methode"], -int(o["eintraege"]), o["ort"]))],
                 felder_offen)
    erg = {"zeilen": zeilen, "gruppen": gruppen_zeilen, "aemter": amt_zeilen, "offen": offen, "treffer": treffer,
           "pruefung": {"zugeordnet": zugeordnet, "abweichend": abweichend, "kantonseintraege": len(kant),
                        "praef_ok": praef_ok, "praef_n": praef_n},
           "methoden": Counter(b["methode"] for _, _, b in kant)}
    schreibe_seite(erg)
    schreibe_doku(erg)
    return erg


def runde(x):
    return int(x) if float(x).is_integer() else round(x, 1)


# ---------------------------------------------------------------------------------------------------------------
# Ausgabe: Seite und Doku
# ---------------------------------------------------------------------------------------------------------------

def zahl(x, stellen: int = 0) -> str:
    """Schweizer Schreibweise: 22 546 (schmales geschütztes Leerzeichen), Dezimalpunkt -> Komma."""
    if x == "" or x is None:
        return "–"
    x = float(x)
    s = f"{x:,.{stellen}f}".replace(",", " ").replace(".", ",")
    return s


KERN = ["Einträge", "verschiedene Personen (Näherung)", "verschiedene Personen je Haushalt",
        "Frauen: Anteil an den Personen", "Witwen je verwitwete Frau"]


def tabellen(erg: dict) -> dict[str, tuple[list[str], list[list[str]]]]:
    """Die Tabellen als (Kopf, Zeilen) – für HTML und Markdown gleich."""
    Z = defaultdict(dict)
    for r in erg["zeilen"]:
        if r["bereich"] == "Stadt Bern":
            Z[r["band"]][r["kennzahl"]] = r
    t = {}
    kopf = ["Band", "Einträge Stadt", "Personen", "Einwohner", "je 100 Einw.", "Haushalte", "je 100 Haushalte"]
    zl = []
    for b in BAENDE:
        p, h = Z[b]["verschiedene Personen (Näherung)"], Z[b]["verschiedene Personen je Haushalt"]
        zl.append([b, zahl(Z[b]["Einträge"]["zaehler"]), zahl(p["zaehler"]), zahl(p["nenner"]), zahl(p["quote"], 1),
                   zahl(h["nenner"]), zahl(h["quote"], 1)])
    t["stadt"] = (kopf, zl)
    kopf = ["Band", "Frauen", "Anteil an den Personen", "je 100 Einwohnerinnen", "Witwen", "je 100 verwitwete Frauen", "Jungfern"]
    zl = []
    for b in BAENDE:
        f, fe, w, j = (Z[b]["Frauen: Anteil an den Personen"], Z[b]["Frauen je Einwohnerin"],
                       Z[b]["Witwen je verwitwete Frau"], Z[b]["Jungfern (Anrede Jungfer, Demoiselle)"])
        zl.append([b, zahl(f["zaehler"]), zahl(f["quote"], 1) + " %", zahl(fe["quote"], 1), zahl(w["zaehler"]),
                   zahl(w["quote"], 1), zahl(j["zaehler"])])
    t["frauen"] = (kopf, zl)
    kopf = ["Band", "Kennzahl", "Zähler", "Nenner", "je 100", "Nenner aus BERNHIST"]
    zl = []
    for r in erg["zeilen"]:
        if r["bereich"] == "Stadt Bern" and re.search(r"urger|Hauseigent|Einsassen-|Köpfe", r["kennzahl"]):
            zl.append([r["band"], r["kennzahl"], zahl(r["zaehler"]), zahl(r["nenner"]),
                       zahl(r["quote"], 1), r["nenner_grundlage"]])
    t["burger"] = (kopf, zl)
    namen = [("Personen mit Erwerb je Erwerbstätigen", "Erwerb"), ("2. Sektor je Erwerbstätigen des Sektors", "2. Sektor"),
             ("3. Sektor je Erwerbstätigen des Sektors", "3. Sektor"),
             ("Selbständige (Näherung) je Selbständigen", "Selbständige"), ("Dienstboten je Dienstboten", "Dienstboten"),
             ("Taglöhner je Taglöhner", "Taglöhner"), ("Ärzte (Arzt, Médecin, Med. Dr.) je Arzt", "Ärzte"),
             ("Ärzte und Wundärzte je Arzt", "Ärzte und Wundärzte")]
    kopf = ["Band"] + [n for _, n in namen]
    zl = []
    for b in BAENDE:
        zl.append([b] + [f'{zahl(Z[b][k]["zaehler"])} / {zahl(Z[b][k]["nenner"])} = {zahl(Z[b][k]["quote"], 0)} %' for k, _ in namen])
    t["berufe"] = (kopf, zl)
    G = defaultdict(dict)
    for g in erg["gruppen"]:
        G[g["gruppe"]][g["band"]] = g
    kopf = ["Gruppe", "Sektor"] + BAENDE
    t["gruppen"] = (kopf, [[GRUPPEN_LABEL[g], SEKTOR[g]] + [zahl(G[g][b]["personen"]) for b in BAENDE] for g in GRUPPEN])
    kopf = ["Amtsbezirk (BERNHIST)", "Einwohner 1810", "Einträge 1810", "je 1000 Einw. 1810",
            "Einwohner 1837", "Einträge 1836", "je 1000 Einw. 1836", "Nachtrag 1836", "Ergänzung 1839"]
    t["aemter"] = (kopf, [[a["amtsbezirk"], zahl(a["einwohner_1810"]), zahl(a["eintraege_1810"]),
                           zahl(a["je_1000_einwohner_1810"], 1), zahl(a["einwohner_1837"]), zahl(a["eintraege_1836"]),
                           zahl(a["je_1000_einwohner"], 1), zahl(a["eintraege_1836_nachtrag"]), zahl(a["eintraege_1839"])]
                          for a in erg["aemter"]])
    return t


TITEL = {"stadt": "Stadt Bern: Personen je Einwohner und je Haushalt",
         "frauen": "Stadt Bern: Frauen, Witwen, Jungfern",
         "burger": "Stadt Bern: Burger, Hauseigentümer, Einsassen",
         "berufe": "Stadt Bern: Berufsgruppen gegen die Zählung von 1856 (Zähler / Nenner = Quote)",
         "gruppen": "Stadt Bern: Personen je Berufsgruppe",
         "aemter": "Kantonsteile 1810, 1836 und 1839: Einträge je Amtsbezirk"}


def md_tabelle(kopf, zeilen) -> str:
    out = ["| " + " | ".join(kopf) + " |", "|" + "|".join("---" if i < 1 else "---:" for i in range(len(kopf))) + "|"]
    out += ["| " + " | ".join(str(c) for c in z) + " |" for z in zeilen]
    return "\n".join(out)


def html_tabelle(kopf, zeilen, titel) -> str:
    e = html.escape
    th = "".join(f"<th>{e(k)}</th>" for k in kopf)
    tr = "".join("<tr>" + "".join(f'<td{"" if i == 0 or not re.match(r"^[\d–]", str(c)) else " class=\"num\""}>{e(str(c))}</td>'
                                  for i, c in enumerate(z)) + "</tr>\n" for z in zeilen)
    return f'<div class="tablewrap"><table class="abd"><caption>{e(titel)}</caption><thead><tr>{th}</tr></thead>\n<tbody>\n{tr}</tbody></table></div>'


def stichprobe_satz(erg: dict) -> str:
    t = erg["treffer"]
    if not t["beurteilt"]:
        return f"Stichprobe von {t['n']} Einträgen gezogen, noch nicht beurteilt."
    return (f"Stichprobe: {t['beurteilt']} zufällig gezogene Einträge (10 je Band), am Wortlaut des Eintrags beurteilt: "
            f"Gruppe richtig bei {t['gruppe_richtig']} ({zahl(100 * t['gruppe_richtig'] / t['beurteilt'])} %), "
            f"Sektor richtig bei {t['sektor_richtig']} ({zahl(100 * t['sektor_richtig'] / t['beurteilt'])} %).")


def pruef_satz(erg: dict) -> str:
    p, m = erg["pruefung"], erg["methoden"]
    return (f"Von {zahl(p['kantonseintraege'])} Einträgen der Kantonsteile (1810, 1836, 1839) sind {zahl(p['zugeordnet'])} einem Amtsbezirk "
            f"zugeordnet: {zahl(m['name'] + m['name_seitenkontext'])} über den Ortsnamen, {zahl(m['gemeinde_heute'] + m['gemeinde_heute_seitenkontext'])} über die "
            f"heutige Gemeinde des Weilers, {zahl(m['naechste_gemeinde'])} über die nächste gebundene Gemeinde. "
            f"{zahl(m['kanton_jura'])} liegen im heutigen Kanton Jura, {zahl(m['ausserhalb'])} ausserhalb, "
            f"{zahl(m['ohne_ort'])} haben keinen Ort, {zahl(m['offen'])} blieben offen. "
            f"Bei {zahl(p['abweichend'])} zugeordneten Einträgen ({zahl(100 * p['abweichend'] / max(1, p['zugeordnet']), 1)} %) "
            f"weicht der Amtsbezirk von der Mehrheit ihrer Buchseite ab (Seitenwechsel zwischen zwei Ämtern oder falsch verorteter Ort). "
            f"1810 nennt das Buch die Préfecture selbst: bei {zahl(p['praef_ok'])} von {zahl(p['praef_n'])} zugeordneten Einträgen "
            f"({zahl(100 * p['praef_ok'] / max(1, p['praef_n']))} %) stimmt sie mit dem Amtsbezirk überein.")


def schreibe_doku(erg: dict) -> None:
    pfad = ROOT / "docs/abdeckung.md"
    t = tabellen(erg)
    block = "\n\n".join(f"### {TITEL[k]}\n\n{md_tabelle(*t[k])}" for k in t)
    block += "\n\n" + stichprobe_satz(erg) + "\n\n" + pruef_satz(erg)
    block = "<!-- abdeckung:tabellen -->\n" + block + "\n<!-- /abdeckung:tabellen -->"
    text = pfad.read_text() if pfad.exists() else "# Abdeckung\n\n<!-- abdeckung:tabellen -->\n<!-- /abdeckung:tabellen -->\n"
    text = re.sub(r"<!-- abdeckung:tabellen -->.*?<!-- /abdeckung:tabellen -->", lambda m: block, text, flags=re.S)
    pfad.write_text(text)


def schreibe_seite(erg: dict) -> None:
    """site/abdeckung.html: Tabellen zwischen den Markierungen; der übrige Text der Seite steht in der Datei."""
    pfad = ROOT / "site/abdeckung.html"
    if not pfad.exists():
        return
    t = tabellen(erg)
    text = pfad.read_text()
    for k in t:
        block = f"<!-- abdeckung:{k} -->{html_tabelle(*t[k], TITEL[k])}<!-- /abdeckung -->"
        text = re.sub(rf"<!-- abdeckung:{k} -->.*?<!-- /abdeckung -->", lambda m: block, text, flags=re.S)
    for k, satz in (("stichprobe", stichprobe_satz(erg)), ("pruefung", pruef_satz(erg))):
        block = f"<!-- abdeckung:{k} -->{html.escape(satz)}<!-- /abdeckung -->"
        text = re.sub(rf"<!-- abdeckung:{k} -->.*?<!-- /abdeckung -->", lambda m: block, text, flags=re.S)
    pfad.write_text(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("schritt", choices=["referenz", "rechnen", "alles"])
    ap.add_argument("--bernhist", default=os.environ.get("BERNHIST_SQLITE"),
                    help="Pfad zum BERNHIST-Dump als SQLite (oder Umgebungsvariable BERNHIST_SQLITE)")
    a = ap.parse_args(argv)
    if a.schritt in ("referenz", "alles"):
        if not a.bernhist or not Path(a.bernhist).exists():
            print("BERNHIST-SQLite nicht gefunden: --bernhist PFAD oder BERNHIST_SQLITE setzen.", file=sys.stderr)
            return 2
        referenz(a.bernhist)
    if a.schritt in ("rechnen", "alles"):
        erg = rechnen()
        print(f"rechnen: {len(erg['zeilen'])} Kennzahlen, {len(erg['aemter'])} Amtsbezirkszeilen ->", OUT)
        print(stichprobe_satz(erg))
        print(pruef_satz(erg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
