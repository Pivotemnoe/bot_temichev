from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


tmp = tempfile.NamedTemporaryFile(prefix="temichevvet_phase7_", suffix=".db", delete=False)
tmp.close()

os.environ["DB_PATH"] = tmp.name
os.environ.setdefault("BOT_TOKEN", "123456:test")
os.environ.setdefault("OPENAI_API_KEY", "phase7-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ["CLINIC_CONTACTS_JSON"] = json.dumps(
    {
        "77": {
            "name": "Клиника Добрый Доктор",
            "phone": "+7 900 000-00-77",
            "address": "ул. Тестовая, 7",
            "hours": "ежедневно 9:00-21:00",
            "telegram": "@clinic77",
        }
    },
    ensure_ascii=False,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import create_user, get_user_by_telegram_id, init_db  # noqa: E402
from app.services.clinic import (  # noqa: E402
    clinic_screen_kb,
    get_clinic_profile,
    render_clinic_screen,
    render_clinic_start_note,
)


def _callbacks(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}


def check_clinic_profile_and_copy() -> None:
    linked = get_clinic_profile(77)
    assert linked["linked"]
    assert linked["name"] == "Клиника Добрый Доктор"
    assert linked["phone"] == "+7 900 000-00-77"

    note = render_clinic_start_note(linked)
    assert "официальный цифровой помощник клиники" in note
    assert "Клиника Добрый Доктор" in note

    screen = render_clinic_screen(linked)
    assert "Вы подключены к сервису вашей клиники" in screen
    assert "Телефон: +7 900 000-00-77" in screen
    assert "Адрес: ул. Тестовая, 7" in screen

    unlinked = get_clinic_profile(None)
    assert not unlinked["linked"]
    unlinked_screen = render_clinic_screen(unlinked)
    assert "нет карты клиник" in unlinked_screen

    callbacks = _callbacks(clinic_screen_kb())
    assert callbacks == {"clinic:start_triage", "open:main_menu"}


def check_user_clinic_storage_for_surface() -> None:
    init_db()
    user_id = create_user(telegram_id=777001, name="Clinic User", clinic_id=77)
    assert user_id > 0
    user = get_user_by_telegram_id(777001)
    assert user["clinic_id"] == 77

    screen = render_clinic_screen(get_clinic_profile(user["clinic_id"]))
    assert "Клиника Добрый Доктор" in screen


def main() -> None:
    check_clinic_profile_and_copy()
    check_user_clinic_storage_for_surface()
    print("phase7 ok")


if __name__ == "__main__":
    main()
