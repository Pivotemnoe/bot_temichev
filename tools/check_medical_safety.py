from __future__ import annotations

import os
import sys
import tempfile
import atexit
from pathlib import Path


tmp = tempfile.NamedTemporaryFile(prefix="temichevvet_medical_safety_", suffix=".db", delete=False)
tmp.close()
atexit.register(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))

os.environ.setdefault("BOT_TOKEN", "medical-safety-dummy-token")
os.environ.setdefault("OPENAI_API_KEY", "medical-safety-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ["DB_PATH"] = tmp.name

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.llm_engine import SYSTEM_PROMPT  # noqa: E402
from app.db import (  # noqa: E402
    create_pet,
    create_user,
    ensure_default_subscription,
    get_subscription,
    get_triage_history_for_user,
    get_user_by_telegram_id,
    init_db,
)
from app.handlers.triage import _record_red_flag_triage  # noqa: E402
from app.prompts.selector import build_final_system_prompt  # noqa: E402
from app.services.medical_safety import detect_red_flags, render_red_flag_response  # noqa: E402


def check_red_flag_detector() -> None:
    cases = {
        "у кота судороги и пена": "судороги",
        "собака тяжело дышит и задыхается": "тяжёлое дыхание",
        "у кошки одышка и дыхание тяжёлое": "тяжёлое дыхание",
        "у кошки понос с кровью": "кровь или кровотечение",
        "щенок съел крысиный яд": "подозрение на отравление",
        "кот без сознания, не реагирует": "потеря сознания",
    }
    for text, expected in cases.items():
        result = detect_red_flags(text)
        assert result.has_red_flags, text
        assert expected in result.matched, (text, result.matched)

    assert not detect_red_flags("кошка вялая, крови нет, дышит нормально").has_red_flags


def check_red_flag_response() -> None:
    result = detect_red_flags("собака тяжело дышит, есть кровь")
    text = render_red_flag_response(result)
    assert "Срочно в клинику" in text
    assert "не ждите ответа бота" in text
    assert "не давайте человеческие лекарства" in text
    assert "Этот ответ не заменяет очный осмотр" in text


def _assert_prompt_has_medical_limits(prompt: str) -> None:
    p = " ".join(prompt.lower().split())
    required = (
        "не ставь диагноз",
        "не назначай лекарства",
        "дозировки",
        "схемы лечения",
        "человеческие препараты",
        "можно наблюдать",
        "нужна консультация",
        "срочно в клинику",
    )
    for needle in required:
        assert needle in p, needle


def check_prompt_medical_limits() -> None:
    _assert_prompt_has_medical_limits(SYSTEM_PROMPT)
    for kwargs in (
        {"plan_code": "free", "clinic_id": None, "complaint_text": "кошка вялая"},
        {"plan_code": "plus", "clinic_id": None, "complaint_text": "собака не ест"},
        {"plan_code": "plus", "clinic_id": 77, "complaint_text": "после операции шов красный"},
    ):
        prompt, _mode = build_final_system_prompt(SYSTEM_PROMPT, **kwargs)
        _assert_prompt_has_medical_limits(prompt)


def check_red_flag_logging_does_not_consume_quota() -> None:
    init_db()
    user_id = create_user(telegram_id=99001, name="MedicalSafety")
    user = get_user_by_telegram_id(99001)
    pet_id = create_pet(user_id, "кошка", "Луна")
    sub = ensure_default_subscription(user_id)
    quota_before = int(sub["quota_used"])
    result = detect_red_flags("кошка тяжело дышит и есть кровь")
    response_text = render_red_flag_response(result)

    triage_id = _record_red_flag_triage(
        user=user,
        pet_id=int(pet_id),
        complaint_text="кошка тяжело дышит и есть кровь",
        response_text=response_text,
        quota_used=quota_before,
        plan_code="free",
        clinic_id=None,
        matched_red_flags=result.matched,
    )

    assert triage_id is not None
    assert int(get_subscription(user_id)["quota_used"]) == quota_before
    history = get_triage_history_for_user(user_id, limit=1)
    assert history and history[0]["urgency_level"] == "red"


def main() -> None:
    check_red_flag_detector()
    check_red_flag_response()
    check_prompt_medical_limits()
    check_red_flag_logging_does_not_consume_quota()
    print("medical safety checks ok")


if __name__ == "__main__":
    main()
