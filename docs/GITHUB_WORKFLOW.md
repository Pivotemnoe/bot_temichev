# TemichevVet - работа через GitHub

Дата: 2026-06-02

Репозиторий:

```text
https://github.com/Pivotemnoe/bot_temichev
```

## 1. Клонирование

```bash
git clone https://github.com/Pivotemnoe/bot_temichev.git
cd bot_temichev
cp .env.example .env
```

Дальше заполнить `.env` и запустить локально или через Docker.

## 2. Ветки

Рекомендуемый формат веток:

```text
feature/<short-name>
fix/<short-name>
docs/<short-name>
release/<version-or-date>
```

Примеры:

```text
feature/admin-plus-command
fix/payment-validation
docs/vps-runbook
```

## 3. Pull Request

Перед PR:

```bash
make check
make security-check
make docker-config
```

В PR обязательно указать:

- что изменено;
- какие сценарии проверены;
- затронуты ли платежи;
- затронута ли база;
- нужны ли изменения `.env`;
- есть ли риск для VPS/боевого бота.

## 4. Issues

Для задач использовать шаблоны:

- Bug report;
- Feature request.

Для срочных проблем в платежах и безопасности не публиковать секреты в issue.

## 5. CI

CI-шаблон подготовлен в репозитории:

```text
docs/examples/github-actions-check.yml
```

Когда GitHub-токен имеет `workflow` scope, этот шаблон можно включить как:

```text
.github/workflows/check.yml
```

Workflow запускается на:

- push в `main`;
- pull request в `main`.

Основная команда:

```bash
make check
```

Workflow использует dummy-env без реальных секретов:

- `BOT_TOKEN`: тестовое значение `123456:test`;
- `OPENAI_API_KEY`: тестовое значение `ci-dummy-openai-key`;
- `ADMIN_IDS`: `0`;
- `ADMIN_CHAT_ID`: `0`;
- `DB_PATH`: `/tmp/temichevvet-ci.db`.

Если GitHub не принимает push с `.github/workflows/check.yml`, значит текущему GitHub-токену не хватает `workflow` scope. Нужно перелогиниться в GitHub CLI/Desktop с правом `workflow` и повторить push.

## 6. Доступы

Минимальный доступ программисту:

- read для просмотра;
- write для веток и PR;
- admin только ответственному за релизы и настройки репозитория.

Не передавать через GitHub:

- `.env`;
- токены;
- базу;
- платежные ключи.

## 7. Защита репозитория

Рекомендуемые настройки GitHub для `main`:

- включить branch protection;
- запретить прямой push в `main` всем, кроме владельца, или полностью работать через PR;
- требовать review перед merge;
- требовать прохождение локального чеклиста из `docs/SECURITY_CHECKLIST.md`;
- включить 2FA для аккаунтов с write/admin доступом;
- включить secret scanning, если тариф GitHub позволяет.

Важно: production-секреты не должны попадать в workflow без отдельной необходимости.
