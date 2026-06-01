from __future__ import annotations

from typing import Any, Optional

from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


def _markup_fingerprint(markup: Any) -> Optional[dict]:
    """
    Convert aiogram ReplyMarkup to a stable dict for comparison.
    Returns None if markup is None.
    """
    if markup is None:
        return None
    # aiogram v3 markups are pydantic models
    for attr in ("model_dump", "dict"):
        fn = getattr(markup, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    # fallback: try __dict__
    try:
        return dict(markup.__dict__)
    except Exception:
        return {"repr": repr(markup)}


async def safe_edit_message(
    message: Message,
    text: str,
    *,
    reply_markup: Any = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: Optional[bool] = None,
) -> Message:
    """
    Safe wrapper around message.edit_text() to avoid TelegramBadRequest: message is not modified.

    Strategy:
      1) If text+keyboard are equal to current -> do nothing.
      2) Try edit_text().
      3) If Telegram rejects edit -> fallback to sending a new message (answer()).
    """
    try:
        current_text = message.text or ""
        same_text = (current_text == (text or ""))
        same_kb = (_markup_fingerprint(message.reply_markup) == _markup_fingerprint(reply_markup))
        if same_text and same_kb:
            return message
    except Exception:
        # If message object is unusual, continue to edit attempt.
        pass

    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
        return message
    except TelegramBadRequest as e:
        # Typical case: "message is not modified"
        if "message is not modified" in str(e).lower():
            return message
    except Exception:
        # Non-telegram exceptions -> fallback to answer below
        pass

    # Fallback: send a new message
    await message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )
    return message
