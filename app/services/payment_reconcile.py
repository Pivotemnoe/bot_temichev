from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.db import activate_plus, list_payment_records, update_payment_status
from app.payments.yookassa import YooKassaPaymentValidationError, get_payment, validate_plus_payment
from app.services.analytics import EVENT_PAYMENT_SUCCESS, track_event


PAYMENT_STATUS_LABELS = {
    "pending": "создан, ожидает оплаты",
    "waiting_for_capture": "оплачен, ожидает подтверждения",
    "succeeded": "оплачен и подтверждён",
    "validation_failed": "не прошёл проверку безопасности",
    "canceled": "отменён",
    "unknown": "неизвестный статус",
}


def payment_status_label(status: str | None) -> str:
    raw = str(status or "unknown").lower()
    return PAYMENT_STATUS_LABELS.get(raw, raw)


def payment_access_note() -> str:
    return (
        "Plus оплачивается разово на 30 дней. Автосписаний нет. "
        "После окончания срока бот автоматически вернёт тариф Free, если Plus не продлить."
    )


def payment_not_found_text() -> str:
    return (
        "🔎 <b>Оплата не найдена</b>\n\n"
        "В боте пока нет созданного платежа для вашего аккаунта.\n\n"
        "Что сделать:\n"
        "1. Откройте «👤 Моя подписка».\n"
        "2. Выберите Plus и нажмите «💳 Оплатить Plus».\n"
        "3. После оплаты вернитесь в бот и нажмите «✅ Я оплатил (проверить)».\n\n"
        "Если вы уже оплатили, подождите 1-3 минуты и попробуйте проверить ещё раз. "
        "Если платёж всё равно не находится, напишите через «✉️ Обратная связь»."
    )


def _payment_amount_rub(payment: dict[str, Any]) -> int:
    amount = payment.get("amount") if isinstance(payment, dict) else {}
    if not isinstance(amount, dict):
        return 0
    try:
        return int(float(amount.get("value") or 0))
    except (TypeError, ValueError):
        return 0


async def reconcile_yookassa_payments(
    *,
    limit: int = 20,
    fetch_payment: Callable[[str], Awaitable[dict[str, Any]]] = get_payment,
) -> dict:
    records = list_payment_records(provider="yookassa", limit=int(limit))
    rows: list[dict] = []
    summary = {
        "checked": len(records),
        "updated": 0,
        "activated": 0,
        "validation_failed": 0,
        "errors": 0,
        "rows": rows,
    }

    for record in records:
        provider_payment_id = str(record.get("provider_payment_id") or "")
        previous_status = str(record.get("status") or "unknown").lower()
        item = {
            "provider_payment_id": provider_payment_id,
            "user_id": record.get("user_id"),
            "telegram_id": record.get("telegram_id"),
            "amount_rub": record.get("amount_rub"),
            "old_status": previous_status,
            "new_status": previous_status,
            "result": "unchanged",
        }

        if not provider_payment_id or not record.get("telegram_id"):
            item["result"] = "missing_user_or_payment_id"
            summary["errors"] += 1
            rows.append(item)
            continue

        try:
            payment = await fetch_payment(provider_payment_id)
        except Exception as exc:
            item["result"] = "fetch_error"
            item["error"] = str(exc)
            summary["errors"] += 1
            rows.append(item)
            continue

        status = str(payment.get("status") or "unknown").lower()
        item["new_status"] = status
        paid_at = payment.get("captured_at") or payment.get("created_at")

        if status == "succeeded":
            try:
                validate_plus_payment(
                    payment,
                    expected_user_id=int(record["user_id"]),
                    expected_telegram_id=int(record["telegram_id"]),
                    expected_amount_rub=int(record.get("amount_rub") or _payment_amount_rub(payment) or 200),
                )
            except YooKassaPaymentValidationError as exc:
                update_payment_status("yookassa", provider_payment_id, "validation_failed", raw_payload=payment)
                item["new_status"] = "validation_failed"
                item["result"] = "validation_failed"
                item["error"] = str(exc)
                summary["updated"] += int(previous_status != "validation_failed")
                summary["validation_failed"] += 1
                rows.append(item)
                continue

            update_payment_status("yookassa", provider_payment_id, "succeeded", paid_at=paid_at, raw_payload=payment)
            if previous_status != "succeeded":
                activate_plus(int(record["user_id"]))
            item["result"] = "activated" if previous_status != "succeeded" else "already_succeeded"
            summary["updated"] += int(previous_status != "succeeded")
            summary["activated"] += int(previous_status != "succeeded")
            if previous_status != "succeeded":
                track_event(
                    int(record["user_id"]),
                    EVENT_PAYMENT_SUCCESS,
                    {
                        "plan_code": "plus",
                        "amount_rub": int(record.get("amount_rub") or _payment_amount_rub(payment) or 200),
                        "provider": "yookassa",
                        "provider_payment_id": provider_payment_id,
                        "source": "admin_reconcile",
                    },
                )
        else:
            update_payment_status("yookassa", provider_payment_id, status, raw_payload=payment)
            item["result"] = "status_updated" if previous_status != status else "unchanged"
            summary["updated"] += int(previous_status != status)

        rows.append(item)

    return summary
