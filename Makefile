PY ?= python

.PHONY: install test eval eval3 chat report

install:
	$(PY) -m pip install -r requirements.txt

test:
	$(PY) -m pytest -q

eval:
	$(PY) -m eval.run_eval --prompt $(or $(PROMPT),v1)

eval3:
	$(PY) -m eval.run_eval --prompt $(or $(PROMPT),v1) --runs 3 --judge

chat:
	$(PY) chat.py

report:
	$(PY) -m eval.report
