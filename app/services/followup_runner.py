from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.db import ensure_default_subscription, get_due_followups, get_user_by_id, mark_followup_sent
from app.services.followup import followup_response_kb, render_followup_text
from app.services.analytics import EVENT_FOLLOWUP_SENT, track_event


logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60


async def run_followups_worker(bot: Bot) -> None:
    logger.info("[followups_worker] стартован")

    while True:
        try:
            due = get_due_followups(limit=20)
            logger.info("[followups_worker] tick due_count=%d", len(due))
            for item in due:
                await _process_single_followup(bot, item)
        except Exception as e:
            logger.exception("[followups_worker] ошибка: %r", e)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _process_single_followup(bot: Bot, item: dict) -> None:
    followup_id = int(item["id"])
    triage_event_id = item.get("triage_event_id")
    user_id = item.get("user_id")
    scenario = item.get("scenario") or "basic"
    chat_id = item.get("telegram_id")
    sub = ensure_default_subscription(int(user_id)) if user_id else {}
    plan_code = (sub or {}).get("plan_code") or (sub or {}).get("plan") or "free"
    user = get_user_by_id(int(user_id)) if user_id else {}
    clinic_id = (user or {}).get("clinic_id")

    logger.info(
        "[followups_worker] send_start followup_id=%s triage_event_id=%s user_id=%s scenario=%s",
        followup_id,
        triage_event_id,
        user_id,
        scenario,
    )

    if not chat_id:
        logger.warning("[followups_worker] followup_id=%s skipped: missing telegram_id", followup_id)
        return

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=render_followup_text(scenario, plan_code=plan_code, clinic_id=clinic_id),
            reply_markup=followup_response_kb(
                followup_id,
                scenario,
                plan_code=plan_code,
                clinic_id=clinic_id,
            ),
        )
    except Exception as e:
        logger.exception("[followups_worker] send_failed followup_id=%s error=%r", followup_id, e)
        return

    if mark_followup_sent(followup_id):
        track_event(
            int(user_id) if user_id else None,
            EVENT_FOLLOWUP_SENT,
            {
                "followup_id": followup_id,
                "triage_log_id": triage_event_id,
                "triage_event_id": triage_event_id,
                "scenario": scenario,
            },
        )
        logger.info("[followups_worker] sent followup_id=%s triage_event_id=%s", followup_id, triage_event_id)
    else:
        logger.warning("[followups_worker] sent_but_not_marked followup_id=%s", followup_id)
