from __future__ import annotations

import json
import os
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _clinic_contacts() -> dict[str, dict[str, Any]]:
    raw = (os.getenv("CLINIC_CONTACTS_JSON") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}

    result: dict[str, dict[str, Any]] = {}
    for key, value in parsed.items():
        if isinstance(value, dict):
            result[str(key)] = dict(value)
    return result


def get_clinic_profile(clinic_id: int | None) -> dict:
    if clinic_id is None:
        return {
            "id": None,
            "name": "TemichevVet",
            "linked": False,
            "phone": None,
            "address": None,
            "hours": None,
            "telegram": None,
        }

    data = _clinic_contacts().get(str(clinic_id), {})
    return {
        "id": int(clinic_id),
        "name": data.get("name") or "ваша клиника",
        "linked": True,
        "phone": data.get("phone"),
        "address": data.get("address"),
        "hours": data.get("hours"),
        "telegram": data.get("telegram"),
    }


def render_clinic_start_note(clinic_profile: dict) -> str:
    name = clinic_profile.get("name") or "ваша клиника"
    return (
        f"Вы открыли бот по ссылке клиники: <b>{name}</b>.\n\n"
        "Это официальный цифровой помощник клиники в Telegram: он помогает понять, "
        "насколько срочно состояние питомца, и при необходимости подготовиться к обращению."
    )


def render_clinic_screen(clinic_profile: dict) -> str:
    if clinic_profile.get("linked"):
        name = clinic_profile.get("name") or "ваша клиника"
        lines = [
            f"🏥 <b>{name}</b>",
            "",
            "Вы подключены к сервису вашей клиники.",
            "Я помогу оценить срочность состояния питомца и подготовить понятное описание для врача.",
            "",
            "Если ситуация выглядит срочной, не ждите ответа бота — свяжитесь с клиникой или езжайте на очный осмотр.",
        ]

        contact_lines: list[str] = []
        if clinic_profile.get("phone"):
            contact_lines.append(f"Телефон: {clinic_profile['phone']}")
        if clinic_profile.get("telegram"):
            contact_lines.append(f"Telegram: {clinic_profile['telegram']}")
        if clinic_profile.get("address"):
            contact_lines.append(f"Адрес: {clinic_profile['address']}")
        if clinic_profile.get("hours"):
            contact_lines.append(f"Режим работы: {clinic_profile['hours']}")
        if contact_lines:
            lines.extend(["", "<b>Контакты</b>", *contact_lines])

        return "\n".join(lines)

    return (
        "🏥 <b>Клиника</b>\n\n"
        "В боте пока нет карты клиник и автоматического подбора по адресу.\n\n"
        "Если у питомца тревожные признаки, лучше обратиться в ближайшую доступную ветеринарную клинику. "
        "Если вы получили ссылку от своей клиники, откройте бот именно по этой ссылке — тогда здесь появятся её контакты."
    )


def clinic_screen_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🩺 Разобрать жалобу", callback_data="clinic:start_triage")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="open:main_menu")],
        ]
    )
