from __future__ import annotations

import atexit
import asyncio
import os
import sys
import tempfile
from pathlib import Path


tmp = tempfile.NamedTemporaryFile(prefix="temichevvet_callback_access_", suffix=".db", delete=False)
tmp.close()
atexit.register(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))

os.environ["DB_PATH"] = tmp.name
os.environ.setdefault("BOT_TOKEN", "callback-access-dummy-token")
os.environ.setdefault("OPENAI_API_KEY", "callback-access-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import (  # noqa: E402
    create_payment_record,
    create_pet,
    create_reminder,
    create_user,
    deactivate_reminder,
    delete_pet,
    get_last_payment,
    get_pet_by_id,
    get_pet_for_user,
    get_pet_reminders,
    get_user_reminders,
    init_db,
    update_reminder,
)
from app.payments.yookassa import validate_plus_payment, YooKassaPaymentValidationError  # noqa: E402
from app.pets_v2.delete import delete_pet_callback, delete_pet_confirm_callback  # noqa: E402
from app.pets_v2.reminders import _find_user_reminder, _reminder_pet_id  # noqa: E402


class FakeFromUser:
    def __init__(self, telegram_id: int) -> None:
        self.id = telegram_id
        self.username = f"user{telegram_id}"


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None, **_kwargs):
        self.answers.append((text, reply_markup))
        return None


class FakeCallback:
    def __init__(self, *, telegram_id: int, data: str) -> None:
        self.from_user = FakeFromUser(telegram_id)
        self.data = data
        self.message = FakeMessage()
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False, **_kwargs):
        self.answers.append((text, show_alert))
        return None


def _payment_payload(user_id: int, telegram_id: int, payment_id: str) -> dict:
    return {
        "id": payment_id,
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "200.00", "currency": "RUB"},
        "metadata": {"user_id": user_id, "telegram_id": telegram_id, "plan_code": "plus"},
    }


def _setup_data() -> dict:
    init_db()
    owner_a = create_user(telegram_id=610001, name="Owner A")
    owner_b = create_user(telegram_id=610002, name="Owner B")
    pet_a = create_pet(owner_a, "кошка", "Ася")
    pet_b = create_pet(owner_b, "собака", "Бим")
    pet_b_extra = create_pet(owner_b, "кошка", "Буся")
    pet_b_delete = create_pet(owner_b, "собака", "Рэй")
    rem_a = create_reminder(owner_a, pet_a, "custom", "A reminder", "2026-06-10", None, "once", None)
    rem_b = create_reminder(owner_b, pet_b_extra, "custom", "B reminder", "2026-06-11", None, "once", None)
    create_payment_record(
        user_id=owner_a,
        provider="yookassa",
        provider_payment_id="pay_owner_a",
        plan_code="plus",
        amount_rub=200,
        status="pending",
        raw_payload={"id": "pay_owner_a", "status": "pending"},
    )
    create_payment_record(
        user_id=owner_b,
        provider="yookassa",
        provider_payment_id="pay_owner_b",
        plan_code="plus",
        amount_rub=200,
        status="pending",
        raw_payload={"id": "pay_owner_b", "status": "pending"},
    )
    return {
        "owner_a": owner_a,
        "owner_b": owner_b,
        "telegram_a": 610001,
        "telegram_b": 610002,
        "pet_a": int(pet_a),
        "pet_b": int(pet_b),
        "pet_b_extra": int(pet_b_extra),
        "pet_b_delete": int(pet_b_delete),
        "rem_a": int(rem_a),
        "rem_b": int(rem_b),
    }


async def check_pet_callbacks(data: dict) -> None:
    assert get_pet_for_user(data["owner_a"], data["pet_b"]) is None
    assert get_pet_for_user(data["owner_b"], data["pet_b"]) is not None
    assert delete_pet(data["owner_a"], data["pet_b"]) is False
    assert get_pet_by_id(data["pet_b"]) is not None

    ask = FakeCallback(telegram_id=data["telegram_a"], data=f"pet:delete:{data['pet_b']}")
    await delete_pet_callback(ask)
    assert not ask.message.answers
    assert ask.answers and ask.answers[-1] == ("Питомец не найден", True)
    assert get_pet_by_id(data["pet_b"]) is not None

    foreign = FakeCallback(telegram_id=data["telegram_a"], data=f"pet:delete_confirm:{data['pet_b_extra']}")
    await delete_pet_confirm_callback(foreign)
    assert get_pet_by_id(data["pet_b_extra"]) is not None
    assert foreign.answers and foreign.answers[-1] == ("Питомец не найден", True)

    own = FakeCallback(telegram_id=data["telegram_b"], data=f"pet:delete_confirm:{data['pet_b_delete']}")
    await delete_pet_confirm_callback(own)
    assert get_pet_by_id(data["pet_b_delete"]) is None


def check_reminder_callbacks(data: dict) -> None:
    assert _find_user_reminder(data["owner_a"], data["rem_b"]) is None
    own_reminder = _find_user_reminder(data["owner_b"], data["rem_b"])
    assert own_reminder is not None
    assert _reminder_pet_id(own_reminder) == data["pet_b_extra"]
    assert get_pet_reminders(data["owner_a"], data["pet_b_extra"]) == []

    update_reminder(data["rem_b"], data["owner_a"], title="Hacked")
    still_owner_b = _find_user_reminder(data["owner_b"], data["rem_b"])
    assert still_owner_b and still_owner_b["title"] == "B reminder"

    deactivate_reminder(data["rem_b"], user_id=data["owner_a"])
    assert any(int(r["id"]) == data["rem_b"] for r in get_user_reminders(data["owner_b"]))


def check_payment_access(data: dict) -> None:
    assert get_last_payment(data["owner_a"])["provider_payment_id"] == "pay_owner_a"
    assert get_last_payment(data["owner_b"])["provider_payment_id"] == "pay_owner_b"

    validate_plus_payment(
        _payment_payload(data["owner_a"], data["telegram_a"], "pay_owner_a"),
        expected_user_id=data["owner_a"],
        expected_telegram_id=data["telegram_a"],
        expected_amount_rub=200,
    )

    try:
        validate_plus_payment(
            _payment_payload(data["owner_b"], data["telegram_b"], "pay_owner_b"),
            expected_user_id=data["owner_a"],
            expected_telegram_id=data["telegram_a"],
            expected_amount_rub=200,
        )
    except YooKassaPaymentValidationError:
        pass
    else:
        raise AssertionError("foreign payment metadata was accepted")


def main() -> None:
    data = _setup_data()
    asyncio.run(check_pet_callbacks(data))
    check_reminder_callbacks(data)
    check_payment_access(data)
    print("callback access checks ok")


if __name__ == "__main__":
    main()
