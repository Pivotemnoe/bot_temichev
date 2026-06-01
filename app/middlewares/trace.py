# app/middlewares/trace.py
import logging
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger("handler_trace")

class HandlerTraceMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        logger.info(
            "[TRACE] %s -> %s",
            event.__class__.__name__,
            handler.__name__,
        )
        return await handler(event, data)