from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.config import ADMIN_CHAT_ID, FEEDBACK_CHAT_ID
from app.db import (
    get_user_by_telegram_id,
    ensure_default_subscription,
    get_pets_for_user,
    create_feedback,
)
from app.keyboards import main_menu_kb
from app.texts import (
    HELP_TEXT,
    FEEDBACK_INTRO_TEXT,
    FEEDBACK_THANKS_TEXT,
    FEEDBACK_ADMIN_TEMPLATE,
)
from app.ux import BTN_MENU, is_cancel_text

logger = logging.getLogger(__name__)

router = Router()


class FeedbackStates(StatesGroup):
    """Состояния FSM для сценария обратной связи."""
    waiting_text = State()


def feedback_exit_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_MENU)]],
        resize_keyboard=True,
    )


def _get_user_plan_safe(telegram_id: int) -> str:
    """
    Аккуратно получить текущий тариф пользователя для служебных сообщений.
    Если пользователя/подписки нет — вернуть понятную строку.
    """
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        return "нет данных (пользователь не найден)"

    sub = ensure_default_subscription(user["id"])
    if not sub or not sub.get("plan"):
        return "нет данных (подписка не определена)"

    return str(sub["plan"])


def _format_pet_info(user_id: int | None) -> str:
    """
    Сформировать краткую строку о питомцах пользователя для служебных сообщений.
    """
    if not user_id:
        return "нет данных (пользователь не найден)"

    pets = get_pets_for_user(user_id)
    if not pets:
        return "нет данных (питомцы не добавлены)"

    parts: list[str] = []
    for pet in pets:
        name = pet.get("pet_name") or "без имени"
        species = pet.get("pet_type") or "питомец"
        parts.append(f"{name} ({species})")

    return ", ".join(parts)


# ===== /help и кнопка «ℹ️ О боте» =====


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """
    Текст «О боте».
    Использует HELP_TEXT из app.texts.
    """
    await message.answer(HELP_TEXT, reply_markup=main_menu_kb())


# ===== /feedback и кнопка «✉️ Обратная связь» =====


@router.message(Command("feedback"))
@router.message(F.text == "✉️ Обратная связь")
async def feedback_start(message: Message, state: FSMContext) -> None:
    """
    Запуск сценария обратной связи.
    Пользователь пишет один текст, мы сохраняем его в БД и отправляем в сервисный чат.
    """
    await state.set_state(FeedbackStates.waiting_text)
    await message.answer(FEEDBACK_INTRO_TEXT, reply_markup=feedback_exit_kb())


@router.message(FeedbackStates.waiting_text)
async def feedback_handle_text(message: Message, state: FSMContext) -> None:
    """
    Принимаем текст фидбэка, сохраняем его в таблицу feedback и отправляем в FEEDBACK_CHAT_ID.
    """
    text = (message.text or "").strip()
    if is_cancel_text(text):
        await state.clear()
        await message.answer(
            "Обратная связь отменена. Сообщение команде не отправлено.",
            reply_markup=main_menu_kb(),
        )
        return

    if not text:
        await message.answer(
            "Сообщение пустое. Пожалуйста, опишите, что вы хотите сообщить.",
            reply_markup=feedback_exit_kb(),
        )
        return

    tg_user = message.from_user
    if tg_user is None:
        # На всякий случай, но в обычном Telegram-сценарии такого не бывает
        await state.clear()
        await message.answer(FEEDBACK_THANKS_TEXT, reply_markup=main_menu_kb())
        return

    # Завершаем FSM, чтобы последующие сообщения не считались фидбеком
    await state.clear()

    # По возможности находим пользователя в нашей БД
    db_user = get_user_by_telegram_id(tg_user.id)
    user_id = db_user["id"] if db_user else None
    pet_info = _format_pet_info(user_id)
    plan = _get_user_plan_safe(tg_user.id)

    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime("%d.%m.%Y %H:%M UTC")

    # Сохраняем запись в таблицу feedback
    try:
        feedback_id = create_feedback(
            user_id=user_id,
            text=text,
            created_at=now_dt,
            category=None,
            can_reply=True,
        )
    except Exception as e:
        logger.error("Не удалось сохранить feedback в БД: %s", e)
        feedback_id = None

    # Служебное сообщение в чат разработчика / техподдержки
    username = f"@{tg_user.username}" if tg_user.username else "—"

    admin_text = FEEDBACK_ADMIN_TEMPLATE.format(
        user_id=tg_user.id,
        username=username,
        pet_info=pet_info,
        feedback_text=text,
        datetime=now_str,
    )

    # Добавим в конец тех.информацию (тариф и ID записи в feedback, если есть)
    admin_text += "\n\nТехническая информация:\n"
    admin_text += f"Тариф: {plan}\n"
    if feedback_id is not None:
        admin_text += f"ID записи feedback: {feedback_id}\n"

    sent_to_admin = False

    target_chat_id = FEEDBACK_CHAT_ID or ADMIN_CHAT_ID
    if target_chat_id:
        try:
            await message.bot.send_message(
             chat_id=target_chat_id,
             text=admin_text,
            # parse_mode="HTML",  # <-- УБРАТЬ ЭТУ СТРОКУ
        )

            sent_to_admin = True
        except Exception as e:
            logger.error("Не удалось отправить фидбек в сервисный чат %s: %s", target_chat_id, e)

    if not sent_to_admin:
        logger.warning(
            "Фидбек от пользователя %s не удалось отправить в сервисный чат. "
            "feedback_id=%s",
            tg_user.id,
            feedback_id,
        )

    await message.answer(
        FEEDBACK_THANKS_TEXT,
        reply_markup=main_menu_kb(),
    )
