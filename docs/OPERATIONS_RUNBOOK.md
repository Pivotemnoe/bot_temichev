# TemichevVet - operations runbook

Дата: 2026-06-02

## 1. Запуск

Локально:

```bash
python main.py
```

Docker:

```bash
docker compose up -d
docker compose logs -f
```

## 2. Проверка состояния

```bash
git status --short --branch
make check
```

Docker:

```bash
docker compose ps
docker compose logs --tail=100
```

## 3. Рестарт

Обычный процесс:

```bash
pkill -f "python main.py"
python main.py
```

Docker:

```bash
docker compose restart
```

Systemd:

```bash
systemctl restart temichevvet
systemctl status temichevvet
```

## 4. Бэкап

Перед обновлением сохранить:

- `.env`;
- `bot.db` или Docker-папку `data/`;
- сервисный файл systemd/supervisor;
- текущую версию кода.

Проверенный SQLite-бэкап:

```bash
make backup-db
```

Docker/архив данных при необходимости:

```bash
tar -czf temichevvet_data_$(date +%Y%m%d_%H%M).tgz data/
```

Подробная инструкция: [Backup and restore](BACKUP_RESTORE.md).

## 4.1. Проверка единственного процесса

На VPS один `BOT_TOKEN` должен обслуживаться только одним процессом:

```bash
.venv/bin/python tools/check_single_bot_process.py
```

## 5. Обновление

```bash
git fetch origin
git status --short --branch
git pull --ff-only
make check
```

Docker:

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

## 6. Инциденты

### Бот не отвечает

Проверить:

- процесс запущен;
- нет второго процесса с тем же токеном;
- сеть до `api.telegram.org`;
- валиден `BOT_TOKEN`;
- selftest проходит;
- логи ошибок.

### Админка не открывается

Проверить:

- Telegram ID есть в `ADMIN_IDS`;
- `ENV=production` и `ADMIN_IDS` задан явно;
- бот был перезапущен после изменения `.env`.

### Plus не активируется

Проверить:

- запись в таблице `payments`;
- статус платежа у YooKassa;
- сумма и валюта;
- `metadata.user_id`;
- `metadata.telegram_id`;
- логи `validation_failed`.
- админский отчёт `💰 Платежи`;
- админскую сверку `🔄 Проверить оплаты` или команду `/reconcile_payments`.

### База повреждена или не открывается

Проверить:

- путь `DB_PATH`;
- права на файл;
- свободное место;
- свежий бэкап.

Восстановление выполнять только при остановленном боте:

```bash
systemctl stop temichevvet
.venv/bin/python tools/restore_db.py backups/bot_YYYYMMDD_HHMMSS.db --yes
systemctl start temichevvet
```

## 7. Откат

1. Остановить новую версию.
2. Вернуть старую папку или предыдущий git commit.
3. Вернуть бэкап базы через `tools/restore_db.py`, если база менялась.
4. Запустить старый сервис.
5. Проверить `/start`, карточку питомца и платежный экран.
