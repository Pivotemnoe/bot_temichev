# app/services/selftest.py

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import closing

from app.config import DB_PATH, BOT_TOKEN
from app.db import init_db

logger = logging.getLogger(__name__)

# Если в config уже есть OPENAI_API_KEY — используем, если нет, берём из окружения напрямую
try:
    from app.config import OPENAI_API_KEY  # type: ignore
except ImportError:  # на всякий случай
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


REQUIRED_TABLES = {
    "users",
    "pets",
    "subscriptions",
    "triage_logs",
    "triage_followups",
    "reminders",
}


class SelftestError(RuntimeError):
    """Исключение для ошибок самопроверки."""


def _check_env() -> None:
    """
    Проверка критичных переменных окружения.
    BOT_TOKEN уже проверяется в app.config, но здесь даём дополнительный лог.
    """
    if not BOT_TOKEN:
        raise SelftestError("BOT_TOKEN не указан (см. .env).")

    if not DB_PATH:
        raise SelftestError("DB_PATH не указан (см. .env).")

    if not OPENAI_API_KEY:
        raise SelftestError("OPENAI_API_KEY не указан (см. .env).")

    logger.info("[SELFTEST] Переменные окружения в порядке.")


def _check_db_file() -> None:
    """
    Проверяем, что каталог под DB_PATH существует (файл может быть создан init_db()).
    Для SQLite достаточно, чтобы существовала директория.
    """
    db_dir = os.path.dirname(DB_PATH) or "."
    if not os.path.isdir(db_dir):
        raise SelftestError(f"Каталог для базы данных не существует: {db_dir}")

    logger.info("[SELFTEST] Каталог для базы данных существует: %s", db_dir)


def _check_db_schema() -> None:
    """
    Проверка доступности БД и наличия ключевых таблиц.
    init_db() создаёт таблицы при необходимости.
    """
    logger.info("[SELFTEST] Проверка базы данных: %s", DB_PATH)

    # init_db сам откроет соединение и создаст таблицы
    init_db()

    # теперь проверяем наличие таблиц
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        )
        rows = cur.fetchall()

    existing = {row[0] for row in rows}
    missing = REQUIRED_TABLES - existing

    if missing:
        raise SelftestError(
            f"В базе данных отсутствуют обязательные таблицы: {', '.join(sorted(missing))}"
        )

    logger.info("[SELFTEST] База данных доступна, все ключевые таблицы на месте.")


def run_selftest() -> None:
    """
    Запустить полный selftest.

    При критической проблеме выбрасывает SelftestError,
    который должен остановить запуск бота.
    """
    logger.info("========== SELFTEST: старт ==========")
    try:
        _check_env()
        _check_db_file()
        _check_db_schema()
    except SelftestError as e:
        logger.error("SELFTEST FAILED: %s", e)
        # Пробрасываем дальше, чтобы main.py мог не запускать polling
        raise
    except Exception as e:
        # Непредвиденная ошибка самопроверки
        logger.exception("SELFTEST CRASH: %r", e)
        raise SelftestError(f"Неожиданная ошибка selftest: {e}") from e
    else:
        logger.info("========== SELFTEST: успешно ==========")
