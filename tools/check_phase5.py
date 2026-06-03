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
    conversion_funnel,
    create_pet,
    create_user,
    fsm_errors_summary,
    funnel,
    get_admin_dashboard_stats,
    init_db,
    log_triage_event,
    mark_followup_answered,
    mark_followup_sent,
    payments_sum,
    retention_d1_d7,
    scenario_dropoffs,
    set_subscription_plan,
    top_food_queries,
    top_triage_complaints,
    top_sources,
    triage_tokens_stats,
    triage_urgency_breakdown,
)
from app.handlers.admin import (  # noqa: E402
    render_admin_complaints_report,
    render_admin_csv_export,
    render_admin_dropoffs_report,
    render_admin_food_report,
    render_admin_fsm_report,
    render_admin_period_report,
    render_admin_sources_report,
)
from app.services.analytics import (  # noqa: E402
    EVENT_APP_START,
    EVENT_FOOD_COMPLEX_DISH,
    EVENT_FOOD_QUERY,
    EVENT_FOOD_SEARCH_STARTED,
    EVENT_FOLLOWUP_ANSWERED,
    EVENT_FOLLOWUP_SCHEDULED,
    EVENT_FOLLOWUP_SENT,
    EVENT_FSM_CANCELLED,
    EVENT_FSM_INVALID_INPUT,
    EVENT_PAYMENT_SUCCESS,
    EVENT_PAYWALL_SHOWN,
    EVENT_PAY_CLICKED,
    EVENT_PET_CREATE_STARTED,
    EVENT_PET_CREATED,
    EVENT_PET_SET_MAIN,
    EVENT_REGISTRATION_STARTED,
    EVENT_TRIAGE_COMPLETED,
    EVENT_TRIAGE_STARTED,
    EVENT_USER_REGISTERED,
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
    assert track_event(user_id, EVENT_REGISTRATION_STARTED, {"source": "test"})
    assert track_event(user_id, EVENT_USER_REGISTERED, {"source": "test"})
    assert track_event(user_id, EVENT_PET_CREATE_STARTED, {"source": "test"})
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
    assert track_event(user_id, EVENT_FOOD_SEARCH_STARTED, {"source": "test"})
    assert track_event(user_id, EVENT_FOOD_QUERY, {"query": "творог", "results_count": 1, "status": "found"})
    assert track_event(
        user_id,
        EVENT_FOOD_COMPLEX_DISH,
        {"dish_name": "борщ", "status": "checked", "ingredients_count": 5},
    )
    assert track_event(
        user_id,
        EVENT_FSM_CANCELLED,
        {"scenario": "triage", "state": "TriageStates:asking_age", "reason": "user_cancel"},
    )
    assert track_event(
        user_id,
        EVENT_FSM_INVALID_INPUT,
        {"scenario": "food_search", "state": "KnowledgeStates:waiting_food_query", "reason": "empty_food_query"},
    )

    date_from, date_to = _bounds()
    assert count_events(EVENT_APP_START, date_from, date_to) == 1
    counts = counts_bundle(date_from, date_to)
    assert counts[EVENT_TRIAGE_COMPLETED] == 1
    assert counts["triage_by_plan"]["plus"] == 1

    funnel_stats = funnel(date_from, date_to)
    assert funnel_stats[EVENT_APP_START] == 1
    assert funnel_stats[EVENT_USER_REGISTERED] == 1
    assert funnel_stats[EVENT_PAYMENT_SUCCESS] == 1

    conversion = conversion_funnel(date_from, date_to)
    assert conversion[EVENT_APP_START] == 1
    assert conversion[EVENT_USER_REGISTERED] == 1
    assert conversion[EVENT_PET_CREATED] == 1
    assert conversion[EVENT_TRIAGE_COMPLETED] == 1

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

    complaints = top_triage_complaints(date_from, date_to)
    assert complaints[0]["topic"] == "рвота"
    assert complaints[0]["count"] == 1

    food_queries = top_food_queries(date_from, date_to)
    assert any(item["query"] == "творог" for item in food_queries)
    assert any(item["query"] == "борщ" and item["kind"] == "готовое блюдо" for item in food_queries)

    dropoffs = scenario_dropoffs(date_from, date_to)
    assert any(item["scenario"] == "triage" and item["cancelled"] == 1 for item in dropoffs)
    assert any(item["scenario"] == "food_search" and item["completed"] == 1 for item in dropoffs)

    fsm_errors = fsm_errors_summary(date_from, date_to)
    assert fsm_errors[0]["scenario"] == "food_search"
    assert fsm_errors[0]["reason"] == "empty_food_query"

    stats = get_admin_dashboard_stats(date_from, date_to)
    assert stats["counts"][EVENT_PAYWALL_SHOWN] == 1
    assert stats["subscriptions"]["plus"] == 1
    assert stats["conversion_funnel"][EVENT_PET_CREATED] == 1
    assert stats["complaints"][0]["topic"] == "рвота"

    report = render_admin_period_report("Тест", date_from, date_to)
    assert "Запуски" in report
    assert "Оплаты" in report

    sources_report = render_admin_sources_report("Тест", date_from, date_to)
    assert "tg" in sources_report

    assert "рвота" in render_admin_complaints_report("Тест", date_from, date_to)
    assert "борщ" in render_admin_food_report("Тест", date_from, date_to)
    assert "Разбор жалобы" in render_admin_dropoffs_report("Тест", date_from, date_to)
    assert "Ошибки сценариев" in render_admin_fsm_report("Тест", date_from, date_to)

    csv_text = render_admin_csv_export("Тест", date_from, date_to).decode("utf-8-sig")
    assert "Раздел,Метрика,Ключ,Значение" in csv_text
    assert "События,Запуски,,1" in csv_text
    assert "Источники,Запуски,tg,1" in csv_text
    assert "Частые жалобы" in csv_text


def main() -> None:
    check_analytics_events_and_reports()
    print("phase5 ok")


if __name__ == "__main__":
    main()
