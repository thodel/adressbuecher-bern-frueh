"""Die Bände stehen auf der Seite nach Jahr, nicht in der Reihenfolge von config/volumes.json.

    python3 -m unittest discover -s tests -v
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _site():
    spec = importlib.util.spec_from_file_location("site90", ROOT / "scripts" / "90_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Ordnung(unittest.TestCase):
    def test_nachgetragener_band_rueckt_an_seinen_platz(self):
        cfg = [{"volume": "1822", "year": 1822}, {"volume": "1848", "year": 1848}, {"volume": "1795", "year": 1795}]
        pages = [{"volume": "1848", "page": "2"}, {"volume": "1795", "page": "10"}, {"volume": "1795", "page": "9"},
                 {"volume": "1822", "page": "1"}]
        cfg, pages = _site().chronological(cfg, pages)
        self.assertEqual([v["volume"] for v in cfg], ["1795", "1822", "1848"])
        self.assertEqual([(p["volume"], p["page"]) for p in pages],
                         [("1795", "9"), ("1795", "10"), ("1822", "1"), ("1848", "2")])


class Staedteleiste(unittest.TestCase):
    """scripts/site_nav.py (in allen adressbuecher-* gleich): mehrere Bestände einer Stadt nach Anfangsjahr."""

    def test_bestaende_einer_stadt_nach_jahr(self):
        import re as _re
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import site_nav
        stadt: dict = {}
        for _key, name, _url in site_nav.CITIES:
            ort, jahre = name.rsplit(" ", 1)
            stadt.setdefault(ort, []).append(int(_re.match(r"\d{4}", jahre).group(0)))
        for ort, anfang in stadt.items():
            self.assertEqual(anfang, sorted(anfang), ort)


if __name__ == "__main__":
    unittest.main()
