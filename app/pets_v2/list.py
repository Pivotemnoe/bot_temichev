# app/pets_v2/list.py

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from app.db import get_user_by_telegram_id, get_pets_for_user
from app.keyboards import main_menu_kb

router = Router(name="pets_v2_list")

def _pet_type_human(pet_type_value: str | None) -> str:
    """
    Нормализация типа питомца с учётом старых записей в БД.

    Варианты:
      - 'cat', 'кошка', 'кот'           → 'кошка'
      - 'dog', 'собака', 'пёс', 'пес'   → 'собака'
      - любое другое значение           → показываем как есть
    """
    if not pet_type_value:
        return "питомец"

    raw = str(pet_type_value).strip()
    low = raw.lower()

    if low in ("cat", "кошка", "кот"):
        return "кошка"
    if low in ("dog", "собака", "пёс", "пес"):
        return "собака"

    # если в БД лежит что-то своё — показываем как есть
    return raw


def _pet_label(pet: dict) -> str:
    """
    Человекочитаемый ярлык питомца для списков и кнопок.
    Формат: "кошка — Лео" или "собака — (без имени)".
    """
    pet_type_ru = _pet_type_human(pet.get("pet_type"))
    name = pet.get("pet_name") or "(без имени)"
    return f"{pet_type_ru} — {name}"


def _pets_list_kb(pets: list[dict]) -> ReplyKeyboardMarkup:
    """
    Клавиатура для раздела «🐾 Мои животные»:

    - отдельная кнопка на каждого питомца;
    - кнопка «➕ Добавить животное» для быстрого добавления;
    - кнопка «⬅️ В главное меню» для выхода.
    """
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=_pet_label(p))] for p in pets
    ]

    # добавить нового питомца
    rows.append([KeyboardButton(text="➕ Добавить животное")])
    # назад в главное меню
    rows.append([KeyboardButton(text="⬅️ В главное меню")])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
    )


@router.message(F.text == "🐾 Мои животные")
async def pets_list_handler(message: Message):
    """
    Раздел «Мои животные».

    Показываем:
    - общее количество питомцев;
    - список строкой;
    - клавиатуру с выбором конкретного питомца или добавлением нового.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)

    if user is None:
        await message.answer(
            "Вы ещё не зарегистрированы. Сначала используйте /start.",
            reply_markup=main_menu_kb(),
        )
        return

    pets = get_pets_for_user(user["id"])

    if not pets:
        # Нет ни одного питомца — сразу предлагаем добавить первого.
        text = (
            "🐾 Раздел «Мои животные».\n\n"
            "Пока у вас нет зарегистрированных питомцев.\n\n"
            "Добавьте первого питомца кнопкой «➕ Добавить животное» ниже.\n"
            "В любой момент можно вернуться в главное меню."
        )

        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Добавить животное")],
                [KeyboardButton(text="⬅️ В главное меню")],
            ],
            resize_keyboard=True,
        )

        await message.answer(text, reply_markup=kb)
        return

    # Есть хотя бы один питомец — показываем список.
    lines: list[str] = [
        "🐾 Раздел «Мои животные».",
        "",
        f"Сейчас у вас зарегистрировано питомцев: {len(pets)}.",
        "",
    ]

    for p in pets:
        lines.append(f"• {_pet_label(p)}")

    lines.append("")
    lines.append(
        "Чтобы посмотреть подробную карточку, выберите питомца ниже.\n"
        "Если нужно, вы можете добавить нового питомца кнопкой "
        "«➕ Добавить животное».\n"
        "В любой момент можно вернуться в главное меню."
    )

    text = "\n".join(lines)
    kb = _pets_list_kb(pets)

    await message.answer(text, reply_markup=kb) 

from .card import show_pet_card


@router.message(StateFilter(None), F.text.regexp(r".+(—|-).+"))
async def pets_open_card_from_label(message: Message):
    """Открыть карточку питомца по нажатию на кнопку-лейбл из списка.

    Кнопки списка формируются без ID (человеческий текст вида: 'кошка — Лео'),
    поэтому сопоставляем по точному совпадению с _pet_label(pet).
    """
    text = (message.text or "").strip()
    if not text:
        return

    # Не перехватываем системные кнопки этого раздела
    if text in {"➕ Добавить животное", "⬅️ В главное меню", "🐾 Мои животные"}:
        return

    # Быстрый фильтр: лейблы питомцев всегда содержат разделитель
    if "—" not in text and "-" not in text:
        return

    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start, чтобы зарегистрироваться.", reply_markup=main_menu_kb())
        return

    pets = get_pets_for_user(user["id"]) or []
    for pet in pets:
        try:
            if _pet_label(pet) == text:
                await show_pet_card(message, int(pet["id"]))
                return
        except Exception:
            continue

    # Если не нашли (например, изменили имя/тип), просто обновим список
    await pets_list_handler(message)
