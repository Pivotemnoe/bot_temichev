# app/handlers/menu.py

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.keyboards import main_menu_kb, subscription_kb
from app.db import (
    log_user_event,

    get_user_by_telegram_id,
    ensure_default_subscription,
    set_subscription_plan,
    get_subscription,
)
from app.texts import INVALID_INPUT_TEXT
from app.system_texts import MAIN_MENU_TITLE
from app.constants import SUBSCRIPTION_BUTTONS, SUBSCRIPTION_PLANS, build_subscription_text
from app.texts import PLAN_FREE_TEXT, PLAN_PLUS_TEMPLATE, PLAN_PRO_TEMPLATE, PLAN_VIP_TEMPLATE
from app.keyboards_reminders import reminders_menu_kb
from app.keyboards_knowledge import faq_menu_kb
from app.services.subscription_resolver import maybe_show_subscription_offer, DECISION_SOFT

logger = logging.getLogger(__name__)

router = Router()


# Тексты кнопок главного меню (и алиасы), которые НЕ должны перехватываться меню-фоллбеком.
MAIN_MENU_BUTTONS = (
    "🩺 Разобрать жалобу",
    "❤️ Здоровье",
    "📜 История здоровья",
    "📜 История по здоровью",
    "📊 Наблюдения",
    "🍽️ Питание",
    "❓ Вопросы и ответы",
    "❓ Вопрос–Ответ",
    "⏰ Напоминания",
    "📅 Напоминания и график",
    "🐾 Мои животные",
    "👤 Моя подписка",
    "🏥 Найти клинику",
    "ℹ️ О боте",
    "ℹ️ О боте",
    "✉️ Обратная связь",

    # Кнопки подменю (knowledge / reminders / pets / observations) — чтобы не ловил menu fallback
    "🔍 Найти продукт",
    "✅ Что можно",
    "⛔ Что нельзя",
    "📌 Популярные вопросы",
    "🔍 Найти ответ по вопросу",
    "📋 Карточки по уходу",
    "🔍 Найти по теме ухода",
    "➕ Добавить напоминание",
    "📋 Мои напоминания",
    "➕ Добавить питомца",
    "📋 Список питомцев",
    "✏️ Изменить питомца",
    "🗑️ Удалить питомца",
    "➕ Добавить наблюдение",
    "📄 Мои наблюдения",
    "🔍 Поиск по наблюдениям",

    "🧴 Уход и привычки",
    "⬅️ В главное меню",
    "📅 Напоминания",
    "📅 Напоминания",
    "🐾 Питомцы",
    "➕ Добавить животное",
)


@router.message(F.text == "⏰ Напоминания")
async def menu_schedule(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/menu.py:menu_schedule user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """
    Нажатие кнопки из главного меню.
    Открываем отдельное подменю напоминаний.
    """
    logger.warning(">>> MENU schedule TRIGGERED")
    await message.answer(
        "Раздел «Напоминания и график».\n"
        "Здесь можно создать напоминания о прививках, обработке от паразитов,\n"
        "плановых осмотрах и других важных событиях для питомца.",
        reply_markup=reminders_menu_kb(),
    )

@router.message(F.text.in_(("❓ Вопросы и ответы", "❓ Вопрос–Ответ")))
async def menu_faq(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:menu_faq user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """Раздел FAQ — вход в подменю вопросов и ответов."""
    await message.answer(
        "Раздел «Вопрос–Ответ».\n"
        "Здесь можно найти ответы на частые вопросы по здоровью, уходу и питанию,"
        " а также поискать по своей теме.",
        reply_markup=faq_menu_kb(),
    )


# ================= Моя подписка =================


@router.message(F.text == "👤 Моя подписка")
async def menu_subscription(message: Message, state: FSMContext):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:menu_subscription user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await message.answer(
            "Вы ещё не зарегистрированы. Сначала используйте /start.",
            reply_markup=main_menu_kb(),
        )
        return

    sub = ensure_default_subscription(user["id"])

    text = build_subscription_text(sub)

    data = await state.get_data()
    last_hash = data.get("subscription_last_hash")
    cur_hash = hash(text)
    if last_hash == cur_hash and data.get("last_screen") == "subscription":
        return
    await state.update_data(last_screen="subscription", subscription_last_hash=cur_hash)

    await message.answer(text, reply_markup=subscription_kb())


@router.message(F.text == "⬅️ В главное меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/menu.py:back_to_main_menu user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    await state.clear()
    user = get_user_by_telegram_id(message.from_user.id)
    if user:
        log_user_event(user["id"], "MENU_OPENED", {})
        decision = maybe_show_subscription_offer(user["id"], "RETENTION_CHECK", {})
        if decision == DECISION_SOFT:
            await message.answer(
                "💡 Подписка открывает доступ к расширенной истории и аналитике по питомцу.",
                reply_markup=subscription_kb(),
            )

    await message.answer(
        MAIN_MENU_TITLE,
        reply_markup=main_menu_kb(),
    )


# ================= Выбор тарифа по кнопке =================


@router.message(F.text.in_(list(SUBSCRIPTION_BUTTONS.keys())))
async def change_subscription_plan(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:change_subscription_plan user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await message.answer(
            "Вы ещё не зарегистрированы. Сначала используйте /start.",
            reply_markup=main_menu_kb(),
        )
        return

    button_text = (message.text or "").strip()
    plan_code = SUBSCRIPTION_BUTTONS.get(button_text)
    if plan_code is None:
        await message.answer(
            "Не удалось определить тариф. Попробуйте выбрать ещё раз.",
            reply_markup=subscription_kb(),
        )
        return

    set_subscription_plan(user["id"], plan_code)
    sub = get_subscription(user["id"])

    text = build_subscription_text(sub)

    await message.answer(text, reply_markup=subscription_kb())


# ================= Фоллбек — только для НЕ-команд =================


@router.message(StateFilter(None), F.text & ~F.text.regexp(r"^/") & ~F.text.in_(MAIN_MENU_BUTTONS))
async def fallback(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:fallback user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    logger.warning(">>> MENU fallback TRIGGERED, text=%r", message.text)
    await message.answer(
        INVALID_INPUT_TEXT,
        reply_markup=main_menu_kb(),
    )
