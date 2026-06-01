# app/services/reminders_runner.py
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from aiogram import Bot

from app.db import (
    get_due_reminders,
    deactivate_reminder,
    shift_reminder_date,
    get_pet_by_id,
)

logger = logging.getLogger(__name__)

# Интервал опроса БД (в секундах)
CHECK_INTERVAL_SECONDS = 60


async def run_reminders_worker(bot: Bot) -> None:
    """
    Фоновый воркер напоминаний.

    Периодически:
      - выбирает из БД все напоминания, срок которых наступил (или просрочен),
      - отправляет пользователю уведомления,
      - для разовых помечает is_active = 0,
      - для периодических сдвигает due_date вперёд.
    """
    logger.info("[reminders_worker] стартован")

    while True:
        try:
            due_reminders = get_due_reminders()
            if due_reminders:
                logger.info(
                    "[reminders_worker] найдено %d напоминаний к отправке",
                    len(due_reminders),
                )

            for r in due_reminders:
                await _process_single_reminder(bot, r)

        except Exception as e:
            # Не даём воркеру упасть из-за одной ошибки
            logger.exception("[reminders_worker] ошибка: %r", e)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _process_single_reminder(bot: Bot, reminder: Dict) -> None:
    """
    Обработка одного напоминания.

    Ожидаемый формат reminder:
      - id
      - user_id
      - telegram_id
      - pet_id
      - reminder_type
      - title
      - due_date
      - due_time
      - periodicity
      - notes
    """
    reminder_id = reminder["id"]
    chat_id = reminder.get("telegram_id")
    if not chat_id:
        # Некорректное состояние данных: у пользователя нет telegram_id
        logger.warning(
            "[reminders_worker] reminder #%s: отсутствует telegram_id, пропускаю",
            reminder_id,
        )
        # Разовые всё равно деактивируем, чтобы не зацикливаться
        if reminder.get("periodicity") == "once":
            deactivate_reminder(reminder_id)
        return

    text = await _build_reminder_text(reminder)
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.exception(
            "[reminders_worker] ошибка при отправке reminder #%s: %r",
            reminder_id,
            e,
        )
        # Даже если отправка не удалась, не меняем due_date, чтобы повторить позже
        return

    periodicity = reminder.get("periodicity") or "once"
    if periodicity == "once":
        deactivate_reminder(reminder_id)
    else:
        shift_reminder_date(reminder_id, periodicity)


async def _build_reminder_text(reminder: Dict) -> str:
    """
    Формирование текста напоминания.
    Минимальный рабочий формат, без лишней логики.
    """
    reminder_type = reminder.get("reminder_type") or "custom"
    title = reminder.get("title") or "Напоминание"
    due_date = reminder.get("due_date") or "-"
    due_time = reminder.get("due_time") or None
    pet_id = reminder.get("pet_id")

    type_label = {
        "vaccine": "Прививка",
        "parasites": "Обработка от паразитов",
        "checkup": "Плановый осмотр",
        "diet": "Корм / диета",
        "custom": "Другое",
    }.get(reminder_type, "Напоминание")

    time_part = f" в {due_time}" if due_time else ""

    pet_line = ""
    if pet_id:
        try:
            pet = get_pet_by_id(pet_id)
        except Exception:
            pet = None
        if pet:
            pet_type = pet.get("pet_type") or ""
            pet_name = pet.get("pet_name") or "(без имени)"
            if pet_type == "cat":
                pet_label = f"🐱 {pet_name}"
            elif pet_type == "dog":
                pet_label = f"🐶 {pet_name}"
            else:
                pet_label = f"{pet_type} — {pet_name}"
            pet_line = f"\nПитомец: {pet_label}"

    lines: List[str] = [
        f"📅 {type_label}",
        f"Тема: {title}",
        f"Когда: {due_date}{time_part}",
    ]
    if pet_line:
        lines.append(pet_line)

    notes = reminder.get("notes")
    if notes:
        lines.append(f"\nЗаметка: {notes}")

    return "\n".join(lines)