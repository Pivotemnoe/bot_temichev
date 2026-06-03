# app/keyboards_reminders.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from app.ux import BTN_MENU


def reminders_menu_kb() -> ReplyKeyboardMarkup:
    """
    Подменю раздела «📅 Напоминания и график»:
    - добавить напоминание;
    - показать список;
    - вернуться в главное меню.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить напоминание")],
            [KeyboardButton(text="📋 Мои напоминания")],
            [KeyboardButton(text=BTN_MENU)],
        ],
        resize_keyboard=True,
    )
