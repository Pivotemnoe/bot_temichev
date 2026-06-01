from __future__ import annotations

from aiogram.types import Message

from app.keyboards import plus_paywall_inline_kb
from app.services.static_assets import send_static_photo


PAYWALL_TEXT = (
    "Plus — спокойствие и системный контроль за здоровьем питомца\n\n"
    "Free помогает время от времени.\n"
    "Plus — когда важно регулярно следить за состоянием питомца.\n\n"
    "В Plus:\n"
    "• больше разборов состояния\n"
    "• история обращений по каждому питомцу\n"
    "• меньше лишних шагов — бот помнит данные\n"
    "• спокойствие и уверенность в срочности ситуации\n\n"
    "Бот помогает оценить срочность ситуации.\n"
    "Мы не ставим диагнозы и не назначаем лечение.\n"
    "Этот ответ не заменяет очный осмотр ветеринарного врача."
)


async def send_plus_paywall(
    message: Message,
    *,
    back_callback_data: str = "open:main_menu",
    show_banner: bool = True,
) -> None:
    if show_banner:
        await send_static_photo(message, "subscription_banner.jpg")

    await message.answer(
        PAYWALL_TEXT,
        reply_markup=plus_paywall_inline_kb(back_callback_data=back_callback_data),
    )


async def send_plus_paywall_explained(
    message: Message,
    *,
    reason: str | None = None,
    reason_text: str | None = None,
    back_callback_data: str = "open:main_menu",
    show_banner: bool = True,
) -> None:
    text = (reason_text or reason or "").strip()
    if text:
        await message.answer(text)
    await send_plus_paywall(message, back_callback_data=back_callback_data, show_banner=show_banner)
