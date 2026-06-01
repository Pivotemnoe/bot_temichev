# Pets v2 — unified Pet Card (overview + sections)
from __future__ import annotations

def _format_age(birth_value: str) -> str | None:
    if not birth_value:
        return None
    s = str(birth_value).strip()
    dt = None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(s[:10], fmt).date()
            break
        except Exception:
            continue
    if dt is None:
        return None
    today = date.today()
    if dt > today:
        return None
    years = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
    months_total = (today.year - dt.year) * 12 + (today.month - dt.month)
    if today.day < dt.day:
        months_total -= 1
    months = months_total % 12
    parts = []
    if years > 0:
        parts.append(f"{years} г")
    parts.append(f"{months} мес")
    return " ".join(parts).strip()


def _age_from_parts(year: int, month: int | None, day: int | None) -> str | None:
    try:
        y = int(year)
    except Exception:
        return None
    m = int(month) if month else 1
    d = int(day) if day else 1
    try:
        dt = date(y, m, d)
    except Exception:
        # fallback: try safest date
        try:
            dt = date(y, 1, 1)
        except Exception:
            return None
    today = date.today()
    years = today.year - dt.year
    if (today.month, today.day) < (dt.month, dt.day):
        years -= 1
    if years < 0:
        years = 0
    return f"{years} лет"

def _birth_display_ru(year: int, month: int | None, day: int | None, precision: str | None) -> str:
    # precision: 'year' | 'month' | 'day' (may be None)
    y = int(year) if year else None
    m = int(month) if month else None
    d = int(day) if day else None
    prec = (precision or '').strip().lower()
    if y is None:
        return "—"
    if prec == 'day' or (d is not None and m is not None):
        return f"{d:02d}.{m:02d}.{y}"
    if prec == 'month' or m is not None:
        return f"{m:02d}.{y}"
    return str(y)
import re
import html

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, date
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardRemove

from app.keyboards import main_menu_kb, onb_step3_kb
from app.db import (
    get_user_by_telegram_id,
    get_pet_by_id,
    set_main_pet,
    clear_main_pet,
    get_user_pets,
    get_pet_history,
    list_pet_history,
    get_pet_observations,
    get_user_reminders,
    list_pet_vaccinations,
    list_pet_measurements,
    update_pet_name,
    update_pet_birth,
    update_pet_sex,
    update_pet_weight,
    update_pet_breed,
    delete_pet,
)
from app.services.safe_edit import safe_edit_message
from app.services.analytics import EVENT_PET_SET_MAIN, track_event

router = Router()


def _render_text(text: str) -> str:
    """Escape text to be safe with HTML parse_mode (prevents Telegram entity parsing errors)."""
    return html.escape(text or "", quote=False)



class PetCardEditStates(StatesGroup):
    waiting_name = State()
    waiting_birth = State()
    waiting_sex = State()
    waiting_weight = State()
    waiting_breed = State()

def _edit_menu_kb(pet_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Имя", callback_data=_cb("edit_name", pet_id))
    kb.button(text="Дата рождения", callback_data=_cb("edit_birth", pet_id))
    kb.button(text="Пол", callback_data=_cb("edit_sex", pet_id))
    kb.button(text="Порода", callback_data=_cb("edit_breed", pet_id))
    kb.button(text="⬅️ Назад", callback_data=_cb("overview", pet_id))
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def _parse_birth(s: str) -> tuple[int|None,int|None,int|None,str|None]:
    s = (s or '').strip()
    if not s:
        return None, None, None, None
    # RU-friendly formats:
    #   ДД.ММ.ГГГГ / ДД-ММ-ГГГГ / ДД/ММ/ГГГГ
    #   ММ.ГГГГ    / ММ-ГГГГ    / ММ/ГГГГ
    #   ГГГГ
    # Backward compatible:
    #   YYYY-MM / YYYY-MM-DD
    s_norm = s.replace('/', '.').replace('-', '.')
    if re.fullmatch(r"\d{4}", s_norm):
        return int(s_norm), None, None, 'year'
    if re.fullmatch(r"\d{1,2}\.\d{4}", s_norm):
        mm, yyyy = s_norm.split('.')
        return int(yyyy), int(mm), None, 'month'
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", s_norm):
        dd, mm, yyyy = s_norm.split('.')
        return int(yyyy), int(mm), int(dd), 'day'
    # ISO-like backward compatibility
    if re.fullmatch(r"\d{4}\.\d{1,2}", s_norm):
        yyyy, mm = s_norm.split('.')
        return int(yyyy), int(mm), None, 'month'
    if re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", s_norm):
        yyyy, mm, dd = s_norm.split('.')
        return int(yyyy), int(mm), int(dd), 'day'
    return None, None, None, None

def _format_observation(o: dict) -> str:
    """Format observation into a readable, non-technical bullet line.

    Expected schema: {id, type, payload:dict|str, source, created_at}.
    """
    o = o or {}
    otype = (o.get("type") or "наблюдение").strip()
    payload = o.get("payload")
    created = (o.get("created_at") or "").strip()

    def _dt_suffix() -> str:
        return f" ({created})" if created else ""

    # Most common: dict payload
    if isinstance(payload, dict):
        # Special pretty-print for triage artifacts
        if otype.lower() == "triage":
            emo = payload.get("urgency_emoji")
            label = payload.get("urgency_label")
            why = payload.get("why") or payload.get("reason")
            complaint = payload.get("complaint")
            summary = payload.get("summary")
            response = payload.get("response")

            header = "Триаж"
            if emo or label:
                header = f"{emo or ''} {label or 'Триаж'}".strip()

            parts: list[str] = []
            if complaint:
                parts.append(f"Жалоба: {str(complaint).strip()}")
            if summary:
                s = str(summary).strip()
                if len(s) > 220:
                    s = s[:217] + "…"
                parts.append(f"Кратко: {s}")
            if why and not summary:
                w = str(why).strip()
                if len(w) > 220:
                    w = w[:217] + "…"
                parts.append(f"Почему: {w}")
            if response and not summary:
                r = str(response).strip()
                if len(r) > 220:
                    r = r[:217] + "…"
                parts.append(r)

            if parts:
                return f"• {header}: " + " / ".join(parts) + _dt_suffix()
            return f"• {header}" + _dt_suffix()

        # Generic dict payload: show selected key=value pairs
        items = []
        for k, v in payload.items():
            if v is None or v == "":
                continue
            items.append((str(k), v))
        items = items[:6]
        if items:
            payload_s = ", ".join([f"{k}={v}" for k, v in items])
            return f"• {otype}: {payload_s}" + _dt_suffix()
        return f"• {otype}" + _dt_suffix()

    # String payload
    if isinstance(payload, str) and payload.strip():
        s = payload.strip()
        if len(s) > 240:
            s = s[:237] + "…"
        return f"• {otype}: {s}" + _dt_suffix()

    # Fallback
    return f"• {otype}" + _dt_suffix()


async def _safe_edit_text(message: Message, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    """Edit message text, ignoring Telegram 'message is not modified' error."""
    try:
        await safe_edit_message(message, _render_text(text), reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise


# Callback data prefixes
CB_PREFIX = "petcard"
def _cb(action: str, pet_id: int) -> str:
    return f"{CB_PREFIX}:{action}:{pet_id}"


async def _safe_callback_answer(callback: CallbackQuery, text: str | None = None, *, show_alert: bool = False) -> None:
    """Avoid TelegramBadRequest: query is too old / invalid callback id."""
    try:
        if text is None:
            await callback.answer()
        else:
            await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "response timeout expired" in msg or "query id is invalid" in msg:
            return
        return
    except Exception:
        return


def _normalize_pet(pet: dict) -> dict:
    """Normalize pet dict keys across legacy/new db accessors."""
    if not pet:
        return {}
    if "name" not in pet and "pet_name" in pet:
        pet["name"] = pet.get("pet_name")
    if "type" not in pet and "pet_type" in pet:
        pet["type"] = pet.get("pet_type")
    if "id" not in pet and "pet_id" in pet:
        pet["id"] = pet.get("pet_id")
    return pet

def _pet_title(pet: dict) -> str:
    pet = _normalize_pet(pet)
    ptype = pet.get("type") or "Питомец"
    name = pet.get("name") or "Без имени"
    emoji = "🐾"
    if str(ptype).lower().startswith("кош"):
        emoji = "🐱"
    elif str(ptype).lower().startswith("соб"):
        emoji = "🐶"
    prefix = "⭐ " if int(pet.get("is_main") or 0) == 1 else ""
    return f"{prefix}{emoji} {ptype} — {name}"

def _pet_card_kb(pet_id: int) -> InlineKeyboardMarkup:
    """Main inline keyboard for Pet Card."""
    kb = InlineKeyboardBuilder()
    try:
        is_main = int((get_pet_by_id(pet_id) or {}).get("is_main") or 0) == 1
    except Exception:
        is_main = False

    kb.button(text="📌 Обзор", callback_data=_cb("overview", pet_id))
    if is_main:
        kb.button(text="⭐ Снять основной", callback_data=_cb("unset_main", pet_id))
    else:
        kb.button(text="⭐ Сделать основным", callback_data=_cb("set_main", pet_id))
    kb.button(text="💉 Вакцинации", callback_data=_cb("vaccinations", pet_id))
    kb.button(text="⏰ Напоминания", callback_data=_cb("reminders", pet_id))
    kb.button(text="📊 Наблюдения", callback_data=_cb("observations", pet_id))
    kb.button(text="⚖️ Вес", callback_data=_cb("stats", pet_id))
    kb.button(text="📜 Вся история", callback_data=f"petcard:history:{pet_id}:0:triage")
    kb.button(text="🩺 Разобрать жалобу", callback_data="onb:start_triage")
    kb.button(text="✏️ Изменить", callback_data=_cb("edit", pet_id))
    kb.button(text="🗑 Удалить", callback_data=_cb("delete", pet_id))
    kb.button(text="⬅️ В меню", callback_data=_cb("back_menu", pet_id))
    kb.adjust(2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def _pet_stats_kb(pet_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить вес", callback_data=f"petstats:add:{pet_id}")
    kb.button(text="📋 История веса", callback_data=f"petstats:list:{pet_id}")
    kb.button(text="⬅️ Назад", callback_data=_cb("overview", pet_id))
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def _confirm_delete_kb(pet_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=_cb("delete_confirm", pet_id))
    kb.button(text="❌ Отмена", callback_data=_cb("overview", pet_id))
    kb.adjust(2)
    return kb.as_markup()


def _short_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d.%m")
    except Exception:
        return str(value)[:5] or "—"


def _one_line(value: str | None, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    text = re.sub(r"^\d+\)\s*", "", text)
    text = re.sub(r"^Кратко\s*:\s*", "", text, flags=re.IGNORECASE).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _triage_history_preview_lines(pet_id: int) -> list[str]:
    events = get_pet_history(pet_id=pet_id, limit=3, event_types=["triage"]) if pet_id else []
    if not events:
        return [
            "📜 История разборов: пока пусто",
            "Вы можете начать с разбора жалобы.",
        ]

    lines = [
        "📜 История разборов (последние 3):",
        "Здесь сохраняются разборы состояния питомца, чтобы вы могли видеть динамику и не терять важные детали.",
    ]
    for event in events:
        meta = event.get("metadata") or {}
        emoji = (meta.get("urgency_emoji") or "").strip()
        summary = _one_line(meta.get("summary") or event.get("details") or event.get("title") or "Разбор жалобы")
        prefix = f"{emoji} " if emoji else ""
        lines.append(f"• {_short_dt(event.get('created_at'))} — {prefix}{summary}".strip())
    return lines


def _build_overview_text(pet: dict, owner_id: int) -> str:
    pet = _normalize_pet(pet)
    pet_id = int(pet.get("id") or 0)

    # lightweight "statuses" as counts
    v_count = len(list_pet_vaccinations(pet_id)) if pet_id else 0
    r_count = len(get_user_reminders(owner_id)) if owner_id else 0
    o_count = len(get_pet_observations(pet_id)) if pet_id else 0

    lines = [
        f"📇 Карточка питомца",
        f"{_pet_title(pet)}",
        "",
    ]

    # basic pet fields (to reflect edits)
    details = []
    breed = pet.get("breed") or pet.get("pet_breed")
    sex = pet.get("sex") or pet.get("pet_sex")
    # normalize sex codes
    if isinstance(sex, str):
        sx = sex.strip().lower()
        if sx in {"m", "male", "самец"}:
            sex = "м"
        elif sx in {"f", "female", "самка"}:
            sex = "ж"
    if breed:
        details.append(f"• Порода: {breed}")
    if sex:
        details.append(f"• Пол: {sex}")
    # Последний актуальный вес из измерений (pet_measurements), если есть
    last_weight = None
    if pet_id:
        try:
            ms = list_pet_measurements(pet_id, limit=1)
            if ms:
                lw = ms[0].get("weight_kg")
                if lw is not None:
                    last_weight = lw
        except Exception:
            last_weight = None

    weight = (
        last_weight
        or pet.get("weight")
        or pet.get("pet_weight")
        or pet.get("weight_kg")
        or pet.get("weightKg")
        or pet.get("pet_weight_kg")
    )

    # Дата рождения хранится в pets.birth_year/birth_month/birth_day (+ birth_precision)
    birth_year = pet.get("birth_year")
    birth_month = pet.get("birth_month")
    birth_day = pet.get("birth_day")
    birth_prec = pet.get("birth_precision")
    legacy_birth = pet.get("birth") or pet.get("birth_date") or pet.get("dob") or pet.get("pet_birth")

    if weight is not None and str(weight).strip() != "":
        if isinstance(weight, (int, float)):
            w_txt = f"{weight} кг"
        else:
            w = str(weight).strip()
            w_txt = w if "кг" in w.lower() else f"{w} кг"
        details.append(f"• Вес: {w_txt}")

    if birth_year:
        age = _age_from_parts(int(birth_year), int(birth_month) if birth_month else None, int(birth_day) if birth_day else None)
        if age:
            details.append(f"• Возраст: {age}")
        details.append(f"• Дата рождения: {_birth_display_ru(int(birth_year), int(birth_month) if birth_month else None, int(birth_day) if birth_day else None, str(birth_prec) if birth_prec else None)}")
    elif legacy_birth:
        age = _format_age(str(legacy_birth))
        if age:
            details.append(f"• Возраст: {age}")
        details.append(f"• Дата рождения: {legacy_birth}")
    if details:
        lines += ["Данные:"] + details + [""]

    lines += [
        "Статусы:",
        f"• 💉 Вакцинации: {v_count}",
        f"• ⏰ Напоминания: {r_count}",
        f"• 📊 Наблюдения: {o_count}",
        "",
        *_triage_history_preview_lines(pet_id),
        "",
        "Выберите раздел ниже 👇",
    ]
    return "\n".join(lines)

async def show_pet_card(message: Message, pet_id: int) -> None:
    user = get_user_by_telegram_id(message.chat.id)
    if not user:
        await message.answer(
            "Сначала нажмите /start, чтобы зарегистрироваться.",
            reply_markup=main_menu_kb(),
        )
        return

    pet = _normalize_pet(get_pet_by_id(pet_id))
    if not pet or int(pet.get("id") or 0) != int(pet_id):
        await message.answer("Питомец не найден.", reply_markup=main_menu_kb())
        return

    # Надёжнее, чем edit_text: отправляем карточку отдельным сообщением и убираем reply-клавиатуру.
    text = _build_overview_text(pet, owner_id=user["id"])
    await message.answer(_render_text(text), reply_markup=_pet_card_kb(pet_id))


@router.message(F.text.in_({"🐾 Карточка питомца", "🐾 Питомцы (v2)"}))
async def entry_from_menu(message: Message):
    """Fallback entry: opens the first pet card if user has pets."""
    user = get_user_by_telegram_id(message.chat.id)
    if not user:
        await message.answer("Сначала нажмите /start, чтобы зарегистрироваться.", reply_markup=main_menu_kb())
        return
    pets = get_user_pets(user["id"])
    if not pets:
        await message.answer("У вас пока нет питомцев. Добавьте питомца через раздел «Питомцы».", reply_markup=main_menu_kb())
        return
    first = _normalize_pet(pets[0])
    await show_pet_card(message, int(first["id"]))

@router.callback_query(F.data.startswith(f"{CB_PREFIX}:"))
async def pet_card_callbacks(callback: CallbackQuery, state: FSMContext):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await _safe_callback_answer(callback)
        return
    _, action, pet_id_s = parts
    try:
        pet_id = int(pet_id_s)
    except ValueError:
        await _safe_callback_answer(callback)
        return

    user = get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await _safe_callback_answer(callback, "Нажмите /start", show_alert=True)
        return

    pet = _normalize_pet(get_pet_by_id(pet_id))
    if not pet:
        await _safe_callback_answer(callback, "Питомец не найден", show_alert=True)
        return

    if action == "set_main":
        if set_main_pet(user["id"], pet_id):
            track_event(user["id"], EVENT_PET_SET_MAIN, {"pet_id": int(pet_id)})
            updated_pet = _normalize_pet(get_pet_by_id(pet_id))
            text = _build_overview_text(updated_pet, owner_id=user["id"])
            await _safe_edit_text(callback.message, text, reply_markup=_pet_card_kb(pet_id))
            await callback.message.answer("✅ Основной питомец выбран. Можно перейти к разбору жалобы.", reply_markup=onb_step3_kb())
            await _safe_callback_answer(callback, "Основной питомец выбран")
        else:
            await _safe_callback_answer(callback, "Не удалось выбрать питомца", show_alert=True)
        return

    if action == "unset_main":
        if clear_main_pet(user["id"]):
            updated_pet = _normalize_pet(get_pet_by_id(pet_id))
            text = _build_overview_text(updated_pet, owner_id=user["id"])
            await _safe_edit_text(callback.message, text, reply_markup=_pet_card_kb(pet_id))
            await _safe_callback_answer(callback, "Основной питомец снят")
        else:
            await _safe_callback_answer(callback, "Не удалось снять основной статус", show_alert=True)
        return

    if action == "overview":
        text = _build_overview_text(pet, owner_id=user["id"])
        await _safe_edit_text(callback.message, text, reply_markup=_pet_card_kb(pet_id))
        await _safe_callback_answer(callback)
        return

    if action == "vaccinations":
        v = list_pet_vaccinations(pet_id)
        lines = [f"💉 Вакцинации — {_pet_title(pet)}", ""]
        if not v:
            lines.append("Пока нет записей о вакцинациях.")
        else:
            for row in v[:20]:
                # tolerate different schemas
                dt = row.get("date") or row.get("vaccination_date") or row.get("at") or ""
                name = row.get("name") or row.get("vaccine") or row.get("title") or "вакцинация"
                lines.append(f"• {name} — {dt}".rstrip(" —"))
        await _safe_edit_text(callback.message, "\n".join(lines), reply_markup=_pet_card_kb(pet_id))
        await _safe_callback_answer(callback)
        return

    if action == "reminders":
        # show reminders for owner (not pet-specific in current schema)
        rems = get_user_reminders(user["id"])
        lines = [f"⏰ Напоминания — {_pet_title(pet)}", ""]
        if not rems:
            lines.append("Напоминаний пока нет.")
        else:
            for r in rems[:20]:
                when = r.get("when") or r.get("date") or r.get("dt") or ""
                text = r.get("text") or r.get("title") or "напоминание"
                lines.append(f"• {when} — {text}".rstrip(" —"))
        await _safe_edit_text(callback.message, "\n".join(lines), reply_markup=_pet_card_kb(pet_id))
        await _safe_callback_answer(callback)
        return

    if action in ("observations", "obs"):
        obs = get_pet_observations(pet_id)
        lines = [f"📊 Наблюдения — {_pet_title(pet)}", ""]
        if not obs:
            lines.append("Наблюдений пока нет.")
        else:
            for o in obs[:20]:
                lines.append(_format_observation(o))
        await _safe_edit_text(callback.message, "\n".join(lines), reply_markup=_pet_card_kb(pet_id))
        await _safe_callback_answer(callback)
        return

    if action == "stats":
        measurements = list_pet_measurements(pet_id, limit=10)
        lines = [f"⚖️ Вес — {_pet_title(pet)}", ""]
        if not measurements:
            lines.append("Записей веса пока нет. Добавьте первую запись.")
        else:
            last = measurements[0]
            w = last.get("weight_kg")
            dt = last.get("created_at","")[:16].replace("T"," ")
            lines.append(f"Последний вес: {w} кг ({dt})")
            if len(measurements) >= 2 and w is not None:
                prev = measurements[1].get("weight_kg")
                if prev is not None:
                    delta = float(w) - float(prev)
                    sign = "+" if delta >= 0 else ""
                    lines.append(f"Изменение vs предыдущий: {sign}{delta:.2f} кг")
        await _safe_edit_text(callback.message, "\n".join(lines), reply_markup=_pet_stats_kb(pet_id))
        await _safe_callback_answer(callback)
        return


    if action == "history":
        hist = list_pet_history(pet_id, limit=10)
        lines = [f"📜 История — {_pet_title(pet)}", ""]
        if not hist:
            lines.append("История пока пустая.")
        else:
            for h in hist:
                ts = h.get("ts") or h.get("created_at") or ""
                note = h.get("text") or h.get("complaint") or h.get("note") or ""
                lines.append(f"• {ts}\n  {note}".strip())
        await _safe_edit_text(callback.message, "\n".join(lines), reply_markup=_pet_card_kb(pet_id))
        await _safe_callback_answer(callback)
        return

    if action == "delete":
        await _safe_edit_text(
            callback.message,
            f"Вы уверены, что хотите удалить {_pet_title(pet)}?\n\nЭто действие нельзя отменить.",
            reply_markup=_confirm_delete_kb(pet_id),
        )
        await _safe_callback_answer(callback)
        return

    if action == "delete_confirm":
        delete_pet(user["id"], pet_id)
        await callback.message.answer(_render_text("✅ Питомец удалён."), reply_markup=main_menu_kb())
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await _safe_callback_answer(callback)
        return

    if action == "edit":
        await _safe_edit_text(
            callback.message,
            f"✏️ Редактирование — {_pet_title(pet)}\n\nВыберите поле, которое хотите изменить:",
            reply_markup=_edit_menu_kb(pet_id),
        )
        await _safe_callback_answer(callback)
        return

    
    if action == "edit_name":
        await _safe_callback_answer(callback)
        await state.set_state(PetCardEditStates.waiting_name)
        await state.update_data(pet_id=pet_id)
        await callback.message.answer("Введите новое имя питомца (или '-' чтобы очистить):", reply_markup=ReplyKeyboardRemove())
        return

    if action == "edit_birth":
        await _safe_callback_answer(callback)
        await state.set_state(PetCardEditStates.waiting_birth)
        await state.update_data(pet_id=pet_id)
        await callback.message.answer("Введите дату рождения: ДД.ММ.ГГГГ или ММ.ГГГГ или ГГГГ (или '-' чтобы очистить):", reply_markup=ReplyKeyboardRemove())
        return

    if action == "edit_sex":
        await _safe_callback_answer(callback)
        await state.set_state(PetCardEditStates.waiting_sex)
        await state.update_data(pet_id=pet_id)
        await callback.message.answer("Введите пол питомца (м/ж) (или '-' чтобы очистить):", reply_markup=ReplyKeyboardRemove())
        return

    if action == "edit_weight":
        # Старое редактирование веса отключено: вес ведём через новый сценарий «⚖️ Вес» (petstats).
        await state.clear()
        await _safe_callback_answer(callback, "Вес меняется через «⚖️ Вес» в карточке питомца.", show_alert=True)
        await show_pet_card(callback.message, pet_id)
        return

    if action == "edit_breed":
        await _safe_callback_answer(callback)
        await state.set_state(PetCardEditStates.waiting_breed)
        await state.update_data(pet_id=pet_id)
        await callback.message.answer("Введите породу (или '-' чтобы очистить):", reply_markup=ReplyKeyboardRemove())
        return

    if action == "back_menu":
        # Restore main menu keyboard
        await callback.message.answer(_render_text("Главное меню:"), reply_markup=main_menu_kb())
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await _safe_callback_answer(callback)
        return

    await _safe_callback_answer(callback)
@router.message(PetCardEditStates.waiting_name)
async def pet_edit_name(message: Message, state: FSMContext):
    user = get_user_by_telegram_id(message.chat.id)
    data = await state.get_data()
    pet_id = int(data.get('pet_id') or 0)
    if not user or not pet_id:
        await state.clear()
        await message.answer("Не удалось определить питомца. Вернитесь в «Мои животные».", reply_markup=main_menu_kb())
        return
    new_name = (message.text or '').strip()
    if new_name == '-':
        new_name = None
    update_pet_name(user['id'], pet_id, new_name)
    await state.clear()
    await show_pet_card(message, pet_id)

@router.message(PetCardEditStates.waiting_birth)
async def pet_edit_birth(message: Message, state: FSMContext):
    user = get_user_by_telegram_id(message.chat.id)
    data = await state.get_data()
    pet_id = int(data.get('pet_id') or 0)
    if not user or not pet_id:
        await state.clear()
        await message.answer("Не удалось определить питомца. Вернитесь в «Мои животные».", reply_markup=main_menu_kb())
        return
    s = (message.text or '').strip()
    if s == '-':
        y=m=d=prec=None
    else:
        y,m,d,prec = _parse_birth(s)
        if prec is None:
            await message.answer("Не понял дату. Форматы: ДД.ММ.ГГГГ / ММ.ГГГГ / ГГГГ. Попробуйте ещё раз:")
            return
    update_pet_birth(user['id'], pet_id, y, m, d, prec)
    await state.clear()
    await show_pet_card(message, pet_id)

@router.message(PetCardEditStates.waiting_sex)
async def pet_edit_sex(message: Message, state: FSMContext):
    user = get_user_by_telegram_id(message.chat.id)
    data = await state.get_data()
    pet_id = int(data.get('pet_id') or 0)
    if not user or not pet_id:
        await state.clear()
        await message.answer("Не удалось определить питомца. Вернитесь в «Мои животные».", reply_markup=main_menu_kb())
        return
    s = (message.text or '').strip().lower()
    if s == '-':
        val=None
    elif s in {'м','m','male','самец'}:
        val='m'
    elif s in {'ж','f','female','самка'}:
        val='f'
    else:
        await message.answer("Введите 'м' или 'ж' (или '-' чтобы очистить):")
        return
    update_pet_sex(user['id'], pet_id, val)
    await state.clear()
    await show_pet_card(message, pet_id)

@router.message(PetCardEditStates.waiting_weight)
async def pet_edit_weight(message: Message, state: FSMContext):
    # Старый хендлер редактирования веса отключён (оставлен как safety-net на случай,
    # если пользователь "застрял" в состоянии из старого сообщения).
    data = await state.get_data()
    pet_id = int(data.get("pet_id") or 0)
    await state.clear()
    if pet_id:
        await message.answer("Вес меняется через «⚖️ Вес» в карточке питомца.")
        await show_pet_card(message, pet_id)
    else:
        await message.answer("Вес меняется через «⚖️ Вес» в карточке питомца.", reply_markup=main_menu_kb())

@router.message(PetCardEditStates.waiting_breed)
async def pet_edit_breed(message: Message, state: FSMContext):
    user = get_user_by_telegram_id(message.chat.id)
    data = await state.get_data()
    pet_id = int(data.get('pet_id') or 0)
    if not user or not pet_id:
        await state.clear()
        await message.answer("Не удалось определить питомца. Вернитесь в «Мои животные».", reply_markup=main_menu_kb())
        return
    s = (message.text or '').strip()
    val = None if s == '-' else s
    update_pet_breed(user['id'], pet_id, val)
    await state.clear()
    await show_pet_card(message, pet_id)
