# Contributing to TemichevVet

## Рабочий процесс

1. Создать отдельную ветку или работать в отдельной копии.
2. Не менять боевую версию на VPS без согласования.
3. Делать маленькие коммиты под одну задачу.
4. Перед коммитом запускать проверки.
5. Проверять пользовательские сценарии в тестовом Telegram-боте.

## Обязательные проверки

```bash
make check
make security-check
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

## Security-правила для кода

- Callback-кнопка не доказывает право доступа. Если в callback есть `pet_id`, `reminder_id`, `payment_id` или похожий ID, обработчик должен заново проверить текущего пользователя.
- Для питомцев использовать owner-check через `get_pet_for_user(owner_id, pet_id)` или эквивалентную проверку.
- Админские сценарии должны быть доступны только Telegram ID из `ADMIN_IDS`.
- Plus нельзя выдавать без серверной проверки платежа.

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
- `docs/ARCHITECTURE.md`;
- `docs/TESTING.md`;
- `docs/OPERATIONS_RUNBOOK.md`;
- `docs/GITHUB_WORKFLOW.md`;
- `docs/DEPLOYMENT_VPS.md`;
- `docs/SECURITY_PLAN_2026-06-01.md`;
- `docs/THREAT_MODEL.md`;
- `docs/SECURITY_CHECKLIST.md`;
- `docs/FINAL_REPORT_AND_NEXT_PLAN_2026-06-01.md`;
- `docs/WORKPLAN.md`.
