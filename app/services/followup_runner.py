from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.db import get_due_followups, mark_followup_sent
from app.services.followup import followup_response_kb, render_followup_text


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
            text=render_followup_text(scenario),
            reply_markup=followup_response_kb(followup_id, scenario),
        )
    except Exception as e:
        logger.exception("[followups_worker] send_failed followup_id=%s error=%r", followup_id, e)
        return

    if mark_followup_sent(followup_id):
        logger.info("[followups_worker] sent followup_id=%s triage_event_id=%s", followup_id, triage_event_id)
    else:
        logger.warning("[followups_worker] sent_but_not_marked followup_id=%s", followup_id)
