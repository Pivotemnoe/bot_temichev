# app/pets_v2/vaccinations.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.db import get_user_by_telegram_id, get_user_pets, get_pet_vaccinations, add_pet_vaccination, add_pet_history_event
from app.keyboards import main_menu_kb
from app.ux import BTN_BACK, BTN_MENU

router = Router(name="pets_v2_vaccinations")


class VaccFlow(StatesGroup):
    waiting_name = State()
    waiting_date = State()


def _vacc_kb(pet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить вакцинацию", callback_data=f"pet:vacc_add:{pet_id}")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data=f"petcard:overview:{pet_id}")],
            [InlineKeyboardButton(text=BTN_MENU, callback_data="pet:back_to_menu")],
        ]
    )


def _fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    # поддержим ISO или YYYY-MM-DD
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y")
    except Exception:
        return value


async def _show_vaccinations(message: Message, pet: dict) -> None:
    vaccs = get_pet_vaccinations(pet["id"])
    lines = [f"💉 Вакцинации — {pet.get('type') or pet.get('pet_type') or ''} — {pet.get('name') or pet.get('pet_name') or ''}", ""]
    if not vaccs:
        lines.append("Пока нет записей о вакцинациях.")
        await message.answer("\n".join(lines), reply_markup=_vacc_kb(pet["id"]))
        return

    for v in vaccs[:30]:
        title = v.get("vaccine_name") or v.get("name") or v.get("title") or "Вакцинация"
        date = _fmt_dt(v.get("vaccinated_at") or v.get("date") or v.get("vaccination_date") or v.get("done_at"))
        lines.append(f"• {title} — {date}")
    await message.answer("\n".join(lines), reply_markup=_vacc_kb(pet["id"]))


@router.callback_query(F.data.startswith("pet:vacc:"))
async def pet_card_open_vaccinations(callback: CallbackQuery, state: FSMContext):
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

    pet = next((p for p in get_user_pets(user["id"]) if p["id"] == pet_id), None)
    if not pet:
        await callback.message.answer("Питомец не найден.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    await state.clear()
    await callback.answer()
    await _show_vaccinations(callback.message, pet)


@router.callback_query(F.data.startswith("pet:vacc_add:"))
async def pet_card_add_vaccination(callback: CallbackQuery, state: FSMContext):
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

    pet = next((p for p in get_user_pets(user["id"]) if p["id"] == pet_id), None)
    if not pet:
        await callback.answer("Питомец не найден.", show_alert=True)
        return

    await state.clear()
    await state.update_data(pet_id=pet_id)
    await state.set_state(VaccFlow.waiting_name)
    await callback.message.answer(
        "Введите название вакцинации (например: «Комплексная», «Рабиес», «Нобивак»).\n\n"
        "Чтобы отменить — напишите «отмена».",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.message(VaccFlow.waiting_name)
async def vacc_waiting_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() in {"отмена", "cancel", "/cancel"}:
        await state.clear()
        await message.answer("Добавление вакцинации отменено.", reply_markup=main_menu_kb())
        return

    await state.update_data(vacc_name=text)
    await state.set_state(VaccFlow.waiting_date)
    await message.answer(
        "Введите дату вакцинации (например: 13.12.2025 или 2025-12-13).\n\n"
        "Чтобы отменить — напишите «отмена».",
        reply_markup=main_menu_kb(),
    )


@router.message(VaccFlow.waiting_date)
async def vacc_waiting_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() in {"отмена", "cancel", "/cancel"}:
        await state.clear()
        await message.answer("Добавление вакцинации отменено.", reply_markup=main_menu_kb())
        return

    data = await state.get_data()
    pet_id = int(data.get("pet_id"))
    name = data.get("vacc_name") or "Вакцинация"

    # нормализуем дату в ISO (YYYY-MM-DD), если возможно
    iso = text
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            iso = datetime.strptime(text, fmt).date().isoformat()
            break
        except Exception:
            pass

    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer("Сначала зарегистрируйтесь через /start.", reply_markup=main_menu_kb())
        return

    pet = next((p for p in get_user_pets(user["id"]) if p["id"] == pet_id), None)
    if not pet:
        await state.clear()
        await message.answer("Питомец не найден.", reply_markup=main_menu_kb())
        return

    try:
        add_pet_vaccination(pet_id=pet_id, vaccine_name=name, vaccinated_at=iso)
    except TypeError:
        add_pet_vaccination(pet_id, name, iso)

    # пишем событие в единую историю питомца
    try:
        add_pet_history_event(
            pet_id=pet_id,
            event_type="vaccination",
            title=f"Вакцинация: {name}",
            details=f"Дата: {iso}" if iso else None,
            metadata={"vaccine": name, "date": iso} if name or iso else {},
        )
    except Exception:
        # история не должна ломать UX вакцинаций
        pass


    await state.clear()
    await message.answer("✅ Вакцинация добавлена.")
    await _show_vaccinations(message, pet)
