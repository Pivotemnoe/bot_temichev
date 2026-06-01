# app/config.py
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# -----------------------------
# ОБЯЗАТЕЛЬНЫЕ ПАРАМЕТРЫ
# -----------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не указан в .env")

# -----------------------------
# БАЗА ДАННЫХ
# -----------------------------

DB_PATH = os.getenv("DB_PATH", "bot.db")

# -----------------------------
# ID АДМИНА: для фидбэка, ошибок, техподдержки
# -----------------------------
# Может быть:
# - твоим личным Telegram ID
# - ID отдельного тех.чата
# Значение 0 означает "не отправлять админ-сообщения".

_admin_raw = os.getenv("ADMIN_CHAT_ID", "0").strip()

try:
    ADMIN_CHAT_ID = int(_admin_raw)
except ValueError:
    raise RuntimeError(
        f"❌ ADMIN_CHAT_ID в .env должен быть числом, сейчас: {repr(_admin_raw)}"
    )


# Чат/канал для обратной связи (по умолчанию совпадает с ADMIN_CHAT_ID)
_feedback_raw = os.getenv("FEEDBACK_CHAT_ID", "").strip()
if _feedback_raw:
    try:
        FEEDBACK_CHAT_ID = int(_feedback_raw)
    except ValueError:
        raise RuntimeError(
            f"❌ FEEDBACK_CHAT_ID в .env должен быть числом, сейчас: {repr(_feedback_raw)}"
        )
else:
    FEEDBACK_CHAT_ID = ADMIN_CHAT_ID

# -----------------------------
# НАСТРОЙКИ LLM (будущее использование)
# -----------------------------
# В будущем пригодится — чтобы на серверах UFA/Sber/Sky функции могли переключаться.
# Сейчас не используется, но пусть будет.

TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "gpt-4o-mini")
FAQ_MODEL = os.getenv("FAQ_MODEL", "gpt-4o-mini")
CARE_MODEL = os.getenv("CARE_MODEL", "gpt-4o-mini")

# -----------------------------
# ОПЦИИ ЛОГИРОВАНИЯ
# -----------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Возможность писать ошибки в файл (серверная конфигурация)
ERROR_LOG_PATH = os.getenv("ERROR_LOG_PATH", "")

# -----------------------------
# СИСТЕМНАЯ ИНФОРМАЦИЯ
# -----------------------------

ENVIRONMENT = os.getenv("ENV", "development")  # development / production