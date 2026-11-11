# Frühe Berner Adressbücher 1795–1848

Sechs gedruckte Verzeichnisse von Einwohnern, Handels- und Gewerbetreibenden der Stadt und Republik
Bern, aus den Beständen der Universitätsbibliothek Bern (digitalisiert auf e-rara.ch), maschinell gelesen
mit Google Gemini und als durchsuchbare statische Seite aufbereitet.

Eigenständige Sammlung: nicht verknüpft mit «Vernetzte Schweiz 1860–1914» und nicht dort eingespielt.

| Band | Titel | e-rara | gelesene PDF-Seiten |
|---|---|---|---|
| 1795 | Berner Address-Handbuch der Handelshäuser, Fabrikanten … | [e-rara-7081](https://doi.org/10.3931/e-rara-7081) | 5–63, 65–72 |
| 1810 | Description de la ville de Berne (Livre d'adresses) | [e-rara-29502](https://doi.org/10.3931/e-rara-29502) | 80–141 |
| 1822 | Adressbuch der Stadt Bern | [e-rara-7082](https://doi.org/10.3931/e-rara-7082) | 9–70 |
| 1836 | Adressenbuch der Republik Bern | [e-rara-4616](https://doi.org/10.3931/e-rara-4616) | 48–124, 267–359, 399–415 |
| 1839 | Ergänzungs-Heft zum Adressbuch 1836 (im selben PDF) | [e-rara-4616](https://doi.org/10.3931/e-rara-4616) | 464–507, 529–545 |
| 1848 | Verzeichniss der Einsassen der Stadt Bern … | [e-rara-28249](https://doi.org/10.3931/e-rara-28249) | 14–202 |

Seitenschlüssel ist überall die PDF-Seite der e-rara-PDF-Datei (PDF-Seite 1 = e-rara-Deckblatt;
e-rara-Bild *k* = PDF-Seite *k*+1). Abschnitte und Begründung der Auswahl: `config/volumes.json`.

## Ablauf

```
make venv          # Python-Umgebung
make pages         # 01_pages.csv + Seitenbilder von e-rara (data/pages/, nicht im Repo)
make read RUN=full-v1   # Gemini liest alle Seiten -> data/raw/full-v1/ (Schlüssel aus .env)
make site RUN=full-v1   # CSV (data/csv/) und Daten für site/
# zweite Lesung und Vergleich:
#   scripts/02_gemini.py --run full-v2 --all --thinking medium --workers 8
#   scripts/03_csv.py --run full-v1 --second full-v2 && python3 scripts/90_site.py
make serve         # Vorschau
```

Gemini-Schlüssel: `GEMINI_API_KEY` in der Umgebung oder in `.env` (nicht eingecheckt).
Prompt: `prompts/gemini_entries.md`, Bandhinweise: `config/hints.json`.
Eine Seite zählt nur, wenn die Antwort mit `finish_reason STOP` endet, als JSON parst, `complete: true`
trägt und alle Zeilenverweise stimmen; sonst wird sie wiederholt bzw. als Fehler geführt
(`data/csv/03_page_status.csv`).

## Daten

`data/csv/` — Schema in `docs/schema.md`. Die Seite (`site/`) ist statisch und lädt die Seitenbilder per
IIIF direkt von e-rara.
