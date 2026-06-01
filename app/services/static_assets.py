from __future__ import annotations

import logging
from pathlib import Path

from aiogram.types import FSInputFile, Message


logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


async def send_static_photo(message: Message, filename: str, caption: str | None = None) -> bool:
    """Best-effort static image sender for product banners."""
    path = STATIC_DIR / filename
    if not path.is_file():
        logger.warning("Static image not found: %s", path)
        return False

    try:
        await message.answer_photo(photo=FSInputFile(str(path)), caption=caption)
        return True
    except Exception:
        logger.exception("Failed to send static image: %s", path)
        return False
