# app/services/subscription_resolver.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict

from app.db import (
    ensure_default_subscription,
    get_subscription,
    mark_offer_shown,
    last_offer_shown_at,
    get_connection,
)

DECISION_NONE = "none"
DECISION_SOFT = "soft"
DECISION_HARD = "hard"

def get_offer_text(event_type: str, decision: str, ctx: Optional[Dict[str, Any]] = None) -> str:
    """Return human-readable copy for offers/paywalls."""
    ctx = ctx or {}
    if event_type == "TRIAGE_COMPLETED" and decision == DECISION_SOFT:
        return (
            "✨ Хотите больше пользы от триажа?\n"
            "В подписке: история обращений, аналитика наблюдений и расширенные рекомендации."
        )
    if event_type == "HISTORY_OPENED":
        if decision == DECISION_HARD:
            return (
                "🔒 Полная история здоровья доступна по подписке.\n"
                "На бесплатном плане есть лимит записей. Оформите подписку для полного доступа."
            )
        return "🔒 История здоровья доступна по подписке."
    if event_type == "ANALYTICS_OPENED":
        if decision == DECISION_HARD:
            return (
                "🔒 Аналитика и наблюдения доступны по подписке.\n"
                "Оформите подписку, чтобы открыть раздел и получать инсайты."
            )
        return "🔒 Аналитика доступна по подписке."
    if event_type == "RETENTION_CHECK" and decision == DECISION_SOFT:
        return "💡 Напоминание: в подписке доступны аналитика, история и расширенные сценарии ухода."
    if event_type == "SUBSCRIPTION_PAGE_OPENED" and decision == DECISION_SOFT:
        return "💳 Выберите тариф, чтобы открыть полный функционал."
    return ""



def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(dt_str: str) -> datetime:
    # DB uses _utc_now_iso() like 'YYYY-MM-DDTHH:MM:SSZ'
    # tolerate 'Z' and '+00:00'
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _is_paid(user_id: int) -> bool:
    sub = ensure_default_subscription(user_id)
    plan = (sub or {}).get("plan_code") or (sub or {}).get("plan") or "free"
    return str(plan).lower() not in {"free", "trial", "basic"}


def _triage_count_for_pet(pet_id: int, days: int = 30) -> int:
    since = _utc_now() - timedelta(days=days)
    since_iso = since.isoformat().replace("+00:00", "Z")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM triage_logs
            WHERE pet_id = ? AND created_at >= ?
            """,
            (pet_id, since_iso),
        )
        (cnt,) = cur.fetchone()
        return int(cnt or 0)
    finally:
        conn.close()


def _first_triage_at(user_id: int) -> Optional[datetime]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at
            FROM triage_logs
            WHERE user_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return _parse_iso(row[0])
    finally:
        conn.close()


def maybe_show_subscription_offer(
    user_id: int,
    event_type: str,
    ctx: Optional[Dict[str, Any]] = None,
) -> str:
    """Return DECISION_* for a subscription offer/paywall.

    Implements minimal version of scenarios from `TemichevVet_Subscription_Scenarios_FOR_DEV`.
    Stores cooldowns in `subscription_offer_logs`.
    """
    ctx = ctx or {}
    if _is_paid(user_id):
        return DECISION_NONE

    now = _utc_now()

    # Scenario 1: after 2nd triage for same pet within 30 days, cooldown 14 days
    if event_type == "TRIAGE_COMPLETED":
        pet_id = ctx.get("pet_id")
        if not pet_id:
            return DECISION_NONE
        cnt = _triage_count_for_pet(int(pet_id), days=30)
        if cnt < 2:
            return DECISION_NONE
        last = last_offer_shown_at(user_id, event_type, key=str(pet_id))
        if last:
            if now - _parse_iso(last) < timedelta(days=14):
                return DECISION_NONE
        mark_offer_shown(user_id, event_type, key=str(pet_id), payload={"triage_count_30d": cnt})
        return DECISION_SOFT

    # Scenario 2: history/analytics opened, hard paywall if over free limit
    if event_type in {"HISTORY_OPENED", "ANALYTICS_OPENED"}:
        exceeds = bool(ctx.get("exceeds_free_limit"))
        if not exceeds:
            return DECISION_NONE
        last = last_offer_shown_at(user_id, event_type, key=None)
        if last and (now - _parse_iso(last) < timedelta(days=7)):
            # don't spam paywall every time
            return DECISION_HARD
        mark_offer_shown(user_id, event_type, key=None, payload={"exceeds_free_limit": True})
        return DECISION_HARD

    # Scenario 4: retention check (7 days after first triage), cooldown 30 days
    if event_type == "RETENTION_CHECK":
        first = _first_triage_at(user_id)
        if not first:
            return DECISION_NONE
        if now - first < timedelta(days=7):
            return DECISION_NONE
        last = last_offer_shown_at(user_id, event_type, key=None)
        if last and (now - _parse_iso(last) < timedelta(days=30)):
            return DECISION_NONE
        mark_offer_shown(user_id, event_type, key=None, payload={"first_triage_at": first.isoformat()})
        return DECISION_SOFT

    # Scenario 5: direct open subscription page
    if event_type == "SUBSCRIPTION_PAGE_OPENED":
        return DECISION_SOFT

    return DECISION_NONE
