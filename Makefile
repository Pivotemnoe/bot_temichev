.PHONY: check compile selftest knowledge-check security-check security-runtime-check backup-restore-check single-process-check phase-check mobile-ux-check mobile-preview backup-db restore-db docker-config docker-build docker-selftest status

PYTHON ?= .venv/bin/python

check: compile selftest knowledge-check security-check security-runtime-check backup-restore-check single-process-check phase-check mobile-ux-check

compile:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall -q app tools main.py

selftest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -c "from app.services.selftest import run_selftest; run_selftest(); print('selftest ok')"

knowledge-check:
	$(PYTHON) tools/check_knowledge_json.py

security-check:
	$(PYTHON) tools/check_secrets.py

security-runtime-check:
	$(PYTHON) tools/check_security_runtime.py

backup-restore-check:
	$(PYTHON) tools/check_backup_restore.py

single-process-check:
	$(PYTHON) tools/check_single_bot_process.py --allow-zero --allow-sandbox-skip

phase-check:
	$(PYTHON) tools/check_phase1.py
	$(PYTHON) tools/check_phase2.py
	$(PYTHON) tools/check_phase3.py
	$(PYTHON) tools/check_phase4.py
	$(PYTHON) tools/check_phase5.py
	$(PYTHON) tools/check_phase6.py
	$(PYTHON) tools/check_phase7.py
	$(PYTHON) tools/check_phase8.py

mobile-ux-check:
	$(PYTHON) tools/check_mobile_ux.py --quiet

mobile-preview:
	$(PYTHON) tools/check_mobile_ux.py

backup-db:
	$(PYTHON) tools/backup_db.py

restore-db:
	@echo "Usage: $(PYTHON) tools/restore_db.py backups/<backup-file>.db --yes"

docker-config:
	docker compose config

docker-build:
	docker compose build

docker-selftest:
	docker compose run --rm temichevvet-bot python -c "from app.services.selftest import run_selftest; run_selftest(); print('docker selftest ok')"

status:
	git status --short --branch
