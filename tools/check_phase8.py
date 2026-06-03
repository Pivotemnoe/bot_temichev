from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


tmp = tempfile.NamedTemporaryFile(prefix="temichevvet_phase8_", suffix=".db", delete=False)
tmp.close()

os.environ["DB_PATH"] = tmp.name
os.environ.setdefault("BOT_TOKEN", "123456:test")
os.environ.setdefault("OPENAI_API_KEY", "phase8-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ["YOOKASSA_SHOP_ID"] = "123456"
os.environ["YOOKASSA_SECRET_KEY"] = "test_secret"
os.environ["YOOKASSA_RETURN_URL"] = "https://t.me/TemichevVettest_bot"
os.environ["YOOKASSA_RECEIPT_EMAIL"] = "test@example.com"
os.environ["YOOKASSA_TAX_SYSTEM_CODE"] = "1"
os.environ["YOOKASSA_VAT_CODE"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.constants import SUBSCRIPTION_BUTTONS  # noqa: E402
from app.db import (  # noqa: E402
    activate_plus,
    create_payment_record,
    create_user,
    get_last_payment,
    get_subscription,
    init_db,
    list_payment_records,
    payment_records_summary,
    set_subscription_plan,
    update_payment_status,
)
from app.keyboards import payment_created_kb, plus_checkout_kb, subscription_inline_kb, subscription_kb  # noqa: E402
from app.handlers.menu import (  # noqa: E402
    EXTRA_REQUEST_BUTTON,
    EXTRA_REQUEST_IN_DEVELOPMENT_TEXT,
    buy_extra_request,
    callback_buy_extra_request,
)
from app.payments.yookassa import build_payment_payload, build_receipt  # noqa: E402
from app.services.payment_reconcile import reconcile_yookassa_payments  # noqa: E402


def _reply_texts(markup) -> set[str]:
    return {button.text for row in markup.keyboard for button in row if button.text}


def _inline_callbacks(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}


def _inline_urls(markup) -> set[str]:
    return {button.url for row in markup.inline_keyboard for button in row if button.url}


def check_keyboards() -> None:
    texts = _reply_texts(subscription_kb())
    assert set(SUBSCRIPTION_BUTTONS) <= texts
    assert "✅ Я оплатил (проверить)" in texts
    assert "📋 Все тарифы" in texts
    assert EXTRA_REQUEST_BUTTON in texts

    assert _inline_callbacks(plus_checkout_kb()) == {"pay:plus", "sub:back"}
    assert {
        "sub:choose:free",
        "sub:choose:plus",
        "sub:choose:pro",
        "sub:buy_extra",
        "sub:unsubscribe",
        "open:main_menu",
    } <= _inline_callbacks(subscription_inline_kb(current_plan="plus"))
    payment_kb = payment_created_kb("https://pay.test/link")
    assert {"pay:check", "sub:back"} <= _inline_callbacks(payment_kb)
    assert "https://pay.test/link" in _inline_urls(payment_kb)


class _FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


class _FakeCallback:
    def __init__(self) -> None:
        self.message = _FakeMessage()
        self.answers: list[tuple[str | None, bool | None]] = []

    async def answer(self, text: str | None = None, show_alert: bool | None = None):
        self.answers.append((text, show_alert))


async def check_extra_request_stub() -> None:
    message = _FakeMessage()
    await buy_extra_request(message)
    assert message.answers
    assert message.answers[0][0] == EXTRA_REQUEST_IN_DEVELOPMENT_TEXT
    assert "в разработке" in message.answers[0][0]

    callback = _FakeCallback()
    await callback_buy_extra_request(callback)
    assert callback.message.answers
    assert callback.message.answers[0][0] == EXTRA_REQUEST_IN_DEVELOPMENT_TEXT
    assert callback.answers == [("Функция в разработке", None)]


def check_yookassa_payload() -> None:
    payload = build_payment_payload(
        amount_rub=200,
        description="TemichevVet Plus — доступ на 30 дней",
        metadata={"user_id": 1, "telegram_id": 2, "plan_code": "plus"},
    )
    assert payload["amount"] == {"value": "200.00", "currency": "RUB"}
    assert payload["capture"] is True
    assert payload["confirmation"]["type"] == "redirect"
    assert payload["confirmation"]["return_url"] == "https://t.me/TemichevVettest_bot"
    assert payload["metadata"]["plan_code"] == "plus"
    assert payload["receipt"]["customer"]["email"] == "test@example.com"

    receipt = build_receipt(amount_rub=200, description="x")
    assert receipt["items"][0]["amount"]["value"] == "200.00"


def check_payment_db_flow() -> None:
    init_db()
    user_id = create_user(telegram_id=880088, name="Phase8")
    payment_id = create_payment_record(
        user_id=user_id,
        provider="yookassa",
        provider_payment_id="pay_test_1",
        plan_code="plus",
        amount_rub=200,
        status="pending",
        raw_payload={"id": "pay_test_1", "status": "pending"},
    )
    assert payment_id > 0

    last = get_last_payment(user_id, provider="yookassa")
    assert last["provider_payment_id"] == "pay_test_1"
    assert last["status"] == "pending"

    assert update_payment_status(
        "yookassa",
        "pay_test_1",
        "succeeded",
        paid_at="2026-06-01T09:00:00+00:00",
        raw_payload={"status": "succeeded"},
    )
    last = get_last_payment(user_id, provider="yookassa")
    assert last["status"] == "succeeded"
    assert last["paid_at"] == "2026-06-01T09:00:00+00:00"

    activate_plus(user_id)
    sub = get_subscription(user_id)
    assert sub["plan"] == "plus"
    assert sub["quota_total"] == 10
    assert sub["period_end"]

    records = list_payment_records(provider="yookassa", limit=5)
    assert records
    assert records[0]["telegram_id"] == 880088

    summary = payment_records_summary("2026-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00")
    assert summary["created"] >= 1
    assert summary["succeeded"] >= 1
    assert summary["succeeded_amount_rub"] >= 200

    expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    set_subscription_plan(user_id, "plus", period_end=expired_at)
    assert get_subscription(user_id)["plan"] == "free"


async def check_payment_reconcile_flow() -> None:
    user_id = create_user(telegram_id=880099, name="Phase8 Reconcile")
    create_payment_record(
        user_id=user_id,
        provider="yookassa",
        provider_payment_id="pay_reconcile_1",
        plan_code="plus",
        amount_rub=200,
        status="pending",
        raw_payload={"id": "pay_reconcile_1", "status": "pending"},
    )

    async def fake_get_payment(payment_id: str) -> dict:
        assert payment_id == "pay_reconcile_1"
        return {
            "id": payment_id,
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "200.00", "currency": "RUB"},
            "metadata": {"user_id": user_id, "telegram_id": 880099, "plan_code": "plus"},
            "captured_at": "2026-06-01T09:00:00+00:00",
            "created_at": "2026-06-01T08:59:00+00:00",
        }

    result = await reconcile_yookassa_payments(limit=1, fetch_payment=fake_get_payment)
    assert result["checked"] == 1
    assert result["activated"] == 1
    assert result["validation_failed"] == 0
    sub = get_subscription(user_id)
    assert sub["plan"] == "plus"
    assert sub["period_end"]

    result_again = await reconcile_yookassa_payments(limit=1, fetch_payment=fake_get_payment)
    assert result_again["checked"] == 1
    assert result_again["activated"] == 0


def main() -> None:
    check_keyboards()
    asyncio.run(check_extra_request_stub())
    check_yookassa_payload()
    check_payment_db_flow()
    asyncio.run(check_payment_reconcile_flow())
    print("phase8 ok")


if __name__ == "__main__":
    main()
