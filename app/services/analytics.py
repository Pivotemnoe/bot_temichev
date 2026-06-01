from __future__ import annotations

import logging
from urllib.parse import parse_qs

from app.db import ensure_default_subscription, log_user_event


logger = logging.getLogger(__name__)

EVENT_APP_START = "app_start"
EVENT_TRIAGE_STARTED = "triage_started"
EVENT_TRIAGE_COMPLETED = "triage_completed"
EVENT_PAYWALL_SHOWN = "paywall_shown"
EVENT_PAY_CLICKED = "pay_clicked"
EVENT_PAYMENT_SUCCESS = "payment_success"
EVENT_FOLLOWUP_SCHEDULED = "followup_scheduled"
EVENT_FOLLOWUP_SENT = "followup_sent"
EVENT_FOLLOWUP_ANSWERED = "followup_answered"
EVENT_PET_CREATED = "pet_created"
EVENT_PET_SET_MAIN = "pet_set_main"

TRIAGE_EVENTS = {
    EVENT_TRIAGE_STARTED,
    EVENT_TRIAGE_COMPLETED,
    EVENT_FOLLOWUP_SCHEDULED,
    EVENT_FOLLOWUP_SENT,
    EVENT_FOLLOWUP_ANSWERED,
}


def prompt_mode_for_plan(plan_code: str | None) -> str:
    plan = (plan_code or "free").strip().lower()
    if plan in {"plus", "pro", "vip"}:
        return "plus_expert"
    return "base"


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
    result.setdefault("clinic_id", None)

    if event_type in TRIAGE_EVENTS:
        result.setdefault("prompt_mode", prompt_mode_for_plan(plan_code))

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
