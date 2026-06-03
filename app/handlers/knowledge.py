from __future__ import annotations

import html
import logging
import re

logger = logging.getLogger(__name__)

from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.state import default_state

from app.keyboards import main_menu_kb, subscription_kb
from app.texts import ABOUT_TEXT, INVALID_INPUT_TEXT, MAIN_MENU_GUIDE_TEXT
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
from app.constants import SUBSCRIPTION_BUTTONS, build_subscription_text
from app.services.analytics import (
    EVENT_FOOD_COMPLEX_DISH,
    EVENT_FOOD_QUERY,
    EVENT_FOOD_SEARCH_STARTED,
    track_event_by_telegram_id,
    track_fsm_cancel,
    track_fsm_invalid_input,
)
from app.ux import WHAT_NEXT_TEXT, is_cancel_text, what_next_kb

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
    "⬅️ В меню",
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
    waiting_food_composition = State()
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


def _track_food_event(message: Message, event_type: str, payload: dict | None = None) -> bool:
    telegram_id = message.from_user.id if message.from_user else None
    return track_event_by_telegram_id(telegram_id, event_type, payload)


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


COMPLEX_DISH_KEYWORDS = {
    "борщ",
    "гуляш",
    "котлета",
    "котлеты",
    "паста",
    "суп",
    "рагу",
    "плов",
    "салат",
    "запеканка",
    "харчо",
    "щи",
    "уха",
    "солянка",
    "окрошка",
    "суп-пюре",
    "пельмени",
    "вареники",
    "шаурма",
    "пицца",
    "лазанья",
    "ризотто",
    "каша",
    "омлет",
    "сырники",
    "блины",
    "оливье",
    "винегрет",
}

DISH_INGREDIENT_ALIASES = {
    "картошка": "картофель",
    "картошкой": "картофель",
    "луком": "лук",
    "чесноком": "чеснок",
    "солью": "соль",
    "специями": "специи",
    "приправами": "специи",
    "морковью": "морковь",
    "капустой": "капуста",
    "курицей": "курица",
    "говядиной": "говядина",
    "свининой": "свинина",
    "фаршем": "фарш",
    "фарш": "мясо",
    "томатной пастой": "томатная паста",
}

DISH_DANGEROUS_HINTS = {
    "лук": "лук",
    "чеснок": "чеснок",
    "соль": "соль",
    "специи": "специи",
    "соус": "соусы",
    "майонез": "майонез",
    "перец": "острые специи",
}


def _complex_dish_name(text: str) -> str | None:
    normalized = (text or "").strip().lower()
    for keyword in COMPLEX_DISH_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", normalized):
            return keyword
    return None


def _extract_ingredients_from_text(text: str, dish_name: str | None = None) -> list[str]:
    normalized = (text or "").strip().lower()
    if not normalized:
        return []
    if "без " in normalized and not any(mark in normalized for mark in (",", ";", "состав:")):
        return []
    if "состав:" in normalized:
        normalized = normalized.split("состав:", 1)[1]
    elif dish_name:
        normalized = re.sub(rf"\b{re.escape(dish_name)}\b", " ", normalized)

    normalized = re.sub(r"\b(с|из|и|со|в составе|состав)\b", ",", normalized)
    parts = [part.strip(" .;:-—") for part in normalized.replace(";", ",").split(",")]
    return [part for part in parts if len(part) >= 3 and part not in COMPLEX_DISH_KEYWORDS]


def _normalize_dish_ingredient(ingredient: str) -> str:
    value = (ingredient or "").strip().lower()
    return DISH_INGREDIENT_ALIASES.get(value, value)


def _dangerous_dish_hint(ingredient: str) -> str | None:
    value = _normalize_dish_ingredient(ingredient)
    for needle, label in DISH_DANGEROUS_HINTS.items():
        if needle in value:
            return label
    return None


def _dish_composition_prompt(dish_name: str, *, unknown_query: bool = False) -> str:
    safe_name = html.escape((dish_name or "блюдо").strip()[:80])
    if unknown_query:
        intro = (
            f"Я не нашёл «<b>{safe_name}</b>» как отдельный продукт в базе.\n\n"
            "Если это готовое блюдо, я могу проверить его по составу."
        )
    else:
        intro = (
            f"Это готовое блюдо: <b>{safe_name}</b>.\n\n"
            "Я не буду угадывать рецепт, потому что состав может сильно отличаться."
        )

    return (
        f"{intro}\n\n"
        "Напишите ингредиенты через запятую.\n"
        "Пример: говядина, рис, томат, лук, чеснок, соль, специи.\n\n"
        "Если это не блюдо, а отдельный продукт, значит его пока нет в базе. "
        "Попробуйте другое название или близкий по смыслу продукт.\n\n"
        "Чтобы выйти, нажмите «⬅️ В меню» или отправьте /cancel."
    )


def _format_complex_dish_result(dish_name: str, ingredients: list[str]) -> str:
    lines = [
        f"🍽️ <b>{dish_name.capitalize()}: проверка по составу</b>",
        "",
    ]
    if not ingredients:
        lines.append("Я не увидел состав блюда. Перечислите ингредиенты через запятую.")
        return "\n".join(lines)

    unsafe: list[str] = []
    unknown: list[str] = []
    checked: list[str] = []
    for ingredient in ingredients[:12]:
        dangerous_hint = _dangerous_dish_hint(ingredient)
        if dangerous_hint:
            unsafe.append(dangerous_hint)
            checked.append(f"• {ingredient}: ⛔ лучше не давать ({dangerous_hint})")
            continue

        query = _normalize_dish_ingredient(ingredient)
        matches = find_food(query, limit=1)
        if not matches:
            unknown.append(ingredient)
            continue
        item = matches[0]
        name = item.get("name") or ingredient
        allowed = item.get("allowed")
        if allowed is False:
            unsafe.append(str(name))
        checked.append(f"• {ingredient}: {('⛔ нельзя' if allowed is False else '✅ допустимо/с осторожностью')} ({name})")

    if checked:
        lines.append("Проверил ингредиенты:")
        lines.extend(checked)
        lines.append("")
    if unsafe:
        lines.append("Итог: лучше <b>не давать</b>, потому что в составе есть потенциально опасные ингредиенты:")
        lines.append(", ".join(dict.fromkeys(unsafe)))
    elif unknown:
        lines.append("Итог: точный вывод сделать нельзя — часть состава не найдена в базе.")
    else:
        lines.append("Итог: явных опасных ингредиентов по базе не нашёл, но давайте небольшими порциями и без специй.")
    if unknown:
        lines.append("")
        lines.append("Не нашёл в базе: " + ", ".join(unknown))
    lines.append("")
    lines.append("Для готовых блюд важны соль, специи, лук, чеснок, соусы, жирность и способ приготовления.")
    return "\n".join(lines)


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
    _track_food_event(message, EVENT_FOOD_SEARCH_STARTED, {"source": message.text or "nutrition_menu"})
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
        if is_cancel_text(text):
            await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
            return
        # Иначе просто вернём пользователя в главное меню
        await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
        return

    # Универсальный выход
    if is_cancel_text(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="food_search")
        await state.clear()
        await message.answer(
            BACK_TO_MAIN_MENU_TEXT,
            reply_markup=main_menu_kb(),
        )
        return

    if not text:
        track_fsm_invalid_input(
            message.from_user.id,
            await state.get_state(),
            scenario="food_search",
            reason="empty_food_query",
            text=text,
        )
        await message.answer(
            NUTRITION_EMPTY_QUERY,
            reply_markup=nutrition_menu_kb(),
        )
        return

    dish_name = _complex_dish_name(text)
    if dish_name:
        ingredients = _extract_ingredients_from_text(text, dish_name=dish_name)
        if not ingredients:
            await state.update_data(food_dish_name=dish_name)
            await state.set_state(KnowledgeStates.waiting_food_composition)
            _track_food_event(
                message,
                EVENT_FOOD_COMPLEX_DISH,
                {"dish_name": dish_name, "status": "needs_composition", "ingredients_count": 0},
            )
            await message.answer(
                _dish_composition_prompt(dish_name),
                reply_markup=nutrition_menu_kb(),
            )
            return
        _track_food_event(
            message,
            EVENT_FOOD_COMPLEX_DISH,
            {"dish_name": dish_name, "status": "checked", "ingredients_count": len(ingredients)},
        )
        await message.answer(_format_complex_dish_result(dish_name, ingredients), reply_markup=nutrition_menu_kb())
        await message.answer(WHAT_NEXT_TEXT, reply_markup=what_next_kb())
        return

    # Питание доступно всем тарифам — фильтрацию по plan не применяем.
    results = find_food(text, limit=3)
    _track_food_event(
        message,
        EVENT_FOOD_QUERY,
        {"query": text.lower()[:80], "results_count": len(results), "status": "found" if results else "not_found"},
    )

    if not results:
        unknown_dish_name = text.lower()[:80]
        await state.update_data(food_dish_name=unknown_dish_name)
        await state.set_state(KnowledgeStates.waiting_food_composition)
        _track_food_event(
            message,
            EVENT_FOOD_COMPLEX_DISH,
            {"dish_name": unknown_dish_name, "status": "needs_composition", "ingredients_count": 0},
        )
        await message.answer(
            _dish_composition_prompt(unknown_dish_name, unknown_query=True),
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
    await message.answer(WHAT_NEXT_TEXT, reply_markup=what_next_kb())


@router.message(KnowledgeStates.waiting_food_composition)
async def nutrition_handle_complex_dish_composition(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if is_cancel_text(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="food_search")
        await state.clear()
        await message.answer(BACK_TO_MAIN_MENU_TEXT, reply_markup=main_menu_kb())
        return

    data = await state.get_data()
    dish_name = str(data.get("food_dish_name") or "блюдо")
    ingredients = _extract_ingredients_from_text(text, dish_name=None)
    if not ingredients:
        track_fsm_invalid_input(
            message.from_user.id,
            await state.get_state(),
            scenario="food_search",
            reason="empty_dish_composition",
            text=text,
        )
        await message.answer(
            "Напишите состав через запятую. Например: говядина, картофель, морковь, лук, соль.",
            reply_markup=nutrition_menu_kb(),
        )
        return

    _track_food_event(
        message,
        EVENT_FOOD_COMPLEX_DISH,
        {"dish_name": dish_name, "status": "checked", "ingredients_count": len(ingredients)},
    )
    await message.answer(_format_complex_dish_result(dish_name, ingredients), reply_markup=nutrition_menu_kb())
    await message.answer(WHAT_NEXT_TEXT, reply_markup=what_next_kb())
    await state.set_state(KnowledgeStates.waiting_food_query)


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
        if is_cancel_text(text):
            await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
            return
        # Иначе просто вернём пользователя в главное меню
        await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
        return

    if is_cancel_text(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="care_search")
        await state.clear()
        await message.answer(
            BACK_TO_MAIN_MENU_TEXT,
            reply_markup=main_menu_kb(),
        )
        return

    if not text:
        track_fsm_invalid_input(
            message.from_user.id,
            await state.get_state(),
            scenario="care_search",
            reason="empty_care_query",
            text=text,
        )
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
        if is_cancel_text(text):
            await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
            return
        # Иначе просто вернём пользователя в главное меню
        await message.answer(MAIN_MENU_TITLE, reply_markup=main_menu_kb())
        return

    if is_cancel_text(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="faq_search")
        await state.clear()
        await message.answer(
            BACK_TO_MAIN_MENU_TEXT,
            reply_markup=main_menu_kb(),
        )
        return

    if not text:
        track_fsm_invalid_input(
            message.from_user.id,
            await state.get_state(),
            scenario="faq_search",
            reason="empty_faq_query",
            text=text,
        )
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
        await message.answer(
            "Платные тарифы подключаются через раздел «👤 Моя подписка»: там создаётся безопасная ссылка на оплату.",
            reply_markup=subscription_kb(),
        )
        return

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

    await message.answer(f"{ABOUT_TEXT}\n\n{MAIN_MENU_GUIDE_TEXT}", reply_markup=main_menu_kb())


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
