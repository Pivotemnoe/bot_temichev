# app/handlers/menu.py

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from app.keyboards import (
    main_menu_kb,
    payment_created_kb,
    plus_checkout_kb,
    pro_vip_back_kb,
    subscription_kb,
)
from app.payments.yookassa import (
    YooKassaConfigError,
    YooKassaPaymentValidationError,
    create_plus_payment,
    get_payment,
    validate_plus_payment,
)
from app.db import (
    activate_plus,
    create_payment_record,
    get_last_payment,
    log_user_event,

    get_user_by_telegram_id,
    ensure_default_subscription,
    set_subscription_plan,
    get_subscription,
    update_payment_status,
)
from app.texts import INVALID_INPUT_TEXT
from app.system_texts import MAIN_MENU_TITLE
from app.constants import SUBSCRIPTION_BUTTONS, SUBSCRIPTION_PLANS, build_subscription_text
from app.texts import PLAN_FREE_TEXT, PLAN_PLUS_TEMPLATE, PLAN_PRO_TEMPLATE, PLAN_VIP_TEMPLATE
from app.keyboards_reminders import reminders_menu_kb
from app.keyboards_knowledge import faq_menu_kb
from app.services.subscription_resolver import maybe_show_subscription_offer, DECISION_SOFT
from app.services.static_assets import send_static_photo
from app.services.analytics import EVENT_PAYMENT_SUCCESS, EVENT_PAY_CLICKED, track_event
from app.services.payment_reconcile import payment_access_note, payment_not_found_text, payment_status_label

logger = logging.getLogger(__name__)

router = Router()


def _format_user_period_end(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)[:10]


PLUS_PLAN_DESCRIPTION = f"""🔹 <b>Plus — 200 ₽ / 30 дней</b>

<b>Что входит:</b>
• разовая оплата на <b>30 дней</b>, без автосписаний;
• до <b>10 запросов по здоровью</b> в месяц;
• усиленный разбор жалоб;
• расширенная история по питомцам;
• до <b>20 активных напоминаний</b>;
• до <b>3 питомцев</b>.

{payment_access_note()}

Нажмите кнопку ниже, чтобы перейти к оплате."""

PRO_PLAN_DESCRIPTION = """🔺 <b>Pro — в разработке</b>

Этот тариф пока недоступен для подключения. Сейчас безопасно подключаем только Plus."""

VIP_PLAN_DESCRIPTION = """👑 <b>VIP — в разработке</b>

Этот тариф пока недоступен для подключения. Сейчас безопасно подключаем только Plus."""


# Тексты кнопок главного меню (и алиасы), которые НЕ должны перехватываться меню-фоллбеком.
MAIN_MENU_BUTTONS = (
    "🩺 Разобрать жалобу",
    "❤️ Здоровье",
    "📜 История здоровья",
    "📜 История по здоровью",
    "📊 Наблюдения",
    "🍽️ Питание",
    "❓ Вопросы и ответы",
    "❓ Вопрос–Ответ",
    "⏰ Напоминания",
    "📅 Напоминания и график",
    "🐾 Мои животные",
    "👤 Моя подписка",
    "🏥 Найти клинику",
    "ℹ️ О боте",
    "✉️ Обратная связь",

    # Кнопки подменю (knowledge / reminders / pets / observations) — чтобы не ловил menu fallback
    "🔍 Найти продукт",
    "✅ Что можно",
    "⛔ Что нельзя",
    "📌 Популярные вопросы",
    "🔍 Найти ответ по вопросу",
    "📋 Карточки по уходу",
    "🔍 Найти по теме ухода",
    "➕ Добавить напоминание",
    "📋 Мои напоминания",
    "➕ Добавить питомца",
    "📋 Список питомцев",
    "✏️ Изменить питомца",
    "🗑️ Удалить питомца",
    "➕ Добавить наблюдение",
    "📄 Мои наблюдения",
    "🔍 Поиск по наблюдениям",

    "🧴 Уход и привычки",
    "⬅️ В главное меню",
    "📅 Напоминания",
    "🐾 Питомцы",
    "➕ Добавить животное",
    "🚀 Быстрый старт",
    "🎯 Как пользоваться",
    "📋 Все тарифы",
    "✅ Я оплатил (проверить)",
)


@router.message(F.text == "⏰ Напоминания")
async def menu_schedule(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/menu.py:menu_schedule user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """
    Нажатие кнопки из главного меню.
    Открываем отдельное подменю напоминаний.
    """
    logger.warning(">>> MENU schedule TRIGGERED")
    await message.answer(
        "Раздел «Напоминания и график».\n"
        "Здесь можно создать напоминания о прививках, обработке от паразитов,\n"
        "плановых осмотрах и других важных событиях для питомца.",
        reply_markup=reminders_menu_kb(),
    )

@router.message(F.text.in_(("❓ Вопросы и ответы", "❓ Вопрос–Ответ")))
async def menu_faq(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:menu_faq user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """Раздел FAQ — вход в подменю вопросов и ответов."""
    await message.answer(
        "Раздел «Вопрос–Ответ».\n"
        "Здесь можно найти ответы на частые вопросы по здоровью, уходу и питанию,"
        " а также поискать по своей теме.",
        reply_markup=faq_menu_kb(),
    )


# ================= Моя подписка =================


async def _send_subscription_screen(
    message: Message,
    state: FSMContext,
    telegram_id: int | None = None,
    *,
    force: bool = False,
) -> None:
    tg_id = telegram_id or message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await message.answer(
            "Вы ещё не зарегистрированы. Сначала используйте /start.",
            reply_markup=main_menu_kb(),
        )
        return

    sub = ensure_default_subscription(user["id"])
    text = build_subscription_text(sub)

    data = await state.get_data()
    last_hash = data.get("subscription_last_hash")
    cur_hash = hash(text)
    if not force and last_hash == cur_hash and data.get("last_screen") == "subscription":
        return
    await state.update_data(last_screen="subscription", subscription_last_hash=cur_hash)

    await send_static_photo(message, "subscription_banner.jpg")
    await message.answer(text, reply_markup=subscription_kb())


@router.message(F.text == "👤 Моя подписка")
async def menu_subscription(message: Message, state: FSMContext):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:menu_subscription user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    await _send_subscription_screen(message, state)


@router.callback_query(F.data == "open:subscription")
async def callback_open_subscription(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        await callback.answer()
        return
    await _send_subscription_screen(callback.message, state, telegram_id=callback.from_user.id, force=True)
    await callback.answer()


@router.callback_query(F.data == "open:main_menu")
async def callback_open_main_menu(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        await callback.answer()
        return
    await state.clear()
    await callback.message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("paywall_back:"))
async def callback_paywall_back(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        await callback.answer()
        return

    target = (callback.data or "").split(":", 1)[1]
    if target == "open:subscription":
        await _send_subscription_screen(callback.message, state, telegram_id=callback.from_user.id, force=True)
    else:
        await state.clear()
        await callback.message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    await callback.answer()


@router.message(F.text == "⬅️ В главное меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/menu.py:back_to_main_menu user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    await state.clear()
    user = get_user_by_telegram_id(message.from_user.id)
    if user:
        log_user_event(user["id"], "MENU_OPENED", {})
        decision = maybe_show_subscription_offer(user["id"], "RETENTION_CHECK", {})
        if decision == DECISION_SOFT:
            await message.answer(
                "💡 Подписка открывает доступ к расширенной истории и аналитике по питомцу.",
                reply_markup=subscription_kb(),
            )

    await message.answer(
        MAIN_MENU_TITLE,
        reply_markup=main_menu_kb(),
    )


# ================= Выбор тарифа по кнопке =================


@router.message(F.text.in_(list(SUBSCRIPTION_BUTTONS.keys())))
async def change_subscription_plan(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:change_subscription_plan user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await message.answer(
            "Вы ещё не зарегистрированы. Сначала используйте /start.",
            reply_markup=main_menu_kb(),
        )
        return

    button_text = (message.text or "").strip()
    plan_code = SUBSCRIPTION_BUTTONS.get(button_text)
    if plan_code is None:
        await message.answer(
            "Не удалось определить тариф. Попробуйте выбрать ещё раз.",
            reply_markup=subscription_kb(),
        )
        return

    if plan_code == "plus":
        await message.answer(PLUS_PLAN_DESCRIPTION, reply_markup=plus_checkout_kb())
        return

    if plan_code == "pro":
        await message.answer(PRO_PLAN_DESCRIPTION, reply_markup=pro_vip_back_kb())
        return

    if plan_code == "vip":
        await message.answer(VIP_PLAN_DESCRIPTION, reply_markup=pro_vip_back_kb())
        return

    set_subscription_plan(user["id"], plan_code)
    sub = get_subscription(user["id"])

    text = build_subscription_text(sub)

    await message.answer(text, reply_markup=subscription_kb())


@router.callback_query(F.data == "sub:back")
async def callback_subscription_back(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        await callback.answer()
        return
    await _send_subscription_screen(callback.message, state, telegram_id=callback.from_user.id, force=True)
    await callback.answer()


@router.callback_query(F.data == "pay:plus")
async def callback_pay_plus(callback: CallbackQuery):
    if callback.message is None:
        await callback.answer()
        return

    user = get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Вы ещё не зарегистрированы. Сначала используйте /start.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    track_event(user["id"], EVENT_PAY_CLICKED, {"plan_code": "plus", "reason": "subscription"})

    try:
        payment = await create_plus_payment(user_id=int(user["id"]), telegram_id=int(callback.from_user.id))
    except YooKassaConfigError as e:
        await callback.message.answer(
            f"Оплата пока не настроена: {e}.",
            reply_markup=plus_checkout_kb(),
        )
        await callback.answer()
        return
    except Exception:
        logger.exception("Failed to create YooKassa payment")
        await callback.message.answer(
            "Не удалось создать платёж. Попробуйте позже.",
            reply_markup=plus_checkout_kb(),
        )
        await callback.answer()
        return

    payment_id = payment.get("id")
    confirmation = payment.get("confirmation") or {}
    pay_url = confirmation.get("confirmation_url")

    if payment_id:
        create_payment_record(
            user_id=int(user["id"]),
            provider="yookassa",
            provider_payment_id=str(payment_id),
            plan_code="plus",
            amount_rub=200,
            status=payment.get("status") or "pending",
            raw_payload=payment,
        )

    if not pay_url:
        await callback.message.answer("Платёж создан, но ссылка на оплату не получена. Попробуйте ещё раз.", reply_markup=plus_checkout_kb())
        await callback.answer()
        return

    await callback.message.answer(
        "Платёж создан.\n\n"
        f"{payment_access_note()}\n\n"
        "Откройте оплату, затем вернитесь в бот и нажмите «Я оплатил».",
        reply_markup=payment_created_kb(str(pay_url)),
    )
    await callback.answer()


@router.message(F.text == "📋 Все тарифы")
async def show_all_tariffs(message: Message):
    await message.answer(
        "Тарифы:\n\n"
        "🆓 Free — базовый доступ.\n"
        "🔹 Plus — 200 ₽ за 30 дней, расширенные лимиты и история, без автосписаний.\n"
        "🔺 Pro — в разработке.\n"
        "👑 VIP — в разработке.",
        reply_markup=subscription_kb(),
    )


async def _check_last_payment(message: Message, telegram_id: int) -> None:
    user = get_user_by_telegram_id(telegram_id)
    if user is None:
        await message.answer("Вы ещё не зарегистрированы. Сначала используйте /start.", reply_markup=main_menu_kb())
        return

    last = get_last_payment(int(user["id"]), provider="yookassa")
    if not last:
        await message.answer(payment_not_found_text(), reply_markup=subscription_kb())
        return

    payment_id = str(last["provider_payment_id"])
    try:
        payment = await get_payment(payment_id)
    except YooKassaConfigError as e:
        await message.answer(f"Оплата пока не настроена: {e}.", reply_markup=subscription_kb())
        return
    except Exception:
        logger.exception("Failed to check YooKassa payment")
        await message.answer("Не удалось проверить оплату. Попробуйте позже.", reply_markup=subscription_kb())
        return

    status = (payment.get("status") or "").lower()
    was_succeeded = (last.get("status") or "").lower() == "succeeded"

    if status == "succeeded":
        try:
            validate_plus_payment(
                payment,
                expected_user_id=int(user["id"]),
                expected_telegram_id=int(telegram_id),
                expected_amount_rub=int(last.get("amount_rub") or 200),
            )
        except YooKassaPaymentValidationError as e:
            logger.warning(
                "YooKassa payment validation failed provider_payment_id=%s user_id=%s reason=%s",
                payment_id,
                user["id"],
                e,
            )
            update_payment_status("yookassa", payment_id, "validation_failed", raw_payload=payment)
            await message.answer(
                "Платёж найден, но не прошёл внутреннюю проверку безопасности. "
                "Напишите в поддержку, мы проверим оплату вручную.",
                reply_markup=subscription_kb(),
            )
            return

        paid_at = payment.get("captured_at") or payment.get("created_at")
        update_payment_status("yookassa", payment_id, "succeeded", paid_at=paid_at, raw_payload=payment)
        if not was_succeeded:
            activate_plus(int(user["id"]))
            track_event(
                int(user["id"]),
                EVENT_PAYMENT_SUCCESS,
                {
                    "plan_code": "plus",
                    "amount_rub": int(last.get("amount_rub") or 200),
                    "provider": "yookassa",
                    "provider_payment_id": payment_id,
                },
            )
        sub = get_subscription(int(user["id"]))
        if was_succeeded:
            await message.answer(
                "Этот платёж уже был подтверждён ранее. Повторная проверка не продлевает срок Plus.",
                reply_markup=subscription_kb(),
            )
            await message.answer(build_subscription_text(sub), reply_markup=subscription_kb())
            return

        period_end = (sub or {}).get("period_end")
        until_text = ""
        if period_end:
            until_text = f"\nДействует до: <b>{_format_user_period_end(period_end)}</b>."
        await message.answer(
            "Оплата подтверждена. Plus активирован на 30 дней."
            f"{until_text}\nАвтосписаний нет.",
            reply_markup=subscription_kb(),
        )
        await message.answer(build_subscription_text(sub), reply_markup=subscription_kb())
        return

    if status in {"pending", "waiting_for_capture"}:
        update_payment_status("yookassa", payment_id, status, raw_payload=payment)
        await message.answer("Платёж ещё не завершён. Если вы только что оплатили, попробуйте проверить через минуту.", reply_markup=subscription_kb())
        return

    update_payment_status("yookassa", payment_id, status or "unknown", raw_payload=payment)
    await message.answer(
        f"Статус платежа: {payment_status_label(status)}.\n\n"
        "Если оплата не прошла, создайте новый платёж. Если деньги списались, "
        "напишите через «✉️ Обратная связь» и приложите время оплаты.",
        reply_markup=subscription_kb(),
    )


@router.message(F.text == "✅ Я оплатил (проверить)")
async def check_payment(message: Message):
    await _check_last_payment(message, message.from_user.id)


@router.callback_query(F.data == "pay:check")
async def callback_check_payment(callback: CallbackQuery):
    if callback.message is None:
        await callback.answer()
        return
    await _check_last_payment(callback.message, callback.from_user.id)
    await callback.answer()


# ================= Фоллбек — только для НЕ-команд =================


@router.message(StateFilter(None), F.text & ~F.text.regexp(r"^/") & ~F.text.in_(MAIN_MENU_BUTTONS))
async def fallback(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/menu.py:fallback user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    logger.warning(">>> MENU fallback TRIGGERED, text=%r", message.text)
    await message.answer(
        INVALID_INPUT_TEXT,
        reply_markup=main_menu_kb(),
    )
