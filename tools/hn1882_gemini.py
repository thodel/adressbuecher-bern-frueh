#!/usr/bin/env python3
"""Die Häuser-Nummerirung in Bern (1882) mit Gemini lesen: alte Quartiernummer -> neue Strassennummer.

Quelle: e-rara, Adressbuch der Stadt Bern, Beilage «Die Häuser-Nummerirung in Bern» 1882
(IIIF 3012646, 52 Bilder; Bilder in data/pages/hn1882/, nicht im Repo).
Ergebnis je Bild: data/raw/hn1882/<run>/pNNN.json; Tabelle: data/csv/07_hausnummern_1882.csv
(scripts: tools/hn1882_table.py). Schlüssel wie scripts/02_gemini.py (.env, nie ausgegeben).

  tools/hn1882_gemini.py --run v1 --workers 8
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("g", ROOT / "scripts/02_gemini.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)  # load_key, now, RETRYABLE

PROMPT = """Das Bild ist eine Seite aus «Die Häuser-Nummerirung in Bern. Gegenüberstellung der alten und neuen
Hausnummern» (Bern 1882). Teil I: die innere Stadt nach den fünf farbigen Quartieren (Rothes, Weisses, Grünes,
Gelbes, Schwarzes Quartier). Teil II: die Stadtbezirke ausserhalb (obenaus, untenaus …) mit ihren Dritteln.

Ist die Seite keine solche Tabelle (Titel, Vorwort, Verordnung, leere Seite), gib "rows": [] zurück.

Sonst: Jede Tabellenhälfte hat die Spalten «Frühere Nummer» und «Jetzige Nummer» mit dem neuen Strassennamen.
Fettgedruckte Zwischentitel (z. B. «Speichergasse.», «Aarzieledrittel.») gelten für die folgenden Zeilen.
Lies erst die linke, dann die rechte Hälfte, jede Zeile von oben nach unten. Je gedruckter Zeile ein Objekt:

- "col": 1 oder 2 (Hälfte)
- "group": der geltende fettgedruckte Zwischentitel, ohne Schlusspunkt
- "old": frühere Nummer wie gedruckt («5 c I», «25 a/b», «27/28», «1 a I, II»); bei Zeilen, die mit «und» bzw. «u.»
  beginnen, die frühere Nummer der Zeile darüber
- "und": true, wenn die Zeile mit «und»/«u.» beginnt (dasselbe alte Haus hat zusätzlich diese neue Nummer)
- "new": jetzige Nummer wie gedruckt («2 a», «32 u. 32 b», «110 bis 110 e»); leer, wenn keine
- "street": neuer Strassenname ausgeschrieben; „ oder » heisst: wie in der Zeile darüber
- "hand": true, wenn handschriftlich ergänzt oder verbessert; dann in "new"/"street" die handschriftliche Fassung
  und in "note" die gedruckte
- "note": Bemerkungen wie «abgebrochen», Klammern, die mehrere alte Nummern zusammenfassen, Unsicheres

Führt eine geschweifte Klammer mehrere frühere Nummern zu einer jetzigen zusammen, gib jeder früheren Nummer
dieselbe jetzige und vermerke es in "note".

Antworte nur mit JSON:
{"page_heading": "Kopfzeile oder Titel der Seite, z. B. «Rothes Quartier.» oder «Stadtbezirk obenaus.»",
 "printed_page": "gedruckte Seitenzahl oder leer",
 "rows": [ ... ],
 "complete": true}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v1")
    ap.add_argument("--pages", default="1-52")
    ap.add_argument("--model", default=g.DEFAULT_MODEL)
    ap.add_argument("--thinking", default="medium")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=g.load_key())
    config = types.GenerateContentConfig(
        temperature=0, response_mime_type="application/json", max_output_tokens=65536,
        thinking_config=types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, args.thinking.upper())))
    outdir = ROOT / "data/raw/hn1882" / args.run
    outdir.mkdir(parents=True, exist_ok=True)
    todo = []
    for p in g.parse_pages(args.pages):
        out = outdir / f"p{p:03d}.json"
        if out.exists() and json.loads(out.read_text()).get("ok"):
            continue
        todo.append((p, out))
    lock = threading.Lock()

    def work(p: int, out: Path) -> str:
        img = (ROOT / f"data/pages/hn1882/p{p:03d}.jpg").read_bytes()
        parts = [types.Part.from_bytes(data=img, mime_type="image/jpeg"), types.Part.from_text(text=PROMPT)]
        rec = {"run": args.run, "model": args.model, "page": p, "thinking": args.thinking, "started": g.now()}
        for attempt in range(6):
            try:
                t0 = time.time()
                r = client.models.generate_content(model=args.model, contents=parts, config=config)
                rec["seconds"] = round(time.time() - t0, 1)
                cand = (r.candidates or [None])[0]
                rec["finish_reason"] = str(getattr(cand, "finish_reason", "")).split(".")[-1]
                m = r.usage_metadata
                rec["usage"] = {"prompt": m.prompt_token_count, "output": m.candidates_token_count,
                                "thoughts": getattr(m, "thoughts_token_count", None)}
                text = r.text or ""
                rec["response_text"] = text
                problems = [] if rec["finish_reason"] == "STOP" else [f"finish_reason {rec['finish_reason']}"]
                try:
                    obj = json.loads(text); rec["parsed"] = obj
                    if obj.get("complete") is not True:
                        problems.append("complete fehlt")
                    if not isinstance(obj.get("rows"), list):
                        problems.append("rows fehlt")
                except json.JSONDecodeError as exc:
                    problems.append(f"JSON: {exc}")
                rec["problems"] = problems; rec["ok"] = not problems
                if problems and attempt < 2:
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                if not any(t in str(exc).lower() for t in g.RETRYABLE) or attempt == 5:
                    rec.update(ok=False, problems=[f"{type(exc).__name__}: {str(exc)[:300]}"]); break
                time.sleep(min(2 ** attempt + random.random(), 60))
        rec["finished"] = g.now()
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        n = len((rec.get("parsed") or {}).get("rows") or [])
        return f"p{p:03d}: {'ok' if rec.get('ok') else 'FEHLER ' + '; '.join(rec.get('problems', []))} ({n} Zeilen, {rec.get('seconds')} s)"

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for f in as_completed([ex.submit(work, p, o) for p, o in todo]):
            with lock:
                print(f.result(), flush=True)


if __name__ == "__main__":
    sys.exit(main())
