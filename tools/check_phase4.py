from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


fd, db_path = tempfile.mkstemp(prefix="temichevvet-phase4-", suffix=".db")
os.close(fd)
Path(db_path).unlink(missing_ok=True)

os.environ.setdefault("BOT_TOKEN", "phase4-dummy-token")
os.environ.setdefault("OPENAI_API_KEY", "phase4-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ["DB_PATH"] = db_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.constants import SUPPORTED_PETS
from app.db import (
    create_pet,
    create_user,
    get_due_followups,
    get_followup_by_id,
    init_db,
    log_triage_event,
    mark_followup_answered,
    mark_followup_sent,
)
from app.services.followup import (
    create_followup_for_triage,
    detect_followup_scenario,
    followup_response_kb,
    render_followup_answer_text,
    render_followup_text,
)


def _callback_data(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row}


def check_scenarios() -> None:
    assert detect_followup_scenario("после операции шов покраснел", []) == "postop"
    assert detect_followup_scenario("рвота и понос второй день", []) == "gi"
    assert detect_followup_scenario("собака хромает, не наступает на лапу", []) == "trauma"
    assert detect_followup_scenario("вялая", []) == "basic"
    assert detect_followup_scenario("обычный текст", [{"event_type": "post_op"}]) == "postop"


def check_followup_creation_and_statuses() -> None:
    init_db()
    user_id = create_user(telegram_id=123123123, name="Phase4")
    pet_id = create_pet(user_id, SUPPORTED_PETS["🐶 Собака"], "Бим")

    green_id = log_triage_event(user_id, pet_id, "вялая", "ok", 0, 1, urgency_level="green")
    green = create_followup_for_triage(
        triage_event_id=green_id,
        user_id=user_id,
        pet_id=pet_id,
        urgency_level="green",
        complaint_text="вялая",
    )
    assert not green["created"] and green["reason"] == "urgency_not_followup"

    yellow_id = log_triage_event(user_id, pet_id, "рвота", "ok", 1, 2, urgency_level="yellow")
    yellow = create_followup_for_triage(
        triage_event_id=yellow_id,
        user_id=user_id,
        pet_id=pet_id,
        urgency_level="yellow",
        complaint_text="рвота",
        response_summary="summary",
    )
    assert yellow["created"]
    assert yellow["scenario"] == "gi"

    duplicate = create_followup_for_triage(
        triage_event_id=yellow_id,
        user_id=user_id,
        pet_id=pet_id,
        urgency_level="yellow",
        complaint_text="рвота",
    )
    assert not duplicate["created"] and duplicate["reason"] == "already_exists"

    red_id = log_triage_event(user_id, pet_id, "хромает", "ok", 2, 3, urgency_level="red")
    red = create_followup_for_triage(
        triage_event_id=red_id,
        user_id=user_id,
        pet_id=pet_id,
        urgency_level="red",
        complaint_text="хромает",
    )
    assert not red["created"] and red["reason"] == "recent_followup"

    followup_id = yellow["followup_id"]
    due_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE triage_followups SET scheduled_at = ? WHERE id = ?", (due_at, followup_id))
        conn.commit()

    due = get_due_followups()
    assert len(due) == 1
    assert due[0]["id"] == followup_id
    assert due[0]["telegram_id"] == 123123123

    assert mark_followup_sent(followup_id)
    assert get_followup_by_id(followup_id)["status"] == "sent"
    assert mark_followup_answered(followup_id, "better")
    assert get_followup_by_id(followup_id)["answer"] == "better"


def check_texts_and_keyboards() -> None:
    text = render_followup_text("postop")
    assert "операции" in text
    assert "Этот ответ не заменяет очный осмотр ветеринарного врача" in text

    answer_text = render_followup_answer_text("postop", "worse")
    assert "послеоперационный" in answer_text.lower()

    callbacks = _callback_data(followup_response_kb(55, "basic"))
    assert {
        "fu:answer:55:better",
        "fu:answer:55:same",
        "fu:answer:55:worse",
        "fu:answer:55:retry",
    } <= callbacks


def main() -> None:
    try:
        check_scenarios()
        check_followup_creation_and_statuses()
        check_texts_and_keyboards()
        print("phase4 checks ok")
    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
