from __future__ import annotations

import sqlite3
import json
from contextlib import closing
from datetime import datetime, timezone, timedelta, date

from .config import DB_PATH

def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection to the bot DB.

    This helper is used by some services added in later stages.
    """
    return sqlite3.connect(DB_PATH)


from .constants import SUBSCRIPTION_PLANS


def init_db():
    """Создать таблицы, если их ещё нет."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        # Пользователи (владельцы)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                tariff TEXT DEFAULT 'free',
                quota INTEGER DEFAULT 5,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        # Питомцы
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                pet_type TEXT NOT NULL,
                pet_name TEXT,
                added_at TEXT NOT NULL,
                -- доп. поля анкеты Pets v2
                birth_year INTEGER,
                birth_month INTEGER,
                birth_day INTEGER,
                birth_precision TEXT,   -- 'year' / 'month' / 'day' или NULL
                sex TEXT,               -- 'male' / 'female' / 'unknown' или NULL
                weight_kg REAL,
                breed TEXT,
                FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        # Подписки
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                quota_total INTEGER NOT NULL,
                quota_used INTEGER NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        # Логи триажа
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pet_id INTEGER,
                complaint_text TEXT NOT NULL,
                response_text TEXT,
                quota_before INTEGER,
                quota_after INTEGER,
                created_at TEXT NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                urgency_level TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE SET NULL
            )
            """
        )
        # Напоминания
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pet_id INTEGER,
                reminder_type TEXT NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                due_time TEXT,
                periodicity TEXT NOT NULL DEFAULT 'once',
                notes TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE SET NULL
            )
            """
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )

        # =================== Pet Card V2 tables ===================
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                title TEXT,
                details TEXT,
                triage_id INTEGER,
                reminder_id INTEGER,
                metadata TEXT,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                weight_kg REAL,
                note TEXT,
                metadata TEXT,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_vaccinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                vaccine_name TEXT NOT NULL,
                vaccinated_at TEXT NOT NULL,
                next_due_at TEXT,
                note TEXT,
                metadata TEXT,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE CASCADE
            )
            """
        )

        # =================== Observations ===================
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pet_id INTEGER NOT NULL,
                obs_type TEXT NOT NULL,
                payload TEXT,
                source TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE CASCADE
            )
            """
        )

        # =================== Subscription / analytics logs ===================
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_offer_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                key TEXT,
                shown_at TEXT NOT NULL,
                payload TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        conn.commit()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===== Пользователи =====


def get_user_by_telegram_id(telegram_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, telegram_id, name, registered_at FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "telegram_id": row[1],
        "name": row[2],
        "registered_at": row[3],
    }


def delete_user_by_telegram_id(telegram_id: int) -> bool:
    """
    ЖЁСТКОЕ удаление пользователя и всех связанных данных (каскадом через FOREIGN KEY).
    Использовать ТОЛЬКО в админских сценариях, НО НЕ для кнопки «Отписаться».
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.rowcount > 0


def wipe_user_data_keep_subscription(telegram_id: int) -> bool:
    """
    МЯГКАЯ очистка данных пользователя для кнопки «Отписаться и удалить доступ».

    Что делаем:
      - находим user_id по telegram_id;
      - удаляем всех питомцев;
      - удаляем все записи triage_logs;
      - удаляем все напоминания;
      - помечаем пользователя как неактивного (is_active = 0);
      - ПОДПИСКУ (таблица subscriptions) НЕ трогаем.

    Таким образом:
      - история использования Free и платных тарифов сохраняется;
      - при повторном /start пользователь не получит новый подарок Free.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()

        # ищем пользователя
        cur.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = cur.fetchone()
        if not row:
            return False

        user_id = row[0]

        # удаляем питомцев
        cur.execute("DELETE FROM pets WHERE owner_id = ?", (user_id,))
        # удаляем логи триажа
        cur.execute("DELETE FROM triage_logs WHERE user_id = ?", (user_id,))
        # удаляем напоминания
        cur.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))

        # помечаем пользователя как неактивного (на будущее, если захочешь учитывать is_active)
        cur.execute(
            """
            UPDATE users
            SET is_active = 0
            WHERE id = ?
            """,
            (user_id,),
        )


        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return True


def get_user_by_id(user_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, telegram_id, name, registered_at, tariff, quota, is_active
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "telegram_id": row[1],
        "name": row[2],
        "registered_at": row[3],
        "tariff": row[4],
        "quota": row[5],
        "is_active": row[6],
    }


def create_user(telegram_id: int, name: str) -> int:
    now = _utc_now_iso()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (telegram_id, name, registered_at) VALUES (?, ?, ?)",
            (telegram_id, name, now),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.lastrowid


# ===== Питомцы =====


def create_pet(owner_id: int, pet_type: str, pet_name: str | None) -> int:
    """
    Создать питомца. Доп. поля анкеты (дата рождения, пол и т.д.) по умолчанию NULL.
    """
    now = _utc_now_iso()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pets (owner_id, pet_type, pet_name, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (owner_id, pet_type, pet_name, now),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.lastrowid


def get_pets_for_user(owner_id: int):
    """Return list of pets (dicts) for a given owner_id.

    Important: must never return None (handlers expect iterable).
    """
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    id,
                    pet_type,
                    pet_name,
                    added_at,
                    birth_year,
                    birth_month,
                    birth_day,
                    birth_precision,
                    sex,
                    weight_kg,
                    breed
                FROM pets
                WHERE owner_id = ?
                ORDER BY id
                """,
                (owner_id,),
            )
            rows = cur.fetchall()
    except Exception:
        return []

    pets: list[dict] = []
    for r in rows:
        pets.append(
            {
                "id": r[0],
                "pet_type": r[1],
                "pet_name": r[2],
                "added_at": r[3],
                "birth_year": r[4],
                "birth_month": r[5],
                "birth_day": r[6],
                "birth_precision": r[7],
                "sex": r[8],
                "weight_kg": r[9],
                "breed": r[10],
            }
        )
    return pets


def get_user_pets(owner_id: int):
    """Backward-compatible alias for get_pets_for_user()."""
    return get_pets_for_user(owner_id)


def get_pet_by_id(pet_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                owner_id,
                pet_type,
                pet_name,
                added_at,
                birth_year,
                birth_month,
                birth_day,
                birth_precision,
                sex,
                weight_kg,
                breed
            FROM pets
            WHERE id = ?
            """,
            (pet_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "owner_id": row[1],
        "pet_type": row[2],
        "pet_name": row[3],
        "added_at": row[4],
        "birth_year": row[5],
        "birth_month": row[6],
        "birth_day": row[7],
        "birth_precision": row[8],
        "sex": row[9],
        "weight_kg": row[10],
        "breed": row[11],
    }


def delete_pet(owner_id: int, pet_id: int) -> bool:
    """
    Удалить питомца владельца.

    Возвращает True, если строка реально была удалена.
    Связанные записи triage_logs/reminders по pet_id при этом
    автоматически переведутся в NULL (ON DELETE SET NULL).
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM pets WHERE id = ? AND owner_id = ?",
            (pet_id, owner_id),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.rowcount > 0


def update_pet_name(owner_id: int, pet_id: int, new_name: str | None) -> bool:
    """
    Обновить имя питомца.

    Возвращает True, если имя действительно изменилось.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pets SET pet_name = ? WHERE id = ? AND owner_id = ?",
            (new_name, pet_id, owner_id),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.rowcount > 0


def update_pet_birth(
    owner_id: int,
    pet_id: int,
    birth_year: int | None,
    birth_month: int | None,
    birth_day: int | None,
    birth_precision: str | None,
) -> bool:
    """
    Обновить дату рождения питомца (частично известную).
    Все поля передаются целиком (можно передать None, чтобы очистить).
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE pets
            SET birth_year = ?, birth_month = ?, birth_day = ?, birth_precision = ?
            WHERE id = ? AND owner_id = ?
            """,
            (birth_year, birth_month, birth_day, birth_precision, pet_id, owner_id),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.rowcount > 0


def update_pet_sex(owner_id: int, pet_id: int, sex: str | None) -> bool:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pets SET sex = ? WHERE id = ? AND owner_id = ?",
            (sex, pet_id, owner_id),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.rowcount > 0


def update_pet_weight(owner_id: int, pet_id: int, weight_kg: float | None) -> bool:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pets SET weight_kg = ? WHERE id = ? AND owner_id = ?",
            (weight_kg, pet_id, owner_id),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.rowcount > 0


def update_pet_breed(owner_id: int, pet_id: int, breed: str | None) -> bool:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pets SET breed = ? WHERE id = ? AND owner_id = ?",
            (breed, pet_id, owner_id),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.rowcount > 0


# ===== Подписки =====


def get_subscription(user_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, plan, quota_total, quota_used, period_start, period_end
            FROM subscriptions
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "plan": row[1],
        "quota_total": row[2],
        "quota_used": row[3],
        "period_start": row[4],
        "period_end": row[5],
    }


def _create_subscription(user_id: int, plan_code: str):
    now = _utc_now_iso()
    plan = SUBSCRIPTION_PLANS[plan_code]
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO subscriptions (user_id, plan, quota_total, quota_used, period_start, period_end)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, plan_code, plan["quota_total"], 0, now, None),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()


def ensure_default_subscription(user_id: int):
    """
    Гарантировать, что у пользователя есть запись о подписке.
    Если нет — создать базовую (free).
    """
    sub = get_subscription(user_id)
    if sub is None:
        _create_subscription(user_id, "free")
        sub = get_subscription(user_id)
    return sub


def set_subscription_plan(user_id: int, plan_code: str):
    """
    Установить тариф (free/plus/pro/vip), сбросить счётчик quota_used.
    """
    now = _utc_now_iso()
    plan = SUBSCRIPTION_PLANS[plan_code]
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        # проверяем, есть ли уже подписка
        cur.execute(
            "SELECT id FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            # создаём
            cur.execute(
                """
                INSERT INTO subscriptions (user_id, plan, quota_total, quota_used, period_start, period_end)
                VALUES (?, ?, ?, 0, ?, NULL)
                """,
                (user_id, plan_code, plan["quota_total"], now),
            )
        else:
            # обновляем
            cur.execute(
                """
                UPDATE subscriptions
                SET plan = ?, quota_total = ?, quota_used = 0, period_start = ?, period_end = NULL
                WHERE user_id = ?
                """,
                (plan_code, plan["quota_total"], now, user_id),
            )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()


def try_consume_quota(user_id: int, amount: int = 1):
    """
    Попробовать списать amount запросов из квоты пользователя.
    Возвращает (ok: bool, sub: dict).
    Если квоты не хватает — ok=False, sub содержит текущую подписку.
    """
    sub = ensure_default_subscription(user_id)
    used = sub["quota_used"]
    total = sub["quota_total"]

    if used + amount > total:
        return False, sub

    new_used = used + amount
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE subscriptions SET quota_used = ? WHERE user_id = ?",
            (new_used, user_id),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()

    sub["quota_used"] = new_used
    return True, sub


# ===== Логирование триажа =====


def log_triage_event(
    user_id: int,
    pet_id: int | None,
    complaint_text: str,
    response_text: str,
    quota_before: int | None,
    quota_after: int | None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    urgency_level: str | None = None,
) -> int:
    now = _utc_now_iso()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO triage_logs (
                user_id,
                pet_id,
                complaint_text,
                response_text,
                quota_before,
                quota_after,
                created_at,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                urgency_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                pet_id,
                complaint_text,
                response_text,
                quota_before,
                quota_after,
                now,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                urgency_level,
            ),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.lastrowid


def get_triage_history_for_user(user_id: int, limit: int = 10):
    """
    Последние N записей триажа для пользователя.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, pet_id, complaint_text, response_text,
                   quota_before, quota_after, created_at,
                   urgency_level
            FROM triage_logs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()

    history: list[dict] = []
    for r in rows:
        history.append(
            {
                "id": r[0],
                "pet_id": r[1],
                "complaint_text": r[2],
                "response_text": r[3],
                "quota_before": r[4],
                "quota_after": r[5],
                "created_at": r[6],
                "urgency_level": r[7],
            }
        )
    return history


# ===== Напоминания и график =====

FREE_TRIAL_DAYS = 30
FREE_TRIAL_LIMIT = 10     # лимит активных напоминаний в первые 30 дней
PLUS_LIMIT = 20           # лимит активных напоминаний для Plus
PRO_LIMIT = 999999        # фактически безлимит для Pro/VIP


def is_free_trial_active(user: dict) -> bool:
    """Проверить, действует ли ещё 30-дневный пробный период для напоминаний."""
    registered_at = user.get("registered_at")
    if not registered_at:
        return False
    try:
        dt = datetime.fromisoformat(registered_at)
    except Exception:
        return False
    return datetime.now(timezone.utc) - dt <= timedelta(days=FREE_TRIAL_DAYS)


def get_free_trial_days_left(user: dict) -> int:
    """Сколько полных дней пробного периода осталось. Если пробный период завершён — 0."""
    registered_at = user.get("registered_at")
    if not registered_at:
        return 0
    try:
        dt = datetime.fromisoformat(registered_at)
    except Exception:
        return 0
    delta = timedelta(days=FREE_TRIAL_DAYS) - (datetime.now(timezone.utc) - dt)
    return max(0, delta.days)


def count_user_reminders(user_id: int) -> int:
    """Количество активных напоминаний пользователя."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM reminders
            WHERE user_id = ? AND is_active = 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def can_user_create_reminder(user: dict, subscription: dict) -> tuple[bool, str]:
    """
    Проверка права на создание напоминания с учётом тарифа и пробного периода.
    Возвращает (allowed, message). Если allowed=False — message содержит объяснение.
    """
    plan = subscription.get("plan", "free")
    total = count_user_reminders(user["id"])

    if plan == "free":
        if is_free_trial_active(user):
            if total < FREE_TRIAL_LIMIT:
                return True, ""
            return False, "Лимит 10 напоминаний в бесплатный пробный период уже достигнут."
        # пробный период закончился — создавать новые напоминания нельзя
        return False, (
            "Бесплатный период закончился. Создание новых напоминаний доступно "
            "в тарифах Plus и Pro."
        )

    if plan == "plus":
        if total < PLUS_LIMIT:
            return True, ""
        return False, "Достигнут лимит 20 активных напоминаний в тарифе Plus."

    # Pro и VIP — ведём одинаково, фактически безлимит
    if plan in ("pro", "vip"):
        if total < PRO_LIMIT:
            return True, ""
        # теоретически недостижимо, но сообщение оставим на всякий случай
        return False, "Достигнут максимальный лимит напоминаний в тарифе Pro/VIP."

    # На всякий случай: для неизвестных планов ведём себя как для free без триала
    return False, (
        "Создание напоминаний недоступно для текущего тарифа. "
        "Обновите подписку до Plus или Pro."
    )


def create_reminder(
    user_id: int,
    pet_id: int | None,
    reminder_type: str,
    title: str,
    due_date: str,
    due_time: str | None,
    periodicity: str,
    notes: str | None,
) -> int:
    """Создать напоминание. Возвращает ID напоминания."""
    now = _utc_now_iso()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO reminders (
                user_id,
                pet_id,
                reminder_type,
                title,
                due_date,
                due_time,
                periodicity,
                notes,
                is_active,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                user_id,
                pet_id,
                reminder_type,
                title,
                due_date,
                due_time,
                periodicity,
                notes,
                now,
                now,
            ),
        )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
        return cur.lastrowid




def get_pet_reminders(user_id: int, pet_id: int) -> list[dict]:
    """Получить активные напоминания пользователя по конкретному питомцу."""
    reminders = get_user_reminders(user_id)
    return [r for r in reminders if int(r.get("pet_id") or 0) == int(pet_id)]


def update_reminder(
    reminder_id: int,
    user_id: int,
    *,
    reminder_type: str | None = None,
    title: str | None = None,
    due_date: str | None = None,
    due_time: str | None = None,
    periodicity: str | None = None,
    notes: str | None = None,
) -> None:
    """Обновить поля напоминания (только владельцу)."""
    fields = []
    params = []
    if reminder_type is not None:
        fields.append("reminder_type = ?")
        params.append(reminder_type)
    if title is not None:
        fields.append("title = ?")
        params.append(title)
    if due_date is not None:
        fields.append("due_date = ?")
        params.append(due_date)
    if due_time is not None:
        fields.append("due_time = ?")
        params.append(due_time)
    if periodicity is not None:
        fields.append("periodicity = ?")
        params.append(periodicity)
    if notes is not None:
        fields.append("notes = ?")
        params.append(notes)

    if not fields:
        return

    fields.append("updated_at = ?")
    params.append(_utc_now_iso())
    params.extend([reminder_id, user_id])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE reminders
            SET {', '.join(fields)}
            WHERE id = ? AND user_id = ? AND is_active = 1
            """,
            tuple(params),
        )
        conn.commit()

def get_user_reminders(user_id: int):
    """Получить все активные напоминания пользователя, отсортированные по дате."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                user_id,
                pet_id,
                reminder_type,
                title,
                due_date,
                due_time,
                periodicity,
                notes,
                is_active,
                created_at,
                updated_at
            FROM reminders
            WHERE user_id = ? AND is_active = 1
            ORDER BY due_date ASC, id ASC
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    result: list[dict] = []
    for r in rows:
        result.append(
            {
                "id": r[0],
                "user_id": r[1],
                "pet_id": r[2],
                "reminder_type": r[3],
                "title": r[4],
                "due_date": r[5],
                "due_time": r[6],
                "periodicity": r[7],
                "notes": r[8],
                "is_active": r[9],
                "created_at": r[10],
                "updated_at": r[11],
            }
        )
    return result


def deactivate_reminder(reminder_id: int, user_id: int | None = None) -> None:
    """
    Мягкое удаление напоминания: помечаем is_active = 0.

    user_id сделан необязательным для совместимости со старыми вызовами:
      - deactivate_reminder(reminder_id)
      - deactivate_reminder(reminder_id, user_id)
    """
    now = _utc_now_iso()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        if user_id is None:
            cur.execute(
                """
                UPDATE reminders
                SET is_active = 0, updated_at = ?
                WHERE id = ?
                """,
                (now, reminder_id),
            )
        else:
            cur.execute(
                """
                UPDATE reminders
                SET is_active = 0, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, reminder_id, user_id),
            )

        # Обратная связь (feedback пользователей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                can_reply INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()


def get_due_reminders() -> list[dict]:
    """
    Вернуть список напоминаний, срок которых наступил (или просрочен), в формате dict.

    Логика:
      - is_active = 1
      - due_date < сегодня
        ИЛИ
        due_date = сегодня И (due_time IS NULL ИЛИ due_time <= текущее время)
    """
    now = datetime.now()  # локное время сервера
    today = now.strftime("%Y-%m-%d")
    now_time = now.strftime("%H:%M")

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                r.id,
                r.user_id,
                u.telegram_id,
                r.pet_id,
                r.reminder_type,
                r.title,
                r.due_date,
                r.due_time,
                r.periodicity,
                r.notes
            FROM reminders r
            JOIN users u ON u.id = r.user_id
            WHERE
                r.is_active = 1
                AND (
                    r.due_date < ?
                    OR (r.due_date = ? AND (r.due_time IS NULL OR r.due_time <= ?))
                )
            """,
            (today, today, now_time),
        )
        rows = cur.fetchall()

    result: list[dict] = []
    for r in rows:
        result.append(
            {
                "id": r[0],
                "user_id": r[1],
                "telegram_id": r[2],
                "pet_id": r[3],
                "reminder_type": r[4],
                "title": r[5],
                "due_date": r[6],
                "due_time": r[7],
                "periodicity": r[8],
                "notes": r[9],
            }
        )
    return result


def calc_next_due_date(current: date, periodicity: str) -> date:
    """
    Упрощённый расчёт следующей даты напоминания.
    Для MVP используем сдвиг по дням.
    """
    if periodicity == "yearly":
        try:
            return date(current.year + 1, current.month, current.day)
        except ValueError:
            # На случай 29 февраля и т.п. — отступаем на день назад
            return date(current.year + 1, current.month, current.day - 1)
    if periodicity == "every_6_months":
        return current + timedelta(days=182)
    if periodicity == "every_3_months":
        return current + timedelta(days=91)
    if periodicity == "monthly":
        return current + timedelta(days=30)
    return current


def shift_reminder_date(reminder_id: int, periodicity: str) -> None:
    """
    Сдвинуть due_date вперёд в зависимости от periodicity.
    Используется для повторяющихся напоминаний.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT due_date FROM reminders WHERE id = ?",
            (reminder_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return

        try:
            current_date = datetime.strptime(row[0], "%Y-%m-%d").date()
        except Exception:
            # Если формат сломан — не трогаем запись
            return

        new_date = calc_next_due_date(current_date, periodicity)
        now = _utc_now_iso()

        cur.execute(
            """
            UPDATE reminders
            SET due_date = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_date.strftime("%Y-%m-%d"), now, reminder_id),
        )
        conn.commit()

# ===== Обратная связь =====


def create_feedback(
    user_id: int | None,
    text: str,
    created_at: datetime | None = None,
    category: str | None = None,
    can_reply: bool = True,
) -> int:
    """
    Сохранить отзыв пользователя в таблицу feedback.

    :param user_id: ID пользователя в таблице users или None
    :param text: текст отзыва
    :param created_at: время создания (UTC). Если None — берётся текущее.
    :param category: опциональная категория сообщения
    :param can_reply: флаг, можно ли связываться с пользователем
    :return: ID созданной записи feedback
    """
    created_at_dt = created_at or datetime.now(timezone.utc)
    created_at_iso = created_at_dt.isoformat()

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO feedback (user_id, created_at, text, category, can_reply)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                created_at_iso,
                text,
                category,
                1 if can_reply else 0,
            ),
        )
        conn.commit()
        return cur.lastrowid


# ======================= Pet Card V2 helpers =======================

def add_pet_history_event(
    pet_id: int,
    event_type: str,
    title: str | None = None,
    details: str | None = None,
    triage_id: int | None = None,
    reminder_id: int | None = None,
    metadata: dict | None = None,
) -> int:
    created_at = _utc_now_iso()
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pet_history (pet_id, event_type, created_at, title, details, triage_id, reminder_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pet_id, event_type, created_at, title, details, triage_id, reminder_id, meta_json),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_pet_history(pet_id: int, limit: int = 20) -> list[dict]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, event_type, created_at, title, details, triage_id, reminder_id, metadata
            FROM pet_history
            WHERE pet_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (pet_id, limit),
        )
        rows = cur.fetchall()
    res = []
    for r in rows:
        res.append(
            {
                "id": r[0],
                "event_type": r[1],
                "created_at": r[2],
                "title": r[3],
                "details": r[4],
                "triage_id": r[5],
                "reminder_id": r[6],
                "metadata": json.loads(r[7] or "{}"),
            }
        )
    return res
def get_pet_history(
    pet_id: int,
    limit: int = 20,
    offset: int = 0,
    event_types: list[str] | None = None,
) -> list[dict]:
    """Extended pet_history list with pagination + optional filtering by event_type.

    Kept for backward compatibility with Pets v2 screens.
    """
    where = "WHERE pet_id = ?"
    params: list = [pet_id]
    if event_types:
        placeholders = ",".join(["?"] * len(event_types))
        where += f" AND event_type IN ({placeholders})"
        params.extend(event_types)

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, event_type, created_at, title, details, triage_id, reminder_id, metadata
            FROM pet_history
            {where}
            ORDER BY id DESC
            LIMIT ?
            OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = cur.fetchall()

    res: list[dict] = []
    for rid, etype, created_at, title, details, triage_id, reminder_id, meta_json in rows:
        try:
            meta = json.loads(meta_json) if meta_json else {}
        except Exception:
            meta = {}
        res.append(
            {
                "id": rid,
                "event_type": etype,
                "created_at": created_at,
                "title": title,
                "details": details,
                "triage_id": triage_id,
                "reminder_id": reminder_id,
                "metadata": meta,
            }
        )
    return res


def count_pet_history(pet_id: int, event_types: list[str] | None = None) -> int:
    """Count pet_history rows for pagination."""
    where = "WHERE pet_id = ?"
    params: list = [pet_id]
    if event_types:
        placeholders = ",".join(["?"] * len(event_types))
        where += f" AND event_type IN ({placeholders})"
        params.extend(event_types)

    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(1)
            FROM pet_history
            {where}
            """,
            tuple(params),
        )
        (cnt,) = cur.fetchone()
    return int(cnt or 0)


def add_pet_measurement(
    pet_id: int,
    weight_kg: float | None = None,
    note: str | None = None,
    metadata: dict | None = None,
) -> int:
    created_at = _utc_now_iso()
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pet_measurements (pet_id, created_at, weight_kg, note, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pet_id, created_at, weight_kg, note, meta_json),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_pet_measurements(pet_id: int, limit: int = 30) -> list[dict]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, weight_kg, note, metadata
            FROM pet_measurements
            WHERE pet_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (pet_id, limit),
        )
        rows = cur.fetchall()
    res=[]
    for r in rows:
        res.append(
            {
                "id": r[0],
                "created_at": r[1],
                "weight_kg": r[2],
                "note": r[3],
                "metadata": json.loads(r[4] or "{}"),
            }
        )
    return res


def add_pet_vaccination(
    pet_id: int,
    vaccine_name: str,
    vaccinated_at: str,
    next_due_at: str | None = None,
    note: str | None = None,
    metadata: dict | None = None,
) -> int:
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pet_vaccinations (pet_id, vaccine_name, vaccinated_at, next_due_at, note, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pet_id, vaccine_name, vaccinated_at, next_due_at, note, meta_json),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_pet_vaccinations(pet_id: int, limit: int = 50) -> list[dict]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, vaccine_name, vaccinated_at, next_due_at, note, metadata
            FROM pet_vaccinations
            WHERE pet_id = ?
            ORDER BY vaccinated_at DESC, id DESC
            LIMIT ?
            """,
            (pet_id, limit),
        )
        rows = cur.fetchall()
    res=[]
    for r in rows:
        res.append(
            {
                "id": r[0],
                "vaccine_name": r[1],
                "vaccinated_at": r[2],
                "next_due_at": r[3],
                "note": r[4],
                "metadata": json.loads(r[5] or "{}"),
            }
        )
    return res


# ======================= Subscription scenario logs =======================

def log_user_event(user_id: int, event_type: str, payload: dict | None = None) -> None:
    created_at = _utc_now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_events (user_id, event_type, created_at, payload)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, event_type, created_at, payload_json),
        )
        conn.commit()


def count_user_events(user_id: int, event_type: str, since_iso: str | None = None) -> int:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        if since_iso:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM user_events
                WHERE user_id = ? AND event_type = ? AND created_at >= ?
                """,
                (user_id, event_type, since_iso),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM user_events
                WHERE user_id = ? AND event_type = ?
                """,
                (user_id, event_type),
            )
        (cnt,) = cur.fetchone()
        return int(cnt or 0)


def mark_offer_shown(user_id: int, event_type: str, key: str | None = None, payload: dict | None = None) -> None:
    shown_at = _utc_now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO subscription_offer_logs (user_id, event_type, key, shown_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, event_type, key, shown_at, payload_json),
        )
        conn.commit()


def last_offer_shown_at(user_id: int, event_type: str, key: str | None = None) -> str | None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        if key is None:
            cur.execute(
                """
                SELECT shown_at
                FROM subscription_offer_logs
                WHERE user_id = ? AND event_type = ? AND key IS NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, event_type),
            )
        else:
            cur.execute(
                """
                SELECT shown_at
                FROM subscription_offer_logs
                WHERE user_id = ? AND event_type = ? AND key = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, event_type, key),
            )
        row = cur.fetchone()
        return row[0] if row else None


def offer_was_shown(user_id: int, event_type: str, key: str | None = None) -> bool:
    return last_offer_shown_at(user_id, event_type, key) is not None


# ======================= Observations =======================

def add_pet_observation(
    user_id: int,
    pet_id: int,
    obs_type: str,
    payload: dict | None = None,
    source: str = "system",
) -> int:
    created_at = _utc_now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pet_observations (user_id, pet_id, obs_type, payload, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, pet_id, obs_type, payload_json, source, created_at),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_pet_vaccinations(pet_id: int, limit: int = 100) -> list[dict]:
    """Список вакцинаций питомца (самые новые сверху)."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, vaccine_name, vaccinated_at, next_due_at, note, metadata
            FROM pet_vaccinations
            WHERE pet_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (pet_id, limit),
        )
        rows = cur.fetchall()
    res: list[dict] = []
    for r in rows:
        res.append(
            {
                "id": r[0],
                "vaccine_name": r[1],
                "vaccinated_at": r[2],
                "next_due_at": r[3],
                "note": r[4],
                "metadata": json.loads(r[5] or "{}"),
            }
        )
    return res

def get_pet_observations(pet_id: int, limit: int = 50) -> list[dict]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, obs_type, payload, source, created_at
            FROM pet_observations
            WHERE pet_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (pet_id, limit),
        )
        rows = cur.fetchall()
    res=[]
    for r in rows:
        res.append(
            {
                "id": r[0],
                "type": r[1],
                "payload": json.loads(r[2] or "{}"),
                "source": r[3],
                "created_at": r[4],
            }
        )
    return res
