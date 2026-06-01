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
# СИСТЕМНАЯ ИНФОРМАЦИЯ
# -----------------------------

ENVIRONMENT = (os.getenv("ENV", "development").strip().lower() or "development")

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


def _parse_admin_ids(raw: str, fallback_admin_id: int) -> set[int]:
    values: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        item = part.strip()
        if not item:
            continue
        try:
            values.add(int(item))
        except ValueError:
            raise RuntimeError(
                f"❌ ADMIN_IDS в .env должен содержать числа через запятую, сейчас: {repr(raw)}"
            )

    if fallback_admin_id:
        values.add(int(fallback_admin_id))
    return values


# Telegram ID администраторов, которым доступен /admin dashboard.
# В production доступ к админ-панели должен быть задан явно через ADMIN_IDS.
# ADMIN_CHAT_ID нужен для уведомлений и обратной связи; в production он не должен
# неявно становиться администратором.
_admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS_EXPLICIT = bool(_admin_ids_raw)
_admin_fallback = ADMIN_CHAT_ID if not ADMIN_IDS_EXPLICIT and ENVIRONMENT != "production" else 0
ADMIN_IDS = _parse_admin_ids(_admin_ids_raw, _admin_fallback)


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
# ОПЛАТА (ЮKassa)
# -----------------------------

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/")
YOOKASSA_RECEIPT_EMAIL = os.getenv("YOOKASSA_RECEIPT_EMAIL", "")
YOOKASSA_TAX_SYSTEM_CODE = os.getenv("YOOKASSA_TAX_SYSTEM_CODE", "")
YOOKASSA_VAT_CODE = os.getenv("YOOKASSA_VAT_CODE", "1")

# -----------------------------
# ОПЦИИ ЛОГИРОВАНИЯ
# -----------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Возможность писать ошибки в файл (серверная конфигурация)
ERROR_LOG_PATH = os.getenv("ERROR_LOG_PATH", "")
