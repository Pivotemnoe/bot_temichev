# app/pets_v2/history.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

from app.db import (
    ensure_default_subscription,
    get_subscription,
    get_user_by_telegram_id,
    get_user_pets,
    get_pet_by_id,
    get_pet_history,
    count_pet_history,
)
from app.keyboards import main_menu_kb
from app.services.subscription_resolver import maybe_show_subscription_offer, get_offer_text
from app.services.subscription_limits import can_access_history
from app.services.paywall import send_plus_paywall_explained

router = Router(name="pets_v2_history")

PAGE_SIZE = 10

_FILTERS = {
    "all": None,
    "triage": ["triage"],
    "vacc": ["vaccination"],
    "rem": ["reminder"],
    "note": ["note"],
}

_FILTER_TITLES = {
    "all": "Все",
    "triage": "Триаж",
    "vacc": "Вакцинации",
    "rem": "Напоминания",
    "note": "Заметки",
}



def _paywall_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Подписка", callback_data="open:subscription")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="open:main_menu")],
        ]
    )


def _fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return value


def _render_event(event: dict) -> str:
    et = (event.get("event_type") or "").lower()
    icon = {
        "triage": "🩺",
        "vaccination": "💉",
        "reminder": "⏰",
        "note": "📝",
    }.get(et, "•")

    title = event.get("title") or ""
    details = event.get("details") or ""
    created_at = _fmt_dt(event.get("created_at"))
    line = f"{icon} <b>{created_at}</b>"
    if title:
        line += f" — {title}"
    if details:
        line += f"\n{details}"
    return line


def _kb(pet_id: int, offset: int, flt: str, total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    # filters
    rows.append(
        [
            InlineKeyboardButton(text="Все", callback_data=f"petcard:history:{pet_id}:0:all"),
            InlineKeyboardButton(text="🩺", callback_data=f"petcard:history:{pet_id}:0:triage"),
            InlineKeyboardButton(text="💉", callback_data=f"petcard:history:{pet_id}:0:vacc"),
            InlineKeyboardButton(text="⏰", callback_data=f"petcard:history:{pet_id}:0:rem"),
            InlineKeyboardButton(text="📝", callback_data=f"petcard:history:{pet_id}:0:note"),
        ]
    )

    # paging
    prev_offset = max(0, offset - PAGE_SIZE)
    next_offset = offset + PAGE_SIZE
    paging_row: list[InlineKeyboardButton] = []
    if offset > 0:
        paging_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"petcard:history:{pet_id}:{prev_offset}:{flt}",
            )
        )
    if next_offset < total:
        paging_row.append(
            InlineKeyboardButton(
                text="Показать ещё ➡️",
                callback_data=f"petcard:history:{pet_id}:{next_offset}:{flt}",
            )
        )
    if paging_row:
        rows.append(paging_row)

    rows.append([InlineKeyboardButton(text="⬅️ В карточку", callback_data=f"petcard:overview:{pet_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_history(message: Message, user_id: int, pet_id: int, offset: int = 0, flt: str = "all") -> None:
    pet = get_pet_by_id(pet_id)
    if not pet:
        await message.answer("Питомец не найден.", reply_markup=main_menu_kb())
        return

    pets = get_user_pets(user_id)
    pet_ids = {int(p.get("id")) for p in (pets or []) if p.get("id") is not None}
    if int(pet_id) not in pet_ids:
        await message.answer("Нет доступа к этому питомцу.", reply_markup=main_menu_kb())
        return

    event_types = _FILTERS.get(flt, None)
    total = count_pet_history(pet_id=pet_id, event_types=event_types)

    sub = ensure_default_subscription(user_id)
    plan = (sub or {}).get('plan') or (get_subscription(user_id) or {}).get('plan') or 'free'

    if not can_access_history(plan, total):
        decision = maybe_show_subscription_offer(
            user_id=user_id,
            event_type="HISTORY_OPENED",
            ctx={"pet_id": pet_id, "total": total, "filter": flt, "exceeds_free_limit": True},
        )
        text = get_offer_text("HISTORY_OPENED", decision, {"total": total}) or (
            "Полная история разборов доступна в Plus. В Free показываем последние 3 разбора."
        )
        await send_plus_paywall_explained(message, reason="history", reason_text=text)
        return

    events = get_pet_history(pet_id=pet_id, limit=PAGE_SIZE, offset=offset, event_types=event_types)

    pet_name = pet.get("name") or pet.get("pet_name") or "питомец"
    pet_type = pet.get("type") or pet.get("pet_type") or pet.get("pet_type_name") or ""
    flt_title = _FILTER_TITLES.get(flt, "Все")

    lines: list[str] = [f"📜 <b>История здоровья</b> — {pet_type} — <b>{pet_name}</b>", f"Фильтр: <b>{flt_title}</b>", ""]
    if not events:
        lines.append("Пока нет событий.")
    else:
        for ev in events:
            lines.append(_render_event(ev))
            lines.append("")

    await message.answer("\n".join(lines).strip(), reply_markup=_kb(pet_id, offset, flt, total))


@router.callback_query(F.data.startswith("petcard:history:"))
async def open_history(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    # petcard:history:<pet_id>[:<offset>:<flt>]
    try:
        pet_id = int(parts[2])
    except Exception:
        await callback.answer("Некорректный идентификатор питомца.", show_alert=True)
        return

    offset = 0
    flt = "all"
    if len(parts) >= 4:
        try:
            offset = int(parts[3])
        except Exception:
            offset = 0
    if len(parts) >= 5:
        flt = parts[4] or "all"

    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer("Сначала зарегистрируйтесь через /start.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    await _show_history(callback.message, int(user["id"]), pet_id, offset=offset, flt=flt)
    await callback.answer()
