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

GitHub Actions workflow пока не добавлен в репозиторий, потому что текущий token при первом push не имел `workflow` scope.

Когда будет token с `workflow` scope, можно добавить workflow:

```text
.github/workflows/ci.yml
```

Минимальные шаги CI:

- install dependencies;
- `python -m compileall -q app tools main.py`;
- `python tools/check_knowledge_json.py`;
- опционально Docker build.

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
