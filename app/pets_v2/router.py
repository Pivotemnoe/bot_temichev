from aiogram import Router

from .list import router as list_router
from .create import router as create_router
from .edit import router as edit_router
from .card import router as card_router
from .reminders import router as reminders_router
from .stats import router as stats_router
from .history import router as history_router
from .vaccinations import router as vaccinations_router

router = Router()
# порядок: сначала вход/списки, затем CRUD, затем карточки и секции
router.include_router(list_router)
router.include_router(create_router)
router.include_router(edit_router)
router.include_router(vaccinations_router)
router.include_router(reminders_router)
router.include_router(history_router)
router.include_router(stats_router)
router.include_router(card_router)
