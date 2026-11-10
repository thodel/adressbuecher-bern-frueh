#!/usr/bin/env python3
"""Stufe 2: Seiten mit Gemini lesen — Zeilen und strukturierte Einträge.

Je Seite ein Aufruf mit Seitenbild + Prompt (prompts/gemini_entries.md, Band-
hinweis aus config/hints.json). Ergebnis roh und geparst nach
data/raw/<run>/<band>/p<NNN>.json. Bereits gültige Seiten werden übersprungen.

Eine Seite gilt nur als gültig, wenn
  - finish_reason STOP ist (sonst abgeschnitten: MAX_TOKENS sieht sonst wie
    Erfolg aus),
  - die Antwort als JSON parst und `complete: true` als letztes Feld trägt,
  - `lines` und `entries` Listen sind und jede Zeilenreferenz existiert.

Schlüssel: GEMINI_API_KEY oder GOOGLE_API_KEY aus der Umgebung oder aus .env im
Repo (nicht eingecheckt). Der Schlüssel wird nie ausgegeben.

Beispiele:
  scripts/02_gemini.py --run smoke-v1 --volume 1848 --pages 30,31
  scripts/02_gemini.py --run full-v1 --all --workers 6
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Zurich")
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
RETRYABLE = ("429", "500", "502", "503", "504", "deadline", "timeout", "unavailable",
             "overloaded", "disconnect", "connection reset", "connection aborted",
             "protocolerror", "incompleteread", "incomplete read", "broken pipe", "eof occurred")


def load_key() -> str:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v.strip():
                return v.strip().strip('"').strip("'")
    sys.exit("Kein Gemini-Schlüssel: GEMINI_API_KEY setzen oder in .env eintragen.")


def parse_pages(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part.strip():
            out.append(int(part))
    return out


def validate(obj: dict) -> list[str]:
    problems = []
    if not isinstance(obj, dict):
        return ["Antwort ist kein Objekt"]
    if obj.get("complete") is not True:
        problems.append("complete fehlt oder nicht true")
    lines = obj.get("lines")
    entries = obj.get("entries")
    if not isinstance(lines, list) or not isinstance(entries, list):
        return problems + ["lines/entries fehlen"]
    ns = {l.get("n") for l in lines if isinstance(l, dict)}
    for i, e in enumerate(entries):
        if e.get("line_to") is None:
            e["line_to"] = e.get("line_from")  # fehlendes Zeilenende = einzeiliger Eintrag
        for k in ("line_from", "line_to"):
            if e.get(k) not in ns:
                problems.append(f"Eintrag {i}: {k}={e.get(k)} nicht in lines")
                break
    return problems


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--volume")
    ap.add_argument("--pages", help="z. B. 30,31 oder 80-90; ohne Angabe alle Seiten des Bandes")
    ap.add_argument("--all", action="store_true", help="alle Bände, alle Seiten aus 01_pages.csv")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--thinking", default="low", help="thinking_level (minimal/low/medium/high) oder leer")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    args = ap.parse_args()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=load_key())
    if args.list_models:
        for m in client.models.list():
            acts = getattr(m, "supported_actions", None) or []
            if not acts or "generateContent" in acts:
                print(m.name.removeprefix("models/"))
        return

    cfg = {v["volume"]: v for v in json.loads((ROOT / "config/volumes.json").read_text())["volumes"]}
    hints = json.loads((ROOT / "config/hints.json").read_text())
    template = (ROOT / "prompts/gemini_entries.md").read_text()
    prompt_sha = hashlib.sha256(template.encode() + json.dumps(hints, sort_keys=True).encode()).hexdigest()[:12]

    pages = list(csv.DictReader((ROOT / "data/csv/01_pages.csv").open()))
    if not args.all:
        if not args.volume:
            sys.exit("--volume oder --all angeben")
        pages = [p for p in pages if p["volume"] == args.volume]
        if args.pages:
            want = set(parse_pages(args.pages))
            pages = [p for p in pages if int(p["page"]) in want]

    outdir = ROOT / "data/raw" / args.run
    todo = []
    for p in pages:
        out = outdir / p["volume"] / f"p{int(p['page']):03d}.json"
        if out.exists() and not args.force:
            try:
                if json.loads(out.read_text()).get("ok"):
                    continue
            except Exception:  # noqa: BLE001
                pass
        todo.append((p, out))
    print(f"{now()} Lauf {args.run}: {len(todo)} Seiten zu lesen, Modell {args.model}, Prompt {prompt_sha}")

    thinking = None
    if args.thinking:
        thinking = types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, args.thinking.upper()))
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        max_output_tokens=65536,
        thinking_config=thinking,
    )
    lock = threading.Lock()
    stats = {"ok": 0, "bad": 0, "in": 0, "out": 0, "think": 0}

    def work(p: dict, out: Path) -> str:
        v = cfg[p["volume"]]
        sec = next(s for s in v["sections"] if s["from"] <= int(p["page"]) <= s["to"])
        prompt = template.format(title=v["title"], year=v["year"], section_label=sec["label"],
                                 page=p["page"], volume_hint=hints.get(p["volume"], ""))
        img = (ROOT / "data/pages" / p["image"]).read_bytes()
        parts = [types.Part.from_bytes(data=img, mime_type="image/jpeg"), types.Part.from_text(text=prompt)]
        rec: dict = {"run": args.run, "model": args.model, "prompt_sha": prompt_sha,
                     "volume": p["volume"], "page": int(p["page"]), "section": sec["section"],
                     "started": now(), "thinking": args.thinking}
        last_err = None
        for attempt in range(6):
            try:
                t0 = time.time()
                r = client.models.generate_content(model=args.model, contents=parts, config=config)
                rec["seconds"] = round(time.time() - t0, 1)
                cand = (r.candidates or [None])[0]
                rec["finish_reason"] = str(getattr(cand, "finish_reason", "")).split(".")[-1]
                meta = r.usage_metadata
                rec["usage"] = {"prompt": meta.prompt_token_count, "output": meta.candidates_token_count,
                                "thoughts": getattr(meta, "thoughts_token_count", None)}
                text = r.text or ""
                rec["response_text"] = text
                problems = []
                if rec["finish_reason"] != "STOP":
                    problems.append(f"finish_reason {rec['finish_reason']}")
                try:
                    obj = json.loads(text)
                    rec["parsed"] = obj
                    problems += validate(obj)
                except json.JSONDecodeError as exc:
                    problems.append(f"JSON: {exc}")
                rec["problems"] = problems
                rec["ok"] = not problems
                if not rec["ok"] and attempt < 2 and any(x.startswith(("finish_reason", "JSON")) for x in problems):
                    last_err = "; ".join(problems)
                    continue  # abgeschnitten/kaputt: noch einmal versuchen
                break
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
                if not any(t in str(exc).lower() for t in RETRYABLE) or attempt == 5:
                    rec.update(ok=False, problems=[last_err[:500]])
                    break
                time.sleep(min(2 ** attempt + random.random(), 60))
        rec["finished"] = now()
        rec["last_error"] = last_err
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        with lock:
            stats["ok" if rec.get("ok") else "bad"] += 1
            u = rec.get("usage") or {}
            stats["in"] += u.get("prompt") or 0
            stats["out"] += u.get("output") or 0
            stats["think"] += u.get("thoughts") or 0
        n = len((rec.get("parsed") or {}).get("entries") or [])
        return f"{p['volume']} p{int(p['page']):03d}: {'ok' if rec.get('ok') else 'FEHLER ' + '; '.join(rec.get('problems', []))[:200]} ({n} Einträge, {rec.get('seconds')} s)"

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, p, out) for p, out in todo]
        for f in as_completed(futs):
            print(f.result(), flush=True)
    print(f"{now()} fertig: {stats}")


if __name__ == "__main__":
    main()
