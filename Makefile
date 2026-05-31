PYTHON ?= .venv/bin/python
STREAMLIT ?= .venv/bin/streamlit

.PHONY: test smoke eval eval-retrieval eval-generation eval-ragas eval-all bench-chunking bench-embedding bench-rerank ingest rebuild app catalog sample

test:
	$(PYTHON) -m unittest discover -s tests -v

smoke:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) sample_chroma_snippets.py -n 3 --seed 42

eval:
	$(PYTHON) eval/run_retrieval_eval.py --questions eval/golden_questions.jsonl

eval-retrieval:
	$(PYTHON) eval/run_retrieval_eval.py --questions eval/golden_questions.jsonl

eval-generation:
	$(PYTHON) eval/run_generation_eval.py --questions eval/golden_questions.jsonl

eval-ragas:
	$(PYTHON) eval/run_ragas_eval.py --questions eval/golden_questions.jsonl

eval-all:
	$(PYTHON) eval/run_all_eval.py --questions eval/golden_questions.jsonl

bench-chunking:
	$(PYTHON) eval/run_chunking_benchmark.py --strategies fixed,header_aware,parent_child

bench-embedding:
	$(PYTHON) eval/run_embedding_benchmark.py --providers google,bge_m3,e5

bench-rerank:
	$(PYTHON) eval/run_rerank_benchmark.py --rerankers none,rule,bge

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
