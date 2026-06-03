from __future__ import annotations

import csv
import html
import io
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import (
    ADMIN_CHAT_ID,
    ADMIN_IDS,
    DB_PATH,
    ENVIRONMENT,
    FEEDBACK_CHAT_ID,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
)
from app.db import (
    ensure_default_subscription,
    get_admin_dashboard_stats,
    get_subscription,
    get_user_by_telegram_id,
    list_admin_audit_events,
    log_admin_audit_event,
    set_subscription_plan,
)


router = Router(name="admin")
logger = logging.getLogger(__name__)

ADMIN_DENIED_TEXT = "Команда не распознана. Откройте меню кнопками ниже."
_DENIED_ADMIN_NOTIFY_COOLDOWN_SEC = 300
_denied_admin_notified_at: dict[int, float] = {}

ADMIN_PLUS_HELP_TEXT = (
    "<b>⭐ Ручное управление Plus</b>\n\n"
    "Только для администраторов из ADMIN_IDS.\n\n"
    "Формат команд:\n"
    "<code>выдать плюс TELEGRAM_ID причина</code>\n"
    "<code>снять плюс TELEGRAM_ID причина</code>\n\n"
    "Примеры:\n"
    "<code>выдать плюс 123456789 тестовая выдача после оплаты</code>\n"
    "<code>снять плюс 123456789 возврат платежа</code>\n\n"
    "Причина обязательна и попадёт в админ-аудит."
)


def _is_admin(telegram_id: int | None) -> bool:
    return bool(telegram_id and int(telegram_id) in ADMIN_IDS)


def _admin_attempt_user_label(user) -> str:
    if user is None:
        return "unknown"

    parts = [f"id={getattr(user, 'id', None)}"]
    username = getattr(user, "username", None)
    if username:
        parts.append(f"@{username}")

    full_name = getattr(user, "full_name", None)
    if full_name:
        parts.append(str(full_name))

    return " ".join(parts)


def _user_audit_identity(user) -> tuple[int | None, str | None]:
    if user is None:
        return None, None
    telegram_id = getattr(user, "id", None)
    username = getattr(user, "username", None)
    return (int(telegram_id) if telegram_id else None, str(username) if username else None)


def _log_admin_event(user, action: str, *, target: str | None = None, details: dict | str | None = None) -> None:
    telegram_id, username = _user_audit_identity(user)
    try:
        log_admin_audit_event(
            telegram_id=telegram_id,
            username=username,
            action=action,
            target=target,
            details=details,
        )
    except Exception:
        logger.exception("Failed to write admin audit event action=%s target=%s", action, target)


async def _report_denied_admin_attempt(*, bot, user, source: str) -> None:
    telegram_id = int(getattr(user, "id", 0) or 0)
    logger.warning("Denied admin access source=%s user=%s", source, _admin_attempt_user_label(user))
    _log_admin_event(user, "admin_denied", target=source)

    if not ADMIN_CHAT_ID or not telegram_id:
        return

    now = time.monotonic()
    last_notified = _denied_admin_notified_at.get(telegram_id, 0)
    if now - last_notified < _DENIED_ADMIN_NOTIFY_COOLDOWN_SEC:
        return

    _denied_admin_notified_at[telegram_id] = now
    try:
        await bot.send_message(
            ADMIN_CHAT_ID,
            "⚠️ Попытка открыть админ-панель\n"
            f"Источник: {html.escape(source)}\n"
            f"Пользователь: {html.escape(_admin_attempt_user_label(user))}",
        )
    except Exception:
        logger.exception("Failed to notify admin about denied admin access")


def _admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Сегодня", callback_data="admin:period:today"),
                InlineKeyboardButton(text="📅 7 дней", callback_data="admin:period:7"),
                InlineKeyboardButton(text="📆 30 дней", callback_data="admin:period:30"),
            ],
            [
                InlineKeyboardButton(text="🧪 Воронка", callback_data="admin:funnel:7"),
                InlineKeyboardButton(text="💳 Подписки", callback_data="admin:subscriptions:30"),
            ],
            [
                InlineKeyboardButton(text="🔁 Удержание", callback_data="admin:retention:30"),
                InlineKeyboardButton(text="🧾 Расходы", callback_data="admin:costs:7"),
            ],
            [InlineKeyboardButton(text="🔗 Источники", callback_data="admin:sources:30")],
            [
                InlineKeyboardButton(text="🛡 Аудит", callback_data="admin:audit:30"),
                InlineKeyboardButton(text="⚙️ Статус", callback_data="admin:status:now"),
            ],
            [InlineKeyboardButton(text="⭐ Plus вручную", callback_data="admin:plushelp:now")],
            [InlineKeyboardButton(text="⬇️ Экспорт CSV", callback_data="admin:export:30")],
        ]
    )


def _period_bounds(kind: str) -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)
    if kind == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return "Сегодня", start.isoformat(), now.isoformat()

    days = int(kind)
    start = now - timedelta(days=days)
    return f"{days} дней", start.isoformat(), now.isoformat()


def _pct(value: int | float, total: int | float) -> str:
    if not total:
        return "0%"
    return f"{(float(value) / float(total)) * 100:.1f}%"


def _fmt_float(value: float) -> str:
    return f"{float(value):.1f}".rstrip("0").rstrip(".")


EVENT_LABELS = {
    "app_start": "Запуски",
    "triage_started": "Начато разборов",
    "triage_completed": "Завершено разборов",
    "paywall_shown": "Показы экрана подписки",
    "pay_clicked": "Клики оплаты",
    "payment_success": "Успешные оплаты",
    "followup_scheduled": "Контрольные вопросы запланированы",
    "followup_sent": "Контрольные вопросы отправлены",
    "followup_answered": "Контрольные вопросы с ответом",
    "pet_created": "Питомцев создано",
    "pet_set_main": "Основной питомец выбран",
}

CSV_SECTION_LABELS = {
    "period": "Период",
    "counts": "События",
    "triage_by_plan": "Разборы по тарифам",
    "urgency": "Срочность",
    "funnel": "Воронка",
    "payments": "Платежи",
    "subscriptions": "Подписки",
    "retention": "Удержание",
    "workload": "Нагрузка",
}

CSV_METRIC_LABELS = {
    **EVENT_LABELS,
    "label": "Название периода",
    "from": "Начало",
    "to": "Конец",
    "count": "Количество",
    "amount_rub": "Сумма, руб.",
    "active": "Активно",
    "d1_cohorts": "Вернулись D1",
    "d7_cohorts": "Вернулись D7",
    "base_cohorts": "База когорт",
    "avg_triage_per_user": "Среднее разборов на пользователя",
    "followup_answered_rate": "Доля ответов на контрольные вопросы",
    "total_tokens": "Всего токенов",
    "avg_tokens_per_triage": "Среднее токенов на разбор",
    "workload_index": "Индекс нагрузки",
    "source_type": "Тип источника",
    "starts": "Запуски",
    "cr_to_pay": "Конверсия в оплату",
}

URGENCY_LABELS = {
    "green": "Зелёная",
    "yellow": "Жёлтая",
    "red": "Красная",
    "unknown": "Не определена",
}

SOURCE_TYPE_LABELS = {
    "direct": "прямой вход",
    "utm": "UTM",
    "clinic_link": "ссылка клиники",
}


def _event_label(key: str) -> str:
    return EVENT_LABELS.get(key, key)


def _csv_section_label(section: str) -> str:
    if section.startswith("sources_"):
        return "Источники"
    return CSV_SECTION_LABELS.get(section, section)


def _csv_metric_label(metric: str) -> str:
    return CSV_METRIC_LABELS.get(metric, metric)


def _source_type_label(value: str | None) -> str:
    raw = str(value or "direct")
    return SOURCE_TYPE_LABELS.get(raw, raw)


def render_admin_period_report(label: str, date_from: str, date_to: str) -> str:
    stats = get_admin_dashboard_stats(date_from, date_to)
    counts = stats["counts"]
    urgency = stats["urgency"]
    payments = stats["payments"]
    triage_by_plan = counts.get("triage_by_plan", {})

    lines = [
        f"<b>📊 Отчёт TemichevVet — {html.escape(label)}</b>",
        "",
        f"Запуски: <b>{counts.get('app_start', 0)}</b>",
        (
            "Разборы жалоб: "
            f"<b>{counts.get('triage_completed', 0)}</b> "
            f"(Free {triage_by_plan.get('free', 0)}, Plus {triage_by_plan.get('plus', 0)}, "
            f"Pro {triage_by_plan.get('pro', 0)}, VIP {triage_by_plan.get('vip', 0)})"
        ),
        (
            "Срочность: "
            f"🟢 зелёная {urgency.get('green', 0)} / "
            f"🟡 жёлтая {urgency.get('yellow', 0)} / "
            f"🟥 красная {urgency.get('red', 0)} / "
            f"не определена {urgency.get('unknown', 0)}"
        ),
        (
            "Контрольные вопросы: "
            f"{counts.get('followup_scheduled', 0)} запланировано / "
            f"{counts.get('followup_sent', 0)} отправлено / "
            f"{counts.get('followup_answered', 0)} с ответом"
        ),
        (
            "Экран подписки: "
            f"{counts.get('paywall_shown', 0)} показов / "
            f"{counts.get('pay_clicked', 0)} кликов оплаты"
        ),
        f"Оплаты: {payments.get('count', 0)} успешных / {_fmt_float(payments.get('amount_rub', 0))} ₽",
        "",
        f"Экран подписки → клик оплаты: <b>{_pct(counts.get('pay_clicked', 0), counts.get('paywall_shown', 0))}</b>",
        f"Клик оплаты → успешная оплата: <b>{_pct(payments.get('count', 0), counts.get('pay_clicked', 0))}</b>",
    ]
    return "\n".join(lines)


def render_admin_funnel_report(label: str, date_from: str, date_to: str) -> str:
    funnel = get_admin_dashboard_stats(date_from, date_to)["funnel"]
    starts = funnel.get("app_start", 0)
    rows = ["app_start", "triage_completed", "paywall_shown", "pay_clicked", "payment_success"]
    lines = [f"<b>🧪 Воронка — {html.escape(label)}</b>", ""]
    for key in rows:
        value = int(funnel.get(key, 0) or 0)
        lines.append(f"{_event_label(key)}: <b>{value}</b> ({_pct(value, starts)} от запусков)")
    return "\n".join(lines)


def render_admin_subscriptions_report(label: str, date_from: str, date_to: str) -> str:
    stats = get_admin_dashboard_stats(date_from, date_to)
    subs = stats["subscriptions"]
    counts = stats["counts"]
    payments = stats["payments"]
    lines = [
        f"<b>💳 Подписки — {html.escape(label)}</b>",
        "",
        f"Free: <b>{subs.get('free', 0)}</b>",
        f"Plus: <b>{subs.get('plus', 0)}</b>",
        f"Pro: <b>{subs.get('pro', 0)}</b>",
        f"VIP: <b>{subs.get('vip', 0)}</b>",
        "",
        f"Показы экрана подписки: {counts.get('paywall_shown', 0)}",
        f"Клики оплаты: {counts.get('pay_clicked', 0)}",
        f"Успешные оплаты: {payments.get('count', 0)} / {_fmt_float(payments.get('amount_rub', 0))} ₽",
    ]
    return "\n".join(lines)


def render_admin_retention_report(label: str, date_from: str, date_to: str) -> str:
    retention = get_admin_dashboard_stats(date_from, date_to)["retention"]
    lines = [
        f"<b>🔁 Удержание — {html.escape(label)}</b>",
        "",
        f"Возврат D1: <b>{_pct(retention.get('d1_cohorts', 0), retention.get('base_cohorts', 0))}</b>",
        f"Возврат D7: <b>{_pct(retention.get('d7_cohorts', 0), retention.get('base_cohorts', 0))}</b>",
        f"База когорт: {retention.get('base_cohorts', 0)}",
        f"Среднее разборов на пользователя: {_fmt_float(retention.get('avg_triage_per_user', 0))}",
        f"Доля ответов на контрольные вопросы: <b>{_pct(retention.get('followup_answered_rate', 0), 1)}</b>",
    ]
    return "\n".join(lines)


def render_admin_costs_report(label: str, date_from: str, date_to: str) -> str:
    stats = get_admin_dashboard_stats(date_from, date_to)
    counts = stats["counts"]
    tokens = stats["tokens"]
    lines = [
        f"<b>🧾 Расходы и нагрузка — {html.escape(label)}</b>",
        "",
        f"Завершено разборов: <b>{counts.get('triage_completed', 0)}</b>",
        f"Контрольных вопросов отправлено: <b>{counts.get('followup_sent', 0)}</b>",
        "",
        f"Всего токенов: <b>{tokens.get('total_tokens', 0)}</b>",
        f"Среднее токенов на разбор: <b>{_fmt_float(tokens.get('avg_tokens_per_triage', 0))}</b>",
        f"Индекс нагрузки: <b>{_fmt_float(tokens.get('workload_index', 0))}</b>",
    ]
    return "\n".join(lines)


def render_admin_sources_report(label: str, date_from: str, date_to: str) -> str:
    stats = get_admin_dashboard_stats(date_from, date_to)
    lines = [f"<b>🔗 Источники — {html.escape(label)}</b>", ""]
    for source in stats["sources"]["utm_source"]:
        lines.append(
            f"{html.escape(str(source['source']))} "
            f"({html.escape(_source_type_label(source.get('source_type')))}): "
            f"{source['starts']} запусков / {source['triage_completed']} разборов / "
            f"{source['payment_success']} оплат / конверсия {_pct(source['payment_success'], source['starts'])}"
        )
    if len(lines) == 2:
        lines.append("Нет запусков за период.")
    return "\n".join(lines)


def render_admin_audit_report(label: str, date_from: str, date_to: str) -> str:
    events = list_admin_audit_events(limit=20)
    lines = [f"<b>🛡 Админ-аудит — {html.escape(label)}</b>", ""]
    if not events:
        lines.append("Событий пока нет.")
        return "\n".join(lines)

    for event in events:
        created_at = str(event.get("created_at") or "")[:19].replace("T", " ")
        telegram_id = event.get("telegram_id") or "?"
        username = f"@{event.get('username')}" if event.get("username") else "без username"
        action = html.escape(str(event.get("action") or "unknown"))
        target = html.escape(str(event.get("target") or ""))
        suffix = f" → {target}" if target else ""
        details_note = _admin_audit_details_note(event.get("details"))
        lines.append(f"• {created_at} — {telegram_id} ({username}): {action}{suffix}{details_note}")
    return "\n".join(lines)


def _admin_audit_details_note(details: str | None) -> str:
    if not details:
        return ""
    try:
        parsed = json.loads(details)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""

    parts: list[str] = []
    if parsed.get("old_plan") or parsed.get("new_plan"):
        parts.append(f"{parsed.get('old_plan', '?')}→{parsed.get('new_plan', '?')}")
    if parsed.get("reason"):
        parts.append(f"причина: {parsed['reason']}")
    if parsed.get("error"):
        parts.append(f"ошибка: {parsed['error']}")
    if not parts:
        return ""
    return " (" + html.escape("; ".join(str(part) for part in parts)) + ")"


def render_admin_status_report() -> str:
    db_exists = bool(DB_PATH and os.path.exists(DB_PATH))
    db_size = os.path.getsize(DB_PATH) if db_exists else 0
    yookassa_configured = bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)
    lines = [
        "<b>⚙️ Статус системы</b>",
        "",
        f"Окружение: <b>{html.escape(ENVIRONMENT)}</b>",
        f"Администраторов: <b>{len(ADMIN_IDS)}</b>",
        f"Чат уведомлений: <b>{'настроен' if ADMIN_CHAT_ID else 'не настроен'}</b>",
        f"Чат обратной связи: <b>{'настроен' if FEEDBACK_CHAT_ID else 'не настроен'}</b>",
        f"YooKassa: <b>{'настроена' if yookassa_configured else 'не настроена'}</b>",
        f"База: <b>{'найдена' if db_exists else 'не найдена'}</b>",
        f"Размер базы: <b>{db_size} байт</b>",
        "",
        "Секреты, токены и ключи здесь не показываются.",
    ]
    return "\n".join(lines)


def _parse_manual_plus_command(text: str) -> tuple[str, int, str] | None:
    raw = (text or "").strip()
    low = raw.casefold()

    plan_code: str | None = None
    rest = ""
    if low.startswith("выдать плюс"):
        plan_code = "plus"
        rest = raw[len("выдать плюс"):].strip()
    elif low.startswith("снять плюс"):
        plan_code = "free"
        rest = raw[len("снять плюс"):].strip()
    else:
        parts = raw.split(maxsplit=1)
        command = parts[0].casefold().split("@", 1)[0] if parts else ""
        if command == "/grant_plus":
            plan_code = "plus"
        elif command == "/revoke_plus":
            plan_code = "free"
        if plan_code:
            rest = parts[1].strip() if len(parts) > 1 else ""

    if not plan_code:
        return None
    parts = rest.split(maxsplit=1)
    if not parts:
        return None
    try:
        target_telegram_id = int(parts[0])
    except ValueError:
        return None
    reason = parts[1].strip() if len(parts) > 1 else ""
    if len(reason) < 3:
        return None
    return plan_code, target_telegram_id, reason


def apply_manual_subscription_change(target_telegram_id: int, plan_code: str) -> dict | None:
    if plan_code not in {"free", "plus"}:
        raise ValueError("manual subscription change supports only free/plus")
    user = get_user_by_telegram_id(int(target_telegram_id))
    if not user:
        return None
    previous = ensure_default_subscription(int(user["id"])) or {}
    old_plan = previous.get("plan") or "free"
    set_subscription_plan(int(user["id"]), plan_code)
    current = get_subscription(int(user["id"])) or {}
    return {
        "user_id": int(user["id"]),
        "telegram_id": int(target_telegram_id),
        "old_plan": old_plan,
        "new_plan": current.get("plan") or plan_code,
    }


def render_admin_csv_export(label: str, date_from: str, date_to: str) -> bytes:
    stats = get_admin_dashboard_stats(date_from, date_to)
    rows: list[list[str | int | float]] = []

    def add(section: str, metric: str, key: str, value: str | int | float) -> None:
        rows.append([_csv_section_label(section), _csv_metric_label(metric), key, value])

    add("period", "label", "", label)
    add("period", "from", "", stats["period"]["from"])
    add("period", "to", "", stats["period"]["to"])

    counts = stats["counts"]
    for metric in (
        "app_start",
        "triage_started",
        "triage_completed",
        "paywall_shown",
        "pay_clicked",
        "payment_success",
        "followup_scheduled",
        "followup_sent",
        "followup_answered",
        "pet_created",
        "pet_set_main",
    ):
        add("counts", metric, "", counts.get(metric, 0))

    for plan, value in sorted((counts.get("triage_by_plan") or {}).items()):
        add("triage_by_plan", "triage_completed", str(plan), value)

    for urgency, value in stats["urgency"].items():
        add("urgency", "triage_completed", URGENCY_LABELS.get(str(urgency), str(urgency)), value)

    for metric, value in stats["funnel"].items():
        add("funnel", metric, "", value)

    for metric, value in stats["payments"].items():
        add("payments", metric, "", value)

    for plan, value in stats["subscriptions"].items():
        add("subscriptions", "active", str(plan), value)

    for metric, value in stats["retention"].items():
        add("retention", metric, "", value)

    for metric, value in stats["tokens"].items():
        add("workload", metric, "", value)

    for source_group, sources in stats["sources"].items():
        for source in sources:
            source_key = str(source.get("source") or "unknown")
            add(f"sources_{source_group}", "source_type", source_key, _source_type_label(source.get("source_type")))
            add(f"sources_{source_group}", "starts", source_key, source.get("starts", 0))
            add(f"sources_{source_group}", "triage_completed", source_key, source.get("triage_completed", 0))
            add(f"sources_{source_group}", "payment_success", source_key, source.get("payment_success", 0))
            add(f"sources_{source_group}", "amount_rub", source_key, source.get("amount_rub", 0))
            add(f"sources_{source_group}", "cr_to_pay", source_key, source.get("cr_to_pay", 0))

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["Раздел", "Метрика", "Ключ", "Значение"])
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _admin_export_filename(arg: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_arg = "".join(ch for ch in arg if ch.isalnum()) or "period"
    return f"temichevvet_admin_{safe_arg}_{stamp}.csv"


@router.message(Command("admin"))
@router.message(F.text.casefold().in_(("админ", "admin")))
async def admin_menu(message: Message) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not _is_admin(telegram_id):
        await _report_denied_admin_attempt(bot=message.bot, user=message.from_user, source="message:admin")
        await message.answer(ADMIN_DENIED_TEXT)
        return
    _log_admin_event(message.from_user, "admin_open", target="message")
    await message.answer("<b>Админ-панель TemichevVet</b>", reply_markup=_admin_menu_kb())


@router.message(F.text.regexp(r"(?i)^(выдать плюс|снять плюс|/grant_plus(?:@\w+)?|/revoke_plus(?:@\w+)?)\b"))
async def admin_manual_plus(message: Message) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not _is_admin(telegram_id):
        await _report_denied_admin_attempt(bot=message.bot, user=message.from_user, source="message:manual_plus")
        await message.answer(ADMIN_DENIED_TEXT)
        return

    parsed = _parse_manual_plus_command(message.text or "")
    if not parsed:
        _log_admin_event(message.from_user, "manual_plus_invalid", target="command")
        await message.answer(ADMIN_PLUS_HELP_TEXT, reply_markup=_admin_menu_kb())
        return

    plan_code, target_telegram_id, reason = parsed
    result = apply_manual_subscription_change(target_telegram_id, plan_code)
    if not result:
        _log_admin_event(
            message.from_user,
            "manual_plus_failed",
            target=str(target_telegram_id),
            details={"plan_code": plan_code, "reason": reason, "error": "user_not_found"},
        )
        await message.answer(
            "Пользователь не найден в базе. Он должен сначала нажать /start в боте.",
            reply_markup=_admin_menu_kb(),
        )
        return

    _log_admin_event(
        message.from_user,
        "manual_subscription_change",
        target=str(target_telegram_id),
        details={**result, "reason": reason},
    )
    action = "выдан" if plan_code == "plus" else "снят"
    await message.answer(
        f"Готово: Plus {action}.\n\n"
        f"Telegram ID: <b>{target_telegram_id}</b>\n"
        f"Тариф: <b>{html.escape(str(result['old_plan']))}</b> → <b>{html.escape(str(result['new_plan']))}</b>\n"
        f"Причина: {html.escape(reason)}",
        reply_markup=_admin_menu_kb(),
    )


@router.callback_query(F.data.startswith("admin:"))
async def admin_callbacks(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await _report_denied_admin_attempt(bot=callback.bot, user=callback.from_user, source="callback:admin")
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    report = parts[1] if len(parts) > 1 else "period"
    arg = parts[2] if len(parts) > 2 else "7"
    _log_admin_event(callback.from_user, "admin_callback", target=report, details={"arg": arg})

    if report == "status":
        text = render_admin_status_report()
        if callback.message:
            await callback.message.answer(text, reply_markup=_admin_menu_kb())
        await callback.answer()
        return

    if report == "plushelp":
        if callback.message:
            await callback.message.answer(ADMIN_PLUS_HELP_TEXT, reply_markup=_admin_menu_kb())
        await callback.answer()
        return

    label, date_from, date_to = _period_bounds(arg)

    if report == "period":
        text = render_admin_period_report(label, date_from, date_to)
    elif report == "funnel":
        text = render_admin_funnel_report(label, date_from, date_to)
    elif report == "subscriptions":
        text = render_admin_subscriptions_report(label, date_from, date_to)
    elif report == "retention":
        text = render_admin_retention_report(label, date_from, date_to)
    elif report == "costs":
        text = render_admin_costs_report(label, date_from, date_to)
    elif report == "sources":
        text = render_admin_sources_report(label, date_from, date_to)
    elif report == "audit":
        text = render_admin_audit_report(label, date_from, date_to)
    elif report == "export":
        if callback.message:
            csv_file = BufferedInputFile(
                render_admin_csv_export(label, date_from, date_to),
                filename=_admin_export_filename(arg),
            )
            await callback.message.answer_document(csv_file, caption=f"CSV экспорт TemichevVet — {label}")
        await callback.answer()
        return
    else:
        text = "Неизвестный отчёт."

    if callback.message:
        await callback.message.answer(text, reply_markup=_admin_menu_kb())
    await callback.answer()
