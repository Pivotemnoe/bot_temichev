from __future__ import annotations

import os
import sys
import tempfile
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
    update_payment_status,
)
from app.keyboards import payment_created_kb, plus_checkout_kb, subscription_kb  # noqa: E402
from app.payments.yookassa import build_payment_payload, build_receipt  # noqa: E402


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

    assert _inline_callbacks(plus_checkout_kb()) == {"pay:plus", "sub:back"}
    payment_kb = payment_created_kb("https://pay.test/link")
    assert {"pay:check", "sub:back"} <= _inline_callbacks(payment_kb)
    assert "https://pay.test/link" in _inline_urls(payment_kb)


def check_yookassa_payload() -> None:
    payload = build_payment_payload(
        amount_rub=200,
        description="TemichevVet Plus — подписка на 1 месяц",
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


def main() -> None:
    check_keyboards()
    check_yookassa_payload()
    check_payment_db_flow()
    print("phase8 ok")


if __name__ == "__main__":
    main()
