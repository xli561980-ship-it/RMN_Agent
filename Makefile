PYTHON ?= .venv/bin/python
STREAMLIT ?= .venv/bin/streamlit

.PHONY: test smoke eval ingest rebuild app catalog sample

test:
	$(PYTHON) -m unittest discover -s tests -v

smoke:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) sample_chroma_snippets.py -n 3 --seed 42

eval:
	$(PYTHON) eval/rag_eval.py --questions eval/golden_questions.jsonl

ingest:
	$(PYTHON) ingest.py

rebuild:
	REBUILD_CHROMA=1 $(PYTHON) ingest.py

app:
	$(STREAMLIT) run app.py

catalog:
	$(PYTHON) list_chroma_catalog.py

sample:
	$(PYTHON) sample_chroma_snippets.py -n 10 --seed 42
