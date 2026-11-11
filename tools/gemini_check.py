#!/usr/bin/env python3
"""Seitenbild + fremde Lesung an Gemini: Korrekturen Zeile für Zeile zurück.

  tools/gemini_check.py data/raw/qwen-p029/1795/p029.json --image data/pages/1795/p029.jpg
Ergebnis neben der Eingabe als <name>.gemini_check.json. Schlüssel aus .env (nie ausgegeben).
"""
import argparse, importlib.util, json, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("g", ROOT / "scripts/02_gemini.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

PROMPT = """Du siehst eine gedruckte Seite (Fraktur, Bern 1795) und darunter eine maschinelle Lesung derselben Seite,
Zeile für Zeile nummeriert. Prüfe jede Zeile gegen das Bild. Massstab ist die gedruckte Schreibung:
ß bleibt ß, langes s wird s, Trennstriche am Zeilenende bleiben, keine Modernisierung.
Gib NUR die Abweichungen zurück, keine unveränderten Zeilen und keinen Gesamttext.

Antworte als JSON:
{{"corrections": [{{"n": <Zeilennummer>, "wrong": "<falsches Wort in der Lesung>", "right": "<Wort wie gedruckt>", "certain": true|false}}],
 "line_breaks_ok": true|false, "missing_lines": [<Text fehlender Zeilen>], "comment": "<ein Satz>", "complete": true}}

Lesung:
{reading}
"""

ap = argparse.ArgumentParser(); ap.add_argument("reading"); ap.add_argument("--image", required=True)
ap.add_argument("--model", default=g.DEFAULT_MODEL); ap.add_argument("--thinking", default="low")
a = ap.parse_args()
rec_in = json.loads(Path(a.reading).read_text())
reading = "\n".join(f'{l["n"]}: {l["text"]}' for l in rec_in["parsed"]["lines"])
client = genai.Client(api_key=g.load_key())
cfg = types.GenerateContentConfig(temperature=0, response_mime_type="application/json", max_output_tokens=16384,
        thinking_config=types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, a.thinking.upper())))
t0 = time.time()
r = client.models.generate_content(model=a.model, config=cfg, contents=[
    types.Part.from_bytes(data=Path(a.image).read_bytes(), mime_type="image/jpeg"),
    types.Part.from_text(text=PROMPT.format(reading=reading))])
c = r.candidates[0] if r.candidates else None
out = {"model": a.model, "input": a.reading, "finish_reason": str(c.finish_reason) if c else None,
       "seconds": round(time.time() - t0, 1), "finished": datetime.now(ZoneInfo("Europe/Zurich")).isoformat(timespec="seconds"),
       "raw": r.text if c and c.content else None}
try: out["parsed"] = json.loads(out["raw"])
except Exception as e: out["error"] = str(e)
dst = Path(a.reading).with_suffix(".gemini_check.json"); dst.write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(dst, out["finish_reason"], out["seconds"], "s")
print(json.dumps(out.get("parsed"), ensure_ascii=False, indent=1) if "parsed" in out else out.get("error"))
