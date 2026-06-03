.PHONY: check compile selftest knowledge-check security-check phase-check docker-config docker-build docker-selftest status

PYTHON ?= .venv/bin/python

check: compile selftest knowledge-check security-check phase-check

compile:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall -q app tools main.py

selftest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -c "from app.services.selftest import run_selftest; run_selftest(); print('selftest ok')"

knowledge-check:
	$(PYTHON) tools/check_knowledge_json.py

security-check:
	$(PYTHON) tools/check_secrets.py

phase-check:
	$(PYTHON) tools/check_phase1.py
	$(PYTHON) tools/check_phase2.py
	$(PYTHON) tools/check_phase3.py
	$(PYTHON) tools/check_phase4.py
	$(PYTHON) tools/check_phase5.py
	$(PYTHON) tools/check_phase6.py
	$(PYTHON) tools/check_phase7.py
	$(PYTHON) tools/check_phase8.py

docker-config:
	docker compose config

docker-build:
	docker compose build

docker-selftest:
	docker compose run --rm temichevvet-bot python -c "from app.services.selftest import run_selftest; run_selftest(); print('docker selftest ok')"

status:
	git status --short --branch
