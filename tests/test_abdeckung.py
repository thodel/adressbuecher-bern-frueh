"""Tests für die Rechenlogik von scripts/abdeckung.py (ohne BERNHIST-Dump lauffähig).

    python3 -m unittest discover -s tests -v
"""
import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import abdeckung as A  # noqa: E402

REGELN = A.lade_regeln()


class Interpolation(unittest.TestCase):
    BEV = {1798: 11343, 1818: 17552, 1837: 22546, 1846: 25129, 1850: 27588}

    def test_stichjahr_exakt(self):
        i = A.interpoliere(self.BEV, 1837)
        self.assertEqual((i["wert"], i["art"], i["jahre"]), (22546.0, "exakt", (1837,)))

    def test_linear_zwischen_zwei_stichjahren(self):
        i = A.interpoliere(self.BEV, 1822)
        self.assertEqual(i["jahre"], (1818, 1837))
        self.assertAlmostEqual(i["wert"], 17552 + (22546 - 17552) * 4 / 19)
        self.assertEqual(i["art"], "interpoliert")

    def test_mitte(self):
        self.assertAlmostEqual(A.interpoliere({1800: 100, 1810: 200}, 1805)["wert"], 150)

    def test_ausserhalb_wird_nicht_extrapoliert(self):
        i = A.interpoliere(self.BEV, 1795)
        self.assertEqual((i["wert"], i["art"], i["jahre"]), (11343.0, "naechstes_stichjahr", (1798,)))
        self.assertEqual(A.interpoliere(self.BEV, 1860)["jahre"], (1850,))

    def test_leere_reihe(self):
        with self.assertRaises(ValueError):
            A.interpoliere({}, 1800)

    def test_skalieren_haelt_den_anteil(self):
        # 1308 verwitwete Frauen 1846; 1837 ist die Bevölkerung 22546/25129 so gross
        self.assertAlmostEqual(A.skaliere(1308, 1846, self.BEV, 1837), 1308 * 22546 / 25129)
        self.assertAlmostEqual(A.skaliere(1308, 1846, self.BEV, 1846), 1308)

    def test_quote(self):
        self.assertAlmostEqual(A.quote(50, 200), 25)
        self.assertAlmostEqual(A.quote(3, 1500, je=1000), 2)
        self.assertIsNone(A.quote(3, None))
        self.assertIsNone(A.quote(3, 0))


class Ortsnamen(unittest.TestCase):
    def test_klammerzusatz_und_kanton(self):
        self.assertEqual(A.ort_schluessel("Bargen (BE)"), "bargen")
        self.assertEqual(A.ort_schluessel("Romont BE"), "romont")
        self.assertEqual(A.ort_schluessel("Kirchberg (BE)"), A.ort_schluessel("Kirchberg"))

    def test_umlaut_und_st(self):
        self.assertEqual(A.ort_schluessel("Büren an der Aare"), "buren an der aare")
        self.assertEqual(A.ort_schluessel("St. Immer"), A.ort_schluessel("Sankt Immer"))
        self.assertEqual(A.ort_schluessel("Saint-Imier"), "st imier")
        self.assertEqual(A.ort_schluessel("Lütschenthal"), A.ort_schluessel("Lütschental"))

    def test_varianten_von_bernhist_namen(self):
        self.assertEqual(A.ort_varianten("Grossaffoltern / Affoltern"), {"grossaffoltern", "affoltern"})
        self.assertEqual(A.ort_varianten("Neuveville, La"), {"la neuveville", "neuveville"})
        self.assertEqual(A.ort_varianten("Bolligen (mit Ittigen, Ostermundigen)"), {"bolligen"})
        self.assertIn("biel", A.ort_varianten("Biel / Bienne (BE) (ab 1920 mit Bözingen, Mett, Madretsch)"))
        self.assertEqual(A.ort_varianten("Kandergrund (bis 1909 mit Kandersteg)"), {"kandergrund"})

    def test_lagezusatz(self):
        self.assertEqual(A.ort_kurz("buren an der aare"), "buren")
        self.assertEqual(A.ort_kurz("bangerten b dieterswil"), "bangerten")
        self.assertEqual(A.ort_kurz("langenthal"), "langenthal")

    def test_distanz(self):
        self.assertAlmostEqual(A.distanz_km(46.948, 7.447, 46.758, 7.628), 25.2, delta=0.5)  # Bern–Thun
        self.assertEqual(A.distanz_km(46.9, 7.4, 46.9, 7.4), 0)

    def test_mehrheit(self):
        self.assertEqual(A.mehrheit(["Thun", "Thun", "Bern", ""]), "Thun")
        self.assertIsNone(A.mehrheit(["", None]))


class Berufe(unittest.TestCase):
    def g(self, text):
        return A.beruf_gruppe(text, REGELN)

    def test_grundwort_hinten_gewinnt(self):
        self.assertEqual(self.g("Tabakfabrikant"), "handwerk")
        self.assertEqual(self.g("Weinhändler"), "handel")
        self.assertEqual(self.g("Landwirth"), "landwirtschaft")
        self.assertEqual(self.g("Pintenwirth"), "gastgewerbe")
        self.assertEqual(self.g("Silberarbeiter"), "handwerk")
        self.assertEqual(self.g("Fabrikarbeiter"), "arbeiter")
        self.assertEqual(self.g("Amtschreiber"), "verwaltung")
        self.assertEqual(self.g("Schreiber"), "angestellte")

    def test_erstgenannte_taetigkeit(self):
        self.assertEqual(self.g("Pintenwirth, auch Krämer"), "gastgewerbe")
        self.assertEqual(self.g("Kellermagd u. Wochenmarktkrämerin"), "dienstboten")
        self.assertEqual(self.g("gew. Pfarrer"), "bildung_kirche")

    def test_angehoerige_zaehlen_nicht(self):
        self.assertEqual(self.g("des Taglöhners Frau, Kellermagd"), "dienstboten")
        self.assertEqual(self.g("des Pächters Wittwe"), "unbestimmt")

    def test_gruppen(self):
        for text, gruppe in [("Schuhmachermstr.", "handwerk"), ("Bäckermeister", "handwerk"), ("Taglöhner", "tagloehner"),
                             ("Lohnbedienter", "dienstboten"), ("Thierarzt", "gesundheit"), ("Médecins.", "gesundheit"),
                             ("Notaires", "recht"), ("Epicerie", "handel"), ("Marchands de vins", "handel"),
                             ("Aubergistes", "gastgewerbe"), ("Lehnkutscher", "verkehr"), ("privat.", "ohne_erwerb"),
                             ("Hauseigenthümer", "ohne_erwerb"), ("Rentière", "ohne_erwerb"), ("Hauptmann", "militaer"),
                             ("Kunstmaler", "kunst"), ("Flachmaler", "handwerk"), ("Lohnwascherin", "dienste"),
                             ("Gärtner", "landwirtschaft"), ("", "unbestimmt"), ("in Thun", "unbestimmt")]:
            with self.subTest(text=text):
                self.assertEqual(self.g(text), gruppe)

    def test_jede_gruppe_hat_sektor_und_namen(self):
        for gruppe, _ in REGELN:
            self.assertIn(gruppe, A.SEKTOR)
            self.assertIn(gruppe, A.GRUPPEN_LABEL)
        self.assertEqual(set(A.GRUPPEN), set(A.SEKTOR))

    def test_aerzte(self):
        self.assertEqual(A.arzt_art("Arzt u. Wundarzt"), "arzt")
        self.assertEqual(A.arzt_art("Med. Dr."), "arzt")
        self.assertEqual(A.arzt_art("Médecins."), "arzt")
        self.assertEqual(A.arzt_art("Aerzte"), "arzt")
        self.assertEqual(A.arzt_art("Wundarzt"), "wundarzt")
        self.assertEqual(A.arzt_art("Chirurgiens"), "wundarzt")
        self.assertEqual(A.arzt_art("Thierarzt"), "")
        self.assertEqual(A.arzt_art("Zahnarzt"), "")
        self.assertEqual(A.arzt_art("Schreiner"), "")

    def test_rubrik_als_ersatz_nur_in_gewerbeteilen(self):
        r = {"volume": "1822", "section": "berufe", "occupation": "", "heading": "Schuhmacher."}
        self.assertEqual(A.gruppe_eintrag(r, REGELN), "handwerk")
        r = {"volume": "1848", "section": "einsassen", "occupation": "", "heading": "Schneider."}  # Familienname
        self.assertEqual(A.gruppe_eintrag(r, REGELN), "unbestimmt")


class Personen(unittest.TestCase):
    def test_kennbuchstaben(self):
        self.assertEqual(A.kennbuchstaben("B.; Rubrik von Vorseite"), {"B"})
        self.assertEqual(A.kennbuchstaben("H. u. B.; Rubrik von Vorseite"), {"H", "B"})
        self.assertEqual(A.kennbuchstaben("H und B."), {"H", "B"})
        self.assertEqual(A.kennbuchstaben("landesabwesend. B.; Rubrik von Vorseite"), {"B"})
        self.assertEqual(A.kennbuchstaben("", "Hu.", ""), {"H"})
        self.assertEqual(A.kennbuchstaben("Rubrik von Vorseite", "von Belp", "Beruf aus Vorzeile"), set())
        self.assertEqual(A.kennbuchstaben("Hebräer"), set())

    def test_frauen(self):
        f = lambda **k: A.ist_frau({"title": "", "forename": "", "occupation": "", **k})
        self.assertTrue(f(title="Wittwe"))
        self.assertTrue(f(title="la Veuve"))
        self.assertTrue(f(forename="Anna Maria"))
        self.assertTrue(f(forename="Elis."))
        self.assertTrue(f(occupation="Schneiderin"))
        self.assertTrue(f(occupation="des Taglöhners Frau, Kellermagd"))
        self.assertFalse(f(forename="Joh. Maria", occupation="Schneider"))
        self.assertFalse(f(forename="Jakob", occupation="Magazinier"))
        self.assertFalse(f(title="Gebrüder", occupation="Tuchhandlung"))

    def test_witwen_und_jungfern(self):
        self.assertTrue(A.ist_witwe({"title": "Frau Wittwe", "occupation": ""}))
        self.assertTrue(A.ist_witwe({"title": "", "occupation": "des Pächters Wittwe"}))
        self.assertTrue(A.ist_witwe({"volume": "1848", "title": "geb. Käser, W. v 2", "occupation": ""}))
        self.assertFalse(A.ist_witwe({"volume": "1836", "title": "W.", "occupation": ""}))
        self.assertTrue(A.ist_jungfer({"title": "Jungfer"}))
        self.assertFalse(A.ist_jungfer({"title": "jünger"}))

    def test_haushalt_1848(self):
        self.assertEqual(A.haushalt_1848("813 Fr. - Christina Zbinden. 5 T. - 833 Anna Maria. - 40 Maria Elisabetha."), (1, 5))
        self.assertEqual(A.haushalt_1848("2 T. - 833 Rosette Adele. - 34 Sophie Isabella."), (0, 2))
        self.assertEqual(A.haushalt_1848("Fr. II Ehe. — Elis. Brum a. Rolle. 5 K. — Aus I Ehe: 820 Christ. Gottl."), (1, 5))
        self.assertEqual(A.haushalt_1848(""), (0, 0))
        self.assertEqual(A.haushalt_1848("1 S. - 827 Eduard. 2 T. - 830 Anna. - 32 Maria."), (0, 3))

    def test_personenschluessel(self):
        a = {"volume": "1822", "section": "berufe", "surname": "Dünz", "forename": "Niklaus", "title": "", "place": "Bern"}
        b = dict(a, address="Bollwerk 84")
        self.assertEqual(A.personen_schluessel(a), A.personen_schluessel(b))            # zwei Gewerbe, eine Person
        self.assertNotEqual(A.personen_schluessel(a), A.personen_schluessel(dict(a, title="Sohn")))
        e1 = {"volume": "1848", "section": "einsassen", "entry_id": "x1", "surname": "Müller", "forename": "Johann"}
        e2 = dict(e1, entry_id="x2")
        self.assertNotEqual(A.personen_schluessel(e1), A.personen_schluessel(e2))       # jeder Haushalt für sich

    def test_stadtbereich_1848_nach_seiten(self):
        r = {"volume": "1848", "section": "beamte", "page": "195"}
        self.assertEqual(A.stadt_bereich(r, {}), "stadt")
        self.assertEqual(A.stadt_bereich(dict(r, page="200"), {}), "veraenderungen")
        self.assertEqual(A.stadt_bereich(dict(r, page="202"), {}), "neue_einsassen")
        self.assertEqual(A.stadt_bereich({"volume": "1795", "section": "handbuch", "page": "5"}, {"map_place": "Lausanne"}), "")


class Ausgabe(unittest.TestCase):
    def test_zahlen_schweizerisch(self):
        self.assertEqual(A.zahl(22546), "22 546")
        self.assertEqual(A.zahl(13.69, 1), "13,7")
        self.assertEqual(A.zahl(""), "–")


@unittest.skipUnless((A.REF / "bernhist_werte.csv").exists(), "Referenzwerte fehlen")
class Referenz(unittest.TestCase):
    """Die Tabellen im Repo: nur verwendete Werte, mit Quelle; Nenner stimmen mit den Stichjahren überein."""

    def setUp(self):
        self.werte = A.lies_csv(A.REF / "bernhist_werte.csv")
        self.N = A.Nenner(self.werte)

    def test_jeder_wert_hat_quelle_ort_thema_jahr(self):
        for w in self.werte:
            for f in ("ort", "thema", "jahr_von", "wert", "quelle"):
                self.assertTrue(w[f], (f, w))
        self.assertLess(len(self.werte), 150)   # keine Rohdaten, nur Einzelwerte

    def test_wohnbevoelkerung_stadt(self):
        for jahr, wert in ((1798, 11343), (1818, 17552), (1837, 22546), (1846, 25129), (1850, 27588)):
            self.assertEqual(self.N.bev[jahr], wert)
        v, g = self.N.einwohner(1836)
        self.assertAlmostEqual(v, 17552 + (22546 - 17552) * 18 / 19)
        self.assertIn("1818", g)
        self.assertIn("1837", g)
        self.assertIn("1764", self.N.einwohner(1795)[1])

    def test_haushalte(self):
        v, g = self.N.haushalte(1848)
        self.assertIn("interpoliert", g)
        self.assertTrue(5231 < v < 6071)
        v, g = self.N.haushalte(1836)
        self.assertIn("geschätzt", g)
        self.assertAlmostEqual(v / self.N.einwohner(1836)[0], 6071 / self.N.einwohner(1847)[0])

    def test_burger_und_nichtburger(self):
        self.assertEqual(self.N.burger(1836)[0], 1315 + 1590)
        self.assertAlmostEqual(self.N.nichtburger(1846)[0], 25129 - 2905)

    def test_amtsbezirke_1837_summe_gleich_kanton(self):
        aemter = [float(w["wert"]) for w in self.werte if w["ortstyp"] == "Amtsbezirk"]
        kanton = [float(w["wert"]) for w in self.werte if w["ortstyp"] == "Kanton"]
        self.assertEqual(len(aemter), 27)
        self.assertEqual(sum(aemter), kanton[0])


@unittest.skipUnless((A.OUT / "baende.csv").exists(), "Ergebnisse fehlen")
class Ergebnis(unittest.TestCase):
    def test_quote_stimmt_mit_zaehler_und_nenner(self):
        for r in A.lies_csv(A.OUT / "baende.csv"):
            if r["quote"]:
                je = int(r["einheit"].split()[1])
                soll = je * float(r["zaehler"]) / float(r["nenner"])   # Nenner steht auf eine Stelle gerundet in der Tabelle
                self.assertAlmostEqual(float(r["quote"]), soll, delta=0.01 + 0.005 * soll, msg=r)
                self.assertTrue(r["nenner_grundlage"], r)

    def test_stichprobe_mindestens_40_und_beurteilt(self):
        sp = A.lies_csv(A.OUT / "berufe_stichprobe.csv")
        self.assertGreaterEqual(len(sp), 40)
        self.assertTrue(all(s["urteil"] in ("richtig", "falsch") for s in sp))
        self.assertTrue(all(s["soll_gruppe"] in A.SEKTOR for s in sp if s["urteil"] == "falsch"))

    def test_stichprobe_ist_reproduzierbar(self):
        with open(A.CSV_DIR / "04_entries.csv", newline="") as f:
            eintraege = list(csv.DictReader(f))
        gezogen = [r["entry_id"] for r in A.ziehe_stichprobe(eintraege)]
        self.assertEqual(gezogen, [s["entry_id"] for s in A.lies_csv(A.OUT / "berufe_stichprobe.csv")])

    def test_amtsbezirke_summe(self):
        z = A.lies_csv(A.OUT / "amtsbezirke.csv")
        summe = [r for r in z if r["amtsbezirk"].startswith("Kanton Bern")][0]
        self.assertEqual(int(summe["eintraege_1836"]),
                         sum(int(r["eintraege_1836"]) for r in z if r["einwohner_1837"] and r is not summe))


if __name__ == "__main__":
    unittest.main()
