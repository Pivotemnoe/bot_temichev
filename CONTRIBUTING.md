# Contributing to TemichevVet

## Рабочий процесс

1. Создать отдельную ветку или работать в отдельной копии.
2. Не менять боевую версию на VPS без согласования.
3. Делать маленькие коммиты под одну задачу.
4. Перед коммитом запускать проверки.
5. Проверять пользовательские сценарии в тестовом Telegram-боте.

## Обязательные проверки

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q app tools main.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from app.services.selftest import run_selftest
run_selftest()
print("selftest ok")
PY
git diff --check
```

## Что нельзя коммитить

- `.env`;
- `bot.db`;
- реальные Telegram/YooKassa/OpenAI ключи;
- логи;
- `.venv/`;
- `__pycache__/`;
- архивы с боевой базой.

## Как оформлять коммиты

Хорошо:

```text
Improve start onboarding UX
Harden admin and payment security
Fix pet reminder card flow
```

Плохо:

```text
fix
updates
misc
```

## Перед релизом

Использовать чеклист:

```text
docs/RELEASE_CHECKLIST.md
```

## Docker

Для проверки контейнера:

```bash
docker compose config
docker compose build
```

Запуск:

```bash
docker compose up
```

## Где читать контекст

- `README.md`;
- `docs/DEVELOPER_HANDOFF.md`;
- `docs/DEPLOYMENT_VPS.md`;
- `docs/SECURITY_PLAN_2026-06-01.md`;
- `docs/FINAL_REPORT_AND_NEXT_PLAN_2026-06-01.md`;
- `docs/WORKPLAN.md`.
