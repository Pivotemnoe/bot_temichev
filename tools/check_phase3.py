from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path


fd, db_path = tempfile.mkstemp(prefix="temichevvet-phase3-", suffix=".db")
os.close(fd)
Path(db_path).unlink(missing_ok=True)

os.environ.setdefault("BOT_TOKEN", "phase3-dummy-token")
os.environ.setdefault("OPENAI_API_KEY", "phase3-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ["DB_PATH"] = db_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.constants import SUPPORTED_PETS
from app.db import add_pet_history_event, create_pet, create_user, get_pet_by_id, init_db, update_pet_birth
from app.handlers.triage import _ensure_trust_phrase, _extract_short_summary, _pet_age_context_from_card
from app.keyboards import triage_done_kb
from app.pets_v2.card import _build_overview_text
from app.services.subscription_limits import can_access_history


def _callback_data(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row}


def check_history_limits() -> None:
    assert can_access_history("free", 3)
    assert not can_access_history("free", 4)
    assert can_access_history("plus", 4)


def check_summary_and_trust() -> None:
    text = "1) Кратко: кошка вялая, плохо ест, состояние ухудшается.\n2) Уровень срочности: 🟡 планово"
    assert _extract_short_summary(text) == "кошка вялая, плохо ест, состояние ухудшается."
    assert _ensure_trust_phrase("Ответ").endswith("Этот ответ не заменяет очный осмотр ветеринарного врача.")


def check_pet_card_triage_preview() -> None:
    init_db()
    owner_id = create_user(telegram_id=777888999, name="Phase3")
    pet_id = create_pet(owner_id, SUPPORTED_PETS["🐱 Кот/Кошка"], "Муся")

    for idx, emoji in enumerate(["🟢", "🟡", "🟥", "🟡"], start=1):
        add_pet_history_event(
            pet_id=pet_id,
            event_type="triage",
            title=f"{emoji} Разбор",
            details=f"summary {idx}",
            metadata={"urgency_emoji": emoji, "summary": f"summary {idx}"},
        )

    text = _build_overview_text(get_pet_by_id(pet_id), owner_id=owner_id)
    assert "История разборов (последние 3)" in text
    assert "summary 4" in text
    assert "summary 3" in text
    assert "summary 2" in text
    assert "summary 1" not in text


def check_post_triage_keyboard() -> None:
    callbacks = _callback_data(triage_done_kb(42))
    assert {"petcard:overview:42", "onb:start_triage", "open:main_menu"} <= callbacks


def check_triage_uses_pet_card_age() -> None:
    init_db()
    owner_id = create_user(telegram_id=777889000, name="Phase3 Age")
    pet_id = create_pet(owner_id, SUPPORTED_PETS["🐱 Кот/Кошка"], "Лео")

    assert _pet_age_context_from_card(get_pet_by_id(pet_id), today=date(2026, 6, 3)) is None

    update_pet_birth(owner_id, pet_id, 2013, None, None, "year")
    context = _pet_age_context_from_card(get_pet_by_id(pet_id), today=date(2026, 6, 3))
    assert context is not None
    assert context["age_group"] == "Старше 7 лет (возрастной)"
    assert context["age_display"] == "13 лет"
    assert context["age_info"] == "Старше 7 лет (возрастной); из карточки питомца: 13 лет"


def main() -> None:
    try:
        check_history_limits()
        check_summary_and_trust()
        check_pet_card_triage_preview()
        check_post_triage_keyboard()
        check_triage_uses_pet_card_age()
        print("phase3 checks ok")
    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
