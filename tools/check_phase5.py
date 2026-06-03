from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


tmp = tempfile.NamedTemporaryFile(prefix="temichevvet_phase5_", suffix=".db", delete=False)
tmp.close()

os.environ["DB_PATH"] = tmp.name
os.environ.setdefault("BOT_TOKEN", "123456:test")
os.environ.setdefault("ADMIN_CHAT_ID", "100500")
os.environ.setdefault("ADMIN_IDS", "100500,200600")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import (  # noqa: E402
    add_triage_followup,
    count_events,
    counts_bundle,
    create_pet,
    create_user,
    funnel,
    get_admin_dashboard_stats,
    init_db,
    log_triage_event,
    mark_followup_answered,
    mark_followup_sent,
    payments_sum,
    retention_d1_d7,
    set_subscription_plan,
    top_sources,
    triage_tokens_stats,
    triage_urgency_breakdown,
)
from app.handlers.admin import render_admin_csv_export, render_admin_period_report, render_admin_sources_report  # noqa: E402
from app.services.analytics import (  # noqa: E402
    EVENT_APP_START,
    EVENT_FOLLOWUP_ANSWERED,
    EVENT_FOLLOWUP_SCHEDULED,
    EVENT_FOLLOWUP_SENT,
    EVENT_PAYMENT_SUCCESS,
    EVENT_PAYWALL_SHOWN,
    EVENT_PAY_CLICKED,
    EVENT_PET_CREATED,
    EVENT_PET_SET_MAIN,
    EVENT_TRIAGE_COMPLETED,
    EVENT_TRIAGE_STARTED,
    parse_start_payload,
    track_event,
)


def _bounds() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=1)).isoformat(), (now + timedelta(days=1)).isoformat()


def check_analytics_events_and_reports() -> None:
    init_db()

    with sqlite3.connect(tmp.name) as conn:
        idx_names = {row[1] for row in conn.execute("PRAGMA index_list(user_events)").fetchall()}
        assert "idx_user_events_type_created" in idx_names
        assert "idx_user_events_user_created" in idx_names

    payload = parse_start_payload("utm_source=tg&utm_campaign=pilot&utm_content=a")
    assert payload["source_type"] == "utm"
    assert payload["utm_source"] == "tg"
    assert parse_start_payload("clinic_77")["source_type"] == "clinic_link"

    user_id = create_user(100500, "Admin")
    set_subscription_plan(user_id, "plus")
    pet_id = create_pet(user_id, "кошка", "Муся")

    assert track_event(user_id, EVENT_APP_START, payload)
    assert track_event(user_id, EVENT_PET_CREATED, {"pet_id": pet_id, "pet_type": "кошка"})
    assert track_event(user_id, EVENT_PET_SET_MAIN, {"pet_id": pet_id})
    assert track_event(user_id, EVENT_TRIAGE_STARTED, {"pet_id": pet_id})

    triage_log_id = log_triage_event(
        user_id=user_id,
        pet_id=pet_id,
        complaint_text="рвота",
        response_text="🟡 нужен контроль",
        quota_before=0,
        quota_after=1,
        prompt_tokens=400,
        completion_tokens=600,
        total_tokens=1000,
        urgency_level="yellow",
    )
    assert track_event(
        user_id,
        EVENT_TRIAGE_COMPLETED,
        {
            "pet_id": pet_id,
            "urgency_level": "yellow",
            "triage_log_id": triage_log_id,
        },
    )

    followup_id = add_triage_followup(
        triage_event_id=triage_log_id,
        user_id=user_id,
        pet_id=pet_id,
        urgency_level="yellow",
        scenario="gi",
        scheduled_at=datetime.now(timezone.utc).isoformat(),
        payload={"summary": "контроль"},
    )
    assert track_event(
        user_id,
        EVENT_FOLLOWUP_SCHEDULED,
        {"followup_id": followup_id, "triage_log_id": triage_log_id, "scenario": "gi"},
    )
    assert mark_followup_sent(followup_id)
    assert track_event(
        user_id,
        EVENT_FOLLOWUP_SENT,
        {"followup_id": followup_id, "triage_log_id": triage_log_id, "scenario": "gi"},
    )
    assert mark_followup_answered(followup_id, "better")
    assert track_event(
        user_id,
        EVENT_FOLLOWUP_ANSWERED,
        {
            "followup_id": followup_id,
            "triage_log_id": triage_log_id,
            "scenario": "gi",
            "answer_type": "better",
        },
    )

    assert track_event(user_id, EVENT_PAYWALL_SHOWN, {"reason": "history"})
    assert track_event(user_id, EVENT_PAY_CLICKED, {"plan_code": "plus", "reason": "subscription"})
    assert track_event(user_id, EVENT_PAYMENT_SUCCESS, {"plan_code": "plus", "amount_rub": 200, "provider": "test"})

    date_from, date_to = _bounds()
    assert count_events(EVENT_APP_START, date_from, date_to) == 1
    counts = counts_bundle(date_from, date_to)
    assert counts[EVENT_TRIAGE_COMPLETED] == 1
    assert counts["triage_by_plan"]["plus"] == 1

    funnel_stats = funnel(date_from, date_to)
    assert funnel_stats[EVENT_APP_START] == 1
    assert funnel_stats[EVENT_PAYMENT_SUCCESS] == 1

    retention = retention_d1_d7(date_from, date_to)
    assert retention["base_cohorts"] >= 1
    assert retention["avg_triage_per_user"] >= 1

    sources = top_sources(date_from, date_to, group_by="utm_source")
    assert sources[0]["source"] == "tg"
    assert sources[0]["triage_completed"] == 1
    assert sources[0]["payment_success"] == 1

    tokens = triage_tokens_stats(date_from, date_to)
    assert tokens["total_tokens"] == 1000
    assert int(tokens["avg_tokens_per_triage"]) == 1000

    urgency = triage_urgency_breakdown(date_from, date_to)
    assert urgency["yellow"] == 1

    payments = payments_sum(date_from, date_to)
    assert payments["count"] == 1
    assert int(payments["amount_rub"]) == 200

    stats = get_admin_dashboard_stats(date_from, date_to)
    assert stats["counts"][EVENT_PAYWALL_SHOWN] == 1
    assert stats["subscriptions"]["plus"] == 1

    report = render_admin_period_report("Тест", date_from, date_to)
    assert "Запуски" in report
    assert "Оплаты" in report

    sources_report = render_admin_sources_report("Тест", date_from, date_to)
    assert "tg" in sources_report

    csv_text = render_admin_csv_export("Тест", date_from, date_to).decode("utf-8-sig")
    assert "Раздел,Метрика,Ключ,Значение" in csv_text
    assert "События,Запуски,,1" in csv_text
    assert "Источники,Запуски,tg,1" in csv_text


def main() -> None:
    check_analytics_events_and_reports()
    print("phase5 ok")


if __name__ == "__main__":
    main()
