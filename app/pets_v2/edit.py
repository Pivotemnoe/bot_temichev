# app/pets_v2/edit.py

from __future__ import annotations

import re
from typing import Optional

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.db import (
    get_user_by_telegram_id,
    update_pet_name,
    update_pet_birth,
    update_pet_sex,
    update_pet_weight,
    update_pet_breed,
)
from app.keyboards import main_menu_kb

router = Router(name="pets_v2_edit")


class PetEditStates(StatesGroup):
    waiting_new_name = State()
    choosing_field = State()
    waiting_birth = State()
    waiting_sex = State()
    legacy_waiting_weight = State()  # legacy, use ⚖️ Вес in card
    waiting_breed = State()


# ===== вспомогательные клавиатуры =====


def _profile_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Дата рождения")],
            [KeyboardButton(text="Пол")],
            [KeyboardButton(text="Порода")],
            [KeyboardButton(text="Готово"), KeyboardButton(text="⬅️ В главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Не знаю/пропустить")],
            [KeyboardButton(text="⬅️ В главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ===== Переименование (как было) =====


@router.callback_query(F.data.startswith("pet:rename:"))
async def start_rename_pet(callback: CallbackQuery, state: FSMContext):
    """
    Старт переименования питомца по нажатию кнопки «✏️ Переименовать».
    """
    tg_id = callback.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await callback.answer("Пользователь не найден. Нажмите /start.")
        return

    try:
        _, _, pet_id_str = callback.data.split(":", 2)
        pet_id = int(pet_id_str)
    except Exception:
        await callback.answer("Не удалось определить питомца.", show_alert=True)
        return

    await state.update_data(pet_id=pet_id)
    await state.set_state(PetEditStates.waiting_new_name)

    await callback.message.answer(
        "Введите новое имя для этого питомца.\n\n"
        "Если хотите оставить питомца без имени, отправьте один дефис «-».\n"
        "Чтобы отменить переименование, нажмите «⬅️ В главное меню» или напишите «Отменить».",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.message(PetEditStates.waiting_new_name, F.text)
async def process_new_name(message: Message, state: FSMContext):
    """
    Обработка введённого нового имени.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await message.answer(
            "Пользователь не найден. Нажмите /start.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    raw_text = (message.text or "").strip()

    # Отмена переименования через кнопку или текст
    if raw_text in ("⬅️ В главное меню", "Отменить"):
        await state.clear()
        await message.answer(
            "Переименование отменено. Вы в главном меню.",
            reply_markup=main_menu_kb(),
        )
        return

    data = await state.get_data()
    pet_id = data.get("pet_id")
    if not pet_id:
        await message.answer(
            "Не удалось определить, какого питомца переименовать.\n"
            "Попробуйте ещё раз через раздел «🐾 Мои животные».",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    if raw_text == "-":
        new_name: Optional[str] = None
    else:
        new_name = raw_text

    ok = update_pet_name(user["id"], pet_id, new_name)
    await state.clear()

    if not ok:
        await message.answer(
            "Не удалось обновить имя питомца.\n"
            "Попробуйте ещё раз через раздел «🐾 Мои животные».",
            reply_markup=main_menu_kb(),
        )
        return

    display_name = new_name if new_name else "(без имени)"
    await message.answer(
        f"Имя питомца обновлено ✅\n\n"
        f"Новое имя: {display_name}\n\n"
        "Откройте «🐾 Мои животные», чтобы увидеть обновлённый список.",
        reply_markup=main_menu_kb(),
    )


@router.message(PetEditStates.waiting_new_name)
async def process_non_text(message: Message, state: FSMContext):
    """
    Защита от не-текстовых сообщений в состоянии ввода имени.
    """
    await message.answer("Пожалуйста, отправьте имя текстом.")


# ===== Редактирование анкеты (новое) =====


@router.callback_query(F.data.startswith("pet:edit:"))
async def start_edit_profile(callback: CallbackQuery, state: FSMContext):
    """
    Старт редактирования карточки питомца по кнопке «✏️ Редактировать карточку».
    """
    tg_id = callback.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await callback.answer("Пользователь не найден. Нажмите /start.")
        return

    try:
        _, _, pet_id_str = callback.data.split(":", 2)
        pet_id = int(pet_id_str)
    except Exception:
        await callback.answer("Не удалось определить питомца.", show_alert=True)
        return

    await state.update_data(pet_id=pet_id)
    await state.set_state(PetEditStates.choosing_field)

    await callback.message.answer(
        "Редактирование карточки питомца.\n\n"
        "Что вы хотите изменить?\n"
        "• Дата рождения\n"
        "• Пол\n"
        "• Вес\n"
        "• Порода\n\n"
        "Выберите пункт в меню или введите его текстом.\n"
        "Чтобы закончить редактирование, нажмите «Готово» или «⬅️ В главное меню».",
        reply_markup=_profile_menu_kb(),
    )
    await callback.answer()


@router.message(PetEditStates.choosing_field, F.text)
async def choose_field(message: Message, state: FSMContext):
    raw = (message.text or "").strip()

    lower = raw.lower()

    # Выход из режима редактирования
    if lower in ("готово", "в главное меню", "⬅️ в главное меню", "отменить"):
        await state.clear()
        await message.answer(
            "Редактирование карточки завершено. Вы в главном меню.",
            reply_markup=main_menu_kb(),
        )
        return

    if "дата" in lower:
        await state.set_state(PetEditStates.waiting_birth)
        await message.answer(
            "Укажите дату рождения питомца.\n\n"
            "Допустимые форматы:\n"
            "• ДД.ММ.ГГГГ  (пример: 05.09.2020)\n"
            "• ММ.ГГГГ      (пример: 09.2020)\n"
            "• ГГГГ         (пример: 2020)\n\n"
            "Если точная дата неизвестна — напишите «Не знаю/пропустить».",
            reply_markup=_cancel_kb(),
        )
        return

    if lower.startswith("пол") or lower in ("пол", "самец", "самка"):
        await state.set_state(PetEditStates.waiting_sex)
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Самец"), KeyboardButton(text="Самка")],
                [KeyboardButton(text="Не знаю/пропустить")],
                [KeyboardButton(text="⬅️ В главное меню")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(
            "Укажите пол питомца:\n"
            "• Самец\n"
            "• Самка\n"
            "• Не знаю/пропустить",
            reply_markup=kb,
        )
        return


    if lower.startswith("вес"):
        # Старый сценарий редактирования веса отключён: вес ведём только через новый flow «⚖️ Вес» в карточке.
        await message.answer(
            "Изменение веса перенесено в карточку питомца.\n\n"
            "Откройте карточку и нажмите «⚖️ Вес».",
            reply_markup=_profile_menu_kb(),
        )
        await state.set_state(PetEditStates.choosing_field)
        return


    if lower.startswith("порода"):
        await state.set_state(PetEditStates.waiting_breed)
        await message.answer(
            "Укажите породу питомца (например: «британская короткошёрстная»).\n"
            "Если не хотите указывать породу — напишите «Не знаю/пропустить».",
            reply_markup=_cancel_kb(),
        )
        return

    await message.answer(
        "Пожалуйста, выберите один из пунктов: «Дата рождения», «Пол», «Вес», «Порода», "
        "либо нажмите «Готово».",
        reply_markup=_profile_menu_kb(),
    )


def _parse_birth(text: str) -> Optional[tuple[int, Optional[int], Optional[int], str]]:
    """
    Разбор текста даты рождения.
    Форматы:
      - ГГГГ
      - ММ.ГГГГ
      - ДД.ММ.ГГГГ
    Возвращает (year, month|None, day|None, precision) или None, если формат не распознан.
    """
    cleaned = text.strip().replace(" ", "")
    # ДД.ММ.ГГГГ
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", cleaned):
        day = int(cleaned[0:2])
        month = int(cleaned[3:5])
        year = int(cleaned[6:10])
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        return year, month, day, "day"
    # ММ.ГГГГ
    if re.fullmatch(r"\d{2}\.\d{4}", cleaned):
        month = int(cleaned[0:2])
        year = int(cleaned[3:7])
        if not 1 <= month <= 12:
            return None
        return year, month, None, "month"
    # ГГГГ
    if re.fullmatch(r"\d{4}", cleaned):
        year = int(cleaned)
        return year, None, None, "year"
    return None


@router.message(PetEditStates.waiting_birth, F.text)
async def process_birth(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await state.clear()
        await message.answer(
            "Пользователь не найден. Нажмите /start.",
            reply_markup=main_menu_kb(),
        )
        return

    raw = (message.text or "").strip()

    if raw in ("⬅️ В главное меню", "Отменить"):
        await state.clear()
        await message.answer(
            "Редактирование карточки отменено. Вы в главном меню.",
            reply_markup=main_menu_kb(),
        )
        return

    if raw.lower() in ("не знаю", "пропустить", "не знаю/пропустить", "-"):
        data = await state.get_data()
        pet_id = data.get("pet_id")
        if not pet_id:
            await state.clear()
            await message.answer(
                "Не удалось определить питомца. Откройте раздел «🐾 Мои животные» и попробуйте ещё раз.",
                reply_markup=main_menu_kb(),
            )
            return

        ok = update_pet_birth(user["id"], pet_id, None, None, None, None)
        await state.set_state(PetEditStates.choosing_field)
        if not ok:
            await message.answer(
                "Не удалось обновить дату рождения.",
                reply_markup=_profile_menu_kb(),
            )
        else:
            await message.answer(
                "Дата рождения очищена.\nЧто дальше хотите изменить?",
                reply_markup=_profile_menu_kb(),
            )
        return

    parsed = _parse_birth(raw)
    if not parsed:
        await message.answer(
            "Не удалось распознать дату.\nПримеры корректных вариантов:\n"
            "• 05.09.2020\n• 09.2020\n• 2020\n\nПопробуйте ещё раз или напишите «Не знаю/пропустить».",
            reply_markup=_cancel_kb(),
        )
        return

    year, month, day, precision = parsed
    data = await state.get_data()
    pet_id = data.get("pet_id")
    if not pet_id:
        await state.clear()
        await message.answer(
            "Не удалось определить питомца. Откройте раздел «🐾 Мои животные» и попробуйте ещё раз.",
            reply_markup=main_menu_kb(),
        )
        return

    ok = update_pet_birth(user["id"], pet_id, year, month, day, precision)
    await state.set_state(PetEditStates.choosing_field)

    if not ok:
        await message.answer(
            "Не удалось обновить дату рождения.",
            reply_markup=_profile_menu_kb(),
        )
        return

    # Чуть аккуратнее форматируем дату для ответа
    if year and month and day:
        shown = f"{day:02d}.{month:02d}.{year}"
    elif year and month:
        shown = f"{month:02d}.{year}"
    else:
        shown = str(year)

    await message.answer(
        f"Дата рождения обновлена: {shown}\n\n"
        "Что дальше хотите изменить?",
        reply_markup=_profile_menu_kb(),
    )


@router.message(PetEditStates.waiting_sex, F.text)
async def process_sex(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await state.clear()
        await message.answer(
            "Пользователь не найден. Нажмите /start.",
            reply_markup=main_menu_kb(),
        )
        return

    raw = (message.text or "").strip()
    low = raw.lower()

    if raw in ("⬅️ В главное меню", "Отменить"):
        await state.clear()
        await message.answer(
            "Редактирование карточки отменено. Вы в главном меню.",
            reply_markup=main_menu_kb(),
        )
        return

    if low in ("не знаю", "пропустить", "не знаю/пропустить", "-"):
        sex_code: Optional[str] = None
        sex_text = "не указан"
    elif "самец" in low or "кобел" in low or "мальчик" in low:
        sex_code = "male"
        sex_text = "самец"
    elif "самка" in low or "сука" in low or "девоч" in low:
        sex_code = "female"
        sex_text = "самка"
    else:
        await message.answer(
            "Не удалось распознать пол.\n"
            "Напишите «Самец», «Самка» или «Не знаю/пропустить».",
        )
        return

    data = await state.get_data()
    pet_id = data.get("pet_id")
    if not pet_id:
        await state.clear()
        await message.answer(
            "Не удалось определить питомца. Откройте раздел «🐾 Мои животные» и попробуйте ещё раз.",
            reply_markup=main_menu_kb(),
        )
        return

    ok = update_pet_sex(user["id"], pet_id, sex_code)
    await state.set_state(PetEditStates.choosing_field)

    if not ok:
        await message.answer(
            "Не удалось обновить пол питомца.",
            reply_markup=_profile_menu_kb(),
        )
        return

    await message.answer(
        f"Пол обновлён: {sex_text}\n\n"
        "Что дальше хотите изменить?",
        reply_markup=_profile_menu_kb(),
    )


@router.message(PetEditStates.legacy_waiting_weight, F.text)
async def process_weight(message: Message, state: FSMContext):
    # Старый сценарий редактирования веса отключён: вес ведём только через новый flow «⚖️ Вес» в карточке.
    await state.set_state(PetEditStates.choosing_field)
    await message.answer(
        "Изменение веса перенесено в карточку питомца.\n\n"
        "Откройте карточку и нажмите «⚖️ Вес».",
        reply_markup=_profile_menu_kb(),
    )

@router.message(PetEditStates.waiting_breed, F.text)
async def process_breed(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await state.clear()
        await message.answer(
            "Пользователь не найден. Нажмите /start.",
            reply_markup=main_menu_kb(),
        )
        return

    raw = (message.text or "").strip()

    if raw in ("⬅️ В главное меню", "Отменить"):
        await state.clear()
        await message.answer(
            "Редактирование карточки отменено. Вы в главном меню.",
            reply_markup=main_menu_kb(),
        )
        return

    low = raw.lower()
    if low in ("не знаю", "пропустить", "не знаю/пропустить", "-"):
        breed_val: Optional[str] = None
        breed_text = "не указана"
    else:
        # Ограничим длину на всякий случай
        breed_val = raw[:100]
        breed_text = breed_val

    data = await state.get_data()
    pet_id = data.get("pet_id")
    if not pet_id:
        await state.clear()
        await message.answer(
            "Не удалось определить питомца. Откройте раздел «🐾 Мои животные» и попробуйте ещё раз.",
            reply_markup=main_menu_kb(),
        )
        return

    ok = update_pet_breed(user["id"], pet_id, breed_val)
    await state.set_state(PetEditStates.choosing_field)

    if not ok:
        await message.answer(
            "Не удалось обновить породу питомца.",
            reply_markup=_profile_menu_kb(),
        )
        return

    await message.answer(
        f"Порода обновлена: {breed_text}\n\n"
        "Что дальше хотите изменить?",
        reply_markup=_profile_menu_kb(),
    )