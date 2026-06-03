from __future__ import annotations

import base64
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from app.constants import SUBSCRIPTION_PLANS
from app.config import (
    YOOKASSA_RECEIPT_EMAIL,
    YOOKASSA_RETURN_URL,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
    YOOKASSA_TAX_SYSTEM_CODE,
    YOOKASSA_VAT_CODE,
)


API_BASE_URL = "https://api.yookassa.ru/v3"


class YooKassaConfigError(RuntimeError):
    pass


class YooKassaPaymentValidationError(RuntimeError):
    pass


def _amount_value(amount_rub: int | float) -> str:
    return f"{float(amount_rub):.2f}"


def _plus_price_rub() -> int:
    return int(SUBSCRIPTION_PLANS["plus"]["price"])


def _auth_header() -> str:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise YooKassaConfigError("YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY не заданы")
    token = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("ascii")


def _decimal_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as e:
        raise YooKassaPaymentValidationError("некорректная сумма платежа") from e


def _metadata_int(metadata: dict[str, Any], key: str) -> int | None:
    value = metadata.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise YooKassaPaymentValidationError(f"некорректный metadata.{key}") from e


def validate_plus_payment(
    payment: dict[str, Any],
    *,
    expected_user_id: int,
    expected_telegram_id: int,
    expected_amount_rub: int | None = None,
) -> None:
    """Проверить, что успешный платёж действительно относится к Plus текущего пользователя."""
    status = str(payment.get("status") or "").lower()
    if status != "succeeded":
        raise YooKassaPaymentValidationError("платёж не в статусе succeeded")

    if payment.get("paid") is not True:
        raise YooKassaPaymentValidationError("платёж не помечен как paid=true")

    amount = payment.get("amount") or {}
    if not isinstance(amount, dict):
        raise YooKassaPaymentValidationError("amount платежа отсутствует")

    if str(amount.get("currency") or "").upper() != "RUB":
        raise YooKassaPaymentValidationError("валюта платежа не RUB")

    paid_amount = _decimal_amount(amount.get("value"))
    expected_amount = Decimal(str(expected_amount_rub or _plus_price_rub())).quantize(Decimal("0.01"))
    if paid_amount != expected_amount:
        raise YooKassaPaymentValidationError("сумма платежа не совпадает с тарифом Plus")

    metadata = payment.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise YooKassaPaymentValidationError("metadata платежа отсутствует")

    if str(metadata.get("plan_code") or "").lower() != "plus":
        raise YooKassaPaymentValidationError("metadata.plan_code не plus")

    metadata_user_id = _metadata_int(metadata, "user_id")
    if metadata_user_id != int(expected_user_id):
        raise YooKassaPaymentValidationError("metadata.user_id не совпадает с пользователем")

    metadata_telegram_id = _metadata_int(metadata, "telegram_id")
    if metadata_telegram_id != int(expected_telegram_id):
        raise YooKassaPaymentValidationError("metadata.telegram_id не совпадает с Telegram ID")


def build_receipt(amount_rub: int, description: str) -> dict[str, Any] | None:
    if not YOOKASSA_RECEIPT_EMAIL:
        return None
    try:
        vat_code = int(YOOKASSA_VAT_CODE or "1")
    except ValueError as e:
        raise YooKassaConfigError("YOOKASSA_VAT_CODE должен быть числом") from e

    receipt: dict[str, Any] = {
        "customer": {"email": YOOKASSA_RECEIPT_EMAIL},
        "items": [
            {
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": _amount_value(amount_rub), "currency": "RUB"},
                "vat_code": vat_code,
                "payment_subject": "service",
                "payment_mode": "full_payment",
            }
        ],
    }
    if YOOKASSA_TAX_SYSTEM_CODE:
        try:
            receipt["tax_system_code"] = int(YOOKASSA_TAX_SYSTEM_CODE)
        except ValueError as e:
            raise YooKassaConfigError("YOOKASSA_TAX_SYSTEM_CODE должен быть числом 1..6") from e
    return receipt


def build_payment_payload(
    *,
    amount_rub: int,
    description: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "amount": {"value": _amount_value(amount_rub), "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL or "https://t.me/",
        },
        "description": description[:128],
        "metadata": metadata,
    }
    receipt = build_receipt(amount_rub=amount_rub, description=description)
    if receipt:
        payload["receipt"] = receipt
    return payload


async def create_payment(
    *,
    amount_rub: int,
    description: str,
    metadata: dict[str, Any],
    idempotence_key: str | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "Idempotence-Key": idempotence_key or str(uuid.uuid4()),
    }
    payload = build_payment_payload(
        amount_rub=amount_rub,
        description=description,
        metadata=metadata,
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/payments", headers=headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(f"YooKassa create payment error: {resp.status} {data}")
            return data


async def create_plus_payment(*, user_id: int, telegram_id: int) -> dict[str, Any]:
    return await create_payment(
        amount_rub=_plus_price_rub(),
        description="TemichevVet Plus — доступ на 30 дней",
        metadata={"telegram_id": int(telegram_id), "user_id": int(user_id), "plan_code": "plus", "access_days": 30},
    )


async def get_payment(payment_id: str) -> dict[str, Any]:
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/payments/{payment_id}", headers=headers) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(f"YooKassa get payment error: {resp.status} {data}")
            return data
