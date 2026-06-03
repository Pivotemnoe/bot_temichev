# app/handlers/observations.py
from __future__ import annotations

import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from app.keyboards import main_menu_kb, choose_pet_kb, subscription_cta_inline_kb
from app.services.subscription_resolver import maybe_show_subscription_offer, get_offer_text
from app.services.subscription_limits import can_access_analytics
from app.db import get_user_by_telegram_id, get_pets_for_user, get_user_pets, ensure_default_subscription, get_subscription
from app.services.pet_observation_service import get_observations
from app.states import ObservationsStates
from app.observations_texts import OBS_PET_NOT_FOUND, OBS_SUBSCRIPTION_HINT, OBS_CANCEL_OK, OBS_CHOOSE_PET_FAIL
from app.services.subscription_resolver import maybe_show_subscription_offer, get_offer_text, DECISION_SOFT
from app.ux import is_cancel_text


logger = logging.getLogger(__name__)
router = Router()


def _pet_label(pet: dict) -> str:
    raw_type = (pet.get("pet_type") or "").strip()
    low = raw_type.lower()
    if low in ("cat", "кошка", "кот"):
        type_label = "Кошка"
    elif low in ("dog", "собака", "пес", "пёс"):
        type_label = "Собака"
    else:
        type_label = raw_type.capitalize() if raw_type else "Питомец"
    name = pet.get("pet_name") or "(без имени)"
    return f"{type_label} — {name}"


async def _render_observations(message: Message, user_id: int, pet: dict) -> None:
    rows = get_observations(pet_id=int(pet["id"]), limit=50)

    title = f"📊 Наблюдения — {_pet_label(pet)}"
    if not rows:
        await message.answer(
            f"{title}\n\n"
            "Пока здесь нет записей.\n"
            "Они появятся автоматически по мере использования бота.",
            reply_markup=main_menu_kb(),
        )
        return

    lines = [f"{title}\n"]
    for r in rows[:15]:
        t = r.get("type", "event")
        ts = (r.get("created_at") or "").strip()
        payload = r.get("payload") or {}

        if t == "triage":
            emoji = (payload.get("urgency_emoji") or "").strip()
            label = (payload.get("urgency_label") or "").strip()
            summary = (payload.get("summary") or "").strip()
            complaint = (payload.get("complaint") or "").strip()

            complaint_short = (complaint[:70] + "…") if len(complaint) > 70 else complaint
            summary_short = (summary[:90] + "…") if len(summary) > 90 else summary

            # Всегда показываем индикатор срочности:
            # если не удалось распарсить из ответа — показываем нейтральный ⚪
            if not emoji and (label or summary or complaint):
                emoji = "⚪"
            if not label and emoji == "⚪":
                label = "Без оценки"

            parts: list[str] = []
            if emoji:
                parts.append(emoji)
            if label:
                parts.append(label)
            if summary_short:
                parts.append(summary_short)
            elif complaint_short:
                parts.append(complaint_short)

            main = " — ".join([p for p in parts if p]) if parts else "triage"
            lines.append(f"• {main} ({ts})")        
            lines.append(f"• {t} — {ts}")

    await message.answer("\n".join(lines), reply_markup=main_menu_kb())


@router.message(F.text == "📊 Наблюдения")
async def observations_entry(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/observations.py:observations_entry user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await message.answer("Вы ещё не зарегистрированы. Сначала используйте /start.", reply_markup=main_menu_kb())
        return

    pets = get_pets_for_user(user["id"])
    if not pets:
        await message.answer(
            "📊 Наблюдения\n\n"
            "Сначала добавьте питомца в разделе «🐾 Питомцы», затем наблюдения начнут заполняться автоматически.",
            reply_markup=main_menu_kb(),
        )
        return

    if len(pets) == 1:
        await state.clear()
        await _render_observations(message, user_id=user["id"], pet=pets[0])
        decision = maybe_show_subscription_offer(user["id"], "OBSERVATIONS_OPENED", ctx={"pet_id": pets[0]["id"]})
        if decision == DECISION_SOFT:
            await message.answer(
                OBS_SUBSCRIPTION_HINT,
                reply_markup=main_menu_kb(),
            )
        return

    labels = [_pet_label(p) for p in pets]
    await state.update_data(obs_pets={_pet_label(p): p["id"] for p in pets})
    await state.set_state(ObservationsStates.choosing_pet)
    await message.answer("Выберите питомца, чтобы посмотреть наблюдения:", reply_markup=choose_pet_kb(labels))


async def open_observations_for_pet(message: Message, state: FSMContext, pet_id: int) -> None:
    """Открыть наблюдения сразу для выбранного питомца (используется из карточки питомца)."""
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer('Сначала зарегистрируйтесь через /start.', reply_markup=main_menu_kb())
        return

    sub = ensure_default_subscription(user['id'])
    plan = (sub or {}).get('plan') or (get_subscription(user['id']) or {}).get('plan') or 'free'
    if not can_access_analytics(plan):
        decision = maybe_show_subscription_offer(user_id=user['id'], event_type='ANALYTICS_OPENED', ctx={'source': 'menu', 'exceeds_free_limit': True})
        text = get_offer_text('ANALYTICS_OPENED', decision, {'source': 'menu'}) or '🔒 Аналитика доступна по подписке.'
        await message.answer(text, reply_markup=subscription_cta_inline_kb())
        return
    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start.", reply_markup=main_menu_kb())
        return

    pets = get_user_pets(user["id"])
    pet = next((p for p in pets if p["id"] == pet_id), None)
    if not pet:
        await message.answer("Питомец не найден.", reply_markup=main_menu_kb())
        return

    await state.clear()
    await state.update_data(pet_id=pet_id)

    # Используем внутренний рендерер, чтобы формат был единый.
    await _render_observations(message, user_id=user["id"], pet=pet)



@router.message(ObservationsStates.choosing_pet)
async def observations_choose_pet(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/observations.py:observations_choose_pet user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()
    if is_cancel_text(text):
        await message.answer(OBS_CANCEL_OK, reply_markup=main_menu_kb())
        await state.clear()
        return

    data = await state.get_data()
    mapping: dict = data.get("obs_pets") or {}
    pet_id = mapping.get(text)
    if not pet_id:
        await message.answer(OBS_CHOOSE_PET_FAIL)
        return

    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await message.answer("Вы ещё не зарегистрированы. Сначала используйте /start.", reply_markup=main_menu_kb())
        await state.clear()
        return

    pets = get_pets_for_user(user["id"])
    pet = next((p for p in pets if int(p["id"]) == int(pet_id)), None)
    if pet is None:
        await message.answer(OBS_PET_NOT_FOUND, reply_markup=main_menu_kb())
        await state.clear()
        return

    await state.clear()
    await _render_observations(message, user_id=user["id"], pet=pet)
    decision = maybe_show_subscription_offer(user["id"], "OBSERVATIONS_OPENED", ctx={"pet_id": pet["id"]})
    if decision == DECISION_SOFT:
        await message.answer(
            OBS_SUBSCRIPTION_HINT,
            reply_markup=main_menu_kb(),
        )

def _analytics_paywall_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Подписка", callback_data="open:subscription")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="open:main_menu")],
        ]
    )
