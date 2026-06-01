# app/pets_v2/stats.py
from __future__ import annotations
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from app.services.safe_edit import safe_edit_message
from app.keyboards import main_menu_kb
from .card import show_pet_card
from app.db import (
    get_user_by_telegram_id,
    get_pet_by_id,
    add_pet_measurement,
    list_pet_measurements,
    update_pet_weight,
    add_pet_history_event,
)
router = Router(name="pets_v2_stats")
CB_PREFIX = "petstats"
class WeightFSM(StatesGroup):
    enter_weight = State()
    enter_note = State()
    confirm_save = State()
def _cb(action: str, pet_id: int, extra: str | None = None) -> str:
    if extra is None:
        return f"{CB_PREFIX}:{action}:{pet_id}"
    return f"{CB_PREFIX}:{action}:{pet_id}:{extra}"
def _safe_edit_text(message, text: str, reply_markup=None) -> None:
    """Edit message text safely (guards 'message is not modified' and falls back to answer)."""
    try:
        return message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return None
        # Fallback: if edit isn't possible for any reason, send a new message
        try:
            return message.answer(text, reply_markup=reply_markup)
        except Exception:
            return None
def _render_weight_history(pet_name: str, ms: list[dict]) -> str:
    lines = [f"📋 История веса — {pet_name}", ""]
    if not ms:
        lines.append("Записей пока нет.")
        return "\n".join(lines)
    for m in ms:
        created = (m.get("created_at") or "")[:16].replace("T", " ")
        w = m.get("weight_kg")
        if w is None:
            w = m.get("value")
        note = (m.get("note") or "").strip()
        s = f"• {created}: {w} кг"
        if note:
            if len(note) > 80:
                note = note[:77] + "…"
            s += f" — {note}"
        lines.append(s)
    return "\n".join(lines)
def _confirm_text(weight: float, note: str | None) -> str:
    lines = ["Проверьте запись перед сохранением:", "", f"⚖️ Вес: <b>{weight}</b> кг"]
    if note:
        lines.append(f"📝 Заметка: {note}")
    else:
        lines.append("📝 Заметка: —")
    lines.append("")
    lines.append("Сохранить?")
    return "\n".join(lines)
def _stats_kb(pet_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить вес", callback_data=_cb("add", pet_id))
    kb.button(text="📋 История веса", callback_data=_cb("list", pet_id))
    kb.button(text="⬅️ В карточку", callback_data=f"petcard:overview:{pet_id}")
    kb.button(text="🏠 Главное меню", callback_data=_cb("menu", pet_id))
    kb.adjust(1, 1, 1, 1)
    return kb
def _confirm_kb(pet_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Сохранить", callback_data=_cb("confirm_save", pet_id))
    kb.button(text="❌ Отменить", callback_data=_cb("cancel", pet_id))
    kb.button(text="⬅️ В карточку", callback_data=f"petcard:overview:{pet_id}")
    kb.adjust(1, 1, 1)
    return kb
def _note_kb(pet_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭️ Пропустить заметку", callback_data=_cb("skip_note", pet_id))
    kb.button(text="❌ Отменить", callback_data=_cb("cancel", pet_id))
    kb.button(text="⬅️ В карточку", callback_data=f"petcard:overview:{pet_id}")
    kb.adjust(1, 1, 1)
    return kb
@router.callback_query(F.data.startswith(f"{CB_PREFIX}:"))
async def petstats_router(callback: CallbackQuery, state: FSMContext) -> None:
    data = (callback.data or "").split(":")
    # petstats:action:pet_id
    if len(data) < 3:
        await callback.answer()
        return
    _, action, pet_id_s, *rest = data
    try:
        pet_id = int(pet_id_s)
    except ValueError:
        await callback.answer()
        return
    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    pet = get_pet_by_id(pet_id)
    if not pet or int(pet.get("owner_id") or 0) != int(user["id"]):
        await callback.answer("Питомец не найден", show_alert=True)
        return
    if action == "skip_note":
        # user skips note entry -> go to confirmation step
        data_state = await state.get_data()
        w = data_state.get("weight")
        if w is None:
            await callback.answer("Сначала введите вес.", show_alert=True)
            return
        await state.update_data(note=None)
        await state.set_state(WeightFSM.confirm_save)
        await safe_edit_message(
            callback.message,
            _confirm_text(float(w), None),
            reply_markup=_confirm_kb(pet_id).as_markup(),
        )
        await callback.answer()
        return
    if action == "confirm_save":
        data_state = await state.get_data()
        w = data_state.get("weight")
        if w is None:
            await callback.answer("Нет данных для сохранения.", show_alert=True)
            return
        note = data_state.get("note")
        # persist
        try:
            weight = float(w)
        except Exception:
            await callback.answer("Некорректный вес.", show_alert=True)
            return
        user_id = int(user["id"])
        prev_list = list_pet_measurements(pet_id, limit=2)
        prev_weight = None
        if len(prev_list) >= 1:
            prev_weight = prev_list[0].get("weight_kg")
        add_pet_measurement(
            pet_id=pet_id,
            weight_kg=weight,
            note=note,
            metadata={"source": "petstats"},
        )
        insight_text = None
        if prev_weight is not None:
            try:
                delta = float(weight) - float(prev_weight)
                if abs(delta) >= 0.5 or (prev_weight and abs(delta) / max(abs(float(prev_weight)), 0.001) >= 0.05):
                    sign = "+" if delta >= 0 else ""
                    insight_text = f"Изменение веса: {sign}{delta:.2f} кг по сравнению с предыдущей записью."
            except Exception:
                insight_text = None
        if insight_text:
            try:
                add_pet_history_event(
                    pet_id=pet_id,
                    event_type="insight",
                    title="Изменение веса",
                    details=insight_text,
                    metadata={"kind": "weight_delta"},
                )
            except Exception:
                pass
        await state.clear()
        msg_lines = [f"✅ Вес сохранён: {weight} кг"]
        if insight_text:
            msg_lines += ["", "⚠️ " + insight_text]
        await callback.message.answer("\n".join(msg_lines))
        await show_pet_card(callback.message, pet_id)
        await callback.answer()
        return
    if action == "cancel":
        await state.clear()
        await callback.message.answer("❌ Отменено.")
        await show_pet_card(callback.message, pet_id)
        await callback.answer()
        return
    if action == "add":
        await state.clear()
        await state.update_data(pet_id=pet_id)
        await state.set_state(WeightFSM.enter_weight)
        try:
            await safe_edit_message(
            callback.message,
            "⚖️ Введите вес (кг), например: 4.2",
            reply_markup=_stats_kb(pet_id).as_markup(),
        )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
        await callback.answer()
        return
    if action == "list":
        ms = list_pet_measurements(pet_id, limit=30)
        text = _render_weight_history(pet.get("name") or "питомец", ms)
        await safe_edit_message(callback.message, text, reply_markup=_stats_kb(pet_id).as_markup())
        await callback.answer()
        return
    if action == "menu":
        # Главное меню в проекте реализовано reply-клавиатурой (не inline).
        await callback.message.answer("🏠 Главное меню", reply_markup=main_menu_kb())
        await callback.answer()
        return
    await callback.answer()
@router.message(WeightFSM.enter_weight)
async def weight_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pet_id = int(data.get("pet_id") or 0)
    if not pet_id:
        await state.clear()
        await message.answer("Не удалось определить питомца. Вернитесь в «Мои животные».", reply_markup=main_menu_kb())
        return
    raw = (message.text or "").strip().replace(",", ".")
    try:
        weight = float(raw)
    except ValueError:
        await message.answer("Не понял. Введите число, например: 4.2")
        return
    if weight <= 0 or weight > 200:
        await message.answer("Вес выглядит некорректно. Введите значение в кг (например 4.2).")
        return
    await state.update_data(weight=weight)
    await state.set_state(WeightFSM.enter_note)
    await message.answer(
        "📝 Добавьте заметку к весу (необязательно).\n"        "Например: «после еды», «после прогулки», «на диете».\n\n"        "Либо нажмите «Пропустить заметку».",
        reply_markup=_note_kb(pet_id).as_markup(),
    )
@router.message(WeightFSM.enter_note)
async def note_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pet_id = int(data.get("pet_id") or 0)
    if not pet_id:
        await state.clear()
        await message.answer("Не удалось определить питомца. Вернитесь в «Мои животные».", reply_markup=main_menu_kb())
        return

    note = (message.text or "").strip()
    if note.lower() in ("отмена", "❌ отменить"):
        await state.clear()
        await message.answer("❌ Отменено.")
        await show_pet_card(message, pet_id)
        return

    await state.update_data(note=note or None)
    w = data.get("weight")
    if w is None:
        await state.clear()
        await message.answer("Не удалось прочитать вес. Начните заново через «⚖️ Вес».")
        await show_pet_card(message, pet_id)
        return

    await state.set_state(WeightFSM.confirm_save)
    await message.answer(
        _confirm_text(float(w), note or None),
        reply_markup=_confirm_kb(pet_id).as_markup(),
    )
