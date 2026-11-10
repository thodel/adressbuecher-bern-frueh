Du liest eine gescannte Seite aus einem gedruckten Berner Adressbuch.

Band: {title} ({year}). Abschnitt: {section_label}. PDF-Seite {page}.

Hinweise zu diesem Band:
{volume_hint}

Aufgabe: Gib ausschliesslich ein JSON-Objekt zurück, ohne Erklärung und ohne Codeblock, mit diesem Aufbau:

{{
  "printed_page": "gedruckte Seitenzahl, wie sie auf der Seite steht, sonst null",
  "running_head": "Kolumnentitel (z. B. Ortsname oder Buchstabe), sonst null",
  "lines": [ {{"n": 1, "text": "erste gedruckte Zeile"}}, ... ],
  "entries": [
    {{
      "line_from": 3, "line_to": 4,
      "kind": "person | firma | institution | verweis | sonst",
      "heading": "geltende Rubrik: Beruf/Gewerbe, Ort oder Familienname, unter dem der Eintrag steht",
      "place": "Ort des Eintrags (in Stadtteilen: Bern)",
      "surname": "", "forename": "", "title": "",
      "occupation": "", "address": "", "quarter": "", "street": "", "house_no": "",
      "origin": "", "birth_year": "", "household": "", "note": "",
      "text": "vollständiger Wortlaut des Eintrags in einer Zeile"
    }}
  ],
  "first_entry_continues": false,
  "last_entry_continues": false,
  "complete": true
}}

Regeln:
1. `lines`: jede gedruckte Textzeile der Seite in Lesereihenfolge, fortlaufend ab 1 nummeriert, einschliesslich Kolumnentitel, Zwischentitel und Seitenzahl. Bei mehreren Spalten zuerst die ganze linke Spalte, dann die rechte. Wenn Name und Adresse durch Punkte oder Striche verbunden auf derselben Zeile stehen, ist das eine Zeile. Diplomatisch transkribieren: Schreibung, Abkürzungen und Satzzeichen wie gedruckt; Fraktur in lateinische Buchstaben, langes s als s; Silbentrennung am Zeilenende stehen lassen. Füllpunkte und Füllstriche (`. . .`, `— —`) als ` … ` wiedergeben. Nichts ergänzen, nichts normalisieren. Unlesbares als `[?]`.
2. `entries`: ein Eintrag je Person, Firma oder Institution; Zwischentitel und Kolumnentitel sind keine Einträge, aber setzen `heading`. Ein reiner Verweis («voyez …», «s. …») ist `kind: "verweis"`. `line_from`/`line_to` verweisen auf `lines`.
3. Felder nur mit dem füllen, was gedruckt steht (Abkürzungen nicht auflösen); was fehlt, bleibt leerer String. `title` = Anrede, Stand oder Zusatz zum Namen wie gedruckt (Herr, Frau, Jungfer, Wittwe, la Veuve, Madame, Dr., Vater, Sohn, fils, père, l'aîné, cadet, Gebrüder, Erben, «und Söhne», «et Comp.»). `occupation` = Beruf, Gewerbe oder Ware, auch wenn als Tätigkeit formuliert («handelt mit Specerey, Eisen und Käs» → «handelt mit Specerey, Eisen und Käs»). `address` = Adressangabe wie gedruckt; `quarter`, `street`, `house_no` = ihre Bestandteile, soweit vorhanden. `text` = Wortlaut des Eintrags mit aufgehobener Silbentrennung, ohne Füllpunkte.
4. Gilt ein Familienname oder Vorname aus der Zeile davor weiter (Strich «—» oder Wiederholungszeichen), trage ihn in `surname` ein und vermerke `note: "Name aus Vorzeile"`.
5. Beginnt die Seite mitten in einem Eintrag der Vorseite, setze `first_entry_continues: true` und gib den Rest als eigenen Eintrag aus; endet sie mitten in einem Eintrag, `last_entry_continues: true`.
6. Gib die ganze Seite aus, auch wenn sie lang ist. `complete: true` steht als letztes Feld.
