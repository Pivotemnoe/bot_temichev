from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import get_user_by_telegram_id
from app.handlers.triage import start_triage_flow
from app.keyboards import main_menu_kb
from app.services.clinic import clinic_screen_kb, get_clinic_profile, render_clinic_screen


router = Router(name="clinic")


async def _send_clinic_screen(message: Message, telegram_id: int) -> None:
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        await message.answer("Сначала нажмите /start, чтобы зарегистрироваться.", reply_markup=main_menu_kb())
        return

    profile = get_clinic_profile(user.get("clinic_id"))
    await message.answer(render_clinic_screen(profile), reply_markup=clinic_screen_kb())


@router.message(F.text == "🏥 Найти клинику")
async def clinic_menu(message: Message) -> None:
    await _send_clinic_screen(message, message.from_user.id)


@router.callback_query(F.data == "clinic:start_triage")
async def clinic_start_triage(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer()
    await start_triage_flow(callback.message, state, telegram_id=callback.from_user.id)
