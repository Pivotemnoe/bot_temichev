# TemichevVet - backup and restore

Дата: 2026-06-03

## Что защищаем

Главный файл данных бота - SQLite-база `bot.db` или путь из `DB_PATH`.
В ней лежат пользователи, питомцы, история, напоминания, подписки, платежные записи и админ-аудит.

Бэкапы нельзя коммитить в git. Папка `backups/` добавлена в `.gitignore`.

## Создать бэкап

Локально или на VPS из корня проекта:

```bash
make backup-db
```

Или напрямую:

```bash
.venv/bin/python tools/backup_db.py --db bot.db --out-dir backups --label before_release
```

Скрипт:

- читает путь из `DB_PATH`, если `--db` не указан;
- проверяет исходную базу через `PRAGMA integrity_check`;
- делает копию через SQLite backup API;
- проверяет созданный бэкап.

## Восстановить базу

Перед восстановлением остановить бота, чтобы не писать в базу во время замены.

```bash
systemctl stop temichevvet
.venv/bin/python tools/restore_db.py backups/bot_YYYYMMDD_HHMMSS.db --yes
systemctl start temichevvet
```

Если используется Docker:

```bash
docker compose stop temichevvet-bot
.venv/bin/python tools/restore_db.py backups/bot_YYYYMMDD_HHMMSS.db --db data/bot.db --yes
docker compose up -d
```

Скрипт restore:

- отказывается работать без `--yes`;
- проверяет backup-файл;
- перед заменой делает pre-restore backup текущей базы;
- заменяет базу атомарно через временный файл;
- проверяет восстановленную базу.

## Проверить backup/restore

```bash
make backup-restore-check
```

Эта проверка создаёт временную SQLite-базу, делает бэкап, меняет данные, восстанавливает бэкап и проверяет, что данные вернулись.

## Проверить один процесс бота

На VPS перед запуском новой версии:

```bash
.venv/bin/python tools/check_single_bot_process.py
```

В локальном `make check` используется режим:

```bash
.venv/bin/python tools/check_single_bot_process.py --allow-zero --allow-sandbox-skip
```

Если найдено больше одного процесса `python main.py`, нужно остановить лишний процесс или старый systemd/Docker-сервис. Один `BOT_TOKEN` не должен обслуживаться несколькими процессами одновременно.

## Минимальный порядок перед релизом

1. `git status --short --branch`
2. `make check`
3. `make backup-db`
4. `.venv/bin/python tools/check_single_bot_process.py`
5. Деплой.
6. Проверка `/start`, админки, платежного экрана и одного тестового пользовательского сценария.
