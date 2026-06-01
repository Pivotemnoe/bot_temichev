# app/pets_v2/reminders.py
from __future__ import annotations

import re
from datetime import datetime
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from app.services.safe_edit import safe_edit_message

from app.db import (
    get_user_by_telegram_id,
    get_pet_by_id,
    get_pet_reminders,
    create_reminder,
    get_user_reminders,
    update_reminder,
    deactivate_reminder,
    add_pet_history_event,
)

router = Router()


async def _safe_callback_answer(cb: CallbackQuery, text: str | None = None, *, show_alert: bool = False) -> None:
    try:
        if text is None:
            await cb.answer()
        else:
            await cb.answer(text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "response timeout expired" in msg or "query id is invalid" in msg:
            return
        return
    except Exception:
        return


def _find_user_reminder(user_id: int, reminder_id: int) -> dict | None:
    """Find a reminder by id среди напоминаний пользователя.

    В проекте исторически есть get_user_reminders(user_id). Отдельной
    функции get_user_reminder(...) может не быть, поэтому используем
    поиск по списку для совместимости.
    """
    items = get_user_reminders(user_id)
    for r in items or []:
        try:
            if int(r.get("id") or 0) == int(reminder_id):
                return r
        except Exception:
            continue
    return None



class ReminderV2States(StatesGroup):
    entering_title = State()
    entering_date = State()
    entering_time = State()
    choosing_periodicity = State()
    entering_notes = State()

    editing_title = State()
    editing_date = State()
    editing_time = State()
    editing_periodicity = State()
    editing_notes = State()


def _parse_date(s: str) -> str | None:
    s = (s or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_time(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}", s):
        h, m = s.split(":")
        hh = int(h)
        mm = int(m)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    return None


def _periodicity_kb(pet_id: int, mode: str) -> object:
    # mode: create|edit
    kb = InlineKeyboardBuilder()
    for code, title in [
        ("once", "Один раз"),
        ("daily", "Ежедневно"),
        ("weekly", "Еженедельно"),
        ("monthly", "Ежемесячно"),
    ]:
        kb.button(text=title, callback_data=f"petrem:{mode}:period:{code}:{pet_id}")
    kb.button(text="⬅️ Назад", callback_data=f"petcard:reminders:{pet_id}")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def _pick_kb(pet_id: int, reminders: list[dict], mode: str) -> object:
    # mode: edit|del
    kb = InlineKeyboardBuilder()
    for r in reminders[:20]:
        rid = int(r["id"])
        title = (r.get("title") or "напоминание").strip()
        date = r.get("due_date") or ""
        kb.button(text=f"{title} ({date})", callback_data=f"petrem:{mode}:{rid}:{pet_id}")
    kb.button(text="⬅️ Назад", callback_data=f"petcard:reminders:{pet_id}")
    kb.adjust(1)
    return kb.as_markup()


def _confirm_del_kb(reminder_id: int, pet_id: int) -> object:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Удалить", callback_data=f"petrem:confirmdel:{reminder_id}:{pet_id}")
    kb.button(text="⬅️ Назад", callback_data=f"petcard:reminders:{pet_id}")
    kb.adjust(2)
    return kb.as_markup()


def _back_to_reminders_kb(pet_id: int) -> object:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ К напоминаниям питомца", callback_data=f"petcard:reminders:{pet_id}")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("petrem:add:"))
async def reminders_add_start(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Нажмите /start", show_alert=True)
        return
    _, _, pet_id_s = (cb.data or "").split(":", 2)
    try:
        pet_id = int(pet_id_s)
    except ValueError:
        await cb.answer()
        return
    pet = get_pet_by_id(pet_id)
    if not pet:
        await cb.answer("Питомец не найден", show_alert=True)
        return

    await state.clear()
    await state.update_data(pet_id=pet_id)
    await state.set_state(ReminderV2States.entering_title)
    await cb.message.edit_text("⏰ Добавление напоминания\n\nВведите заголовок напоминания:")
    await cb.answer()


@router.message(ReminderV2States.entering_title)
async def reminders_add_title(msg: Message, state: FSMContext):
    title = (msg.text or "").strip()
    if not title:
        await msg.answer("Введите текст заголовка.")
        return
    await state.update_data(title=title)
    await state.set_state(ReminderV2States.entering_date)
    await msg.answer("Введите дату (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД):")


@router.message(ReminderV2States.entering_date)
async def reminders_add_date(msg: Message, state: FSMContext):
    date_iso = _parse_date(msg.text or "")
    if not date_iso:
        await msg.answer("Не понял дату. Пример: 31.12.2025 или 2025-12-31")
        return
    await state.update_data(due_date=date_iso)
    await state.set_state(ReminderV2States.entering_time)
    await msg.answer("Введите время (ЧЧ:ММ) или отправьте «-», если не нужно:")


@router.message(ReminderV2States.entering_time)
async def reminders_add_time(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    due_time = None
    if text not in ("-", "—"):
        due_time = _parse_time(text)
        if text and due_time is None:
            await msg.answer("Не понял время. Пример: 09:30 или «-»")
            return
    await state.update_data(due_time=due_time)
    data = await state.get_data()
    pet_id = int(data["pet_id"])
    await state.set_state(ReminderV2States.choosing_periodicity)
    await msg.answer("Выберите периодичность:", reply_markup=_periodicity_kb(pet_id, "create"))


@router.callback_query(F.data.startswith("petrem:create:period:"))
async def reminders_add_periodicity(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await _safe_callback_answer(cb, "Нажмите /start", show_alert=True)
        return
    parts = (cb.data or "").split(":")
    # petrem:create:period:<code>:<pet_id>
    if len(parts) != 5:
        await _safe_callback_answer(cb)
        return
    _, _, _, code, pet_id_s = parts
    try:
        pet_id = int(pet_id_s)
    except ValueError:
        await _safe_callback_answer(cb)
        return

    data = await state.get_data()
    if not {"pet_id", "title", "due_date"} <= set(data):
        await state.clear()
        await cb.message.edit_text(
            "Создание напоминания было прервано. Начните добавление заново из карточки питомца.",
            reply_markup=_back_to_reminders_kb(pet_id),
        )
        await _safe_callback_answer(cb)
        return

    await state.update_data(periodicity=code)
    await state.set_state(ReminderV2States.entering_notes)
    await cb.message.edit_text("Добавьте заметку (или отправьте «-»):")
    await _safe_callback_answer(cb)


@router.message(ReminderV2States.entering_notes)
async def reminders_add_notes(msg: Message, state: FSMContext):
    user = get_user_by_telegram_id(msg.from_user.id)
    if not user:
        await msg.answer("Нажмите /start")
        return
    data = await state.get_data()
    if not {"pet_id", "title", "due_date", "periodicity"} <= set(data):
        await state.clear()
        await msg.answer("Создание напоминания было прервано. Начните добавление заново из карточки питомца.")
        return
    pet_id = int(data["pet_id"])
    notes_raw = (msg.text or "").strip()
    notes = None if notes_raw in ("-", "—", "") else notes_raw

    rid = create_reminder(
        user_id=int(user["id"]),
        pet_id=pet_id,
        reminder_type="custom",
        title=str(data["title"]),
        due_date=str(data["due_date"]),
        due_time=data.get("due_time"),
        periodicity=str(data["periodicity"]),
        notes=notes,
    )
    # история
    try:
        add_pet_history_event(
            pet_id=pet_id,
            event_type="reminder",
            title=f"Напоминание: {data['title']}",
            details=f"{data['due_date']} {data.get('due_time') or ''}".strip(),
            reminder_id=rid,
            metadata={"periodicity": data["periodicity"], "notes": notes},
        )
    except Exception:
        pass

    await state.clear()
    await msg.answer("✅ Напоминание сохранено.")
    await msg.answer("Откройте карточку питомца → «⏰ Напоминания» для просмотра.")


@router.callback_query(F.data.startswith("petrem:editpick:"))
async def reminders_edit_pick(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Нажмите /start", show_alert=True)
        return
    _, _, pet_id_s = (cb.data or "").split(":", 2)
    try:
        pet_id = int(pet_id_s)
    except ValueError:
        await cb.answer()
        return

    rems = get_pet_reminders(int(user["id"]), pet_id)
    if not rems:
        await cb.answer("Нет напоминаний", show_alert=True)
        return
    await state.clear()
    await cb.message.edit_text("Выберите напоминание для изменения:", reply_markup=_pick_kb(pet_id, rems, "edit"))
    await cb.answer()


@router.callback_query(F.data.startswith("petrem:delpick:"))
async def reminders_del_pick(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Нажмите /start", show_alert=True)
        return
    _, _, pet_id_s = (cb.data or "").split(":", 2)
    try:
        pet_id = int(pet_id_s)
    except ValueError:
        await cb.answer()
        return

    rems = get_pet_reminders(int(user["id"]), pet_id)
    if not rems:
        await cb.answer("Нет напоминаний", show_alert=True)
        return
    await state.clear()
    await cb.message.edit_text("Выберите напоминание для удаления:", reply_markup=_pick_kb(pet_id, rems, "del"))
    await cb.answer()


@router.callback_query(F.data.startswith("petrem:del:"))
async def reminders_del_confirm(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Нажмите /start", show_alert=True)
        return
    parts = (cb.data or "").split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    _, _, rid_s, pet_id_s = parts
    try:
        rid = int(rid_s)
        pet_id = int(pet_id_s)
    except ValueError:
        await cb.answer()
        return
    r = _find_user_reminder(int(user["id"]), rid)
    if not r or int(r.get("user_id") or 0) != int(user["id"]):
        await cb.answer("Напоминание не найдено", show_alert=True)
        return

    await cb.message.edit_text(
        f"Удалить напоминание «{r.get('title') or 'напоминание'}»?",
        reply_markup=_confirm_del_kb(rid, pet_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("petrem:confirmdel:"))
async def reminders_del_do(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Нажмите /start", show_alert=True)
        return
    parts = (cb.data or "").split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    _, _, rid_s, pet_id_s = parts
    try:
        rid = int(rid_s)
        pet_id = int(pet_id_s)
    except ValueError:
        await cb.answer()
        return

    # мягкое удаление (is_active=0)
    deactivate_reminder(rid, user_id=int(user["id"]))
    try:
        add_pet_history_event(
            pet_id=pet_id,
            event_type="reminder",
            title="Напоминание удалено",
            details=f"ID: {rid}",
            reminder_id=rid,
            metadata={"action": "deleted"},
        )
    except Exception:
        pass

    await cb.message.edit_text("✅ Напоминание удалено.", reply_markup=None)
    await cb.answer()


@router.callback_query(F.data.regexp(r"^petrem:edit:\d+:\d+$"))
async def reminders_edit_start(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Нажмите /start", show_alert=True)
        return
    parts = (cb.data or "").split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    _, _, rid_s, pet_id_s = parts
    try:
        rid = int(rid_s)
        pet_id = int(pet_id_s)
    except ValueError:
        await cb.answer()
        return

    r = _find_user_reminder(int(user["id"]), rid)
    if not r or int(r.get("user_id") or 0) != int(user["id"]):
        await cb.answer("Напоминание не найдено", show_alert=True)
        return

    await state.clear()
    await state.update_data(reminder_id=rid, pet_id=pet_id)
    await state.set_state(ReminderV2States.editing_title)
    await cb.message.edit_text(
        f"✏️ Изменение напоминания\n\nТекущий заголовок: {r.get('title')}\n\nВведите новый заголовок (или «-» чтобы оставить):"
    )
    await cb.answer()


@router.message(ReminderV2States.editing_title)
async def reminders_edit_title(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if text and text not in ("-", "—"):
        await state.update_data(title=text)
    await state.set_state(ReminderV2States.editing_date)
    await msg.answer("Введите новую дату (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД) или «-»:")


@router.message(ReminderV2States.editing_date)
async def reminders_edit_date(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if text and text not in ("-", "—"):
        date_iso = _parse_date(text)
        if not date_iso:
            await msg.answer("Не понял дату. Пример: 31.12.2025 или 2025-12-31, либо «-»")
            return
        await state.update_data(due_date=date_iso)
    await state.set_state(ReminderV2States.editing_time)
    await msg.answer("Введите новое время (ЧЧ:ММ) или «-» (оставить/убрать):")


@router.message(ReminderV2States.editing_time)
async def reminders_edit_time(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if text and text not in ("—",):
        if text in ("-", ""):
            # уберём время
            await state.update_data(due_time=None)
        else:
            due_time = _parse_time(text)
            if due_time is None:
                await msg.answer("Не понял время. Пример: 09:30 или «-»")
                return
            await state.update_data(due_time=due_time)

    data = await state.get_data()
    if not {"reminder_id", "pet_id"} <= set(data):
        await state.clear()
        await msg.answer("Редактирование было прервано. Откройте карточку питомца и начните изменение заново.")
        return
    pet_id = int(data["pet_id"])
    await state.set_state(ReminderV2States.editing_periodicity)
    await msg.answer("Выберите периодичность (или нажмите «Назад» для выхода):", reply_markup=_periodicity_kb(pet_id, "edit"))


@router.callback_query(F.data.startswith("petrem:edit:period:"))
async def reminders_edit_periodicity(cb: CallbackQuery, state: FSMContext):
    parts = (cb.data or "").split(":")
    # petrem:edit:period:<code>:<pet_id>
    if len(parts) != 5:
        await _safe_callback_answer(cb)
        return
    _, _, _, code, pet_id_s = parts
    try:
        pet_id = int(pet_id_s)
    except ValueError:
        await _safe_callback_answer(cb)
        return

    data = await state.get_data()
    if not {"reminder_id", "pet_id"} <= set(data):
        await state.clear()
        await cb.message.edit_text(
            "Редактирование было прервано. Откройте напоминания питомца и начните изменение заново.",
            reply_markup=_back_to_reminders_kb(pet_id),
        )
        await _safe_callback_answer(cb)
        return

    await state.update_data(periodicity=code)
    await state.set_state(ReminderV2States.editing_notes)
    await cb.message.edit_text("Введите новую заметку или «-» чтобы оставить как есть (пусто = убрать):")
    await _safe_callback_answer(cb)


@router.message(ReminderV2States.editing_notes)
async def reminders_edit_notes(msg: Message, state: FSMContext):
    user = get_user_by_telegram_id(msg.from_user.id)
    if not user:
        await msg.answer("Нажмите /start")
        return
    data = await state.get_data()
    if not {"reminder_id", "pet_id"} <= set(data):
        await state.clear()
        await msg.answer("Редактирование было прервано. Откройте карточку питомца и начните изменение заново.")
        return
    rid = int(data["reminder_id"])
    pet_id = int(data["pet_id"])

    notes_raw = (msg.text or "").strip()
    # '-' => оставить как есть
    notes_to_set = None
    keep_notes = notes_raw in ("-", "—")
    if not keep_notes:
        notes_to_set = None if notes_raw == "" else notes_raw

    kwargs = {}
    for k in ("title", "due_date", "due_time", "periodicity"):
        if k in data:
            kwargs[k] = data[k]
    if not keep_notes:
        kwargs["notes"] = notes_to_set

    update_reminder(rid, int(user["id"]), **kwargs)
    try:
        add_pet_history_event(
            pet_id=pet_id,
            event_type="reminder",
            title="Напоминание обновлено",
            details=(kwargs.get("title") or "").strip() or None,
            reminder_id=rid,
            metadata={"updated": list(kwargs.keys())},
        )
    except Exception:
        pass

    await state.clear()
    await msg.answer("✅ Напоминание обновлено.")
    await msg.answer("Откройте карточку питомца → «⏰ Напоминания» для просмотра.")
