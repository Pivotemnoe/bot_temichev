# app/handlers/triage.py

from __future__ import annotations

import asyncio
import html
import re
import logging
from datetime import date
from typing import Dict, Optional

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.db import (
    get_user_by_telegram_id,
    get_pets_for_user,
    get_pet_by_id,
    try_consume_quota,
    ensure_default_subscription,
    log_triage_event,
    get_triage_history_for_user,
    add_pet_history_event,
)
from app.keyboards import main_menu_kb, choose_pet_kb, age_group_kb, duration_kb, subscription_kb, triage_done_kb
from app.llm_engine import call_triage_llm
from app.states import TriageStates
from app.triage_texts import (
    TRIAGE_SUBSCRIPTION_HINT,
    TRIAGE_HISTORY_EMPTY,
    TRIAGE_HISTORY_HEADER,
    TRIAGE_HISTORY_PET_FALLBACK,
    TRIAGE_START_NEED_USER,
    TRIAGE_START_NO_PETS,
    TRIAGE_START_INTRO,
    TRIAGE_CHOOSE_PET_INTRO,
    TRIAGE_CHOOSE_PET_FAIL,
    TRIAGE_ASK_AGE,
    TRIAGE_ASK_DURATION,
    TRIAGE_ASK_COMPLAINT,
    TRIAGE_EMPTY_COMPLAINT,
    TRIAGE_CANCELLED_BY_USER,
    TRIAGE_QUOTA_EXHAUSTED,
    TRIAGE_PROCESSING_TEXT,
    TRIAGE_ERROR_TEXT,
)

from app.services.subscription_resolver import maybe_show_subscription_offer, DECISION_SOFT
from app.services.pet_observation_service import add_observation
from app.services.static_assets import send_static_photo
from app.services.paywall import send_plus_paywall_explained
from app.services.followup import create_followup_for_triage
from app.services.medical_safety import detect_red_flags, render_red_flag_response
from app.services.analytics import (
    EVENT_TRIAGE_COMPLETED,
    EVENT_TRIAGE_STARTED,
    prompt_mode_for_context,
    track_event,
    track_fsm_cancel,
    track_fsm_invalid_input,
)
from app.ux import WHAT_NEXT_TEXT, is_cancel_text



logger = logging.getLogger(__name__)
router = Router()

TRUST_PHRASE = "Этот ответ не заменяет очный осмотр ветеринарного врача"


URGENCY_EMOJI_TO_LEVEL = {
    "🟢": "green",
    "🟡": "yellow",
    "🟥": "red",
    "🔴": "red",
}


def _extract_urgency(response_text: str) -> tuple[str | None, str | None]:
    """Try to extract urgency emoji and label from LLM response.

    Supports patterns:
    - 'Уровень срочности: 🟢 ...'
    - 'Срочность: 🟡 ...'
    - with optional numbering like '2) Уровень срочности: ...'
    """
    if not response_text:
        return None, None

    # 1) Primary patterns
    m = re.search(
        r"(?:^|\n)\s*(?:\d+\)\s*)?(?:Уровень\s+срочности|Срочность)\s*:\s*([🟢🟡🟥🔴])\s*([^\n\r]+)",
        response_text,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1), m.group(2).strip()

    # 2) Fallback: any of the emojis at start of a line followed by text
    m = re.search(r"(?:^|\n)\s*([🟢🟡🟥🔴])\s*([^\n\r]{3,})", response_text)
    if m:
        return m.group(1), m.group(2).strip()

    return None, None


def _urgency_level_from_emoji(emoji: str | None) -> str | None:
    if not emoji:
        return None
    return URGENCY_EMOJI_TO_LEVEL.get(emoji)


def _normalize_summary(text: str | None, limit: int = 160) -> str | None:
    if not text:
        return None
    value = " ".join(str(text).split())
    value = re.sub(r"^\d+\)\s*", "", value)
    value = re.sub(r"^Кратко\s*:\s*", "", value, flags=re.IGNORECASE)
    value = value.strip()
    if not value:
        return None
    if len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def _extract_short_summary(response_text: str) -> str | None:
    """Extract a short summary (1-liner) from the LLM response.

    Prefer the 'Кратко:' section, otherwise take the first non-empty line.
    """
    if not response_text:
        return None

    m = re.search(r"(?:^|\n)\s*(?:\d+\)\s*)?Кратко\s*:\s*([^\n\r]+)", response_text, flags=re.IGNORECASE)
    if m:
        return _normalize_summary(m.group(1))

    for line in response_text.splitlines():
        line = line.strip()
        if line:
            return _normalize_summary(line)
    return None


def _ensure_trust_phrase(response_text: str) -> str:
    text = (response_text or "").strip()
    if TRUST_PHRASE.lower() in text.lower():
        return text
    return f"{text}\n\n{TRUST_PHRASE}." if text else f"{TRUST_PHRASE}."


def _pet_label(pet: Dict) -> str:
    raw_type = (pet.get("pet_type") or "").strip().lower()
    name = (pet.get("pet_name") or "").strip() or "(без имени)"
    if "кот" in raw_type or "кошка" in raw_type or raw_type == "cat":
        t = "🐱 Кошка"
    elif "соб" in raw_type or raw_type == "dog":
        t = "🐶 Собака"
    else:
        t = pet.get("pet_type") or "Питомец"
    return f"{t} — {name}"


def _is_cancel(text: str) -> bool:
    return is_cancel_text(text)


def _triage_start_payload(user: dict, pet_id: int) -> dict:
    sub = ensure_default_subscription(int(user["id"])) or {}
    plan_code = sub.get("plan_code") or sub.get("plan") or "free"
    clinic_id = user.get("clinic_id")
    return {
        "pet_id": int(pet_id),
        "plan_code": plan_code,
        "clinic_id": clinic_id,
        "prompt_mode": prompt_mode_for_context(plan_code, clinic_id=clinic_id),
    }


def _plural_ru(value: int, one: str, few: str, many: str) -> str:
    value_abs = abs(int(value))
    if 11 <= value_abs % 100 <= 14:
        return many
    if value_abs % 10 == 1:
        return one
    if 2 <= value_abs % 10 <= 4:
        return few
    return many


def _pet_age_months_from_card(pet: Dict | None, today: date | None = None) -> int | None:
    if not pet:
        return None
    birth_year = pet.get("birth_year")
    if not birth_year:
        return None
    try:
        year = int(birth_year)
        month = int(pet.get("birth_month") or 1)
        day = int(pet.get("birth_day") or 1)
        birth_date = date(year, month, day)
    except (TypeError, ValueError):
        return None

    current = today or date.today()
    if birth_date > current:
        return None

    months = (current.year - birth_date.year) * 12 + (current.month - birth_date.month)
    if current.day < birth_date.day:
        months -= 1
    return max(months, 0)


def _age_display_from_months(months: int) -> str:
    months = max(int(months), 0)
    years = months // 12
    rest_months = months % 12
    if years <= 0:
        return f"{months} {_plural_ru(months, 'месяц', 'месяца', 'месяцев')}"
    year_text = f"{years} {_plural_ru(years, 'год', 'года', 'лет')}"
    if rest_months and years < 2:
        month_text = f"{rest_months} {_plural_ru(rest_months, 'месяц', 'месяца', 'месяцев')}"
        return f"{year_text} {month_text}"
    return year_text


def _age_group_from_months(months: int) -> str:
    if months < 12:
        return "До 1 года (котёнок/щенок)"
    if months <= 84:
        return "1–7 лет (взрослый)"
    return "Старше 7 лет (возрастной)"


def _pet_age_context_from_card(pet: Dict | None, today: date | None = None) -> dict | None:
    months = _pet_age_months_from_card(pet, today=today)
    if months is None:
        return None
    age_display = _age_display_from_months(months)
    age_group = _age_group_from_months(months)
    return {
        "age_info": f"{age_group}; из карточки питомца: {age_display}",
        "age_display": age_display,
        "age_group": age_group,
    }


async def _ask_duration_or_age_from_pet(message: Message, state: FSMContext, pet: Dict | None) -> None:
    age_context = _pet_age_context_from_card(pet)
    if age_context:
        await state.update_data(
            age_info=age_context["age_info"],
            age_source="pet_card",
        )
        await message.answer(
            f"Возраст взял из карточки питомца: {age_context['age_display']}.\n\n{TRIAGE_ASK_DURATION}",
            reply_markup=duration_kb(),
        )
        await state.set_state(TriageStates.asking_duration)
        return

    await message.answer(TRIAGE_ASK_AGE, reply_markup=age_group_kb())
    await state.set_state(TriageStates.asking_age)


def _record_red_flag_triage(
    *,
    user: dict,
    pet_id: int | None,
    complaint_text: str,
    response_text: str,
    quota_used: int,
    plan_code: str,
    clinic_id: int | None,
    matched_red_flags: tuple[str, ...],
) -> int | None:
    summary = "Красные симптомы: " + ", ".join(matched_red_flags)
    triage_log_id = None
    try:
        triage_log_id = log_triage_event(
            user_id=int(user["id"]),
            pet_id=int(pet_id) if pet_id else None,
            complaint_text=complaint_text,
            response_text=response_text,
            quota_before=quota_used,
            quota_after=quota_used,
            urgency_level="red",
        )
    except Exception as e:
        logger.warning("Failed to log pre-LLM red-flag triage: %s", e)

    if triage_log_id:
        track_event(
            int(user["id"]),
            EVENT_TRIAGE_COMPLETED,
            {
                "pet_id": int(pet_id) if pet_id else None,
                "urgency_level": "red",
                "triage_log_id": int(triage_log_id),
                "plan_code": plan_code,
                "clinic_id": clinic_id,
                "prompt_mode": prompt_mode_for_context(plan_code, clinic_id=clinic_id, complaint_text=complaint_text),
                "medical_safety": "red_flag_pre_llm",
                "matched_red_flags": list(matched_red_flags),
            },
        )

    try:
        followup_result = create_followup_for_triage(
            triage_event_id=triage_log_id,
            user_id=int(user["id"]),
            pet_id=int(pet_id) if pet_id else None,
            urgency_level="red",
            complaint_text=complaint_text,
            response_summary=summary,
        )
        logger.info(
            "pre_llm_red_flag_followup_%s triage_event_id=%s reason=%s scenario=%s",
            "scheduled" if followup_result.get("created") else "skipped",
            triage_log_id,
            followup_result.get("reason"),
            followup_result.get("scenario"),
        )
    except Exception as e:
        logger.warning("Failed to schedule pre-LLM red-flag follow-up: %s", e)

    if pet_id:
        try:
            add_observation(
                user_id=int(user["id"]),
                pet_id=int(pet_id),
                obs_type="triage",
                payload={
                    "urgency_emoji": "🟥",
                    "urgency_label": "Срочно в клинику",
                    "urgency_level": "red",
                    "complaint": complaint_text,
                    "summary": summary,
                    "triage_id": triage_log_id,
                    "medical_safety": "red_flag_pre_llm",
                    "matched_red_flags": list(matched_red_flags),
                },
                source="triage",
            )
        except Exception as e:
            logger.warning("Failed to add pre-LLM red-flag observation: %s", e)

        try:
            add_pet_history_event(
                pet_id=int(pet_id),
                event_type="triage",
                title="🟥 Срочно в клинику",
                details=summary,
                triage_id=triage_log_id,
                metadata={
                    "complaint": complaint_text,
                    "summary": summary,
                    "urgency_emoji": "🟥",
                    "urgency_label": "Срочно в клинику",
                    "urgency_level": "red",
                    "medical_safety": "red_flag_pre_llm",
                    "matched_red_flags": list(matched_red_flags),
                },
            )
        except Exception as e:
            logger.warning("Failed to add pre-LLM red-flag history event: %s", e)

    return triage_log_id


async def start_triage_flow(message: Message, state: FSMContext, telegram_id: int | None = None) -> None:
    """Start triage for a Telegram user, usable from message and callback flows."""
    tg_id = telegram_id or message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        await message.answer(TRIAGE_START_NEED_USER, reply_markup=main_menu_kb())
        return

    pets = get_pets_for_user(user["id"])
    if not pets:
        await message.answer(TRIAGE_START_NO_PETS, reply_markup=main_menu_kb())
        return

    await state.clear()
    await send_static_photo(message, "triage_banner.jpg")

    # Если питомец один — пропускаем выбор.
    if len(pets) == 1:
        pet = pets[0]
        await state.update_data(pet_id=int(pet["id"]))
        track_event(user["id"], EVENT_TRIAGE_STARTED, _triage_start_payload(user, int(pet["id"])))
        await message.answer(TRIAGE_START_INTRO)
        await _ask_duration_or_age_from_pet(message, state, pet)
        return

    labels = [_pet_label(p) for p in pets]
    await state.update_data(
        triage_pet_map={labels[i]: int(pets[i]["id"]) for i in range(len(pets))}
    )

    await message.answer(TRIAGE_START_INTRO)
    await message.answer(TRIAGE_CHOOSE_PET_INTRO, reply_markup=choose_pet_kb(labels))
    await state.set_state(TriageStates.choosing_pet)


@router.message(F.text.in_(("❤️ Здоровье", "🩺 Разобрать жалобу")))
async def triage_entry(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/triage.py:triage_entry user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """Вход в triage."""
    await start_triage_flow(message, state)


@router.message(TriageStates.choosing_pet)
async def triage_choose_pet(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/triage.py:triage_choose_pet user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()
    if _is_cancel(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="triage")
        await message.answer(TRIAGE_CANCELLED_BY_USER, reply_markup=main_menu_kb())
        await state.clear()
        return

    data = await state.get_data()
    mapping: Dict[str, int] = data.get("triage_pet_map") or {}
    pet_id = mapping.get(text)

    if not pet_id:
        track_fsm_invalid_input(
            message.from_user.id,
            await state.get_state(),
            scenario="triage",
            reason="unknown_pet_choice",
            text=text,
        )
        await message.answer(TRIAGE_CHOOSE_PET_FAIL)
        return

    await state.update_data(pet_id=int(pet_id))
    user = get_user_by_telegram_id(message.from_user.id)
    if user:
        track_event(user["id"], EVENT_TRIAGE_STARTED, _triage_start_payload(user, int(pet_id)))
    await _ask_duration_or_age_from_pet(message, state, get_pet_by_id(int(pet_id)))


@router.message(TriageStates.asking_age)
async def triage_ask_age(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/triage.py:triage_ask_age user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()
    if _is_cancel(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="triage")
        await message.answer(TRIAGE_CANCELLED_BY_USER, reply_markup=main_menu_kb())
        await state.clear()
        return

    # Разрешаем пользовательский ввод, но кнопки — предпочтительны.
    await state.update_data(age_info=text)
    await message.answer(TRIAGE_ASK_DURATION, reply_markup=duration_kb())
    await state.set_state(TriageStates.asking_duration)


@router.message(TriageStates.asking_duration)
async def triage_ask_duration(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/triage.py:triage_ask_duration user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()
    if _is_cancel(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="triage")
        await message.answer(TRIAGE_CANCELLED_BY_USER, reply_markup=main_menu_kb())
        await state.clear()
        return

    await state.update_data(duration_info=text)
    await message.answer(TRIAGE_ASK_COMPLAINT, reply_markup=None)
    await state.set_state(TriageStates.waiting_for_complaint)


@router.message(TriageStates.waiting_for_complaint)
async def triage_get_complaint(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/triage.py:triage_get_complaint user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()
    if _is_cancel(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="triage")
        await message.answer(TRIAGE_CANCELLED_BY_USER, reply_markup=main_menu_kb())
        await state.clear()
        return

    if not text:
        track_fsm_invalid_input(
            message.from_user.id,
            await state.get_state(),
            scenario="triage",
            reason="empty_complaint",
            text=text,
        )
        await message.answer(TRIAGE_EMPTY_COMPLAINT)
        return

    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(TRIAGE_START_NEED_USER, reply_markup=main_menu_kb())
        await state.clear()
        return

    data = await state.get_data()
    pet_id = data.get("pet_id")
    age_info = data.get("age_info")
    duration_info = data.get("duration_info")

    pets = get_pets_for_user(user["id"])
    main_pet: Optional[Dict] = get_pet_by_id(int(pet_id)) if pet_id else None

    red_flags = detect_red_flags(text)
    if red_flags.has_red_flags:
        sub = ensure_default_subscription(int(user["id"])) or {}
        quota_used = int(sub.get("quota_used", 0) or 0)
        plan_code = sub.get("plan_code") or sub.get("plan") or "free"
        clinic_id = user.get("clinic_id")
        response_text = render_red_flag_response(red_flags)
        _record_red_flag_triage(
            user=user,
            pet_id=int(pet_id) if pet_id else None,
            complaint_text=text,
            response_text=response_text,
            quota_used=quota_used,
            plan_code=plan_code,
            clinic_id=clinic_id,
            matched_red_flags=red_flags.matched,
        )
        await message.answer(response_text, reply_markup=main_menu_kb())
        if pet_id:
            await message.answer("Событие сохранено в историю питомца.")
        await state.clear()
        return

    ok, sub = try_consume_quota(user["id"], amount=1)
    if not ok:
        await send_plus_paywall_explained(message, reason="limit", reason_text=TRIAGE_QUOTA_EXHAUSTED)
        await state.clear()
        return

    quota_before = int(sub.get("quota_used", 0)) - 1
    quota_after = int(sub.get("quota_used", 0))
    plan_code = sub.get("plan_code") or sub.get("plan") or "free"
    clinic_id = user.get("clinic_id")

    await message.answer(TRIAGE_PROCESSING_TEXT)

    try:
        response_text = await asyncio.to_thread(
            call_triage_llm,
            user=user,
            pets=pets,
            complaint_text=text,
            main_pet=main_pet,
            age_info=age_info,
            duration_info=duration_info,
            plan_code=(sub.get("plan_code") or sub.get("plan") or "free"),
            clinic_id=clinic_id,
        )
    except (TimeoutError, asyncio.TimeoutError) as e:
        logger.warning("Triage LLM timeout: %s", e)
        await message.answer(
            "Ответ задерживается из‑за нагрузки или проблем сети.\n\n"
            "Попробуйте ещё раз через минуту или опишите жалобу короче.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return
    except Exception as e:
        logger.exception("Triage LLM failed: %s", e)
        await message.answer(TRIAGE_ERROR_TEXT, reply_markup=main_menu_kb())
        await state.clear()
        return

    response_text = _ensure_trust_phrase(response_text)
    urgency_emoji, urgency_label = _extract_urgency(response_text)
    urgency_level = _urgency_level_from_emoji(urgency_emoji)
    summary = _extract_short_summary(response_text) or _normalize_summary(text)
    triage_log_id = None

    # Лог в БД + мягкий paywall (если подходит сценарий)
    try:
        triage_log_id = log_triage_event(
            user_id=int(user["id"]),
            pet_id=int(pet_id) if pet_id else None,
            complaint_text=text,
            response_text=response_text,
            quota_before=quota_before,
            quota_after=quota_after,
            urgency_level=urgency_level,
        )
    except Exception as e:
        logger.warning("Failed to log triage: %s", e)

    if triage_log_id:
        track_event(
            int(user["id"]),
            EVENT_TRIAGE_COMPLETED,
            {
                "pet_id": int(pet_id) if pet_id else None,
                "urgency_level": urgency_level or "unknown",
                "triage_log_id": int(triage_log_id),
                "plan_code": plan_code,
                "clinic_id": clinic_id,
                "prompt_mode": prompt_mode_for_context(plan_code, clinic_id=clinic_id, complaint_text=text),
            },
        )

    try:
        followup_result = create_followup_for_triage(
            triage_event_id=triage_log_id,
            user_id=int(user["id"]),
            pet_id=int(pet_id) if pet_id else None,
            urgency_level=urgency_level,
            complaint_text=text,
            response_summary=summary,
        )
        logger.info(
            "followup_%s triage_event_id=%s reason=%s scenario=%s",
            "scheduled" if followup_result.get("created") else "skipped",
            triage_log_id,
            followup_result.get("reason"),
            followup_result.get("scenario"),
        )
    except Exception as e:
        logger.warning("Failed to schedule follow-up: %s", e)

    try:
        decision = maybe_show_subscription_offer(
            int(user["id"]),
            "TRIAGE_COMPLETED",
            ctx={"pet_id": int(pet_id)} if pet_id else {},
        )
    except Exception:
        decision = None

    # LLM может вернуть строки с символами '<' и '>' (например '<24'), что ломает HTML parse_mode в Telegram.
    # Поэтому экранируем ответ перед отправкой.
    safe_response_text = html.escape(response_text)
    await message.answer(safe_response_text, reply_markup=main_menu_kb())
    if pet_id:
        await message.answer(
            "Разбор сохранён в историю питомца.\n\n" + WHAT_NEXT_TEXT,
            reply_markup=triage_done_kb(int(pet_id)),
        )

    # Записываем событие triage в наблюдения (короткое резюме для ленты)
    if pet_id:
        try:
            add_observation(
                user_id=int(user["id"]),
                pet_id=int(pet_id),
                obs_type="triage",
                payload={
                    "urgency_emoji": urgency_emoji,
                    "urgency_label": urgency_label,
                    "urgency_level": urgency_level,
                    "complaint": text,
                    "summary": summary,
                    "triage_id": triage_log_id,
                },
                source="triage",
            )
        except Exception as e:
            logger.warning("Failed to add triage observation: %s", e)

    # Записываем triage также в единую историю питомца
    if pet_id:
        try:
            title_parts = [part for part in (urgency_emoji, urgency_label) if part]
            add_pet_history_event(
                pet_id=int(pet_id),
                event_type="triage",
                title=" ".join(title_parts) if title_parts else "Разбор жалобы",
                details=summary or None,
                triage_id=triage_log_id,
                metadata={
                    "complaint": text,
                    "summary": summary,
                    "urgency_emoji": urgency_emoji,
                    "urgency_label": urgency_label,
                    "urgency_level": urgency_level,
                },
            )
        except Exception as e:
            logger.warning("Failed to add triage history event: %s", e)



    if decision == DECISION_SOFT:
        await message.answer(
            TRIAGE_SUBSCRIPTION_HINT,
            reply_markup=subscription_kb(),
        )

    await state.clear()


@router.message(F.text.in_(("📜 История здоровья", "📜 История по здоровью")))
async def triage_history(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/triage.py:triage_history user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """Краткая история triage (последние записи)."""
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(TRIAGE_START_NEED_USER, reply_markup=main_menu_kb())
        return

    items = get_triage_history_for_user(user["id"], limit=10)
    if not items:
        await message.answer(
            TRIAGE_HISTORY_EMPTY,
            reply_markup=main_menu_kb(),
        )
        return

    lines = [TRIAGE_HISTORY_HEADER, ""]
    pets = {int(p["id"]): p for p in get_pets_for_user(user["id"])}
    for it in items:
        created = (it.get("created_at") or "").strip()
        pet_id = it.get("pet_id")
        pet = pets.get(int(pet_id)) if pet_id is not None else None
        pet_name = _pet_label(pet) if pet else TRIAGE_HISTORY_PET_FALLBACK
        complaint = (it.get("complaint_text") or "").strip()
        lines.append(f"🗓 <b>{html.escape(created)}</b>")
        lines.append(f"🐾 <b>{html.escape(pet_name)}</b>")
        lines.append(f"📝 {html.escape(complaint[:240])}")
        lines.append("—" * 18)

    await message.answer("\n".join(lines), reply_markup=main_menu_kb())
    await state.clear()
