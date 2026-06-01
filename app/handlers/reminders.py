# app/handlers/reminders.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.db import (
    get_user_by_telegram_id,
    get_pets_for_user,
    get_pet_by_id,
    get_subscription,
    can_user_create_reminder,
    create_reminder,
    get_user_reminders,
    deactivate_reminder,
)
from app.services.pet_observation_service import add_observation
from app.keyboards import main_menu_kb, choose_pet_kb, skip_kb

logger = logging.getLogger(__name__)

from app.reminders_texts import (
    REMINDERS_NEED_REGISTER,
    REMINDERS_SECTION_INTRO,
    REMINDERS_NO_PETS,
    REMINDERS_CHOOSE_PET,
    REMINDERS_CHOOSE_TYPE,
    REMINDERS_ENTER_TEXT,
    REMINDERS_ENTER_DATE,
    REMINDERS_CANCELLED,
    REMINDERS_INVALID_DATE,
    REMINDERS_SAVED,
    REMINDERS_LIST_HEADER,
    REMINDERS_LIST_EMPTY,
    REMINDERS_DELETE_PROMPT,
    REMINDERS_DELETED,
)

router = Router()


class ReminderStates(StatesGroup):
    choosing_pet = State()
    choosing_type = State()
    entering_title = State()
    entering_date = State()
    entering_time = State()
    choosing_periodicity = State()


# ===== Вспомогательные функции =====


def _format_date_for_storage(dt: datetime) -> str:
    """Сохраняем дату в ISO-формате YYYY-MM-DD."""
    return dt.strftime("%Y-%m-%d")


def _parse_date(text: str) -> Optional[datetime]:
    """
    Разбор даты в нескольких форматах:
      - ДД.ММ.ГГГГ
      - ДД.ММ.ГГ
      - YYYY-MM-DD
    """
    text = (text or "").strip()
    if not text:
        return None

    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_time(text: str) -> Optional[str]:
    """
    Разбор времени:
      - HH:MM
      - H:MM

    Возвращает нормализованное HH:MM или None.
    """
    text = (text or "").strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered in {"пропустить", "без времени", "не важно", "неважно"}:
        return None

    try:
        t = datetime.strptime(text, "%H:%M")
        return t.strftime("%H:%M")
    except ValueError:
        return None


def _map_periodicity(text: str) -> Optional[str]:
    """
    Преобразуем текст из клавиатуры в код periodicity для БД.
    """
    normalized = (text or "").strip().lower()
    if normalized in {"один раз", "разово"}:
        return "once"
    if normalized in {"каждый год", "ежегодно"}:
        return "yearly"
    if normalized in {
        "каждые 6 месяцев",
        "каждые шесть месяцев",
        "раз в полгода",
    }:
        return "every_6_months"
    if normalized in {
        "каждые 3 месяца",
        "каждые три месяца",
        "раз в квартал",
    }:
        return "every_3_months"
    if normalized in {"каждый месяц", "ежемесячно"}:
        return "monthly"
    return None


def _reminder_types_keyboard() -> List[List[str]]:
    """
    Варианты типа напоминания (подписи кнопок).
    """
    return [
        ["💉 Прививка", "🪳 Паразиты (блохи/клещи/глисты)"],
        ["🩺 Плановый осмотр", "🍽️ Корм/диета"],
        ["📌 Другое"],
        ["Отменить"],
    ]


def _map_reminder_type(text: str) -> Tuple[str, str]:
    """
    Маппинг текста кнопки на внутренний код reminder_type и человеко-понятный заголовок.
    """
    normalized = (text or "").strip().lower()
    if normalized.startswith("💉") or "привив" in normalized:
        return "vaccine", "Прививка"
    if "паразит" in normalized or "блохи" in normalized or "клещи" in normalized:
        return "parasites", "Обработка от паразитов"
    if "осмотр" in normalized or "чекап" in normalized or "чек-ап" in normalized:
        return "checkup", "Плановый осмотр"
    if "корм" in normalized or "диета" in normalized:
        return "diet", "Корм / диета"
    return "custom", "Другое"


def _build_pet_options(pets: List[Dict]) -> Dict[str, int]:
    """
    Формируем карту «подпись → id питомца».
    """
    options: Dict[str, int] = {}
    for p in pets:
        pet_type = p.get("pet_type") or ""
        pet_name = p.get("pet_name") or "(без имени)"

        if pet_type == "cat":
            label = f"🐱 {pet_name}"
        elif pet_type == "dog":
            label = f"🐶 {pet_name}"
        else:
            label = f"{pet_type} — {pet_name}"

        options[label] = p["id"]
    return options


def _reminder_pet_label(pet_id: int | str | None) -> str | None:
    if not pet_id:
        return None
    try:
        pet = get_pet_by_id(int(pet_id))
    except Exception:
        return None
    if not pet:
        return None

    pet_type = pet.get("pet_type") or pet.get("type") or "питомец"
    pet_name = pet.get("pet_name") or pet.get("name") or "(без имени)"
    emoji = "🐾"
    normalized_type = str(pet_type).strip().lower()
    if normalized_type in ("cat", "кошка", "кот") or normalized_type.startswith("кош"):
        emoji = "🐱"
    elif normalized_type in ("dog", "собака", "пёс", "пес") or normalized_type.startswith("соб"):
        emoji = "🐶"
    return f"{emoji} {pet_type} — {pet_name}"


# ===== Вход в модуль напоминаний (через команды) =====


@router.message(Command("reminders"))
async def reminders_entry(message: Message, state: FSMContext) -> None:
    """
    Входная точка в модуль напоминаний.
    Сейчас — через /reminders.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(
            REMINDERS_NEED_REGISTER,
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    logger.warning(">>> reminders_entry TRIGGERED")

    await message.answer(
        "Раздел «Напоминания и график».\n\n"
        "Сейчас доступны команды:\n"
        "• /reminders_add — добавить новое напоминание;\n"
        "• /reminders_list — список активных напоминаний;\n"
        "• /reminders_off ID — отключить напоминание по id.\n\n"
        "Позже сюда подвяжем кнопки из главного меню.",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


# ===== Создание напоминания =====




@router.message(F.text == "➕ Добавить напоминание")
async def reminders_add_from_menu(message: Message, state: FSMContext) -> None:
    # Эквивалент /reminders_add
    await reminders_add_start(message, state)


@router.message(F.text == "📋 Мои напоминания")
async def reminders_list_from_menu(message: Message, state: FSMContext) -> None:
    # Эквивалент /reminders_list
    await reminders_list(message, state)
@router.message(Command("reminders_add"))
async def reminders_add_start(message: Message, state: FSMContext) -> None:
    """
    Старт создания напоминания.
    1) проверяем пользователя;
    2) проверяем, есть ли питомцы;
    3) проверяем лимиты/тариф через can_user_create_reminder;
    4) предлагаем выбрать питомца.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(
            REMINDERS_NEED_REGISTER,
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    pets = get_pets_for_user(user["id"])
    if not pets:
        await message.answer(REMINDERS_NO_PETS, reply_markup=main_menu_kb())
        await state.clear()
        return

    pet_options = _build_pet_options(pets)
    await state.update_data(reminder_pet_options=pet_options)

    labels = list(pet_options.keys())
    await state.set_state(ReminderStates.choosing_pet)
    await message.answer(
        "Для какого питомца создать напоминание?\n"
        "Выберите из списка ниже.",
        reply_markup=choose_pet_kb(labels),
    )


@router.message(ReminderStates.choosing_pet)
async def reminders_choose_pet(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(REMINDERS_CANCELLED, reply_markup=main_menu_kb())
        return

    data = await state.get_data()
    options: Dict[str, int] = data.get("reminder_pet_options") or {}
    pet_id = options.get(text)
    if not pet_id:
        await message.answer(
            "Пожалуйста, выберите питомца из списка на клавиатуре или нажмите «Отменить».",
        )
        return

    await state.update_data(reminder_pet_id=pet_id)

    # Переходим к выбору типа напоминания
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    rows = [
        [KeyboardButton(text=label) for label in row]
        for row in _reminder_types_keyboard()
    ]
    kb = ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await state.set_state(ReminderStates.choosing_type)
    await message.answer(
        "Какой тип напоминания нужно создать?\n"
        "Выберите вариант:\n"
        "• 💉 Прививка\n"
        "• 🪳 Паразиты (блохи/клещи/глисты)\n"
        "• 🩺 Плановый осмотр\n"
        "• 🍽️ Корм/диета\n"
        "• 📌 Другое",
        reply_markup=kb,
    )


@router.message(ReminderStates.choosing_type)
async def reminders_choose_type(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(REMINDERS_CANCELLED, reply_markup=main_menu_kb())
        return

    reminder_type, type_title = _map_reminder_type(text)
    await state.update_data(reminder_type=reminder_type, reminder_type_title=type_title)

    await state.set_state(ReminderStates.entering_title)
    await message.answer(
        "Кратко опишите, о чём напомнить.\n\n"
        "Примеры:\n"
        "• Вакцинация от бешенства\n"
        "• Обработка от блох и клещей\n"
        "• Плановый чекап у терапевта\n"
        "• Купить и начать новый корм",
    )


@router.message(ReminderStates.entering_title)
async def reminders_enter_title(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(REMINDERS_CANCELLED, reply_markup=main_menu_kb())
        return

    if not text:
        await message.answer(
            "Пожалуйста, напишите, о чём напомнить, или нажмите «Отменить».",
        )
        return

    await state.update_data(reminder_title=text)
    await state.set_state(ReminderStates.entering_date)
    await message.answer(
        "На какую дату поставить напоминание?\n\n"
        "Допустимые форматы:\n"
        "• 10.12.2025\n"
        "• 10.12.25\n"
        "• 2025-12-10",
    )


@router.message(ReminderStates.entering_date)
async def reminders_enter_date(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(REMINDERS_CANCELLED, reply_markup=main_menu_kb())
        return

    dt = _parse_date(text)
    if dt is None:
        await message.answer(
            "Не удалось разобрать дату.\n"
            "Пожалуйста, укажите дату в формате 10.12.2025 или 2025-12-10.",
        )
        return

    await state.update_data(reminder_due_date=_format_date_for_storage(dt))

    await state.set_state(ReminderStates.entering_time)
    await message.answer(
        "Во сколько напомнить?\n\n"
        "Формат: ЧЧ:ММ, например 09:30.\n"
        "Если время не важно — напишите «Пропустить».",
        reply_markup=skip_kb(),
    )


@router.message(ReminderStates.entering_time)
async def reminders_enter_time(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(REMINDERS_CANCELLED, reply_markup=main_menu_kb())
        return

    time_str = _parse_time(text)
    if time_str is None and text.lower() not in {
        "пропустить",
        "без времени",
        "не важно",
        "неважно",
    }:
        await message.answer(
            "Не удалось разобрать время.\n"
            "Укажите время в формате 09:30 или напишите «Пропустить».",
            reply_markup=skip_kb(),
        )
        return

    await state.update_data(reminder_due_time=time_str)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    rows = [
        [KeyboardButton(text="Один раз")],
        [KeyboardButton(text="Каждый год")],
        [KeyboardButton(text="Каждые 6 месяцев")],
        [KeyboardButton(text="Каждые 3 месяца")],
        [KeyboardButton(text="Каждый месяц")],
        [KeyboardButton(text="Отменить")],
    ]
    kb = ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await state.set_state(ReminderStates.choosing_periodicity)
    await message.answer(
        "Как часто повторять напоминание?\n"
        "Выберите вариант:\n"
        "• Один раз\n"
        "• Каждый год\n"
        "• Каждые 6 месяцев\n"
        "• Каждые 3 месяца\n"
        "• Каждый месяц",
        reply_markup=kb,
    )


@router.message(ReminderStates.choosing_periodicity)
async def reminders_choose_periodicity(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(REMINDERS_CANCELLED, reply_markup=main_menu_kb())
        return

    periodicity = _map_periodicity(text)
    if periodicity is None:
        await message.answer(
            "Не удалось определить периодичность.\n"
            "Пожалуйста, выберите вариант с клавиатуры или нажмите «Отменить».",
        )
        return

    data = await state.get_data()
    reminder_type = data.get("reminder_type", "custom")
    reminder_type_title = data.get("reminder_type_title", "Напоминание")
    title = data.get("reminder_title") or reminder_type_title
    due_date = data.get("reminder_due_date")
    due_time = data.get("reminder_due_time")
    pet_id = data.get("reminder_pet_id")

    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(
            "Пользователь не найден. Попробуйте начать сначала через /start.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    subscription = get_subscription(user["id"])
    allowed, reason = can_user_create_reminder(user, subscription)
    if not allowed:
        await message.answer(reason, reply_markup=main_menu_kb())
        await state.clear()
        return

    create_reminder(
        user_id=user["id"],
        pet_id=pet_id,
        reminder_type=reminder_type,
        title=title,
        due_date=due_date,
        due_time=due_time,
        periodicity=periodicity,
        notes=None,
    )

    # Observation: vaccination reminder created (linked to конкретному питомцу)
    if reminder_type == "vaccine" and pet_id is not None:
        try:
            add_observation(
                user_id=user["id"],
                pet_id=int(pet_id),
                obs_type="REMINDER_VACCINATION_CREATED",
                payload={
                    "title": title,
                    "due_date": due_date,
                    "due_time": due_time,
                    "periodicity": periodicity,
                },
                source="reminders",
            )
        except Exception:
            # наблюдения не должны ломать создание напоминаний
            pass

    time_part = f" в {due_time}" if due_time else ""
    await message.answer(
        f"Напоминание создано ✅\n\n"
        f"Тип: {reminder_type_title}\n"
        f"Тема: {title}\n"
        f"Дата: {due_date}{time_part}\n"
        f"Повтор: {text}",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


# ===== Просмотр и отключение напоминаний =====


@router.message(Command("reminders_list"))
async def reminders_list(message: Message, state: FSMContext) -> None:
    """
    Показать активные напоминания пользователя.
    Отключение — через кнопку «❌ Отключить» или /reminders_off <id>.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(
            REMINDERS_NEED_REGISTER,
            reply_markup=main_menu_kb(),
        )
        return

    reminders = get_user_reminders(user["id"])
    if not reminders:
        await message.answer(
            "Активных напоминаний пока нет.",
            reply_markup=main_menu_kb(),
        )
        return

    for r in reminders:
        rid = r.get("id")
        title = r.get("title") or "(без названия)"
        rtype = r.get("reminder_type") or "custom"
        due_date = r.get("due_date") or "-"
        due_time = r.get("due_time") or ""
        periodicity = r.get("periodicity") or "once"
        pet_label = _reminder_pet_label(r.get("pet_id"))

        type_label = {
            "vaccine": "Прививка",
            "parasites": "Обработка от паразитов",
            "checkup": "Плановый осмотр",
            "diet": "Корм / диета",
            "custom": "Другое",
        }.get(rtype, rtype)

        time_part = f" {due_time}" if due_time else ""
        pet_part = f"Питомец: {pet_label}\n" if pet_label else ""
        text = (
            f"#{rid}: [{type_label}] {title}\n"
            f"{pet_part}"
            f"Когда: {due_date}{time_part}, повтор: {periodicity}"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отключить",
                        callback_data=f"rem_off:{rid}",
                    )
                ]
            ]
        )

        await message.answer(text, reply_markup=kb)

    await message.answer(
        "Чтобы создать новое напоминание, используйте раздел «⏰ Напоминания».",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


@router.message(Command("reminders_off"))
async def reminders_off(message: Message, state: FSMContext) -> None:
    """
    Отключение конкретного напоминания по id:
    /reminders_off 12
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(
            REMINDERS_NEED_REGISTER,
            reply_markup=main_menu_kb(),
        )
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "Укажите id напоминания.\n"
            "Пример: /reminders_off 12\n\n"
            "Посмотреть список: /reminders_list",
            reply_markup=main_menu_kb(),
        )
        return

    try:
        reminder_id = int(parts[1])
    except ValueError:
        await message.answer(
            "id напоминания должен быть числом.\n"
            "Пример: /reminders_off 12",
            reply_markup=main_menu_kb(),
        )
        return

    reminders = get_user_reminders(user["id"])
    ids = {r["id"] for r in reminders}
    if reminder_id not in ids:
        await message.answer(
            "Активного напоминания с таким id не найдено среди ваших.\n"
            "Проверьте номер через /reminders_list.",
            reply_markup=main_menu_kb(),
        )
        return

    deactivate_reminder(reminder_id)
    await message.answer(
        f"Напоминание #{reminder_id} отключено.",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


async def open_reminders_for_pet(message: Message, state: FSMContext, pet_id: int) -> None:
    """Открыть напоминания сразу для выбранного питомца (используется из карточки питомца)."""
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(REMINDERS_NEED_REGISTER, reply_markup=main_menu_kb())
        return

    pets = get_pets_for_user(user["id"])
    pet = next((p for p in pets if p["id"] == pet_id), None)
    if not pet:
        await message.answer("Питомец не найден.", reply_markup=main_menu_kb())
        return

    await state.clear()
    await state.update_data(selected_pet_id=pet_id)

    # Покажем список активных напоминаний именно для питомца
    reminders = [r for r in get_user_reminders(user["id"]) if r.get("pet_id") == pet_id and r.get("is_active")]
    header = f"⏰ Напоминания — {pet['type']} — {pet['name']}"
    if not reminders:
        await message.answer(
            f"{header}\n\nАктивных напоминаний пока нет.\n\n"
            "Чтобы добавить напоминание, нажмите «➕ Добавить напоминание» в разделе «⏰ Напоминания» главного меню.",
            reply_markup=main_menu_kb(),
        )
        return

    lines = [header, ""]
    for r in reminders[:20]:
        dt = f"{r.get('due_date','')} {r.get('due_time','')}".strip()
        title = r.get("title") or r.get("reminder_type") or "Напоминание"
        lines.append(f"• {title} — {dt}")
    await message.answer("\n".join(lines), reply_markup=main_menu_kb())



@router.callback_query(F.data.startswith("rem_off:"))
async def reminders_off_callback(query: CallbackQuery, state: FSMContext) -> None:
    """
    Отключение напоминания по нажатию inline-кнопки «❌ Отключить».
    """
    try:
        rid = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer("Некорректный идентификатор напоминания.", show_alert=True)
        return

    tg_id = query.from_user.id
    user = get_user_by_telegram_id(tg_id)

    if not user:
        await query.answer("Ошибка: пользователь не найден.", show_alert=True)
        return

    reminders = get_user_reminders(user["id"])
    valid_ids = {r["id"] for r in reminders}

    if rid not in valid_ids:
        await query.answer("Это напоминание не найдено среди ваших.", show_alert=True)
        return

    deactivate_reminder(rid)
    await query.answer("Напоминание отключено ✔️")
    try:
        await query.message.edit_text(f"Напоминание #{rid} отключено.")
    except Exception:
        # Если не удалось отредактировать (например, слишком старое сообщение) — просто игнорируем
        pass
