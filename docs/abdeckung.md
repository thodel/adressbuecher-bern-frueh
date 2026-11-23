# Abdeckung der Verzeichnisse, gemessen an BERNHIST

Stand 21.11.2026. Frage: Welcher Teil der Bevölkerung steht in den sechs Berner Verzeichnissen von 1795 bis
1848, und welche Gruppen fehlen? Zähler sind die maschinell gelesenen Einträge (`data/csv/04_entries.csv`),
Nenner die Zählungen aus BERNHIST (Historisch-Statistische Datenbank des Kantons Bern 1700–1996, Projekt
Christian Pfister, Universität Bern; Datenbestand der Universitätsbibliothek Bern, Dump
`github.com/ub-unibe-ch/bernhist`, Stand 22.03.2024).

## Reproduzieren

```
# 1. verwendete BERNHIST-Werte und Ortsbindung aus dem lokalen Dump ziehen (SQLite, nicht im Repo)
python3 scripts/abdeckung.py referenz --bernhist /pfad/zu/bernhist.sqlite    # oder BERNHIST_SQLITE=…
# 2. rechnen: braucht nur die Dateien im Repo
python3 scripts/abdeckung.py rechnen
python3 -m unittest discover -s tests
```

| Datei | Inhalt |
|---|---|
| `data/ref/bernhist_werte.csv` | die 115 verwendeten BERNHIST-Werte mit Ort, Thema, Jahr, Wert, Quelle |
| `data/ref/bernhist_orte.csv` | Orte der Kantonsteile 1810, 1836 und 1839 mit BERNHIST-Ort, Kirchgemeinde, Amtsbezirk, Verfahren |
| `config/bernhist_orte_hand.csv` | 24 Zuordnungen von Hand (heutige Fusionsgemeinden, deutsche und französische Namen) |
| `config/berufe_regeln.csv` | Regeln der Berufszuordnung (Gruppe, Muster) |
| `data/abdeckung/baende.csv` | alle Kennzahlen je Band: Zähler, Nenner, Quote, Grundlage des Nenners |
| `data/abdeckung/berufsgruppen.csv` | Personen je Berufsgruppe und Band (Stadt) |
| `data/abdeckung/amtsbezirke.csv` | Einträge je 1000 Einwohner je Amtsbezirk |
| `data/abdeckung/orte_offen.csv` | Orte ohne Amtsbezirk in BERNHIST (Kanton Jura, ausserhalb, ohne Ort) |
| `data/abdeckung/berufe_stichprobe.csv` | 60 Einträge mit Zuordnung und Urteil |

Rohdaten von BERNHIST liegen nicht im Repo, weil die Nutzungsrechte nicht ausgewiesen sind.

## Was die Bände verzeichnen und welcher Nenner dazu passt

| Band | verzeichnet | Gebiet | passender Nenner |
|---|---|---|---|
| 1795 | Handelshäuser, Fabrikanten, Künstler, «ansehnliche» Gewerbetreibende | alte Republik: 245 Einträge im heutigen Kanton Bern, 258 Waadt, 179 Aargau, 10 Freiburg; Stadt Bern 106 | Selbständige in Handel und Gewerbe; als Einwohnerliste ungeeignet |
| 1810 | «principales maisons de commerce et manufactures», Notare, Advokaten, Ärzte, Künstler | Stadt (Teil A) und Kanton (Teil B) | Selbständige, 3. Sektor, Ärzte |
| 1822 | Berufe und Geschäfte der Stadt, nach Gewerben geordnet | Stadt Bern | Selbständige, 2. und 3. Sektor, Ärzte |
| 1836 | Einwohnerschaft der Stadt (alphabetisch, mit B. = Burger, H. = Hauseigentümer); Gewerbe der Amtsbezirke | Stadt und ganzer Kanton | Haushalte; Burger; Hausbesitzer; Wohnbevölkerung der Amtsbezirke 1837 |
| 1839 | Ergänzungsheft: neue Namen, veränderte Wohnungen, Veränderungen in den Ämtern | Stadt und Kanton | keiner: Nachträge, keine vollständige Liste |
| 1848 | Einsassen (Niedergelassene ohne Burgerrecht) je Haushalt mit Ehefrau und Kindern | Stadt Bern | Haushalte; Wohnbevölkerung ohne Burger |

Die Abschnittsgrenzen des Bandes 1848 in `config/volumes.json` stimmen nicht mit dem Inhalt überein: Das
Einsassenverzeichnis läuft bis PDF-Seite 199 (198–199 Nachtrag), die Veränderungen stehen auf 200–201, die
neuen Einsassen auf 202; eine Beamtenliste ist auf den gelesenen Seiten nicht enthalten. Die Auswertung
rechnet darum nach Seiten, nicht nach dem Feld `section`.

## Nenner

Stadt Bern ist die Einwohnergemeinde (BERNHIST-Ort 457, vor 1920 ohne Bümpliz).

| Grösse | Stichjahre in BERNHIST | Verwendung |
|---|---|---|
| Wohnbevölkerung | 1764, 1798, 1818, 1837, 1846, 1850, 1856 | linear interpoliert: 1795 zwischen 1764 und 1798, 1810 zwischen 1798 und 1818, 1822 und 1836 zwischen 1818 und 1837, 1839 zwischen 1837 und 1846, 1848 zwischen 1846 und 1850 |
| Haushalte | 1847 (6071), 1856 (5231) | 1848 interpoliert; davor geschätzt als Haushalte 1847 × Wohnbevölkerung des Jahres / Wohnbevölkerung 1847 |
| Frauen, Männer | 1846, 1856 | 1848 interpoliert; davor Wert von 1846, mit der Wohnbevölkerung umgerechnet |
| Zivilstand nach Geschlecht | 1846 | verwitwete Frauen (1308), mit der Wohnbevölkerung umgerechnet |
| Heimatklasse | 1846 (nach Geschlecht), 1856 | Burger der Stadt 1846: 1315 Männer, 1590 Frauen; unverändert übernommen. Für 1818 führt BERNHIST nur Nullen |
| Erwerbstätige nach Sektor, Selbständige, Dienstboten, Taglöhner, Ärzte | 1856 | mit der Wohnbevölkerung auf das Jahr des Bandes umgerechnet (gleicher Anteil angenommen) |
| Hausbesitzer, Wohnhäuser | 1856 | unverändert übernommen |
| Wohnbevölkerung der 27 Amtsbezirke | 1798, 1818, 1837 | 1836: Wert von 1837 direkt; 1810: linear zwischen 1798 und 1818, nur die 22 damals bernischen Bezirke |

«Umgerechnet» heisst: Der Anteil der Gruppe an der Wohnbevölkerung wird als gleichbleibend angenommen. Für
die Burgerschaft gilt das nicht (geschlossene Körperschaft; 1846: 2905, 1856: 2934), darum bleibt ihr Wert
stehen. Welche Stichjahre in einen Nenner eingehen, steht bei jeder Kennzahl in der Spalte
`nenner_grundlage` von `data/abdeckung/baende.csv`.

Auffälligkeiten in BERNHIST: Für «Bürger anderer bernischer Gemeinden» 1846 und «Erwerbstätige insgesamt»
1856 stehen je zwei verschiedene Werte; verwendet wird der, der mit den Teilsummen aufgeht (Erwerbstätige:
11 163 = Selbständige + Unselbständige + Dienstboten + Taglöhner). Der 1. Sektor zählt 1856 in der Stadt
5296 Erwerbstätige; die Summe legt nahe, dass Dienstboten (3016) und Taglöhner (1665) darin stecken.

## Zähler

- **Einträge**: Personen und Firmen (`kind` = person, firma), ohne Institutionen, Verweise und Erläuterungen.
- **Verschiedene Personen**: In den alphabetischen Verzeichnissen (1836, 1839, 1848) zählt jeder Eintrag. In
  den nach Gewerben gegliederten Bänden (1795, 1810, 1822) gelten Einträge mit gleichem Namen, Vornamen und
  Unterscheider (Vater/Sohn, Wittwe, Gebrüder) als eine Person.
- **Frauen**: weibliche Anrede (Frau, Wittwe, Jungfer, Madame, Veuve, Schwestern, «geb.»), weiblicher erster
  Vorname oder weibliche Berufsform (Schneiderin, Wirthin, Hebamme). Die Ehefrau im Haushalt von 1848 zählt nicht.
- **Burger, Hauseigentümer**: Kennbuchstaben B. und H. des Adressenbuchs 1836 und des Ergänzungshefts.
- **Köpfe 1848**: Haushaltsvorstand, Ehefrau («Fr.») und die Kinderzahl («5 K.», «2 T.», «1 S.»).
- **Berufsgruppen**: Regeltabelle `config/berufe_regeln.csv`. Die Angabe wird gefaltet (ä → a, ß → ss) und in
  Wörter zerlegt; es zählt das erste Wort, auf das eine Regel passt, und darin das Grundwort am Wortende
  (Tabak-fabrikant → Handwerk und Gewerbe, Wein-händler → Handel). In den nach Gewerben gegliederten Teilen
  dient die Rubrik als Ersatz, wenn das Berufsfeld leer ist. Gruppen → Sektoren: Land- und Forstwirtschaft = 1;
  Handwerk und Gewerbe, Arbeiter und Gesellen = 2; Handel, Gastgewerbe, Verkehr, Gesundheit, Recht,
  Verwaltung, Offiziere, Bildung und Kirche, Kunst, Angestellte, persönliche Dienste = 3; Dienstboten und
  Taglöhner je für sich. «Selbständige» sind eine Näherung: alle Gruppen ausser Arbeitern, Angestellten,
  Verwaltung, Offizieren, Bildung und Kirche, Dienstboten, Taglöhnern und Personen ohne Erwerb.
- **Stichprobe**: 60 Einträge (10 je Band, Zufallsauswahl mit festem Startwert), von Claude am Wortlaut des
  Eintrags beurteilt, nicht am Scan, und erst nachdem die Regeln feststanden. Ergebnis unten; die vier
  Fehler: «Zuckerbek, handelt zugleich …» (Handel statt Handwerk), «facteur de clavecin» (Verwaltung statt
  Handwerk), «Gemshornarbeiter» (Arbeiter statt Handwerk), «Hausbesitzer u. Lebküchler» (ohne Erwerb statt Handwerk).

## Befund

1. **Abdeckung der Stadt.** Je 100 Einwohner nennen die Bände 0,9 (1795), 3,1 (1810), 6,5 (1822), 13,7
   (1836) und 8,6 (1848) Personen; je 100 Haushalte 4, 13, 28, 58 und 38. Nur das Einwohnerverzeichnis von
   1836 kommt in die Nähe einer Einwohnerliste. Das Ergänzungsheft von 1839 bringt 1396 Einträge, knapp halb
   so viele wie das Hauptwerk.
2. **Burger gegen Nichtburger (1836).** 1159 Einträge tragen «B.», 38 % des Verzeichnisses, bei einem
   Burgeranteil an der Bevölkerung von 11,6 % (1846). Auf 100 männliche Burger jeden Alters kommen 81
   männliche Einträge mit «B.»: Die erwachsenen Burger stehen nahezu vollständig im Buch. Von 100
   Einwohnern ohne Burgerrecht stehen knapp 10 darin.
3. **Einsassen (1848).** 2262 Haushalte mit 7337 Köpfen (Vorstände, Ehefrauen, Kinder): 33 % der Einwohner
   ohne Burgerrecht, 47 % der Niedergelassenen von 1856, 28 % der Wohnbevölkerung. Es fehlen die Burger und
   alle, die ohne eigenes Einsassenrecht in der Stadt lebten (Aufenthalter, Dienstboten, Gesellen).
4. **Frauen.** Ihr Anteil an den verzeichneten Personen steigt von 4 % (1795, 1810) über 9 % (1822) und 13 %
   (1836) auf 20 % (1848). Gemessen an allen Einwohnerinnen bleiben es höchstens 3 von 100; von 100
   verwitweten Frauen stehen 1848 fünf als Witwe im Verzeichnis.
5. **Berufsgruppen.** Ärzte sind seit 1810 zu drei Vierteln und mehr erfasst (1836: 37 Einträge auf
   umgerechnet 40 Ärzte). Der 3. Sektor erreicht 1836 64 % des umgerechneten Bestands von 1856, Handwerk
   und Gewerbe seit 1822 rund ein Viertel, die Selbständigen 37 bis 47 %. Dienstboten und Taglöhner (1856
   zusammen 4681 Personen, 42 % der Erwerbstätigen) kommen in keinem Band über 1 %.
6. **Hauseigentümer.** 1836 tragen 782 Einträge «H.», mehr als die 569 wohnhaften Hausbesitzer, die
   BERNHIST für 1856 führt, und 45 % der 1738 Wohnhäuser. Die beiden Grössen meinen offenbar nicht dasselbe.
7. **Kanton 1836.** 5330 Einträge in den 27 Amtsbezirken von BERNHIST, 14,2 je 1000 Einwohner von 1837. Am
   dichtesten sind kleine Bezirke mit Landstadt (Laufen 48, Biel 35, Büren 29, Moutier 29), am dünnsten
   das Oberland und das Emmental (Obersimmental 6, Trachselwald 7, Niedersimmental und Konolfingen 8) sowie
   das Amt Bern ohne die Stadt (7).
8. **Kanton 1810.** Teil B des Livre d'adresses nennt 207 Personen und Firmen in den 22 damals bernischen
   Amtsbezirken (Biel und das ehemalige Fürstbistum gehörten 1810 zu Frankreich), 0,8 je 1000 Einwohner
   (Bevölkerung 1810 zwischen 1798 und 1818 interpoliert, 251 715). Das ist ein Siebzehntel der Dichte von
   1836. Der Band verzeichnet nur die «principales maisons»: Am dichtesten sind Saanen (2,4), Thun (2,2),
   Oberhasli (1,9) und Burgdorf (1,6), also Käse- und Viehhandel, Tourismus und Landstädte; Fraubrunnen,
   Laupen und Obersimmental fehlen ganz. Die Ortsbindung lässt sich hier am Buch prüfen, weil die Rubrik oft
   die Préfecture nennt: Bei 130 von 133 solchen Einträgen stimmt sie mit dem Amtsbezirk überein. Die drei
   Abweichungen: zweimal «Buren» mit einem vom Vorgänger übernommenen Ort (Hindelbank), einmal «Schwanden»
   unter Frutigen, das die Ortsbindung als Schwanden bei Brienz las.

## Was sich nicht messen liess

- **Burgerrecht vor 1836**: Die Bände 1795, 1810 und 1822 kennzeichnen Burger nicht.
- **Heimatklasse 1818**: BERNHIST führt für die Stadt nur Nullen; der früheste Wert ist 1846.
- **Jungfern**: Der einzige Nenner («ledige Frauen» 1846: 8561) schliesst Kinder ein. Es bleibt bei der Anzahl.
- **Haushalte vor 1847**: nur geschätzt.
- **Kanton Jura**: 507 Einträge von 1836 und 168 von 1839 (Delsberg, Pruntrut, Freiberge) liegen in
  Bezirken, für die BERNHIST keine Bevölkerung führt. Moutier (seit 2026 Kanton Jura) ist enthalten.
- **1795 ausserhalb des heutigen Kantons**: Waadt und Aargau haben in BERNHIST keinen Nenner.
- **Erwerb vor 1856**: kein Stichjahr; die Umrechnung über die Bevölkerung trägt für 1795 und 1810 wenig.

## Grenzen

- **Haushaltsvorstände statt Köpfe.** Ein Adressbuch nennt Vorstände und Gewerbe. Die Quote je Einwohner
  ist eine Untergrenze. Die Quote je Haushalt hängt an der Haushaltszahl von 1847; mit der von 1856 (5231
  bei mehr Einwohnern) läge sie rund ein Sechstel höher.
- **Interpolation.** Linear zwischen Stichjahren, die bis zu 34 Jahre auseinanderliegen (1764–1798); 1798
  ist ein Ausnahmejahr. Gruppen mit einem einzigen Stichjahr sind über die Bevölkerung umgerechnet.
- **Lesefehler.** Die Einträge sind von Gemini gelesen und nicht korrigiert; 5,4 % weichen in der zweiten
  Lesung in einem Wort ab. Ein verlesenes «B.» oder «H.» ändert die Zuordnung eines Eintrags.
- **Personen statt Einträge.** Die Zusammenführung gleichnamiger Einträge in 1795–1822 ist eine Näherung;
  Vater und Sohn gleichen Namens ohne Zusatz fallen zusammen.
- **Berufszuordnung.** Regeln, keine Systematik; Trefferquote siehe Stichprobe. Meister und Gesellen lassen
  sich meist nicht trennen, frühere Berufe («gew. Pfarrer») zählen wie ausgeübte.
- **Amtsbezirke.** BERNHIST führt die Bezirke in späteren Grenzen (Biel, Neuenstadt, Laufen eigene Bezirke;
  Ursenbach bei Aarwangen statt Wangen). Weiler sind über die heutige Gemeinde zugeordnet; gleichnamige
  Weiler können im falschen Bezirk liegen. Die Abweichung von der Seitenmehrheit (unten) ist eine Obergrenze
  für solche Fehler, weil sie auch Seiten mit zwei Ämtern und die Grenzänderungen enthält. 1175 Einträge
  von 1836 haben den Ort vom vorangehenden Eintrag übernommen.
- **Nachträge.** Die Nachträge von 1836 (Stadt 207, Kanton 442 Einträge) sind nicht in die Quoten
  eingerechnet, weil Berichtigungen und neue Einträge darin nicht trennbar sind.

## Tabellen

<!-- abdeckung:tabellen -->
### Stadt Bern: Personen je Einwohner und je Haushalt

| Band | Einträge Stadt | Personen | Einwohner | je 100 Einw. | Haushalte | je 100 Haushalte |
|---|---:|---:|---:|---:|---:|---:|
| 1795 | 106 | 103 | 11 549 | 0,9 | 2 724 | 3,8 |
| 1810 | 518 | 470 | 15 068 | 3,1 | 3 554 | 13,2 |
| 1822 | 1 385 | 1 213 | 18 603 | 6,5 | 4 387 | 27,6 |
| 1836 | 3 051 | 3 051 | 22 283 | 13,7 | 5 255 | 58,1 |
| 1839 | 1 396 | 1 396 | 23 120 | 6,0 | 5 452 | 25,6 |
| 1848 | 2 262 | 2 262 | 26 358 | 8,6 | 5 978 | 37,8 |

### Stadt Bern: Frauen, Witwen, Jungfern

| Band | Frauen | Anteil an den Personen | je 100 Einwohnerinnen | Witwen | je 100 verwitwete Frauen | Jungfern |
|---|---:|---:|---:|---:|---:|---:|
| 1795 | 4 | 3,9 % | 0,1 | 1 | 0,2 | 0 |
| 1810 | 21 | 4,5 % | 0,3 | 9 | 1,1 | 1 |
| 1822 | 111 | 9,2 % | 1,1 | 27 | 2,8 | 23 |
| 1836 | 384 | 12,6 % | 3,2 | 45 | 3,9 | 8 |
| 1839 | 209 | 15,0 % | 1,7 | 33 | 2,7 | 28 |
| 1848 | 452 | 20,0 % | 3,3 | 69 | 5,0 | 0 |

### Stadt Bern: Burger, Hauseigentümer, Einsassen

| Band | Kennzahl | Zähler | Nenner | je 100 | Nenner aus BERNHIST |
|---|---:|---:|---:|---:|---:|
| 1836 | Burger (Kennbuchstabe B.): Anteil an den Personen | 1 159 | 3 051 | 38,0 | verschiedene Personen des Bandes in der Stadt |
| 1836 | Burger (B.) je Burger und Burgerin | 1 159 | 2 905 | 39,9 | Burger der Stadt 1846 (2905), unverändert übernommen (geschlossene Körperschaft) |
| 1836 | Burger (B.) je männlichen Burger | 1 070 | 1 315 | 81,4 | männliche Burger 1846 (alle Alter), unverändert übernommen |
| 1836 | Nichtburger (ohne B.) je Einwohner ohne Burgerrecht | 1 892 | 19 707 | 9,6 | Wohnbevölkerung ohne Burger der Stadt 1846 (22224), mit der Wohnbevölkerung auf 1836 umgerechnet (gleicher Anteil angenommen) |
| 1836 | Hauseigentümer (Kennbuchstabe H.) je Hausbesitzer | 782 | 569 | 137,4 | in der Stadt wohnhafte Hausbesitzer 1856, unverändert übernommen |
| 1836 | Hauseigentümer (H.) je Wohnhaus | 782 | 1 738 | 45,0 | ausschliessliche Wohnhäuser 1856, unverändert übernommen |
| 1839 | Burger (Kennbuchstabe B.): Anteil an den Personen | 217 | 1 396 | 15,5 | verschiedene Personen des Bandes in der Stadt |
| 1839 | Burger (B.) je Burger und Burgerin | 217 | 2 905 | 7,5 | Burger der Stadt 1846 (2905), unverändert übernommen (geschlossene Körperschaft) |
| 1839 | Burger (B.) je männlichen Burger | 193 | 1 315 | 14,7 | männliche Burger 1846 (alle Alter), unverändert übernommen |
| 1839 | Nichtburger (ohne B.) je Einwohner ohne Burgerrecht | 1 179 | 20 447 | 5,8 | Wohnbevölkerung ohne Burger der Stadt 1846 (22224), mit der Wohnbevölkerung auf 1839 umgerechnet (gleicher Anteil angenommen) |
| 1839 | Hauseigentümer (Kennbuchstabe H.) je Hausbesitzer | 117 | 569 | 20,6 | in der Stadt wohnhafte Hausbesitzer 1856, unverändert übernommen |
| 1839 | Hauseigentümer (H.) je Wohnhaus | 117 | 1 738 | 6,7 | ausschliessliche Wohnhäuser 1856, unverändert übernommen |
| 1848 | Einsassen-Haushalte je Haushalt der Stadt | 2 262 | 5 978 | 37,8 | Haushalte, linear interpoliert zwischen 1847 und 1856 |
| 1848 | Köpfe in Einsassen-Haushalten (Vorstand, Ehefrau, Kinder) je Einwohner ohne Burgerrecht | 7 337 | 22 466 | 32,7 | Wohnbevölkerung ohne Burger der Stadt, linear interpoliert zwischen 1846 und 1856 |
| 1848 | Köpfe in Einsassen-Haushalten je Niedergelassenen von 1856 | 7 337 | 15 759 | 46,6 | Niedergelassene ohne Burgerrecht 1856 (Berner, andere Kantone, Ausländer), unverändert übernommen |
| 1848 | Köpfe in Einsassen-Haushalten je Einwohner | 7 337 | 26 358 | 27,8 | Wohnbevölkerung, linear interpoliert zwischen 1846 und 1850 |

### Stadt Bern: Berufsgruppen gegen die Zählung von 1856 (Zähler / Nenner = Quote)

| Band | Erwerb | 2. Sektor | 3. Sektor | Selbständige | Dienstboten | Taglöhner | Ärzte | Ärzte und Wundärzte |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1795 | 98 / 4 889 = 2 % | 35 / 1 627 = 2 % | 63 / 1 177 = 5 % | 94 / 1 851 = 5 % | 0 / 1 321 = 0 % | 0 / 729 = 0 % | 1 / 21 = 5 % | 2 / 21 = 10 % |
| 1810 | 430 / 6 379 = 7 % | 124 / 2 122 = 6 % | 299 / 1 536 = 19 % | 413 / 2 415 = 17 % | 0 / 1 724 = 0 % | 0 / 952 = 0 % | 20 / 27 = 74 % | 29 / 27 = 108 % |
| 1822 | 1 187 / 7 876 = 15 % | 571 / 2 620 = 22 % | 589 / 1 896 = 31 % | 1 115 / 2 981 = 37 % | 8 / 2 128 = 0 % | 0 / 1 175 = 0 % | 27 / 33 = 81 % | 37 / 33 = 112 % |
| 1836 | 2 410 / 9 433 = 26 % | 853 / 3 138 = 27 % | 1 465 / 2 272 = 64 % | 1 686 / 3 571 = 47 % | 11 / 2 549 = 0 % | 2 / 1 407 = 0 % | 37 / 40 = 93 % | 39 / 40 = 98 % |
| 1839 | 1 214 / 9 788 = 12 % | 512 / 3 256 = 16 % | 662 / 2 357 = 28 % | 902 / 3 705 = 24 % | 8 / 2 644 = 0 % | 3 / 1 460 = 0 % | 6 / 41 = 15 % | 9 / 41 = 22 % |
| 1848 | 2 058 / 11 159 = 18 % | 1 019 / 3 712 = 27 % | 931 / 2 687 = 35 % | 1 842 / 4 224 = 44 % | 30 / 3 015 = 1 % | 9 / 1 664 = 1 % | 8 / 47 = 17 % | 11 / 47 = 23 % |

### Stadt Bern: Personen je Berufsgruppe

| Gruppe | Sektor | 1795 | 1810 | 1822 | 1836 | 1839 | 1848 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Land- und Forstwirtschaft, Gartenbau | 1 | 0 | 7 | 19 | 79 | 29 | 69 |
| Handwerk und Gewerbe | 2 | 33 | 124 | 564 | 846 | 508 | 1 003 |
| Arbeiter, Gesellen | 2 | 2 | 0 | 7 | 7 | 4 | 16 |
| Handel | 3 | 50 | 145 | 249 | 398 | 137 | 405 |
| Gastgewerbe | 3 | 0 | 20 | 24 | 112 | 69 | 166 |
| Verkehr | 3 | 1 | 1 | 24 | 32 | 15 | 30 |
| Gesundheit | 3 | 1 | 34 | 45 | 40 | 16 | 28 |
| Recht, Geschäftsbüros | 3 | 0 | 55 | 80 | 87 | 48 | 41 |
| Verwaltung, Ämter | 3 | 1 | 7 | 29 | 242 | 115 | 39 |
| Offiziere | 3 | 0 | 0 | 1 | 131 | 42 | 1 |
| Bildung, Kirche | 3 | 1 | 10 | 27 | 242 | 74 | 31 |
| Kunst, Architektur | 3 | 9 | 26 | 51 | 50 | 38 | 34 |
| Schreiber, Angestellte | 3 | 0 | 0 | 0 | 89 | 66 | 90 |
| persönliche Dienste | 3 | 0 | 1 | 59 | 42 | 42 | 66 |
| Dienstboten | Dienstboten | 0 | 0 | 8 | 11 | 8 | 30 |
| Taglöhner | Taglöhner | 0 | 0 | 0 | 2 | 3 | 9 |
| ohne Erwerb (Rentner, Besitzer) | ohne Erwerb | 0 | 0 | 0 | 76 | 10 | 106 |
| unbestimmt | unbestimmt | 5 | 40 | 26 | 565 | 172 | 98 |

### Kantonsteile 1810, 1836 und 1839: Einträge je Amtsbezirk

| Amtsbezirk (BERNHIST) | Einwohner 1810 | Einträge 1810 | je 1000 Einw. 1810 | Einwohner 1837 | Einträge 1836 | je 1000 Einw. 1836 | Nachtrag 1836 | Ergänzung 1839 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Aarberg | 9 583 | 4 | 0,4 | 13 653 | 171 | 12,5 | 34 | 0 |
| Aarwangen | 18 525 | 26 | 1,4 | 24 524 | 493 | 20,1 | 135 | 3 |
| Bern | 30 116 | 4 | 0,1 | 43 786 | 157 | 3,6 | 2 | 0 |
| Biel / Bienne | – | 0 | – | 5 202 | 184 | 35,4 | 0 | 0 |
| Burgdorf | 14 870 | 24 | 1,6 | 20 706 | 250 | 12,1 | 15 | 33 |
| Büren | 6 038 | 3 | 0,5 | 8 062 | 237 | 29,4 | 6 | 96 |
| Courtelary | – | 0 | – | 14 560 | 381 | 26,2 | 0 | 4 |
| Erlach | 5 005 | 3 | 0,6 | 6 242 | 133 | 21,3 | 5 | 0 |
| Fraubrunnen | 8 366 | 0 | 0,0 | 11 089 | 243 | 21,9 | 3 | 6 |
| Frutigen | 7 838 | 10 | 1,3 | 10 515 | 104 | 9,9 | 0 | 112 |
| Interlaken | 13 390 | 9 | 0,7 | 17 947 | 191 | 10,6 | 0 | 98 |
| Konolfingen | 20 024 | 11 | 0,6 | 29 564 | 242 | 8,2 | 54 | 0 |
| Laufen | – | 0 | – | 4 563 | 217 | 47,6 | 0 | 0 |
| Laupen | 5 645 | 0 | 0,0 | 8 011 | 136 | 17,0 | 9 | 0 |
| Moutier | – | 0 | – | 6 795 | 195 | 28,7 | 0 | 1 |
| Neuveville, La | – | 0 | – | 3 396 | 67 | 19,7 | 0 | 54 |
| Nidau | 5 806 | 7 | 1,2 | 8 015 | 187 | 23,3 | 0 | 0 |
| Niedersimmental | 7 572 | 8 | 1,1 | 9 660 | 79 | 8,2 | 0 | 2 |
| Oberhasli | 5 199 | 10 | 1,9 | 6 724 | 84 | 12,5 | 0 | 8 |
| Obersimmental | 6 059 | 0 | 0,0 | 7 455 | 48 | 6,4 | 0 | 0 |
| Saanen | 4 608 | 11 | 2,4 | 4 590 | 47 | 10,2 | 0 | 10 |
| Schwarzenburg | 9 141 | 3 | 0,3 | 10 769 | 112 | 10,4 | 0 | 0 |
| Seftigen | 13 185 | 7 | 0,5 | 17 613 | 240 | 13,6 | 0 | 19 |
| Signau | 15 744 | 20 | 1,3 | 20 453 | 224 | 11,0 | 0 | 13 |
| Thun | 16 582 | 36 | 2,2 | 22 104 | 354 | 16,0 | 0 | 69 |
| Trachselwald | 17 575 | 6 | 0,3 | 22 618 | 157 | 6,9 | 178 | 151 |
| Wangen | 10 845 | 5 | 0,5 | 15 484 | 397 | 25,6 | 1 | 9 |
| (ausserhalb des Kantons) | – | 0 | – | – | 15 | – | 0 | 1 |
| (heute Kanton Jura, nicht in BERNHIST) | – | 0 | – | – | 507 | – | 0 | 168 |
| (ohne Ort) | – | 5 | – | – | 0 | – | 62 | 0 |
| Kanton Bern (27 Amtsbezirke von BERNHIST) | 251 715 | 207 | 0,8 | 374 100 | 5 330 | 14,2 | 442 | 688 |

Stichprobe: 60 zufällig gezogene Einträge (10 je Band), am Wortlaut des Eintrags beurteilt: Gruppe richtig bei 56 (93 %), Sektor richtig bei 57 (95 %).

Von 7 425 Einträgen der Kantonsteile (1810, 1836, 1839) sind 6 667 einem Amtsbezirk zugeordnet: 5 717 über den Ortsnamen, 934 über die heutige Gemeinde des Weilers, 16 über die nächste gebundene Gemeinde. 675 liegen im heutigen Kanton Jura, 16 ausserhalb, 67 haben keinen Ort, 0 blieben offen. Bei 626 zugeordneten Einträgen (9,4 %) weicht der Amtsbezirk von der Mehrheit ihrer Buchseite ab (Seitenwechsel zwischen zwei Ämtern oder falsch verorteter Ort). 1810 nennt das Buch die Préfecture selbst: bei 130 von 133 zugeordneten Einträgen (98 %) stimmt sie mit dem Amtsbezirk überein.
<!-- /abdeckung:tabellen -->
