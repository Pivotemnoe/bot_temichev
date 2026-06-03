from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from app.db import (
    get_user_by_telegram_id,
    ensure_default_subscription,
    get_subscription,
    set_subscription_plan,
)
from app.keyboards import main_menu_kb, subscription_kb, subscription_unsubscribe_confirm_kb

router = Router(name="unsubscribe")


UNSUBSCRIBE_TEXT = "🚪 Отписаться и удалить доступ"


@router.message(F.text == UNSUBSCRIBE_TEXT)
async def unsubscribe_start(message: Message):
    """Запрос подтверждения отключения подписки (downgrade до Free)."""
    tg_id = message.from_user.id
    await _send_unsubscribe_confirmation(message, tg_id)


async def _send_unsubscribe_confirmation(message: Message, telegram_id: int) -> None:
    user = get_user_by_telegram_id(telegram_id)
    if user is None:
        await message.answer(
            "Сначала нажмите /start, чтобы зарегистрироваться.",
            reply_markup=main_menu_kb(),
        )
        return

    ensure_default_subscription(user_id=user["id"])
    sub = get_subscription(user_id=user["id"]) or {}
    current_plan = (sub.get("plan") or "free").lower()

    if current_plan == "free":
        await message.answer(
            "У вас уже активен тариф Free. Отписка не требуется.",
            reply_markup=subscription_kb(),
        )
        return

    await message.answer(
        "Вы уверены, что хотите отключить подписку?"
        "\n\nПосле отключения ваш тариф станет Free.",
        reply_markup=subscription_unsubscribe_confirm_kb(),
    )


@router.callback_query(F.data == "sub:unsubscribe")
async def unsubscribe_start_callback(call: CallbackQuery):
    """Inline-вход в подтверждение отключения подписки."""
    if call.message is None:
        await call.answer()
        return
    await _send_unsubscribe_confirmation(call.message, call.from_user.id)
    await call.answer()


@router.callback_query(F.data == "sub:unsubscribe:cancel")
async def unsubscribe_cancel(call: CallbackQuery):
    await call.answer("Отмена")
    # Возвращаем в экран подписки
    await call.message.answer(
        "Отписка отменена.",
        reply_markup=subscription_kb(),
    )


@router.callback_query(F.data == "sub:unsubscribe:confirm")
async def unsubscribe_confirm(call: CallbackQuery):
    tg_id = call.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        await call.answer("Нужно /start", show_alert=True)
        await call.message.answer(
            "Сначала нажмите /start, чтобы зарегистрироваться.",
            reply_markup=main_menu_kb(),
        )
        return

    ensure_default_subscription(user_id=user["id"])
    # downgrade до Free
    set_subscription_plan(user_id=user["id"], plan_code="free")

    await call.answer("Готово")
    await call.message.answer(
        "✅ Подписка отключена. Теперь у вас тариф Free.",
        reply_markup=main_menu_kb(),
    )
