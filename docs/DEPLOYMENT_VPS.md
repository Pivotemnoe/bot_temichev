# TemichevVet - безопасный деплой на VPS

Дата: 2026-06-02

## 1. Цель

Развернуть новую версию рядом со старой рабочей версией, не ломая текущего боевого бота и платежи.

Главное правило: сначала аудит и бэкап, потом тестовый запуск, только после этого решение о переключении.

## 2. Аудит VPS без изменений

На сервере нужно выяснить:

- где лежит старая версия;
- как она запущена: `systemd`, `supervisor`, `docker`, `pm2`, ручной процесс;
- где лежит `.env`;
- где лежит база;
- какой токен бота используется;
- какие платежные ключи используются;
- куда пишутся логи.

Нельзя на этом этапе:

- останавливать старый бот;
- заменять файлы старой версии;
- менять `.env`;
- менять платежные ключи.

## 3. Бэкап старой версии

Перед любым деплоем сделать копии:

- папки старого проекта;
- `.env`;
- базы SQLite;
- systemd/supervisor/docker-конфига;
- логов, если они нужны для диагностики.

Пример структуры бэкапа:

```text
/root/backups/temichevvet_YYYY-MM-DD_HHMM/
  app/
  .env
  bot.db
  service.txt
```

## 4. Размещение новой версии

Новую версию ставить в отдельную папку, например:

```text
/opt/temichevvet-new/
```

Не раскладывать новую версию поверх старой.

Минимальный состав:

- `main.py`;
- `requirements.txt`;
- `README.md`;
- `.env.example`;
- `app/`;
- `docs/`.

Не переносить:

- локальный `.env`;
- локальный `bot.db`;
- `.venv/`;
- логи;
- кэш Python.

## 5. Настройка `.env` на VPS

Для тестового деплоя:

```env
ENV=production
BOT_TOKEN=<test_bot_token>
DB_PATH=bot.db
OPENAI_API_KEY=<key>
ADMIN_CHAT_ID=<admin_telegram_id>
ADMIN_IDS=<admin_telegram_id>
FEEDBACK_CHAT_ID=<admin_telegram_id>
LOG_LEVEL=INFO
ERROR_LOG_PATH=errors.log
```

Для платежного теста добавить:

```env
YOOKASSA_SHOP_ID=<test_or_live_shop_id>
YOOKASSA_SECRET_KEY=<test_or_live_secret>
YOOKASSA_RETURN_URL=https://t.me/<bot_username>
```

## 6. Установка и запуск

```bash
cd /opt/temichevvet-new
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

После успешной ручной проверки оформить сервис.

## 6.1. Запуск через Docker

```bash
cd /opt/temichevvet-new
cp .env.example .env
# заполнить .env реальными значениями
docker compose up --build -d
docker compose logs -f
```

В Docker база и логи лежат в:

```text
/opt/temichevvet-new/data/
```

Папку `data/` нужно бэкапить перед обновлениями.

## 7. Systemd пример

```ini
[Unit]
Description=TemichevVet test bot
After=network.target

[Service]
WorkingDirectory=/opt/temichevvet-new
ExecStart=/opt/temichevvet-new/.venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

## 8. Проверка на VPS

Минимальный Telegram smoke-test:

1. `/start`;
2. открыть главное меню;
3. открыть карточку питомца;
4. создать тестового питомца;
5. удалить тестового питомца;
6. разобрать тестовую жалобу;
7. проверить историю;
8. создать и удалить напоминание;
9. открыть питание;
10. открыть админку через `админ`;
11. скачать CSV.

## 9. Проверка платежей

Проверить отдельно:

- создание платежа;
- открытие ссылки YooKassa;
- успешный статус;
- выдачу Plus;
- повторное нажатие `Я оплатил`;
- отмену платежа;
- ошибку платежа;
- несовпадение суммы или пользователя.

Plus не должен выдаваться, если платеж не прошел внутреннюю проверку.

## 10. Переключение на боевой бот

Переключать только после:

- успешного тестового деплоя;
- успешной проверки платежей;
- бэкапа старой версии;
- понятного плана отката.

Варианты:

- оставить новую версию на тестовом боте;
- переключить боевой токен на новую версию;
- держать старую и новую версии параллельно до полной уверенности.

## 11. Откат

План отката должен быть готов до релиза:

- остановить новый сервис;
- вернуть старый сервис;
- вернуть старую базу, если она менялась;
- проверить `/start` на боевом боте;
- проверить платежный экран.
