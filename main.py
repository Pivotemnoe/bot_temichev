# main.py

import asyncio
import logging
from logging import StreamHandler, FileHandler, Formatter

from app.middlewares.trace import HandlerTraceMiddleware
from app.middlewares.rate_limit import RateLimitMiddleware
logging.getLogger("aiogram").setLevel(logging.DEBUG)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import BOT_TOKEN, LOG_LEVEL, ERROR_LOG_PATH
from app.handlers.start import router as start_router
from app.handlers.cancel import router as cancel_router
from app.handlers.onboarding import router as onboarding_router
from app.handlers.menu import router as menu_router
from app.handlers.triage import router as triage_router
from app.handlers.pets import router as pets_router
from app.handlers.observations import router as observations_router
from app.handlers.followup import router as followup_router
from app.handlers.admin import router as admin_router
from app.handlers.clinic import router as clinic_router
from app.handlers import reminders as reminders_handler
from app.handlers.knowledge import router as knowledge_router
from app.pets_v2.router import router as pets_v2_router
from app.handlers.feedback import router as feedback_router
from app.handlers.unsubscribe import router as unsubscribe_router  # ⬅️ ДОБАВЛЕНО
from app.services.reminders_runner import run_reminders_worker
from app.services.followup_runner import run_followups_worker
from app.services.selftest import run_selftest


def setup_logging() -> None:
    """
    Базовая конфигурация логирования:
      - консоль: общий уровень LOG_LEVEL;
      - файл errors.log: только ошибки и выше, с трейсбеком.
    """
    # Общий уровень
    level = getattr(logging, (LOG_LEVEL or "INFO").upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Удаляем возможные дефолтные хендлеры, если basicConfig уже вызывался
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Форматы
    console_format = Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    file_format = Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Консоль
    console_handler = StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # Файл для ошибок
    if ERROR_LOG_PATH:
        error_handler = FileHandler(ERROR_LOG_PATH, encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_format)
        root_logger.addHandler(error_handler)


async def main():
    # 1. Логи
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Запуск TemichevVet Bot v3: инициализация...")

    # 2. Самотест (env, БД, таблицы)
    run_selftest()
    logger.info("SELFTEST пройден, продолжаем старт бота.")

    # 3. Бот
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    # 4. Диспетчер и роутеры
    dp = Dispatcher()

    # 1) Старт и базовая регистрация
    dp.include_router(start_router)
    dp.include_router(cancel_router)
    dp.include_router(onboarding_router)
    dp.include_router(pets_router)
    dp.include_router(pets_v2_router)
    dp.include_router(triage_router)
    dp.include_router(observations_router)
    dp.include_router(followup_router)
    dp.include_router(reminders_handler.router)
    dp.include_router(admin_router)
    dp.include_router(clinic_router)
    dp.include_router(unsubscribe_router)
    dp.include_router(feedback_router)
    dp.include_router(menu_router)
    dp.include_router(knowledge_router)
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.message.middleware(HandlerTraceMiddleware())
    dp.callback_query.middleware(HandlerTraceMiddleware())
    
    # 5. Фоновый воркер напоминаний
    asyncio.create_task(run_reminders_worker(bot))
    asyncio.create_task(run_followups_worker(bot))

    print(
        "TemichevVet Bot v3 — запущен "
        "(регистрация, питомцы, Pets v2, подписки, LLM-оценка состояния, напоминания, знания, help/feedback)."
    )
    logger.info("Старт polling.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
