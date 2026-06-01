# app/pets_v2/delete.py

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.db import get_user_by_telegram_id, delete_pet
from app.keyboards import main_menu_kb

router = Router(name="pets_v2_delete")


def _confirm_delete_kb(pet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"pet:delete_confirm:{pet_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"pet:delete_cancel:{pet_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="pet:back_to_menu")],
        ]
    )


@router.callback_query(F.data.startswith("pet:delete:"))
async def delete_pet_callback(callback: CallbackQuery):
    """Запрос подтверждения удаления питомца из карточки."""
    try:
        pet_id = int(callback.data.split(":")[-1])
    except Exception:
        await callback.answer("Некорректный идентификатор питомца.", show_alert=True)
        return

    await callback.message.answer(
        "⚠️ Вы уверены, что хотите удалить этого питомца?\n\n"
        "Это действие необратимо: будут удалены данные питомца, связанные напоминания и записи.",
        reply_markup=_confirm_delete_kb(pet_id),
    )

@router.callback_query(F.data.startswith("pet:delete_confirm:"))
async def delete_pet_confirm_callback(callback: CallbackQuery):
    """Фактическое удаление питомца после подтверждения."""
    try:
        pet_id = int(callback.data.split(":")[-1])
    except Exception:
        await callback.answer("Некорректный идентификатор питомца.", show_alert=True)
        return

    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer("Сначала зарегистрируйтесь через /start.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    # БД: delete_pet проверяет user_id, поэтому опасности удалить чужого питомца нет.
    try:
        delete_pet(pet_id, user_id=user["id"])
    except TypeError:
        # на случай старой сигнатуры delete_pet(pet_id, user_id)
        delete_pet(pet_id, user["id"])

    await callback.message.answer("✅ Питомец удалён.", reply_markup=main_menu_kb())
    await callback.answer("Удалено")


@router.callback_query(F.data.startswith("pet:delete_cancel:"))
async def delete_pet_cancel_callback(callback: CallbackQuery):
    await callback.message.answer("Удаление отменено.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "pet:back_to_menu")
async def back_to_main_menu_callback(callback: CallbackQuery):
    """Возврат в главное меню из карточки питомца."""
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())
    await callback.answer()