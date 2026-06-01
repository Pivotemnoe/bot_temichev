from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.db import (
    get_user_by_telegram_id,
    create_pet,
    get_pets_for_user,
    ensure_default_subscription,
)
from app.keyboards import pet_type_kb, skip_kb, main_menu_kb, subscription_kb
from app.pets_texts import PETS_ADD_START, PETS_ADD_CANCELLED, PETS_ADDED_SUCCESS
from app.states import AddPetStates
from app.constants import PETS_LIMIT_BY_PLAN, SUPPORTED_PETS
from app.services.analytics import EVENT_PET_CREATED, track_event

router = Router()


def _get_plan_and_limits(user_id: int) -> tuple[str, int, int]:
    """
    Определить тариф пользователя и лимит по количеству питомцев.

    Возвращает (plan_code, pets_limit, current_pets_count).
    План берётся через ensure_default_subscription, чтобы всегда был хотя бы free.
    """
    sub = ensure_default_subscription(user_id)
    plan_code = sub["plan"]
    pets = get_pets_for_user(user_id)
    limit = PETS_LIMIT_BY_PLAN.get(plan_code, PETS_LIMIT_BY_PLAN["free"])
    return plan_code, limit, len(pets)


def _format_pets_list(pets: list[dict]) -> str:
    """
    Сервисная функция для человекочитаемого списка питомцев.
    """
    if not pets:
        return "Питомцы ещё не добавлены."
    lines: list[str] = []
    for p in pets:
        name = p["pet_name"] or "(без имени)"
        lines.append(f"• {p['pet_type']} — {name}")
    return "\n".join(lines)


@router.message(F.text == "➕ Добавить животное")
async def add_pet_start(message: Message, state: FSMContext):
    """
    Старт добавления нового питомца из меню.

    Перед запуском FSM проверяем:
      - зарегистрирован ли пользователь;
      - не превышен ли лимит количества питомцев на его тарифе.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)

    if user is None:
        await message.answer(
            "Вы ещё не зарегистрированы. Сначала используйте /start.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    plan_code, limit, count = _get_plan_and_limits(user["id"])

    if count >= limit:
        # Лимит уже достигнут — предлагаем перейти на более высокий тариф.
        if plan_code == "free":
            upgrade_text = (
                "На текущем тарифе <b>Free</b> вы можете вести только одного питомца.\n\n"
                "Чтобы добавить ещё одно животное, перейдите на тариф <b>Plus</b> или <b>Pro</b> "
                "в разделе «👤 Моя подписка»."
            )
        elif plan_code == "plus":
            upgrade_text = (
                "На тарифе <b>Plus</b> можно вести до двух питомцев.\n\n"
                "Вы уже добавили максимальное количество животных для этого тарифа.\n"
                "Чтобы добавить больше питомцев, перейдите на тариф <b>Pro</b> в разделе «👤 Моя подписка»."
            )
        else:
            # pro / vip — лимит высокий, но всё равно сообщаем корректно
            upgrade_text = (
                "На вашем тарифе достигнут лимит по количеству питомцев.\n\n"
                "Если вам нужен больший лимит, обратитесь в поддержку проекта TemichevVet."
            )

        await message.answer(
            upgrade_text,
            reply_markup=subscription_kb(),
        )
        await state.clear()
        return

    # Лимит не превышен — запускаем FSM добавления питомца.
    await message.answer(
        PETS_ADD_START,
        reply_markup=pet_type_kb(),
    )
    await state.set_state(AddPetStates.waiting_for_pet_type)


@router.message(AddPetStates.waiting_for_pet_type)
async def add_pet_choose_type(message: Message, state: FSMContext):
    """
    Выбор вида питомца (кошка/собака).
    Делаем сопоставление устойчивым к эмодзи и разным формулировкам.
    """
    raw_text = (message.text or "").strip()
    text = raw_text.lower()

    if text in {"отменить", "⬅️ в главное меню"}:
        await message.answer(
            PETS_ADD_CANCELLED,
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    pet_type: str | None = None

    # 1) Пытаемся сопоставить через SUPPORTED_PETS (мягко, без точного совпадения)
    for label, code in SUPPORTED_PETS.items():
        label_lower = label.lower()
        if (
            text == label_lower
            or text in label_lower
            or label_lower in text
        ):
            pet_type = code
            break

    # 2) Дополнительная защита по ключевым словам
    if pet_type is None:
        if "кот" in text or "кошка" in text:
            pet_type = "cat"
        elif "собак" in text:
            pet_type = "dog"

    if pet_type is None:
        await message.answer(
            "Сейчас бот работает только с кошками и собаками.\n"
            "Пожалуйста, выберите вариант из клавиатуры:",
            reply_markup=pet_type_kb(),
        )
        return

    await state.update_data(pet_type=pet_type)

    await message.answer(
        "Если хотите, укажите кличку питомца (например: Барсик).\n"
        "Если не хотите — напишите «Пропустить».",
        reply_markup=skip_kb(),
    )
    await state.set_state(AddPetStates.waiting_for_pet_name)


@router.message(AddPetStates.waiting_for_pet_name)
async def add_pet_set_name(message: Message, state: FSMContext):
    """
    Финальный шаг: кличка питомца (опционально) и сохранение.
    Дополнительно перед созданием ещё раз проверяем лимит по тарифу.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)

    if user is None:
        await message.answer(
            "Пользователь не найден. Сначала используйте /start.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    text = (message.text or "").strip()
    if text.lower() in {"отменить", "⬅️ в главное меню"}:
        await message.answer(
            PETS_ADD_CANCELLED,
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    pet_name = None if text.lower() == "пропустить" else text

    # Проверяем лимит ещё раз на случай, если пользователь успел изменить тариф или добавить питомца другим способом.
    plan_code, limit, count = _get_plan_and_limits(user["id"])
    if count >= limit:
        if plan_code == "free":
            upgrade_text = (
                "На текущем тарифе <b>Free</b> вы можете вести только одного питомца.\n\n"
                "Чтобы добавить ещё одно животное, перейдите на тариф <b>Plus</b> или <b>Pro</b> "
                "в разделе «👤 Моя подписка»."
            )
        elif plan_code == "plus":
            upgrade_text = (
                "На тарифе <b>Plus</b> можно вести до двух питомцев.\n\n"
                "Вы уже добавили максимальное количество животных для этого тарифа.\n"
                "Чтобы добавить больше питомцев, перейдите на тариф <b>Pro</b> в разделе «👤 Моя подписка»."
            )
        else:
            upgrade_text = (
                "На вашем тарифе достигнут лимит по количеству питомцев.\n\n"
                "Если вам нужен больший лимит, обратитесь в поддержку проекта TemichevVet."
            )

        await message.answer(
            upgrade_text,
            reply_markup=subscription_kb(),
        )
        await state.clear()
        return

    # Лимит не превышен — создаём питомца.
    state_data = await state.get_data()
    pet_type = state_data.get("pet_type")

    if not pet_type:
        # Страховка от рассинхронизации состояния.
        await message.answer(
            "Не удалось определить вид питомца. Попробуйте начать добавление снова.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    pet_id = create_pet(user["id"], pet_type, pet_name)
    track_event(
        user["id"],
        EVENT_PET_CREATED,
        {"pet_id": int(pet_id), "pet_type": pet_type},
    )
    pets = get_pets_for_user(user["id"])
    pets_block = _format_pets_list(pets)

    await message.answer(
        PETS_ADDED_SUCCESS.format(pets_block=pets_block),
        reply_markup=main_menu_kb(),
    )
    await state.clear()
