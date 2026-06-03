# TemichevVet DB Schema

Дата: 2026-06-03

Основная база: SQLite. Путь задаётся переменной `DB_PATH`. Схема создаётся и дорасширяется в `app/db.py` через `init_db()`.

## Общие правила

1. Все даты хранятся текстом в ISO-подобном формате.
2. JSON-поля хранятся как `TEXT` с сериализованным JSON.
3. Для доступа через callback нельзя доверять ID из кнопки. Нужно проверять владельца:
   - питомец: `get_pet_for_user(owner_id, pet_id)`;
   - напоминание: напоминание должно принадлежать `user_id` и нужному `pet_id`;
   - платёж: проверять текущего пользователя и metadata YooKassa.

## users

Пользователи Telegram.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | Внутренний ID пользователя |
| `telegram_id` | INTEGER | Telegram ID |
| `name` | TEXT | Имя пользователя |
| `registered_at` | TEXT | Дата регистрации |
| `tariff` | TEXT | Старое поле тарифа, основная логика в `subscriptions` |
| `quota` | INTEGER | Старое поле квоты |
| `is_active` | INTEGER | Активность пользователя |
| `clinic_id` | INTEGER | Привязка к клинике, если пользователь пришёл по clinic-link |

## pets

Питомцы пользователя.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID питомца |
| `owner_id` | INTEGER | `users.id` владельца |
| `pet_type` | TEXT | `кошка`, `собака` или старое значение |
| `pet_name` | TEXT | Кличка |
| `added_at` | TEXT | Дата добавления |
| `birth_year` | INTEGER | Год рождения |
| `birth_month` | INTEGER | Месяц рождения |
| `birth_day` | INTEGER | День рождения |
| `birth_precision` | TEXT | `year`, `month`, `day` |
| `sex` | TEXT | Пол |
| `weight_kg` | REAL | Последний/анкетный вес |
| `breed` | TEXT | Порода |
| `is_main` | INTEGER | Основной питомец пользователя |

## subscriptions

Текущий тариф и лимиты.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID подписки |
| `user_id` | INTEGER | `users.id` |
| `plan` | TEXT | `free`, `plus`, `pro`, `vip` |
| `quota_total` | INTEGER | Лимит разборов |
| `quota_used` | INTEGER | Использовано разборов |
| `period_start` | TEXT | Начало периода |
| `period_end` | TEXT | Конец периода, для Plus 30 дней |

## payments

Записи платежей YooKassa.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID записи |
| `user_id` | INTEGER | Пользователь, который создал платёж |
| `provider` | TEXT | Сейчас `yookassa` |
| `provider_payment_id` | TEXT | ID платежа у провайдера |
| `plan_code` | TEXT | Тариф |
| `amount_rub` | INTEGER | Сумма в рублях |
| `status` | TEXT | `pending`, `succeeded`, `validation_failed` и т.д. |
| `created_at` | TEXT | Создан |
| `updated_at` | TEXT | Обновлён |
| `paid_at` | TEXT | Оплачен |
| `raw_payload` | TEXT | JSON ответа провайдера |

Важно: Plus активируется только после проверки YooKassa-ответа через `validate_plus_payment()`.

## triage_logs

История разборов жалоб.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID разбора |
| `user_id` | INTEGER | Пользователь |
| `pet_id` | INTEGER | Питомец, может быть `NULL` |
| `complaint_text` | TEXT | Жалоба пользователя |
| `response_text` | TEXT | Ответ бота/LLM |
| `quota_before` | INTEGER | Квота до разбора |
| `quota_after` | INTEGER | Квота после разбора |
| `created_at` | TEXT | Дата |
| `prompt_tokens` | INTEGER | Токены prompt |
| `completion_tokens` | INTEGER | Токены ответа |
| `total_tokens` | INTEGER | Всего токенов |
| `urgency_level` | TEXT | `green`, `yellow`, `red`, `unknown` |

Красные pre-LLM случаи пишутся как `urgency_level='red'`, но не списывают квоту.

## triage_followups

Контрольные вопросы после разбора.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID follow-up |
| `triage_event_id` | INTEGER | `triage_logs.id` |
| `user_id` | INTEGER | Пользователь |
| `pet_id` | INTEGER | Питомец |
| `urgency_level` | TEXT | Срочность |
| `scenario` | TEXT | Сценарий follow-up |
| `scheduled_at` | TEXT | Когда отправить |
| `sent_at` | TEXT | Когда отправлено |
| `answered_at` | TEXT | Когда ответили |
| `status` | TEXT | `scheduled`, `sent`, `answered` |
| `answer` | TEXT | Ответ пользователя |
| `payload` | TEXT | JSON |
| `created_at` | TEXT | Создан |
| `updated_at` | TEXT | Обновлён |

## reminders

Напоминания пользователя.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID напоминания |
| `user_id` | INTEGER | Владелец |
| `pet_id` | INTEGER | Питомец, может быть `NULL` |
| `reminder_type` | TEXT | `vaccine`, `parasites`, `checkup`, `grooming`, `diet`, `custom` |
| `title` | TEXT | Заголовок |
| `due_date` | TEXT | Дата |
| `due_time` | TEXT | Время |
| `periodicity` | TEXT | `once`, `daily`, `weekly`, `monthly`, `every_3_months`, `every_6_months`, `yearly` |
| `notes` | TEXT | Заметки |
| `is_active` | INTEGER | Активно или отключено |
| `created_at` | TEXT | Создано |
| `updated_at` | TEXT | Обновлено |

## pet_history

Единая история питомца.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID события |
| `pet_id` | INTEGER | Питомец |
| `event_type` | TEXT | `triage`, `reminder`, `vaccination`, `note`, `insight` |
| `created_at` | TEXT | Дата |
| `title` | TEXT | Заголовок |
| `details` | TEXT | Подробности |
| `triage_id` | INTEGER | Связь с `triage_logs` |
| `reminder_id` | INTEGER | Связь с `reminders` |
| `metadata` | TEXT | JSON |

## pet_observations

Наблюдения по питомцу.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID наблюдения |
| `user_id` | INTEGER | Пользователь |
| `pet_id` | INTEGER | Питомец |
| `obs_type` | TEXT | Тип наблюдения |
| `payload` | TEXT | JSON |
| `source` | TEXT | Источник |
| `created_at` | TEXT | Дата |

## pet_measurements

История веса.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID записи |
| `pet_id` | INTEGER | Питомец |
| `created_at` | TEXT | Дата |
| `weight_kg` | REAL | Вес |
| `note` | TEXT | Заметка |
| `metadata` | TEXT | JSON |

## pet_vaccinations

Вакцинации питомца.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID записи |
| `pet_id` | INTEGER | Питомец |
| `vaccine_name` | TEXT | Название |
| `vaccinated_at` | TEXT | Дата вакцинации |
| `next_due_at` | TEXT | Следующая дата |
| `note` | TEXT | Заметка |
| `metadata` | TEXT | JSON |

## user_events

Аналитические события.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID события |
| `user_id` | INTEGER | Пользователь |
| `event_type` | TEXT | Тип события |
| `created_at` | TEXT | Дата |
| `payload` | TEXT | JSON |

## subscription_offer_logs

Логи показа paywall/upsell.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID |
| `user_id` | INTEGER | Пользователь |
| `event_type` | TEXT | Событие |
| `key` | TEXT | Ключ дедупликации |
| `shown_at` | TEXT | Дата показа |
| `payload` | TEXT | JSON |

## feedback

Обратная связь.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID |
| `user_id` | INTEGER | Пользователь или `NULL` |
| `created_at` | TEXT | Дата |
| `text` | TEXT | Текст |
| `category` | TEXT | Категория |
| `can_reply` | INTEGER | Можно ли отвечать |

## admin_audit_log

Аудит админских действий.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | ID |
| `telegram_id` | INTEGER | Telegram ID админа |
| `username` | TEXT | Username |
| `action` | TEXT | Действие |
| `target` | TEXT | Цель действия |
| `details` | TEXT | Подробности |
| `created_at` | TEXT | Дата |

## Индексы и ограничения

Ключевые индексы создаются в `init_db()`:

- пользователи по `telegram_id`;
- питомцы по `owner_id`;
- напоминания по `user_id`, `pet_id`, `due_date`;
- разборы по `user_id`, `pet_id`, `created_at`;
- платежи по `provider`, `provider_payment_id`;
- аналитика по `event_type`, `created_at`.

При изменении схемы нужно:

1. Добавить колонку через `_ensure_column()` или отдельный безопасный миграционный блок.
2. Обновить этот документ.
3. Запустить `make check`.
4. Проверить backup/restore: `make backup-restore-check`.
