from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import ADMIN_IDS
from app.db import get_admin_dashboard_stats


router = Router(name="admin")


def _is_admin(telegram_id: int | None) -> bool:
    return bool(telegram_id and int(telegram_id) in ADMIN_IDS)


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
                InlineKeyboardButton(text="🔁 Retention", callback_data="admin:retention:30"),
                InlineKeyboardButton(text="🧾 Расходы", callback_data="admin:costs:7"),
            ],
            [InlineKeyboardButton(text="🔗 Источники", callback_data="admin:sources:30")],
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


def render_admin_period_report(label: str, date_from: str, date_to: str) -> str:
    stats = get_admin_dashboard_stats(date_from, date_to)
    counts = stats["counts"]
    urgency = stats["urgency"]
    payments = stats["payments"]
    triage_by_plan = counts.get("triage_by_plan", {})

    lines = [
        f"<b>📊 Отчёт TemichevVet — {html.escape(label)}</b>",
        "",
        f"Starts: <b>{counts.get('app_start', 0)}</b>",
        (
            "Triage: "
            f"<b>{counts.get('triage_completed', 0)}</b> "
            f"(free {triage_by_plan.get('free', 0)}, plus {triage_by_plan.get('plus', 0)}, "
            f"pro {triage_by_plan.get('pro', 0)}, vip {triage_by_plan.get('vip', 0)})"
        ),
        (
            "Urgency: "
            f"🟢 {urgency.get('green', 0)} / "
            f"🟡 {urgency.get('yellow', 0)} / "
            f"🟥 {urgency.get('red', 0)} / "
            f"? {urgency.get('unknown', 0)}"
        ),
        (
            "Follow-ups: "
            f"{counts.get('followup_scheduled', 0)} scheduled / "
            f"{counts.get('followup_sent', 0)} sent / "
            f"{counts.get('followup_answered', 0)} answered"
        ),
        f"Paywall: {counts.get('paywall_shown', 0)} shown / {counts.get('pay_clicked', 0)} clicked",
        f"Payments: {payments.get('count', 0)} success / {_fmt_float(payments.get('amount_rub', 0))} ₽",
        "",
        f"paywall→pay: <b>{_pct(counts.get('pay_clicked', 0), counts.get('paywall_shown', 0))}</b>",
        f"click→pay: <b>{_pct(payments.get('count', 0), counts.get('pay_clicked', 0))}</b>",
    ]
    return "\n".join(lines)


def render_admin_funnel_report(label: str, date_from: str, date_to: str) -> str:
    funnel = get_admin_dashboard_stats(date_from, date_to)["funnel"]
    starts = funnel.get("app_start", 0)
    rows = [
        ("app_start", "app_start"),
        ("triage_completed", "triage_completed"),
        ("paywall_shown", "paywall_shown"),
        ("pay_clicked", "pay_clicked"),
        ("payment_success", "payment_success"),
    ]
    lines = [f"<b>🧪 Воронка — {html.escape(label)}</b>", ""]
    for key, title in rows:
        value = int(funnel.get(key, 0) or 0)
        lines.append(f"{title}: <b>{value}</b> ({_pct(value, starts)} от starts)")
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
        f"paywall_shown: {counts.get('paywall_shown', 0)}",
        f"pay_clicked: {counts.get('pay_clicked', 0)}",
        f"payment_success: {payments.get('count', 0)} / {_fmt_float(payments.get('amount_rub', 0))} ₽",
    ]
    return "\n".join(lines)


def render_admin_retention_report(label: str, date_from: str, date_to: str) -> str:
    retention = get_admin_dashboard_stats(date_from, date_to)["retention"]
    lines = [
        f"<b>🔁 Retention — {html.escape(label)}</b>",
        "",
        f"D1: <b>{_pct(retention.get('d1_cohorts', 0), retention.get('base_cohorts', 0))}</b>",
        f"D7: <b>{_pct(retention.get('d7_cohorts', 0), retention.get('base_cohorts', 0))}</b>",
        f"Base cohorts: {retention.get('base_cohorts', 0)}",
        f"Avg triage/user: {_fmt_float(retention.get('avg_triage_per_user', 0))}",
        f"Follow-up answered rate: <b>{_pct(retention.get('followup_answered_rate', 0), 1)}</b>",
    ]
    return "\n".join(lines)


def render_admin_costs_report(label: str, date_from: str, date_to: str) -> str:
    stats = get_admin_dashboard_stats(date_from, date_to)
    counts = stats["counts"]
    tokens = stats["tokens"]
    lines = [
        f"<b>🧾 Расходы / workload — {html.escape(label)}</b>",
        "",
        f"triage_completed: <b>{counts.get('triage_completed', 0)}</b>",
        f"followup_sent: <b>{counts.get('followup_sent', 0)}</b>",
        "",
        f"total_tokens: <b>{tokens.get('total_tokens', 0)}</b>",
        f"avg_tokens_per_triage: <b>{_fmt_float(tokens.get('avg_tokens_per_triage', 0))}</b>",
        f"workload_index: <b>{_fmt_float(tokens.get('workload_index', 0))}</b>",
    ]
    return "\n".join(lines)


def render_admin_sources_report(label: str, date_from: str, date_to: str) -> str:
    stats = get_admin_dashboard_stats(date_from, date_to)
    lines = [f"<b>🔗 Источники — {html.escape(label)}</b>", ""]
    for source in stats["sources"]["utm_source"]:
        lines.append(
            f"{html.escape(str(source['source']))} "
            f"({html.escape(str(source['source_type']))}): "
            f"{source['starts']} starts / {source['triage_completed']} triage / "
            f"{source['payment_success']} pay / CR {_pct(source['payment_success'], source['starts'])}"
        )
    if len(lines) == 2:
        lines.append("Нет app_start за период.")
    return "\n".join(lines)


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await message.answer("<b>Admin dashboard TemichevVet</b>", reply_markup=_admin_menu_kb())


@router.callback_query(F.data.startswith("admin:"))
async def admin_callbacks(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    report = parts[1] if len(parts) > 1 else "period"
    arg = parts[2] if len(parts) > 2 else "7"
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
    else:
        text = "Неизвестный отчёт."

    if callback.message:
        await callback.message.answer(text, reply_markup=_admin_menu_kb())
    await callback.answer()
