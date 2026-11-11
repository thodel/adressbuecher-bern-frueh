#!/usr/bin/env python3
"""Eine Seite mit qwen3.8 auf GPUStack (UniBE) lesen, gleicher Prompt wie Gemini.

Schlüssel: GPUSTACK_API_KEY aus der Umgebung (wird nie ausgegeben).
  tools/qwen_page.py --volume 1795 --page 29 --run qwen-p029
"""
import argparse, base64, csv, importlib.util, json, os, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("g", ROOT / "scripts/02_gemini.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

ap = argparse.ArgumentParser()
ap.add_argument("--volume", required=True); ap.add_argument("--page", type=int, required=True)
ap.add_argument("--run", required=True); ap.add_argument("--model", default="qwen3.8-27b")
ap.add_argument("--base-url", default=os.environ.get("GPUSTACK_BASE_URL", "https://gpustack.unibe.ch/v1"))
a = ap.parse_args()
key = os.environ.get("GPUSTACK_API_KEY") or sys.exit("GPUSTACK_API_KEY fehlt")

vols = json.loads((ROOT / "config/volumes.json").read_text())["volumes"]
v = vols[a.volume] if isinstance(vols, dict) else next(x for x in vols if str(x.get("volume", x.get("year"))) == a.volume)
p = next(r for r in csv.DictReader(open(ROOT / "data/csv/01_pages.csv")) if r["volume"] == a.volume and int(r["page"]) == a.page)
sec = next(s for s in v["sections"] if s["from"] <= a.page <= s["to"])
hints = json.loads((ROOT / "config/hints.json").read_text())
prompt = (ROOT / "prompts/gemini_entries.md").read_text().format(
    title=v["title"], year=v["year"], section_label=sec["label"], page=a.page, volume_hint=hints.get(a.volume, ""))
img = base64.b64encode((ROOT / "data/pages" / p["image"]).read_bytes()).decode()
body = {"model": a.model, "temperature": 0, "max_tokens": 32000,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}},
            {"type": "text", "text": prompt}]}]}
req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
t0 = time.time()
resp = json.load(urllib.request.urlopen(req, timeout=1800))
ch = resp["choices"][0]; txt = ch["message"]["content"] or ""
rec = {"run": a.run, "model": a.model, "reader": "gpustack", "finish_reason": ch.get("finish_reason"),
       "usage": resp.get("usage"), "seconds": round(time.time() - t0, 1),
       "finished": datetime.now(ZoneInfo("Europe/Zurich")).isoformat(timespec="seconds"), "raw": txt}
s = txt.strip()
if s.startswith("```"):
    s = s.split("\n", 1)[1].rsplit("```", 1)[0]
try:
    obj = json.loads(s); rec["parsed"] = obj; rec["problems"] = g.validate(obj)
except Exception as e:
    rec["problems"] = [f"json: {e}"]
rec["ok"] = rec["finish_reason"] == "stop" and not rec["problems"]
out = ROOT / "data/raw" / a.run / a.volume / f"p{a.page:03d}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
print(out, "ok" if rec["ok"] else rec["problems"], rec["finish_reason"], rec["seconds"], "s")
