from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.state import default_state

from app.keyboards import main_menu_kb, subscription_kb
from app.texts import ABOUT_TEXT, INVALID_INPUT_TEXT
from app.system_texts import MAIN_MENU_TITLE, BACK_TO_MAIN_MENU_TEXT, UNKNOWN_STEP_TEXT
from app.knowledge_texts import (
    NUTRITION_SECTION_TEXT,
    NUTRITION_SEARCH_PROMPT,
    NUTRITION_EMPTY_QUERY,
    NUTRITION_NOT_FOUND,
    NUTRITION_TRY_ANOTHER,
    CARE_SECTION_TEXT,
    CARE_EXAMPLES_INTRO,
    CARE_SEARCH_PROMPT,
    CARE_EMPTY_QUERY,
    CARE_NOT_FOUND,
    CARE_TRY_ANOTHER,
    CARE_EMPTY_OR_LOCKED,
    CARE_LOCKED,
    FAQ_SECTION_TEXT,
    FAQ_EMPTY_OR_LOCKED,
    FAQ_SEARCH_PROMPT,
    FAQ_EMPTY_QUERY,
    FAQ_NOT_FOUND,
    FAQ_TRY_ANOTHER,
)
from app.keyboards_knowledge import (
    nutrition_menu_kb,
    faq_menu_kb,
    care_menu_kb,
)
from app.services.knowledge_service import (
    find_food,
    search_faq,
    search_care,
)
from app.db import (
    get_user_by_telegram_id,
    ensure_default_subscription,
    set_subscription_plan,
    get_subscription,
)
from app.constants import SUBSCRIPTION_BUTTONS, SUBSCRIPTION_PLANS, build_subscription_text
from app.services.analytics import EVENT_PAY_CLICKED, track_event

router = Router()

# ===== Кнопки главного меню, которые не должны попадать в fallback =====

MAIN_MENU_TEXTS: set[str] = {
    "➕ Добавить питомца",
    "🐾 Мои питомцы",
    "🩺 Разобрать жалобу",
    "⏰ Напоминания",
    "📅 Напоминания и график",
    "ℹ️ О боте",
        "ℹ️ О боте",
    "💳 Подписка",
    "✉️ Обратная связь",
    "👤 Моя подписка",
    "🍽️ Питание",
    "🧴 Уход и привычки",
    "❓ Вопросы и ответы",
        "❓ Вопрос–Ответ",
    "⬅️ В главное меню",
    "📋 Карточки по уходу",
    "🔍 Найти продукт",
    "🔍 Найти по теме ухода",
    "🔍 Найти ответ по вопросу",
    "✅ Что можно",
    "⛔ Что нельзя",
    "📌 Популярные вопросы",
    "➕ Добавить напоминание",
    "📋 Мои напоминания",
    "🚪 Отписаться и удалить доступ",
}

# Aiogram F.text.in_() стабильно работает с list/tuple (set может не отфильтровать ожидаемо)
MAIN_MENU_TEXTS_LIST: tuple[str, ...] = tuple(MAIN_MENU_TEXTS)


# ===== Состояния FSM для раздела знаний =====


class KnowledgeStates(StatesGroup):
    waiting_food_query = State()
    waiting_faq_query = State()
    waiting_care_query = State()


# ===== Вспомогательные функции =====


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _get_user_plan(message: Message) -> str | None:
    """
    Определение текущего плана пользователя по telegram_id.
    Если пользователя/подписки нет — вернём None (без жёсткого отсека).
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        return None

    # Гарантируем наличие подписки по умолчанию
    sub = ensure_default_subscription(user["id"])
    if not sub:
        return None

    plan = sub.get("plan")
    if not plan:
        return None

    return str(plan)


    plan_meta = SUBSCRIPTION_PLANS.get(plan_code, SUBSCRIPTION_PLANS["free"])
    # plan_meta['title'] используем только как резерв — текст ниже даёт понятные расшифровки

    lines: list[str] = []
    lines.append("💳 Ваша подписка")
    lines.append("")

    if plan_code == "free":
        lines.append("Текущий тариф: <b>Free</b> — бесплатно")
        lines.append("")
        lines.append("Как работает Free:")
        lines.append("• до <b>5 запросов по здоровью</b> питомцев в первый месяц;")
        lines.append("• базовый интеллект: простая логика и короткие понятные рекомендации в типичных ситуациях;")
        lines.append("• доступ к разделам «Можно / нельзя», «Уход и привычки» и FAQ;")
        lines.append("• до <b>10 активных напоминаний</b> в течение первых 30 дней после регистрации;")
        lines.append("• после 30 дней новые напоминания можно создавать только на платных тарифах.")
    elif plan_code == "plus":
        lines.append("Текущий тариф: <b>Plus</b> — 200 ₽/мес")
        lines.append("")
        lines.append("Что даёт Plus:")
        lines.append("• до <b>10 запросов по здоровью</b> в месяц;")
        lines.append("• усиленный интеллект: более развёрнутые разборы жалоб и аккуратная оценка срочности;")
        lines.append("• расширенные материалы по уходу и FAQ;")
        lines.append("• до <b>20 активных напоминаний</b> по питомцам.")
    elif plan_code == "pro":
        lines.append("Текущий тариф: <b>Pro</b> — 400 ₽/мес")
        lines.append("")
        lines.append("Что даёт Pro:")
        lines.append("• до <b>30 запросов по здоровью</b> в месяц;")
        lines.append(
            "• ещё более мощный интеллект: глубокие разборы сложных случаев, "
            "подробные пояснения по рискам и типичным ошибкам ухода;"
        )
        lines.append("• практически безлимитные напоминания (лимит высокий, в обычной жизни его не достичь).")
    elif plan_code == "vip":
        lines.append("Текущий тариф: <b>VIP</b>")
        lines.append("")
        lines.append("Что даёт VIP:")
        lines.append("• максимум запросов по здоровью и напоминаний;")
        lines.append("• самый мощный интеллект: максимально подробные, индивидуальные подсказки по жалобам;")
        lines.append("• онлайн-консультация доктора Темичева Константина Валерьевича (по предварительному согласованию времени);")
        lines.append("• приоритетное развитие новых функций сначала на этом тарифе.")
    else:
        lines.append(f"Текущий тариф: <b>{plan_meta['title']}</b>")

    lines.append("")
    lines.append("Статистика текущего периода:")
    lines.append(f"• доступно запросов по здоровью: <b>{quota_total}</b>")
    lines.append(f"• использовано: <b>{quota_used}</b>")

    lines.append("")
    lines.append(
        "Чем выше тариф, тем сложнее алгоритмы, которые анализируют жалобы, "
        "и тем более развёрнутыми и аккуратными будут ответы бота."
    )

    lines.append("")
    lines.append(
        "Выберите тариф ниже, если хотите изменить условия доступа.\n"
        "Оплата будет подключена позже — сейчас это только выбор режима."
    )

    return "\n".join(lines)


def _format_food_item(item: dict) -> str:
    name = item.get("name", "Без названия")
    allowed = item.get("allowed", None)

    if allowed is True:
        status = "✅ Можно"
    elif allowed is False:
        status = "⛔ Нельзя"
    else:
        status = "⚠️ Использовать с осторожностью"

    why = item.get("why") or {}
    effects = why.get("effects") or ""
    risk = why.get("risk_level") or ""
    toxicity = why.get("toxicity") or ""

    how_much = item.get("how_much_is_dangerous") or ""
    advice = item.get("advice") or ""
    category = item.get("category") or ""

    parts = [
        f"{status}: <b>{name}</b>",
    ]

    if category:
        parts.append(f"Категория: {category}")

    if toxicity:
        parts.append(f"Токсичность: {toxicity}")

    if effects:
        parts.append(f"Почему это важно: {effects}")

    if risk:
        parts.append(f"Уровень риска: {risk}")

    if how_much:
        parts.append(f"Опасное количество: {how_much}")

    if advice:
        parts.append(f"Совет: {advice}")

    return "\n".join(parts)


def _format_faq_item(item: dict) -> str:
    q = item.get("question", "Вопрос")
    short = item.get("short_answer") or ""
    detailed = item.get("detailed_answer") or ""

    parts = [f"❓ <b>{q}</b>"]
    if short:
        parts.append(f"\nКратко:\n{short}")
    if detailed:
        parts.append(f"\nПодробно:\n{detailed}")
    return "\n".join(parts)


def _format_care_item(item: dict) -> str:
    title = item.get("title", "Карточка ухода")
    summary = item.get("summary") or ""
    details = item.get("details") or ""
    steps = item.get("steps") or []
    warning = item.get("warning") or ""

    parts = [f"📋 <b>{title}</b>"]

    if summary:
        parts.append(f"\nКратко:\n{summary}")

    if details:
        parts.append(f"\nПодробно:\n{details}")

    if steps:
        steps_lines = "\n".join(f"• {s}" for s in steps)
        parts.append(f"\nШаги:\n{steps_lines}")

    if warning:
        parts.append(f"\n⚠️ Важно:\n{warning}")

    return "\n".join(parts)


# ===== Питание: подменю и поиск продукта =====


@router.message(F.text == "🍽️ Питание")
async def menu_food(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/knowledge.py:menu_food user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    await state.clear()
    """Раздел «Питание» — вход в подменю работы с продуктами."""
    await message.answer(
        NUTRITION_SECTION_TEXT,
        reply_markup=nutrition_menu_kb(),
    )


@router.message(F.text == "🔍 Найти продукт")
@router.message(F.text == "✅ Что можно")
@router.message(F.text == "⛔ Что нельзя")
@router.message(F.text == "✅ Что можно")
@router.message(F.text == "⛔ Что нельзя")
@router.message(F.text == "⛔ Что нельзя")
async def nutrition_start_search(message: Message, state: FSMContext) -> None:
    """
    Точка входа в поиск по продуктам.
    Все три кнопки ведут в один сценарий: пользователь вводит название продукта.
    """
    await state.set_state(KnowledgeStates.waiting_food_query)
    await message.answer(
        NUTRITION_SEARCH_PROMPT,
        reply_markup=nutrition_menu_kb(),
    )


@router.message(KnowledgeStates.waiting_food_query)
async def nutrition_handle_query(message: Message, state: FSMContext) -> None:
    """
    Обработка текстового ввода для поиска продукта.
    """
    text = (message.text or "").strip()

    # Если пользователь нажал любую кнопку меню/подменю во время ввода запроса,
    # не воспринимаем это как поисковую строку. Сбрасываем состояние.
    if text in MAIN_MENU_TEXTS_LIST:
        await state.clear()
        # Для ключевых разделов сразу показываем соответствующее подменю
        if text == "🍽️ Питание":
            await menu_food(message, state)
            return
        if text == "🧴 Уход и привычки":
            await menu_care(message, state)
            return
        if text in ("❓ Вопросы и ответы", "❓ Вопрос–Ответ"):
            await menu_faq(message, state)
            return
        if text == "⬅️ В главное меню":
            await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
            return
        # Иначе просто вернём пользователя в главное меню
        await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
        return

    # Универсальный выход
    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(
            BACK_TO_MAIN_MENU_TEXT,
            reply_markup=main_menu_kb(),
        )
        return

    if not text:
        await message.answer(
            NUTRITION_EMPTY_QUERY,
            reply_markup=nutrition_menu_kb(),
        )
        return

    # Питание доступно всем тарифам — фильтрацию по plan не применяем.
    results = find_food(text, limit=3)

    if not results:
        await message.answer(
            "Я не нашёл такой продукт в базе.\n"
            "Попробуйте другое написание или близкий по смыслу вариант.",
            reply_markup=nutrition_menu_kb(),
        )
        return

    for item in results:
        formatted = _format_food_item(item)
        await message.answer(formatted)

    await message.answer(
        NUTRITION_TRY_ANOTHER,
        reply_markup=nutrition_menu_kb(),
    )


# ===== Уход и привычки: меню и поиск =====


@router.message(F.text == "🧴 Уход и привычки")
async def menu_care(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/knowledge.py:menu_care user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    await state.clear()
    """Раздел «Уход и привычки» — вход в подменю карточек ухода."""
    await message.answer(
        CARE_SECTION_TEXT,
        reply_markup=care_menu_kb(),
    )


@router.message(F.text == "📋 Карточки по уходу")
async def care_show_cards(message: Message, state: FSMContext) -> None:
    """
    Показать список базовых карточек ухода (только заголовки и категории).
    Фильтрация по тарифу.
    Подробный текст — через поиск по теме.
    """
    await state.clear()
    plan = _get_user_plan(message)
    items = search_care("", species=None, plan=plan, limit=5)

    if not items:
        await message.answer(
            CARE_EMPTY_OR_LOCKED,
            reply_markup=care_menu_kb(),
        )
        return

    lines = []
    for idx, item in enumerate(items, start=1):
        title = item.get("title", "Карточка ухода")
        category = item.get("category") or ""
        if category:
            lines.append(f"{idx}. {title} — {category}")
        else:
            lines.append(f"{idx}. {title}")

    text = (
        CARE_EXAMPLES_INTRO
    )

    await message.answer(text, reply_markup=care_menu_kb())


@router.message(F.text == "🔍 Найти по теме ухода")
async def care_start_search(message: Message, state: FSMContext) -> None:
    """
    Запрос текста для поиска по карточкам ухода.
    """
    await state.set_state(KnowledgeStates.waiting_care_query)
    await message.answer(
        CARE_SEARCH_PROMPT,
        reply_markup=care_menu_kb(),
    )


@router.message(KnowledgeStates.waiting_care_query)
async def care_handle_query(message: Message, state: FSMContext) -> None:
    """
    Обработка текстового ввода для поиска по уходу.
    С учётом тарифа: если на текущем плане карточки есть, но закрыты,
    покажем аккуратный upsell.
    """
    text = (message.text or "").strip()

    # Если пользователь нажал любую кнопку меню/подменю во время ввода запроса,
    # не воспринимаем это как поисковую строку. Сбрасываем состояние.
    if text in MAIN_MENU_TEXTS_LIST:
        await state.clear()
        # Для ключевых разделов сразу показываем соответствующее подменю
        if text == "🍽️ Питание":
            await menu_food(message, state)
            return
        if text == "🧴 Уход и привычки":
            await menu_care(message, state)
            return
        if text in ("❓ Вопросы и ответы", "❓ Вопрос–Ответ"):
            await menu_faq(message, state)
            return
        if text == "⬅️ В главное меню":
            await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
            return
        # Иначе просто вернём пользователя в главное меню
        await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
        return

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(
            BACK_TO_MAIN_MENU_TEXT,
            reply_markup=main_menu_kb(),
        )
        return

    if not text:
        await message.answer(
            CARE_EMPTY_QUERY,
            reply_markup=care_menu_kb(),
        )
        return

    plan = _get_user_plan(message)

    # 1) Пытаемся найти карточки с учётом тарифа
    items = search_care(text, species=None, plan=plan, limit=3)

    if items:
        for item in items:
            formatted = _format_care_item(item)
            await message.answer(formatted)

        await message.answer(
            CARE_TRY_ANOTHER,
            reply_markup=care_menu_kb(),
        )
        return

    # 2) Ничего не найдено на этом тарифе. Проверяем, есть ли что-то без ограничения по тарифу.
    all_items = search_care(text, species=None, plan=None, limit=3)

    if all_items:
        # Значит, материалы есть, но не открыты текущим тарифом → upsell
        await message.answer(
            "По этой теме есть подробные карточки по уходу, но они недоступны на вашем текущем тарифе.\n\n"
            "Вы можете перейти в раздел «👤 Моя подписка» и выбрать тариф Plus или Pro, "
            "чтобы открыть расширенные материалы по уходу.",
            reply_markup=care_menu_kb(),
        )
        return

    # 3) Вообще нет подходящей карточки
    await message.answer(
        CARE_NOT_FOUND,
        reply_markup=care_menu_kb(),
    )


# ===== Вопрос–Ответ =====


@router.message(F.text.in_(("❓ Вопрос–Ответ", "❓ Вопросы и ответы")))
async def menu_faq(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/knowledge.py:menu_faq user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """Раздел FAQ — вход в подменю вопросов и ответов."""
    await message.answer(
        "Раздел «Вопрос–Ответ».\n"
        "Здесь можно найти ответы на частые вопросы по здоровью, уходу и питанию,"
        " а также поискать по своей теме.",
        reply_markup=faq_menu_kb(),
    )


@router.message(F.text == "📌 Популярные вопросы")
async def faq_popular(message: Message, state: FSMContext) -> None:
    """
    Показываем список популярных вопросов (без развёрнутых ответов).
    Фильтрация по тарифу.
    """
    await state.clear()
    plan = _get_user_plan(message)
    items = search_faq("", species=None, plan=plan, limit=5)

    if not items:
        await message.answer(
            FAQ_EMPTY_OR_LOCKED,
            reply_markup=faq_menu_kb(),
        )
        return

    lines = []
    for idx, item in enumerate(items, start=1):
        q = item.get("question", "Вопрос")
        lines.append(f"{idx}. {q}")

    text = (
        "📌 Популярные вопросы:\n\n"
        + "\n".join(lines)
        + "\n\n"
        "Чтобы получить подробный ответ по своей ситуации, нажмите "
        "«🔍 Найти ответ по вопросу» и опишите свой вопрос словами."
    )

    await message.answer(text, reply_markup=faq_menu_kb())


@router.message(F.text == "🔍 Найти ответ по вопросу")
async def faq_start_search(message: Message, state: FSMContext) -> None:
    """
    Запрос текста для поиска по FAQ.
    """
    await state.set_state(KnowledgeStates.waiting_faq_query)
    await message.answer(
        "Напишите, какой вопрос вас интересует.\n\n"
        "Примеры:\n"
        "• прививки щенку\n"
        "• стерилизация кошки\n"
        "• когда ехать к врачу при поносе",
        reply_markup=faq_menu_kb(),
    )


@router.message(KnowledgeStates.waiting_faq_query)
async def faq_handle_query(message: Message, state: FSMContext) -> None:
    """
    Обработка текстового ввода для поиска FAQ.
    С учётом тарифа: если ответы есть, но закрыты тарифом — показываем upsell.
    """
    text = (message.text or "").strip()

    # Если пользователь нажал любую кнопку меню/подменю во время ввода запроса,
    # не воспринимаем это как поисковую строку. Сбрасываем состояние.
    if text in MAIN_MENU_TEXTS_LIST:
        await state.clear()
        # Для ключевых разделов сразу показываем соответствующее подменю
        if text == "🍽️ Питание":
            await menu_food(message, state)
            return
        if text == "🧴 Уход и привычки":
            await menu_care(message, state)
            return
        if text in ("❓ Вопросы и ответы", "❓ Вопрос–Ответ"):
            await menu_faq(message, state)
            return
        if text == "⬅️ В главное меню":
            await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
            return
        # Иначе просто вернём пользователя в главное меню
        await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
        return

    if text in ("Отменить", "⬅️ В главное меню"):
        await state.clear()
        await message.answer(
            BACK_TO_MAIN_MENU_TEXT,
            reply_markup=main_menu_kb(),
        )
        return

    if not text:
        await message.answer(
            "Пожалуйста, напишите, что вас интересует.",
            reply_markup=faq_menu_kb(),
        )
        return

    plan = _get_user_plan(message)

    # 1) Поиск с учётом тарифа
    items = search_faq(text, species=None, plan=plan, limit=3)

    if items:
        for item in items:
            formatted = _format_faq_item(item)
            await message.answer(formatted)

        await message.answer(
            FAQ_TRY_ANOTHER,
            reply_markup=faq_menu_kb(),
        )
        return

    # 2) Проверяем, есть ли ответы без ограничения по тарифу
    all_items = search_faq(text, species=None, plan=None, limit=3)

    if all_items:
        # Ответы есть в базе, но не открыты текущим тарифом
        await message.answer(
            "По этому вопросу есть подробные ответы в базе, но они доступны на расширенных тарифах.\n\n"
            "Зайдите в раздел «👤 Моя подписка» и выберите тариф Plus или Pro, "
            "чтобы открыть полный доступ к FAQ.",
            reply_markup=faq_menu_kb(),
        )
        return

    # 3) Вообще нет подходящих FAQ
    await message.answer(
        "Я не нашёл ответ в базе FAQ.\n"
        "Попробуйте переформулировать вопрос или задать другую тему.",
        reply_markup=faq_menu_kb(),
    )


# ===== Моя подписка =====

@router.message(F.text.in_(list(SUBSCRIPTION_BUTTONS.keys())))
async def change_subscription_plan(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/knowledge.py:change_subscription_plan user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
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

    if plan_code != "free":
        track_event(user["id"], EVENT_PAY_CLICKED, {"plan_code": plan_code, "reason": "subscription"})

    set_subscription_plan(user["id"], plan_code)
    sub = get_subscription(user["id"])

    text = build_subscription_text(sub)

    await message.answer(text, reply_markup=subscription_kb())


# ===== ℹ️ О боте и ✉️ Обратная связь =====


@router.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    _state = None
    logger.info("[HANDLER] app/handlers/knowledge.py:about_bot user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """
    Краткая справка: что умеет бот и куда нажимать.
    Добавили отправку логотипа перед текстом.
    """
    # Пытаемся отправить логотип, как при /start
    logo_path = "app/static/logo_temichevvet.jpg"
    try:
        photo = FSInputFile(logo_path)
        await message.answer_photo(photo)
    except Exception as e:
        logger.warning("Не удалось отправить логотип в about_bot: %r", e)

    await message.answer(ABOUT_TEXT, reply_markup=main_menu_kb())


@router.message(
    default_state,
    F.text
    & ~F.text.regexp(r"^/")
    & ~F.text.in_(MAIN_MENU_TEXTS_LIST)
)
async def fallback_knowledge(message: Message):
    """
    Фоллбек для текстовых запросов раздела «Знания».

    ВАЖНО:
    - Команды (/xxx и /xxx@BotName) отфильтрованы на уровне декоратора (regexp "^/").
    - Кнопки главного меню отфильтрованы (MAIN_MENU_TEXTS),
      чтобы их могли обрабатывать другие роутеры (menu, triage, feedback и т.п.).
    - Обработчик срабатывает ТОЛЬКО в default_state, чтобы не мешать FSM
      других разделов (triage, напоминания и т.д.).
    """
    text = (message.text or "").strip()
    if text in MAIN_MENU_TEXTS:
        # Не перехватываем кнопки/пункты меню; пусть их обработают другие роутеры
        return
    logger.warning(">>> KNOWLEDGE fallback TRIGGERED, text=%r", text)

    await message.answer(
        INVALID_INPUT_TEXT,
        reply_markup=main_menu_kb(),
    )
