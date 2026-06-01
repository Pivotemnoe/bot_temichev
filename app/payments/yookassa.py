from __future__ import annotations

import base64
import uuid
from typing import Any

import aiohttp

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


def _amount_value(amount_rub: int | float) -> str:
    return f"{float(amount_rub):.2f}"


def _auth_header() -> str:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise YooKassaConfigError("YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY не заданы")
    token = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("ascii")


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
        amount_rub=200,
        description="TemichevVet Plus — подписка на 1 месяц",
        metadata={"telegram_id": int(telegram_id), "user_id": int(user_id), "plan_code": "plus"},
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
