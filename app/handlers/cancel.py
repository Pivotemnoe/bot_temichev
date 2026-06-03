from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.keyboards import main_menu_kb
from app.services.analytics import track_fsm_cancel
from app.system_texts import MAIN_MENU_TITLE
from app.ux import is_cancel_text


router = Router(name="cancel")


@router.message(Command("cancel"))
@router.message(F.text.func(is_cancel_text))
async def cancel_any_flow(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    track_fsm_cancel(message.from_user.id if message.from_user else None, current_state)
    await state.clear()
    prefix = "Текущий сценарий остановлен.\n\n" if current_state else ""
    await message.answer(prefix + MAIN_MENU_TITLE, reply_markup=main_menu_kb())
