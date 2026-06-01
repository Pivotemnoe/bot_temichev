from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def nutrition_menu_kb() -> ReplyKeyboardMarkup:
    """
    Подменю раздела «🍽️ Питание»:
    - поиск по конкретному продукту;
    - быстрый доступ к спискам «что можно» / «что нельзя»;
    - возврат в главное меню.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти продукт")],
            [
                KeyboardButton(text="✅ Что можно"),
                KeyboardButton(text="⛔ Что нельзя"),
            ],
            [KeyboardButton(text="⬅️ В главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def faq_menu_kb() -> ReplyKeyboardMarkup:
    """
    Подменю раздела «❓ Вопрос-ответ»:
    - популярные вопросы;
    - поиск по вопросу / теме;
    - возврат в главное меню.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📌 Популярные вопросы")],
            [KeyboardButton(text="🔍 Найти ответ по вопросу")],
            [KeyboardButton(text="⬅️ В главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def care_menu_kb() -> ReplyKeyboardMarkup:
    """
    Подменю раздела «🧴 Уход и привычки»:
    - готовые карточки ухода;
    - поиск по теме;
    - возврат в главное меню.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Карточки по уходу")],
            [KeyboardButton(text="🔍 Найти по теме ухода")],
            [KeyboardButton(text="⬅️ В главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )