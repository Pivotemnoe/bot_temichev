.PHONY: check compile selftest knowledge-check docker-config docker-build docker-selftest status

PYTHON ?= .venv/bin/python

check: compile selftest knowledge-check

compile:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall -q app tools main.py

selftest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -c "from app.services.selftest import run_selftest; run_selftest(); print('selftest ok')"

knowledge-check:
	$(PYTHON) tools/check_knowledge_json.py

docker-config:
	docker compose config

docker-build:
	docker compose build

docker-selftest:
	docker compose run --rm temichevvet-bot python -c "from app.services.selftest import run_selftest; run_selftest(); print('docker selftest ok')"

status:
	git status --short --branch
