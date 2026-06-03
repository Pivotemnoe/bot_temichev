from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


BTN_BACK = "⬅️ Назад"
BTN_MENU = "⬅️ В меню"
BTN_DONE = "Готово"

WHAT_NEXT_TEXT = "Что дальше?"


def is_cancel_text(text: str | None) -> bool:
    value = (text or "").strip().casefold()
    return value in {
        "/cancel",
        "cancel",
        "отмена",
        "отменить",
        "⬅️ назад",
        "⬅️ назад в меню",
        "в главное меню",
        "⬅️ в главное меню",
        "в меню",
        "⬅️ в меню",
    }


def what_next_kb(pet_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if pet_id:
        rows.append([InlineKeyboardButton(text="🐾 Открыть карточку питомца", callback_data=f"petcard:overview:{pet_id}")])
        rows.append([InlineKeyboardButton(text="➕ Добавить напоминание", callback_data=f"petrem:add:{pet_id}")])
    rows.append([InlineKeyboardButton(text="🩺 Новый разбор", callback_data="onb:start_triage")])
    rows.append([InlineKeyboardButton(text=BTN_MENU, callback_data="open:main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
