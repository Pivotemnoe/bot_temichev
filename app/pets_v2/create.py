# app/pets_v2/create.py
# Pets v2 — создание питомца через inline-entrypoint, чтобы не конфликтовать с legacy handlers.

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardRemove

from app.db import (
    get_user_by_telegram_id,
    create_pet,
    get_pets_for_user,
    ensure_default_subscription,
)
from app.keyboards import pet_type_kb, skip_kb, main_menu_kb, subscription_kb
from app.constants import SUPPORTED_PETS
from app.pets_v2.card import show_pet_card


router = Router(name="pets_v2_create")


# Лимиты по количеству питомцев в зависимости от тарифа.
# Значения синхронизированы с docs/plans_matrix.md (как и в legacy app/handlers/pets.py).
PLAN_PETS_LIMIT: dict[str, int] = {
    "free": 1,
    "plus": 3,
    "pro": 10,
    "vip": 10,
}


def _get_plan_and_limits(user_id: int) -> tuple[str, int, int]:
    """Вернёт (plan_code, pets_limit, current_pets_count)."""
    sub = ensure_default_subscription(user_id)
    plan_code = (sub or {}).get("plan") or "free"
    pets = get_pets_for_user(user_id) or []
    limit = PLAN_PETS_LIMIT.get(plan_code, PLAN_PETS_LIMIT["free"])
    return plan_code, limit, len(pets)


class PetCreateV2States(StatesGroup):
    choosing_type = State()
    choosing_name = State()


@router.callback_query(F.data == "petv2:create")
async def start_create_pet_v2(callback: CallbackQuery, state: FSMContext):
    """Точка входа для создания питомца (v2). Запускается только через inline-кнопку."""
    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Нажмите /start", show_alert=True)
        return

    plan_code, limit, count = _get_plan_and_limits(user["id"])
    if count >= limit:
        # Предложение подписки (hard-limit по питомцам)
        if plan_code == "free":
            text = (
                "На бесплатном тарифе можно добавить только 1 питомца.\n\n"
                "Подписка TemichevVet Plus увеличивает лимит до 3 питомцев, "
                "а Pro — до 10 питомцев."
            )
        elif plan_code == "plus":
            text = (
                "На тарифе Plus достигнут лимит по количеству питомцев (3).\n\n"
                "Подписка TemichevVet Pro увеличивает лимит до 10 питомцев."
            )
        else:
            text = (
                "На вашем тарифе достигнут лимит по количеству питомцев.\n\n"
                "Если вам нужен больший лимит, обратитесь в поддержку TemichevVet."
            )

        await callback.message.answer(text, reply_markup=subscription_kb())
        await callback.answer()
        return

    await state.clear()
    await state.set_state(PetCreateV2States.choosing_type)

    await callback.message.answer(
        "Кого добавляем? Выберите тип питомца:",
        reply_markup=pet_type_kb(),
    )
    await callback.answer()


@router.message(PetCreateV2States.choosing_type, F.text)
async def create_pet_v2_choose_type(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text.lower() in {"отменить", "cancel"}:
        await state.clear()
        await message.answer("Добавление питомца отменено.", reply_markup=main_menu_kb())
        return

    # Нормализуем выбор типа
    pet_type = None
    if "кот" in text.lower() or "кошка" in text.lower() or "🐱" in text:
        pet_type = "cat"
    elif "собак" in text.lower() or "🐶" in text:
        pet_type = "dog"

    if not pet_type or pet_type not in SUPPORTED_PETS:
        await message.answer("Пожалуйста, выберите тип кнопкой ниже:", reply_markup=pet_type_kb())
        return

    await state.update_data(pet_type=pet_type)
    await state.set_state(PetCreateV2States.choosing_name)

    await message.answer(
        "Введите имя питомца (или нажмите «Пропустить», если не хотите указывать имя):",
        reply_markup=skip_kb(),
    )


@router.message(PetCreateV2States.choosing_name, F.text)
async def create_pet_v2_choose_name(message: Message, state: FSMContext):
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer("Сначала нажмите /start, чтобы зарегистрироваться.", reply_markup=main_menu_kb())
        return

    # Проверяем лимит ещё раз на случай конкурентных действий
    plan_code, limit, count = _get_plan_and_limits(user["id"])
    if count >= limit:
        await state.clear()
        await message.answer(
            "Лимит по количеству питомцев достигнут. Откройте подписку, чтобы увеличить лимит.",
            reply_markup=subscription_kb(),
        )
        return

    data = await state.get_data()
    pet_type = (data or {}).get("pet_type")
    if not pet_type:
        await state.clear()
        await message.answer("Не удалось определить тип питомца. Попробуйте снова.", reply_markup=main_menu_kb())
        return

    raw = (message.text or "").strip()
    pet_name: str | None
    if raw.lower() in {"пропустить", "skip"}:
        pet_name = None
    else:
        pet_name = raw[:64] if raw else None

    pet_id = create_pet(owner_id=int(user["id"]), pet_type=str(pet_type), pet_name=pet_name)
    await state.clear()

    await message.answer("✅ Питомец добавлен!", reply_markup=ReplyKeyboardRemove())

    # Сразу открываем карточку нового питомца (v2)
    try:
        await show_pet_card(message, int(pet_id))
    except Exception:
        # fallback — в главное меню
        await message.answer("Открываю главное меню.", reply_markup=main_menu_kb())