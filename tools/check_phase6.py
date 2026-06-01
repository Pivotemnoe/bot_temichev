from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


tmp = tempfile.NamedTemporaryFile(prefix="temichevvet_phase6_", suffix=".db", delete=False)
tmp.close()

os.environ["DB_PATH"] = tmp.name
os.environ.setdefault("BOT_TOKEN", "123456:test")
os.environ.setdefault("OPENAI_API_KEY", "phase6-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import create_user, get_user_by_telegram_id, init_db, set_user_clinic_id_if_empty  # noqa: E402
from app.llm_engine import SYSTEM_PROMPT  # noqa: E402
from app.prompts.selector import build_final_system_prompt, is_postop_context, select_prompt_mode  # noqa: E402
from app.services.analytics import EVENT_TRIAGE_STARTED, prompt_mode_for_context, track_event  # noqa: E402
from app.services.followup import (  # noqa: E402
    followup_response_kb,
    render_followup_answer_text,
    render_followup_text,
)


def _callbacks(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}


def check_prompt_selector() -> None:
    base_prompt, base_mode = build_final_system_prompt(
        SYSTEM_PROMPT,
        plan_code="free",
        clinic_id=None,
        complaint_text="кот вялый",
    )
    assert base_mode == "base"
    assert "ДОПОЛНИТЕЛЬНЫЙ ЭКСПЕРТНЫЙ РЕЖИМ" not in base_prompt

    plus_prompt, plus_mode = build_final_system_prompt(
        SYSTEM_PROMPT,
        plan_code="plus",
        clinic_id=None,
        complaint_text="собака после операции, шов красный",
    )
    assert plus_mode == "plus_expert"
    assert "ДОПОЛНИТЕЛЬНЫЙ ЭКСПЕРТНЫЙ РЕЖИМ" in plus_prompt
    assert "Структуру ответа сохраняй стандартную" in plus_prompt

    clinic_prompt, clinic_mode = build_final_system_prompt(
        SYSTEM_PROMPT,
        plan_code="plus",
        clinic_id=77,
        complaint_text="кошка не ест",
    )
    assert clinic_mode == "clinic"
    assert "ДОПОЛНИТЕЛЬНЫЙ РЕЖИМ КЛИНИКИ" in clinic_prompt
    assert "ДОПОЛНИТЕЛЬНЫЙ ЭКСПЕРТНЫЙ РЕЖИМ" not in clinic_prompt

    postop_prompt, postop_mode = build_final_system_prompt(
        SYSTEM_PROMPT,
        plan_code="plus",
        clinic_id=77,
        complaint_text="после операции шов опух, есть выделения",
    )
    assert postop_mode == "clinic_postop"
    assert "ПОСЛЕОПЕРАЦИОННЫЙ МОДУЛЬ" in postop_prompt
    assert is_postop_context("наркоз и швы")
    assert not is_postop_context("чихает утром")
    assert select_prompt_mode(plan_code="plus", clinic_id=77, complaint_text="шов") == "clinic_postop"
    assert prompt_mode_for_context("plus", None, "шов") == "plus_expert"


def check_clinic_id_and_analytics_payload() -> None:
    init_db()
    clinic_user_id = create_user(telegram_id=9001, name="Clinic", clinic_id=77)
    clinic_user = get_user_by_telegram_id(9001)
    assert clinic_user["clinic_id"] == 77

    regular_user_id = create_user(telegram_id=9002, name="Regular")
    assert set_user_clinic_id_if_empty(regular_user_id, 88)
    assert not set_user_clinic_id_if_empty(regular_user_id, 99)
    assert get_user_by_telegram_id(9002)["clinic_id"] == 88

    assert track_event(clinic_user_id, EVENT_TRIAGE_STARTED, {"pet_id": 1})
    with sqlite3.connect(tmp.name) as conn:
        row = conn.execute(
            """
            SELECT payload
            FROM user_events
            WHERE user_id = ? AND event_type = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (clinic_user_id, EVENT_TRIAGE_STARTED),
        ).fetchone()
    payload = json.loads(row[0])
    assert payload["clinic_id"] == 77
    assert payload["prompt_mode"] == "clinic"


def check_plus_followup_copy() -> None:
    text = render_followup_text("postop", plan_code="plus", clinic_id=None)
    assert "место операции" in text
    assert "аппетит и активность" in text

    callbacks = _callbacks(followup_response_kb(5, "postop", plan_code="plus", clinic_id=None))
    assert callbacks == {"fu:answer:5:better", "fu:answer:5:same", "fu:answer:5:worse", "fu:answer:5:retry"}

    answer = render_followup_answer_text("postop", "same", plan_code="plus", clinic_id=None)
    assert "любые изменения требуют внимания" in answer

    base_answer = render_followup_answer_text("postop", "same", plan_code="free", clinic_id=None)
    assert "любые изменения требуют внимания" not in base_answer


def main() -> None:
    check_prompt_selector()
    check_clinic_id_and_analytics_payload()
    check_plus_followup_copy()
    print("phase6 ok")


if __name__ == "__main__":
    main()
