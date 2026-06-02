# TemichevVet Bot

Telegram-бот для оценки состояния питомцев, напоминаний и ведения истории животных.

## Быстрый старт (локально)

1. Создайте и активируйте виртуальное окружение (Python 3.10+):

```bash
python -m venv .venv
source .venv/bin/activate  # Linux / macOS
# или
.venv\Scripts\activate   # Windows
```

2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` в корне проекта по образцу:

```env
BOT_TOKEN=токен_бота_из_BotFather
DB_PATH=bot.db

OPENAI_API_KEY=ключ_OpenAI_или_совместимого_API

# Чат/канал для админ-уведомлений
ADMIN_CHAT_ID=123456789

# Явный список Telegram ID администраторов.
# В production обязателен, ADMIN_CHAT_ID не должен использоваться как запасной админ-доступ.
ADMIN_IDS=123456789

# (опционально) отдельный чат для обратной связи
FEEDBACK_CHAT_ID=123456789

# (опционально) YooKassa для Plus-оплаты
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
YOOKASSA_RETURN_URL=https://t.me/<bot_username>

# Логирование
LOG_LEVEL=INFO
ERROR_LOG_PATH=errors.log

# Окружение: development / production
ENV=development
```

4. Запустите бота:

```bash
python main.py
```

При первом запуске будет выполнен self-test и создана база `bot.db` (если её ещё нет).

## Запуск через Docker

1. Создайте `.env` из `.env.example` и заполните реальные значения.

2. Соберите и запустите контейнер:

```bash
docker compose up --build
```

В Docker база и логи лежат в локальной папке `data/`, которая не коммитится в git.

## Документы для разработчика

- [Developer handoff](docs/DEVELOPER_HANDOFF.md) — что это за проект, где что лежит, как проверять изменения.
- [Architecture](docs/ARCHITECTURE.md) — схема модулей, потоков данных, платежей и админки.
- [Testing](docs/TESTING.md) — локальные, Docker и Telegram-проверки.
- [Operations runbook](docs/OPERATIONS_RUNBOOK.md) — запуск, рестарт, бэкап, инциденты, откат.
- [GitHub workflow](docs/GITHUB_WORKFLOW.md) — ветки, PR, issues, доступы.
- [VPS deployment](docs/DEPLOYMENT_VPS.md) — безопасный деплой рядом со старой версией.
- [Release checklist](docs/RELEASE_CHECKLIST.md) — чеклист перед публикацией.
- [Security plan](docs/SECURITY_PLAN_2026-06-01.md) — защита админки, платежей и секретов.
- [Security policy](SECURITY.md) — правила по секретам и security-проблемам.
- [Final report](docs/FINAL_REPORT_AND_NEXT_PLAN_2026-06-01.md) — итоговый статус проекта и дальнейший план.
- [Workplan](docs/WORKPLAN.md) — история выполненных этапов.
- [Plans matrix](docs/plans_matrix.md) — матрица тарифов и лимитов.

## Безопасность

- Админ-панель открывается только Telegram ID из `ADMIN_IDS`.
- В `production` переменная `ADMIN_IDS` обязательна явно; `ADMIN_CHAT_ID` используется для уведомлений и обратной связи, а не как неявный доступ к админке.
- Неавторизованные попытки открыть `админ` или нажать админ-кнопки логируются и отправляются в `ADMIN_CHAT_ID` с ограничением частоты уведомлений.
- `.env`, токены бота, YooKassa-ключи, база и логи не должны попадать в git или прод-архив.
- Plus выдаётся только после проверки платежа у YooKassa: статус `succeeded`, `paid=true`, валюта `RUB`, ожидаемая сумма и metadata текущего пользователя.

## Структура проекта

- `main.py` — точка входа, запуск бота.
- `app/` — основной код:
  - `config.py` — конфигурация и чтение `.env`;
  - `db.py` — работа с SQLite-базой;
  - `handlers/` — хэндлеры Telegram-бота;
  - `pets_v2/` — новый модуль работы с питомцами;
  - `payments/` — интеграции с платёжными провайдерами;
  - `services/` — фоновые задачи и сервисы;
  - `static/` — баннеры и изображения.
- `docs/` — рабочие документы и матрица тарифов.
- `tools/` — локальные проверки и dev-утилиты.

## Что не должно попадать в прод-сборку

При выкладке на сервер **не включайте** в архив/образ:

- `.env` — файл с секретами;
- `bot.db` — рабочая база с реальными пользователями;
- `errors.log` — файлы логов;
- `.venv/` — виртуальное окружение;
- `__pycache__/` и любые `*.pyc`;
- временные JSON с продуктами в корне:
  - `foods1-50.json`,
  - `foods51-100.json`,
  - `foods101-150.json`,
  - `foods151-200.json`;
- папку `tools/` можно не включать в минимальный прод-архив, если проверки запускаются отдельно.

Минимальный прод-архив должен содержать:

- `main.py`;
- `requirements.txt`;
- `README.md`;
- `.env.example`;
- `Dockerfile`;
- `docker-compose.yml`;
- папку `app/` со всем кодом и данными (`app/data/`);
- папку `docs/` можно оставить для справки, но она не нужна для запуска.

На сервере заказчик:

1. Распаковывает архив.
2. Создаёт `.env` по образцу.
3. Устанавливает зависимости.
4. Запускает `python main.py` и тестирует бота.
