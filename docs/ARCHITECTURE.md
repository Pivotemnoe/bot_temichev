# TemichevVet - архитектура проекта

Дата: 2026-06-02

## 1. Общая схема

```text
Telegram user
  -> aiogram Dispatcher
  -> app/handlers/*
  -> app/db.py
  -> SQLite bot.db

Дополнительно:
  -> app/llm_engine.py для разбора жалоб
  -> app/payments/yookassa.py для платежей
  -> app/services/* для фоновых задач и общей логики
```

Бот работает через polling. Точка входа: `main.py`.

## 2. Роутеры

`main.py` подключает роутеры в таком порядке:

- `start_router` - `/start`, регистрация, первый питомец;
- `onboarding_router` - быстрый старт;
- `pets_router` и `pets_v2_router` - питомцы и карточка питомца;
- `triage_router` - разбор жалобы;
- `observations_router` - наблюдения;
- `followup_router` - контрольные вопросы;
- `reminders_handler.router` - напоминания;
- `admin_router` - админ-панель;
- `clinic_router` - поверхность клиник, пока не основной продуктовый блок;
- `unsubscribe_router` - отписка/удаление пользовательских данных;
- `feedback_router` - обратная связь;
- `menu_router` - главное меню, подписка, платежи;
- `knowledge_router` - питание, уход, FAQ.

## 3. База данных

Основной файл: `app/db.py`.

Используется SQLite. Путь задаётся через `DB_PATH`.

Ключевые таблицы:

- `users`;
- `pets`;
- `subscriptions`;
- `payments`;
- `triage_logs`;
- `triage_followups`;
- `reminders`;
- `observations`;
- `user_events`;
- `feedback`.

Схема создаётся при запуске через `init_db()`, который вызывается selftest.

## 4. Разбор жалобы

Поток:

```text
Пользователь
  -> app/handlers/triage.py
  -> app/llm_engine.py
  -> модель LLM
  -> сохранение в triage_logs
  -> follow-up через app/services/followup.py
```

Разбор сохраняется в историю питомца. Для Plus и других тарифов могут использоваться разные prompt-добавки и лимиты.

## 5. Питомцы

Новый основной модуль: `app/pets_v2/`.

Состав:

- `list.py` - список питомцев;
- `create.py` - создание;
- `edit.py` - изменение;
- `delete.py` - удаление;
- `card.py` - карточка питомца;
- `history.py` - история;
- `reminders.py` - напоминания по питомцу;
- `vaccinations.py` - вакцинации;
- `stats.py` - статистика карточки.

## 6. Напоминания и follow-up

Фоновые воркеры запускаются в `main.py`:

- `run_reminders_worker(bot)`;
- `run_followups_worker(bot)`.

Они работают в том же процессе, что и polling.

## 7. Платежи

YooKassa-клиент: `app/payments/yookassa.py`.

Поток Plus:

```text
Пользователь нажимает оплату
  -> create_plus_payment()
  -> create_payment_record()
  -> пользователь оплачивает
  -> "Я оплатил"
  -> get_payment()
  -> validate_plus_payment()
  -> activate_plus()
```

Plus активируется только после внутренней проверки платежа.

## 8. Админка

Файл: `app/handlers/admin.py`.

Доступ:

- только Telegram ID из `ADMIN_IDS`;
- в `production` `ADMIN_IDS` обязателен явно;
- чужие попытки логируются и отправляются в `ADMIN_CHAT_ID`.

Отчёты:

- период;
- воронка;
- подписки;
- удержание;
- расходы и нагрузка;
- источники;
- CSV экспорт.

## 9. Статические данные

JSON-базы:

- `app/data/foods.json`;
- `app/data/care.json`;
- `app/data/faq.json`.

Проверка:

```bash
make knowledge-check
```

Изображения:

- `app/static/triage_banner.jpg`;
- `app/static/pets_banner.jpg`;
- `app/static/subscription_banner.jpg`;
- onboarding-баннеры.

## 10. Конфигурация

Файл `.env` создаётся из `.env.example`.

Критичные переменные:

- `BOT_TOKEN`;
- `DB_PATH`;
- `OPENAI_API_KEY`;
- `ADMIN_IDS`;
- `ADMIN_CHAT_ID`;
- `ENV`;
- `YOOKASSA_*` при тесте/релизе платежей.

Selftest останавливает запуск при критичной ошибке конфигурации.
