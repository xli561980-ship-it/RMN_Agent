PYTHON ?= .venv/bin/python
STREAMLIT ?= .venv/bin/streamlit

.PHONY: test smoke eval eval-retrieval eval-generation eval-ragas eval-all eval-gold-check eval-expanded bench-chunking bench-embedding bench-embedding-local bench-embedding-hf bench-rerank bench-rerank-hf ingest rebuild app catalog sample

test:
	$(PYTHON) -m unittest discover -s tests -v

smoke:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) sample_chroma_snippets.py -n 3 --seed 42

eval:
	$(PYTHON) eval/run_retrieval_eval.py --questions eval/golden_questions.jsonl

eval-retrieval:
	$(PYTHON) eval/run_retrieval_eval.py --questions eval/golden_questions.jsonl

eval-gold-check:
	$(PYTHON) eval/check_gold_evidence_alignment.py

eval-expanded:
	$(PYTHON) eval/run_expanded_eval_summary.py

eval-generation:
	$(PYTHON) eval/run_generation_eval.py --questions eval/golden_questions.jsonl

eval-ragas:
	$(PYTHON) eval/run_ragas_eval.py --questions eval/golden_questions.jsonl

eval-all:
	$(PYTHON) eval/run_all_eval.py --questions eval/golden_questions.jsonl

bench-chunking:
	$(PYTHON) eval/run_chunking_benchmark.py --strategies fixed,header_aware,parent_child

bench-embedding:
	$(PYTHON) eval/run_embedding_benchmark.py --providers google

bench-embedding-local:
	$(PYTHON) eval/run_embedding_benchmark.py --providers local_hash

bench-embedding-hf:
	$(PYTHON) eval/run_embedding_benchmark.py --providers bge_m3,e5

bench-rerank:
	$(PYTHON) eval/run_rerank_benchmark.py --rerankers none,rule

bench-rerank-hf:
	$(PYTHON) eval/run_rerank_benchmark.py --rerankers bge

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
