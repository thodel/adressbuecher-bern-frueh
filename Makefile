PY ?= .venv/bin/python
RUN ?= full-v1
SECOND ?= full-v2
PREFER ?= fix-rn,qwen-p029-korr

.PHONY: venv pages smoke read csv site serve
venv:  ## Python-Umgebung
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

pages:  ## Seitenliste (01_pages.csv) und Seitenbilder von e-rara (data/pages/, nicht im Repo)
	$(PY) scripts/01_pages.py

read:  ## alle gewählten Seiten mit Gemini lesen (RUN=…)
	$(PY) scripts/02_gemini.py --run $(RUN) --all --workers 6

csv:  ## Gemini-Antworten -> data/csv/02_lines.csv, 03_page_status.csv, 04_entries.csv
	$(PY) scripts/03_csv.py --run $(RUN) $(if $(SECOND),--second $(SECOND)) $(if $(PREFER),--prefer $(PREFER))

site: csv  ## Daten für site/ erzeugen
	$(PY) scripts/90_site.py

serve:  ## lokale Vorschau auf http://localhost:8000
	cd site && python3 -m http.server 8000
