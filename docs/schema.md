# CSV-Schema

Alle Dateien in `data/csv/`, UTF-8, Komma-getrennt, mit Kopfzeile. Seitenschlüssel ist `volume` + `page`
(PDF-Seite, 1-basiert, der e-rara-PDF-Datei).

## 00_volumes.csv — ein Band je Zeile
`volume` (Bandschlüssel = Jahr), `year`, `short`, `title`, `publisher`, `language`, `doi`, `shelfmark`,
`iiif_manifest`, `pdf` (Dateiname der Quelle), `sections` (gelesene Abschnitte mit PDF-Seiten), `notes`.

## 01_pages.csv — eine gelesene Seite je Zeile
`volume`, `page`, `section`, `erara_canvas` (Canvas-ID; Viewer: `https://www.e-rara.ch/bes_1/content/pageview/<id>`),
`erara_label`, `width`, `height` (Pixel bei e-rara), `image` (lokaler Pfad unter `data/pages/`, nicht im Repo),
`iiif_image` (IIIF-Bilddienst).

## 02_lines.csv — gelesene Zeilen
`volume`, `page`, `line` (fortlaufend je Seite, Lesereihenfolge, bei zwei Spalten erst links), `text`
(diplomatisch: Schreibung wie gedruckt, Fraktur in lateinischen Buchstaben, Füllpunkte als `…`).

## 03_page_status.csv — Lesestatus je Seite
`status` (`ok`, `fehler`, `fehlt`), `problems`, `finish_reason`, `printed_page`, `running_head`, `n_lines`,
`n_entries`, `first_entry_continues`, `last_entry_continues`, `model`, `prompt_sha`, `tokens_in`,
`tokens_out`, `tokens_thought`, `finished` (Zeitstempel Europe/Zurich).

## 04_entries.csv — Einträge
| Spalte | Inhalt |
|---|---|
| `entry_id` | `<band>-p<seite>-L<erste zeile>` (bei Doppelung `-2` …) |
| `volume`, `page`, `printed_page`, `section` | Herkunft |
| `line_from`, `line_to` | Zeilen in `02_lines.csv` |
| `kind` | `person`, `firma`, `institution`, `verweis`, `sonst` |
| `heading` | geltende Rubrik: Gewerbe, Ort oder Familienname (bei leerem Seitenanfang von der Vorseite übernommen, dann Vermerk «Rubrik von Vorseite») |
| `place` | Ort (Stadtteile: Bern) |
| `surname`, `forename`, `title` | Name wie gedruckt; `title` = Anrede, Stand, Zusatz (Herr, Wittwe, fils, Gebrüder …) |
| `occupation` | Beruf, Gewerbe oder Ware wie gedruckt |
| `address`, `quarter`, `street`, `house_no` | Adresse wie gedruckt und ihre Teile |
| `origin` | Herkunfts- bzw. Heimatort («a. …») |
| `birth_year` | 1848: Geburtsjahr, vierstellig ergänzt |
| `household` | 1848: Ehefrau und Kinder, wörtlich |
| `note` | Vermerke: übernommene Namen/Berufe/Quartiere, Kennbuchstaben (B., H., G.), Berichtigungen |
| `continues` | `von_vorseite` / `auf_folgeseite`, wenn der Eintrag über den Seitenwechsel läuft |
| `text` | Wortlaut des Eintrags, Silbentrennung aufgehoben |
| `erara_url` | Seite im e-rara-Viewer |
| `reader`, `run` | Modell und Lauf |

Alle Felder ausser `text` sind Deutungen des Modells; `02_lines.csv` ist die nähere Lesung.
