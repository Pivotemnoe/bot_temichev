from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.db import ensure_default_subscription, get_followup_by_id, get_user_by_id, mark_followup_answered
from app.handlers.triage import start_triage_flow
from app.services.followup import render_followup_answer_text
from app.services.analytics import EVENT_FOLLOWUP_ANSWERED, track_event


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

    sub = ensure_default_subscription(int(followup["user_id"]))
    plan_code = (sub or {}).get("plan_code") or (sub or {}).get("plan") or "free"
    user = get_user_by_id(int(followup["user_id"])) or {}
    clinic_id = user.get("clinic_id")

    mark_followup_answered(followup_id, answer)
    track_event(
        int(followup.get("user_id")) if followup.get("user_id") else None,
        EVENT_FOLLOWUP_ANSWERED,
        {
            "followup_id": int(followup_id),
            "triage_log_id": followup.get("triage_event_id"),
            "triage_event_id": followup.get("triage_event_id"),
            "scenario": followup.get("scenario"),
            "answer_type": answer,
        },
    )
    logger.info(
        "[followup] answered followup_id=%s triage_event_id=%s answer=%s",
        followup_id,
        followup.get("triage_event_id"),
        answer,
    )

    await callback.answer()
    await callback.message.answer(
        render_followup_answer_text(
            followup.get("scenario"),
            answer,
            plan_code=plan_code,
            clinic_id=clinic_id,
        )
    )

    if answer == "retry":
        await start_triage_flow(callback.message, state, telegram_id=callback.from_user.id)
