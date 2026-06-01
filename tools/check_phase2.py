from __future__ import annotations

import os
import sys
import tempfile
import inspect
from pathlib import Path


fd, db_path = tempfile.mkstemp(prefix="temichevvet-phase2-", suffix=".db")
os.close(fd)
Path(db_path).unlink(missing_ok=True)

os.environ.setdefault("BOT_TOKEN", "phase2-dummy-token")
os.environ.setdefault("OPENAI_API_KEY", "phase2-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ["DB_PATH"] = db_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.constants import SUPPORTED_PETS
from app.db import (
    clear_main_pet,
    create_pet,
    create_user,
    get_main_pet_id,
    get_pet_by_id,
    get_pets_for_user,
    init_db,
    set_main_pet,
)
from app.keyboards import onb_step1_kb, onb_step2_kb, onb_step3_kb, plus_paywall_inline_kb
from app.pets_v2.card import _pet_reminders_kb
from app.pets_v2.reminders import _periodicity_kb, reminders_edit_start


STATIC_FILES = [
    "onb_step1_add_pet.jpg",
    "onb_step2_set_main.jpg",
    "onb_step3_triage.jpg",
    "subscription_banner.jpg",
    "pets_banner.jpg",
    "triage_banner.jpg",
]


def _callback_data(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row}


def check_static_files() -> None:
    static_dir = Path(__file__).resolve().parents[1] / "app" / "static"
    for filename in STATIC_FILES:
        path = static_dir / filename
        assert path.is_file(), f"missing static file: {filename}"
        assert path.stat().st_size > 0, f"empty static file: {filename}"


def check_main_pet_flow() -> None:
    init_db()
    owner_id = create_user(telegram_id=444555666, name="Phase2")
    first_id = create_pet(owner_id, SUPPORTED_PETS["🐱 Кот/Кошка"], "Муся")
    second_id = create_pet(owner_id, SUPPORTED_PETS["🐶 Собака"], "Бим")

    assert get_main_pet_id(owner_id) == first_id
    assert get_pet_by_id(first_id)["is_main"] == 1
    assert get_pet_by_id(second_id)["is_main"] == 0

    assert set_main_pet(owner_id, second_id)
    assert get_main_pet_id(owner_id) == second_id
    pets = get_pets_for_user(owner_id)
    assert int(pets[0]["id"]) == second_id

    assert clear_main_pet(owner_id)
    assert get_main_pet_id(owner_id) is None


def check_keyboards() -> None:
    step1 = _callback_data(onb_step1_kb())
    assert {"onb:add_pet", "open:main_menu"} <= step1

    step2 = _callback_data(
        onb_step2_kb(
            [
                {"id": 1, "pet_type": "кошка", "pet_name": "Муся"},
                {"id": 2, "pet_type": "собака", "pet_name": "Бим"},
            ]
        )
    )
    assert {"onb:set_main:1", "onb:set_main:2", "onb:skip_main", "open:main_menu"} <= step2

    step3 = _callback_data(onb_step3_kb())
    assert {"onb:start_triage", "onb:done", "open:main_menu"} <= step3

    paywall = _callback_data(plus_paywall_inline_kb())
    assert {"open:subscription", "paywall_back:open:main_menu"} <= paywall

    empty_reminders = _callback_data(_pet_reminders_kb(7, has_reminders=False))
    assert {"petrem:add:7", "petcard:overview:7"} <= empty_reminders
    assert "petrem:editpick:7" not in empty_reminders

    reminders = _callback_data(_pet_reminders_kb(7, has_reminders=True))
    assert {"petrem:add:7", "petrem:editpick:7", "petrem:delpick:7", "petcard:overview:7"} <= reminders

    edit_periodicity = _callback_data(_periodicity_kb(7, "edit"))
    assert "petrem:edit:period:once:7" in edit_periodicity


def check_reminder_callback_filters() -> None:
    source = inspect.getsource(reminders_edit_start)
    assert 'F.data.regexp(r"^petrem:edit:\\d+:\\d+$")' in source

    reminders_module = __import__("app.pets_v2.reminders", fromlist=[""])
    period_source = inspect.getsource(reminders_module.reminders_edit_periodicity)
    notes_source = inspect.getsource(reminders_module.reminders_edit_notes)
    assert "reminder_id" in period_source and "Редактирование было прервано" in period_source
    assert "reminder_id" in notes_source and "Редактирование было прервано" in notes_source


def main() -> None:
    try:
        check_static_files()
        check_main_pet_flow()
        check_keyboards()
        check_reminder_callback_filters()
        print("phase2 checks ok")
    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
