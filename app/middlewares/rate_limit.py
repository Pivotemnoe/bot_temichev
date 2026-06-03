from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import ADMIN_IDS


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_sec: int
    message: str


RULES: dict[str, RateLimitRule] = {
    "global_message": RateLimitRule(45, 60, "Слишком много сообщений подряд. Подождите немного и попробуйте снова."),
    "global_callback": RateLimitRule(70, 60, "Слишком много нажатий подряд. Подождите немного."),
    "start": RateLimitRule(5, 60, "Вы часто нажимаете /start. Подождите минуту и попробуйте снова."),
    "triage_start": RateLimitRule(8, 60, "Слишком много попыток начать разбор. Подождите немного."),
    "feedback": RateLimitRule(3, 300, "Слишком много сообщений в обратную связь. Попробуйте позже."),
    "payment_check": RateLimitRule(10, 60, "Слишком много проверок оплаты подряд. Попробуйте через минуту."),
}


class RateLimitMiddleware(BaseMiddleware):
    """Простой per-process rate limit для защиты от пользовательского спама."""

    def __init__(self, *, notify_cooldown_sec: int = 15) -> None:
        self._hits: dict[tuple[int, str], Deque[float]] = defaultdict(deque)
        self._last_notice: dict[tuple[int, str], float] = {}
        self._notify_cooldown_sec = notify_cooldown_sec

    def _bucket_for_message(self, message: Message) -> str:
        text = (message.text or "").strip()
        low = text.casefold()
        if low.startswith("/start"):
            return "start"
        if text in {"🩺 Разобрать жалобу", "❤️ Здоровье"}:
            return "triage_start"
        if low.startswith("/feedback") or text == "✉️ Обратная связь":
            return "feedback"
        return "global_message"

    def _bucket_for_callback(self, callback: CallbackQuery) -> str:
        data = callback.data or ""
        if data in {"onb:start_triage", "clinic:start_triage"}:
            return "triage_start"
        if data.startswith("pay:"):
            return "payment_check"
        return "global_callback"

    def check_allowed(self, user_id: int, bucket: str, now: float | None = None) -> tuple[bool, RateLimitRule]:
        rule = RULES[bucket]
        current = time.monotonic() if now is None else now
        key = (int(user_id), bucket)
        hits = self._hits[key]
        cutoff = current - rule.window_sec
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= rule.limit:
            return False, rule
        hits.append(current)
        return True, rule

    def should_notify(self, user_id: int, bucket: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        key = (int(user_id), bucket)
        last = self._last_notice.get(key, 0)
        if current - last < self._notify_cooldown_sec:
            return False
        self._last_notice[key] = current
        return True

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = None
        bucket = "global_message"
        if isinstance(event, Message):
            user = event.from_user
            bucket = self._bucket_for_message(event)
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            bucket = self._bucket_for_callback(event)

        user_id = int(getattr(user, "id", 0) or 0)
        if not user_id or user_id in ADMIN_IDS:
            return await handler(event, data)

        allowed, rule = self.check_allowed(user_id, bucket)
        if allowed:
            return await handler(event, data)

        logger.warning("Rate limit exceeded user_id=%s bucket=%s", user_id, bucket)
        if not self.should_notify(user_id, bucket):
            return None

        if isinstance(event, Message):
            await event.answer(rule.message)
            return None
        if isinstance(event, CallbackQuery):
            await event.answer(rule.message, show_alert=False)
            return None
        return None
