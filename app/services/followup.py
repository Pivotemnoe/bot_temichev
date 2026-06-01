from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db import (
    add_triage_followup,
    get_followup_by_triage_event,
    get_pet_history,
    has_recent_followup_for_user,
)
from app.services.analytics import EVENT_FOLLOWUP_SCHEDULED, track_event


TRUST_PHRASE = "Этот ответ не заменяет очный осмотр ветеринарного врача"

FOLLOWUP_DELAYS = {
    "red": timedelta(hours=6),
    "yellow": timedelta(hours=12),
}

SCENARIO_TEXTS = {
    "postop": "Вы ранее обращались по состоянию питомца после операции.\nКак сейчас выглядит место операции и общее самочувствие?",
    "gi": "Вы ранее обращались по проблемам с пищеварением.\nКак сейчас состояние питомца?",
    "trauma": "Вы ранее обращались по поводу травмы или хромоты.\nЕсть ли улучшения в движении питомца?",
    "basic": "Вы ранее разбирали состояние питомца.\nКак он чувствует себя сейчас?",
}

ANSWER_TEXTS = {
    "better": "Хорошо. Продолжайте наблюдение и следуйте рекомендациям врача, если они были даны.",
    "same": "Продолжайте внимательно наблюдать. Если есть сомнения или состояние не улучшается — лучше показать питомца врачу.",
    "worse": "Ухудшение состояния — повод для очного осмотра. Рекомендуется обратиться в клинику как можно скорее.",
}

POSTOP_ANSWER_TEXTS = {
    "better": "Хорошо. Продолжайте наблюдение и следуйте рекомендациям врача, если они были даны.",
    "same": "В послеоперационный период важно внимательно наблюдать. Если есть сомнения — лучше показать питомца врачу.",
    "worse": "В послеоперационный период ухудшение состояния — повод для очного осмотра. Рекомендуется обратиться в клинику как можно скорее.",
}

PLUS_POSTOP_TEXT = (
    "Вы ранее обращались по состоянию питомца после операции.\n\n"
    "Подскажите, пожалуйста:\n"
    "– как сейчас выглядит место операции (сухо ли, есть ли покраснение или отёк)?\n"
    "– изменились ли аппетит и активность питомца?"
)

PLUS_POSTOP_ANSWER_TEXTS = {
    "better": "Это хороший признак.\nВ послеоперационный период продолжайте внимательное наблюдение.",
    "same": "В послеоперационный период любые изменения требуют внимания.\nЕсли сомнения сохраняются, плановый осмотр у врача будет полезен.",
    "worse": "Ухудшение состояния после операции — повод для очного осмотра.\nРекомендуется обратиться в клинику как можно скорее.",
}


def _is_plus_postop(plan_code: str | None, clinic_id: int | None, scenario: str | None) -> bool:
    return (
        (plan_code or "").strip().lower() == "plus"
        and clinic_id is None
        and (scenario or "").strip().lower() == "postop"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def detect_followup_scenario(triage_text: str | None, pet_history: list[dict] | None = None) -> str:
    text = " ".join(str(triage_text or "").lower().split())
    history = pet_history or []

    if any((item.get("event_type") or "").lower() == "post_op" for item in history):
        return "postop"

    postop_markers = (
        "операц",
        "после операции",
        "послеопера",
        "шов",
        "кастрац",
        "стерилизац",
        "наркоз",
    )
    gi_markers = ("рвота", "рвет", "рвёт", "понос", "диар", "жидкий стул", "отказ от корма", "не ест")
    trauma_markers = ("хромает", "хромота", "ушиб", "падение", "упал", "не наступает", "лапу", "травм")

    if any(marker in text for marker in postop_markers):
        return "postop"
    if any(marker in text for marker in gi_markers):
        return "gi"
    if any(marker in text for marker in trauma_markers):
        return "trauma"
    return "basic"


def create_followup_for_triage(
    *,
    triage_event_id: int | None,
    user_id: int,
    pet_id: int | None,
    urgency_level: str | None,
    complaint_text: str | None = None,
    response_summary: str | None = None,
) -> dict[str, Any]:
    if not triage_event_id:
        return {"created": False, "reason": "missing_triage_event_id"}

    urgency = (urgency_level or "").strip().lower()
    if urgency not in FOLLOWUP_DELAYS:
        return {"created": False, "reason": "urgency_not_followup"}

    existing = get_followup_by_triage_event(int(triage_event_id))
    if existing:
        return {"created": False, "reason": "already_exists", "followup_id": existing["id"]}

    since = (_utc_now() - timedelta(hours=24)).isoformat()
    if has_recent_followup_for_user(int(user_id), since):
        return {"created": False, "reason": "recent_followup"}

    pet_history = get_pet_history(int(pet_id), limit=20) if pet_id else []
    scenario = detect_followup_scenario(complaint_text, pet_history)
    scheduled_at = (_utc_now() + FOLLOWUP_DELAYS[urgency]).isoformat()
    followup_id = add_triage_followup(
        triage_event_id=int(triage_event_id),
        user_id=int(user_id),
        pet_id=int(pet_id) if pet_id else None,
        urgency_level=urgency,
        scenario=scenario,
        scheduled_at=scheduled_at,
        payload={
            "complaint": complaint_text,
            "summary": response_summary,
        },
    )
    if not followup_id:
        return {"created": False, "reason": "insert_conflict"}

    track_event(
        int(user_id),
        EVENT_FOLLOWUP_SCHEDULED,
        {
            "followup_id": int(followup_id),
            "triage_log_id": int(triage_event_id),
            "triage_event_id": int(triage_event_id),
            "pet_id": int(pet_id) if pet_id else None,
            "urgency_level": urgency,
            "scenario": scenario,
        },
    )

    return {
        "created": True,
        "reason": "scheduled",
        "followup_id": followup_id,
        "scenario": scenario,
        "scheduled_at": scheduled_at,
    }


def render_followup_text(
    scenario: str | None,
    *,
    plan_code: str | None = None,
    clinic_id: int | None = None,
) -> str:
    if _is_plus_postop(plan_code, clinic_id, scenario):
        return f"{PLUS_POSTOP_TEXT}\n\n{TRUST_PHRASE}."

    key = (scenario or "basic").strip().lower()
    text = SCENARIO_TEXTS.get(key, SCENARIO_TEXTS["basic"])
    return f"{text}\n\n{TRUST_PHRASE}."


def followup_response_kb(
    followup_id: int,
    scenario: str | None = None,
    *,
    plan_code: str | None = None,
    clinic_id: int | None = None,
) -> InlineKeyboardMarkup:
    if _is_plus_postop(plan_code, clinic_id, scenario):
        better = "👍 Всё спокойно"
        same = "➖ Есть изменения"
    elif (scenario or "").strip().lower() == "postop":
        better = "👍 Всё спокойно"
        same = "➖ Есть сомнения"
    else:
        better = "👍 Стало лучше"
        same = "➖ Без изменений"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=better, callback_data=f"fu:answer:{followup_id}:better"),
                InlineKeyboardButton(text=same, callback_data=f"fu:answer:{followup_id}:same"),
            ],
            [
                InlineKeyboardButton(text="👎 Стало хуже", callback_data=f"fu:answer:{followup_id}:worse"),
                InlineKeyboardButton(text="🩺 Разобрать заново", callback_data=f"fu:answer:{followup_id}:retry"),
            ],
        ]
    )


def render_followup_answer_text(
    scenario: str | None,
    answer: str,
    *,
    plan_code: str | None = None,
    clinic_id: int | None = None,
) -> str:
    if answer == "retry":
        return "Ок, начнём новый разбор."

    if _is_plus_postop(plan_code, clinic_id, scenario):
        source = PLUS_POSTOP_ANSWER_TEXTS
    else:
        source = POSTOP_ANSWER_TEXTS if (scenario or "").strip().lower() == "postop" else ANSWER_TEXTS
    text = source.get(answer, ANSWER_TEXTS["same"])
    return f"{text}\n\n{TRUST_PHRASE}."
