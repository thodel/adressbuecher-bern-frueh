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
| `heading` | geltende Rubrik: Gewerbe, Ort oder Familienname (bei leerem Seitenanfang von der Vorseite übernommen, dann Vermerk «Rubrik von Vorseite»; 1795 wird der Spaltenkopf «Herr»/«Monsieur» nicht als Rubrik genommen, Vermerk «Spaltenkopf … nicht als Rubrik übernommen») |
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

| `run` | Lauf, aus dem die Seite stammt: `full-v1`, für 85 Seiten die Neulesung `fix-rn`, für 1795 S. 29 `qwen-p029-korr` (qwen3.8-27b, von Hand berichtigt) |
| `doubt` | Felder, in denen die zweite Lesung ein Wort anders hat (`surname;street` …), leer = keine Abweichung gefunden |
| `doubt_detail` | die Abweichungen, z. B. `surname: Noth → Roth` (erste → zweite Lesung) |

`02_lines.csv` hat dazu `text_b` (Zeile der zweiten Lesung, nur wo sie abweicht) und `agree`
(`ja`, `nein`, `ohne_gegenstueck`). Beim Vergleich gelten ß/ss/ſ, Trenn- und Gedankenstriche und Sperrsatz als gleich.

## 05_second_reading.csv — Vergleich je Seite
`volume`, `page`, `lines_a`, `lines_b` (Zeilen der ersten und zweiten Lesung), `lines_same`, `lines_differ`,
`lines_unpaired` (ohne zuordenbare Zeile), `chars_differ`, `share_chars_differ`, `run_b`, `model_b`.

## 06_entry_places.csv — Ort je Eintrag (für die Karte)
`entry_id`, `volume`, `place` (wie im Eintrag), `map_place` (heutiger Name bei swisstopo), `canton`, `lat`, `lon`
(WGS84), `method` (`auto`, `auto_bezug`, `kontext`, `unscharf`, `bezugsort`, `hand`, bzw. `ungefähr`), `precision`
(`ort` = Ort des Eintrags; `ungefähr` = vom vorangehenden verorteten Eintrag desselben Bandes übernommen; leer = ohne Ort),
`source` (swisstopo-Quelle und Kennung). Die Zuordnung je Schreibung steht in `config/places.csv`
(erzeugt von `tools/geocode_places.py`), Korrekturen von Hand in `config/places_hand.csv`.

## 07_hausnummern_1882.csv — alte und neue Hausnummern (Heft von 1882)
Eine Zeile je gedruckter Zeile: `part` (innere Stadt / Stadtbezirke), `district`, `quarter` (Farbe bzw. Drittel),
`group` (Zwischentitel: alte Gasse bzw. Drittel), `old`, `old_base`, `old_suffix`, `und` (zusätzliche neue Adresse
desselben alten Hauses), `new`, `street` (Adresse 1882), `hand` (handschriftlich), `note`, `page` (Bild im e-rara-Heft),
`agree` (zweite Lesung: ja/nein/ohne_gegenstueck/berichtigt), `second_new`, `second_street`, `street_today`,
`street_match`, `lat`, `lon`, `geo_precision` (genau, ohne Buchstabe, zwischen Nachbarnummern, Strassenmitte,
nach alten Nachbarnummern im Quartier …).

## 08_entry_houses.csv — Haus je städtischem Eintrag
`entry_id`, `volume`, `address`, `quarter` (Farbe), `old_no`, `status` (gefunden, Nummer nicht in der Konkordanz,
ohne Quartier, ohne Verortung, mehrdeutig), `n_rows`, `group_1881`, `new_1882`, `street_check` (passt / passt nicht:
Gasse des Eintrags gegen Zwischentitel von 1882), `lat`, `lon`, `spread_m` (Abstand der Teilhäuser).

Alle Felder ausser `text` sind Deutungen des Modells; `02_lines.csv` ist die nähere Lesung.
