from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.db import get_followup_by_id, mark_followup_answered
from app.handlers.triage import start_triage_flow
from app.services.followup import render_followup_answer_text


logger = logging.getLogger(__name__)
router = Router(name="followup")


@router.callback_query(F.data.startswith("fu:answer:"))
async def followup_answer(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Некорректный ответ.", show_alert=True)
        return

    try:
        followup_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный follow-up.", show_alert=True)
        return

    answer = parts[3]
    followup = get_followup_by_id(followup_id)
    if not followup:
        await callback.answer("Follow-up не найден.", show_alert=True)
        return

    mark_followup_answered(followup_id, answer)
    logger.info(
        "[followup] answered followup_id=%s triage_event_id=%s answer=%s",
        followup_id,
        followup.get("triage_event_id"),
        answer,
    )

    await callback.answer()
    await callback.message.answer(render_followup_answer_text(followup.get("scenario"), answer))

    if answer == "retry":
        await start_triage_flow(callback.message, state, telegram_id=callback.from_user.id)
