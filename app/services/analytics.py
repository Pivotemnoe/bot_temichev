from __future__ import annotations

import logging
from urllib.parse import parse_qs

from app.db import ensure_default_subscription, get_user_by_id, get_user_by_telegram_id, log_user_event
from app.prompts.selector import select_prompt_mode


logger = logging.getLogger(__name__)

EVENT_APP_START = "app_start"
EVENT_REGISTRATION_STARTED = "registration_started"
EVENT_USER_REGISTERED = "user_registered"
EVENT_TRIAGE_STARTED = "triage_started"
EVENT_TRIAGE_COMPLETED = "triage_completed"
EVENT_PAYWALL_SHOWN = "paywall_shown"
EVENT_PAY_CLICKED = "pay_clicked"
EVENT_PAYMENT_SUCCESS = "payment_success"
EVENT_FOLLOWUP_SCHEDULED = "followup_scheduled"
EVENT_FOLLOWUP_SENT = "followup_sent"
EVENT_FOLLOWUP_ANSWERED = "followup_answered"
EVENT_PET_CREATE_STARTED = "pet_create_started"
EVENT_PET_CREATED = "pet_created"
EVENT_PET_SET_MAIN = "pet_set_main"
EVENT_FOOD_SEARCH_STARTED = "food_search_started"
EVENT_FOOD_QUERY = "food_query"
EVENT_FOOD_COMPLEX_DISH = "food_complex_dish"
EVENT_FSM_CANCELLED = "fsm_cancelled"
EVENT_FSM_INVALID_INPUT = "fsm_invalid_input"

TRIAGE_EVENTS = {
    EVENT_TRIAGE_STARTED,
    EVENT_TRIAGE_COMPLETED,
    EVENT_FOLLOWUP_SCHEDULED,
    EVENT_FOLLOWUP_SENT,
    EVENT_FOLLOWUP_ANSWERED,
}


def prompt_mode_for_plan(plan_code: str | None) -> str:
    return select_prompt_mode(plan_code=plan_code, clinic_id=None)


def prompt_mode_for_context(
    plan_code: str | None,
    clinic_id: int | None = None,
    complaint_text: str | None = None,
) -> str:
    return select_prompt_mode(
        plan_code=plan_code,
        clinic_id=clinic_id,
        complaint_text=complaint_text,
    )


def parse_start_payload(raw: str | None) -> dict:
    """Parse Telegram deep-link payload into analytics fields."""
    value = (raw or "").strip()
    payload: dict = {
        "source_type": "direct",
        "clinic_id": None,
    }
    if not value:
        return payload

    payload["start_arg"] = value[:256]

    normalized = value.replace(";", "&").replace("__", "&")
    parsed = parse_qs(normalized, keep_blank_values=False)
    flat = {k: v[-1] for k, v in parsed.items() if v}

    for key in ("utm_source", "utm_campaign", "utm_content"):
        if flat.get(key):
            payload[key] = str(flat[key])[:128]

    clinic_raw = flat.get("clinic_id") or flat.get("clinic")
    if clinic_raw is None:
        for prefix in ("clinic_", "clinic-", "clinic"):
            if value.lower().startswith(prefix):
                clinic_raw = value[len(prefix) :]
                break
    if clinic_raw:
        try:
            payload["clinic_id"] = int(str(clinic_raw).strip())
        except ValueError:
            payload["clinic_id"] = None

    if payload.get("clinic_id") is not None:
        payload["source_type"] = "clinic_link"
    elif any(payload.get(k) for k in ("utm_source", "utm_campaign", "utm_content")):
        payload["source_type"] = "utm"
    elif value.lower() in {"promo", "channel", "from_channel"}:
        payload["source_type"] = "utm"
        payload.setdefault("utm_source", value.lower())

    return payload


def _standard_payload(user_id: int, event_type: str, payload: dict | None) -> dict:
    result = dict(payload or {})
    try:
        sub = ensure_default_subscription(int(user_id)) or {}
        plan_code = (sub.get("plan_code") or sub.get("plan") or "free")
    except Exception:
        plan_code = result.get("plan_code") or "free"

    result.setdefault("plan_code", plan_code)
    if result.get("clinic_id") is None:
        try:
            user = get_user_by_id(int(user_id)) or {}
            result["clinic_id"] = user.get("clinic_id")
        except Exception:
            result.setdefault("clinic_id", None)
    else:
        result.setdefault("clinic_id", None)

    if event_type in TRIAGE_EVENTS:
        result.setdefault(
            "prompt_mode",
            prompt_mode_for_context(
                plan_code,
                clinic_id=result.get("clinic_id"),
            ),
        )

    return result


def track_event(user_id: int | None, event_type: str, payload: dict | None = None) -> bool:
    """Best-effort analytics event writer; never breaks the user flow."""
    if not user_id:
        return False
    try:
        log_user_event(int(user_id), event_type, _standard_payload(int(user_id), event_type, payload))
        return True
    except Exception as e:
        logger.warning("Failed to track analytics event %s for user_id=%s: %s", event_type, user_id, e)
        return False


def track_event_by_telegram_id(
    telegram_id: int | None,
    event_type: str,
    payload: dict | None = None,
) -> bool:
    """Best-effort analytics writer when only Telegram id is available."""
    if not telegram_id:
        return False
    try:
        user = get_user_by_telegram_id(int(telegram_id))
    except Exception:
        user = None
    if not user:
        return False
    return track_event(int(user["id"]), event_type, payload)


def _state_name(state: str | None) -> str:
    value = str(state or "").strip()
    return value or "none"


def track_fsm_cancel(
    telegram_id: int | None,
    state: str | None,
    *,
    scenario: str | None = None,
    reason: str | None = None,
) -> bool:
    return track_event_by_telegram_id(
        telegram_id,
        EVENT_FSM_CANCELLED,
        {
            "state": _state_name(state),
            "scenario": scenario or _state_name(state).split(":", 1)[0],
            "reason": reason or "user_cancel",
        },
    )


def track_fsm_invalid_input(
    telegram_id: int | None,
    state: str | None,
    *,
    scenario: str | None = None,
    reason: str | None = None,
    text: str | None = None,
) -> bool:
    raw = (text or "").strip()
    payload = {
        "state": _state_name(state),
        "scenario": scenario or _state_name(state).split(":", 1)[0],
        "reason": reason or "invalid_input",
        "text_len": len(raw),
    }
    return track_event_by_telegram_id(telegram_id, EVENT_FSM_INVALID_INPUT, payload)
