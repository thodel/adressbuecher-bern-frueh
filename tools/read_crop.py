"""Einmalig: Seite nur teilweise lesen, wenn Gemini die ganze Seite wegen RECITATION verweigert.
Schreibt nach data/raw/<run>/<band>/p<NNN>.json wie 02_gemini.py, mit Vermerk `partial`."""
import json, sys, importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("g", ROOT / "scripts/02_gemini.py"); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
from google import genai
from google.genai import types
run, vol, page, crop, why = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
cfg = {v["volume"]: v for v in json.loads((ROOT / "config/volumes.json").read_text())["volumes"]}[vol]
hints = json.loads((ROOT / "config/hints.json").read_text())
sec = next(s for s in cfg["sections"] if s["from"] <= page <= s["to"])
prompt = (ROOT / "prompts/gemini_entries.md").read_text().format(title=cfg["title"], year=cfg["year"], section_label=sec["label"], page=page, volume_hint=hints.get(vol, ""))
prompt += "\n\nHinweis: Das Bild zeigt nur den oberen Teil der Seite (Ausschnitt)."
client = genai.Client(api_key=g.load_key())
conf = types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json", max_output_tokens=65536,
                                   thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW))
r = client.models.generate_content(model=g.DEFAULT_MODEL, contents=[types.Part.from_bytes(data=(ROOT / crop).read_bytes(), mime_type="image/jpeg"), types.Part.from_text(text=prompt)], config=conf)
fr = str(r.candidates[0].finish_reason).split(".")[-1]
rec = {"run": run, "model": g.DEFAULT_MODEL, "volume": vol, "page": page, "section": sec["section"], "finish_reason": fr,
       "response_text": r.text, "partial": why, "crop": crop, "started": g.now(), "finished": g.now()}
problems = [] if fr == "STOP" else [f"finish_reason {fr}"]
try:
    rec["parsed"] = json.loads(r.text or ""); problems += g.validate(rec["parsed"])
except Exception as e:
    problems.append(f"JSON: {e}")
rec["problems"], rec["ok"] = problems, not problems
m = r.usage_metadata; rec["usage"] = {"prompt": m.prompt_token_count, "output": m.candidates_token_count, "thoughts": m.thoughts_token_count}
out = ROOT / "data/raw" / run / vol / f"p{page:03d}.json"; out.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
print(fr, problems, len((rec.get("parsed") or {}).get("entries") or []))
