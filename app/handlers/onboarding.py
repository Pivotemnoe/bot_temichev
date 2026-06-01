from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import get_main_pet_id, get_pets_for_user, get_user_by_telegram_id, set_main_pet
from app.handlers.triage import start_triage_flow
from app.keyboards import main_menu_kb, onb_step1_kb, onb_step2_kb, onb_step3_kb
from app.onboarding_texts import (
    DONE_BODY,
    DONE_TITLE,
    ONB_WELCOME,
    STEP1_BODY,
    STEP1_TITLE,
    STEP2_BODY,
    STEP2_TITLE,
    STEP3_BODY,
    STEP3_TITLE,
)
from app.pets_v2.create import start_create_pet_v2
from app.services.static_assets import send_static_photo


logger = logging.getLogger(__name__)
router = Router(name="onboarding")


def _step_text(title: str, body: str) -> str:
    return f"<b>{title}</b>\n\n{body}"


async def show_step1(message: Message) -> None:
    await send_static_photo(message, "onb_step1_add_pet.jpg")
    await message.answer(_step_text(STEP1_TITLE, STEP1_BODY), reply_markup=onb_step1_kb())


async def show_step2(message: Message, pets: list[dict] | None = None) -> None:
    user = get_user_by_telegram_id(message.chat.id)
    if not user:
        await message.answer("Сначала используйте /start.", reply_markup=main_menu_kb())
        return

    pets = pets if pets is not None else (get_pets_for_user(user["id"]) or [])
    if not pets:
        await show_step1(message)
        return

    await send_static_photo(message, "onb_step2_set_main.jpg")
    await message.answer(_step_text(STEP2_TITLE, STEP2_BODY), reply_markup=onb_step2_kb(pets))


async def show_step3(message: Message) -> None:
    await send_static_photo(message, "onb_step3_triage.jpg")
    await message.answer(_step_text(STEP3_TITLE, STEP3_BODY), reply_markup=onb_step3_kb())


async def onboarding_start(message: Message, state: FSMContext, telegram_id: int | None = None) -> None:
    tg_id = telegram_id or message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer("Сначала используйте /start, чтобы зарегистрироваться.", reply_markup=main_menu_kb())
        return

    await state.clear()
    pets = get_pets_for_user(user["id"]) or []
    await message.answer(ONB_WELCOME)
    if not pets:
        await show_step1(message)
        return

    if len(pets) > 1 and get_main_pet_id(user["id"]) is None:
        await show_step2(message, pets)
        return

    await show_step3(message)


async def maybe_show_onboarding_after_start(message: Message, state: FSMContext, user: dict) -> bool:
    pets = get_pets_for_user(user["id"]) or []
    if not pets:
        await show_step1(message)
        return True

    if len(pets) > 1 and get_main_pet_id(user["id"]) is None:
        await show_step2(message, pets)
        return True

    return False


@router.message(F.text.in_({"🚀 Быстрый старт", "🎯 Как пользоваться"}))
async def onboarding_from_menu(message: Message, state: FSMContext) -> None:
    logger.info("[HANDLER] app/handlers/onboarding.py:onboarding_from_menu user=%s", getattr(message.from_user, "id", None))
    await onboarding_start(message, state)


@router.callback_query(F.data == "onb:add_pet")
async def onb_add_pet(callback: CallbackQuery, state: FSMContext) -> None:
    await start_create_pet_v2(callback, state)


@router.callback_query(F.data.startswith("onb:set_main:"))
async def onb_set_main(callback: CallbackQuery) -> None:
    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Нажмите /start", show_alert=True)
        return

    try:
        pet_id = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer("Не удалось определить питомца.", show_alert=True)
        return

    if not set_main_pet(user["id"], pet_id):
        await callback.answer("Не удалось выбрать питомца.", show_alert=True)
        return

    await callback.answer("Основной питомец выбран")
    await callback.message.answer("✅ Основной питомец выбран.")
    await show_step3(callback.message)


@router.callback_query(F.data == "onb:skip_main")
async def onb_skip_main(callback: CallbackQuery) -> None:
    await callback.answer()
    await show_step3(callback.message)


@router.callback_query(F.data == "onb:start_triage")
async def onb_start_triage(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await start_triage_flow(callback.message, state, telegram_id=callback.from_user.id)


@router.callback_query(F.data == "onb:done")
async def onb_done(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(f"<b>{DONE_TITLE}</b>\n\n{DONE_BODY}", reply_markup=main_menu_kb())
