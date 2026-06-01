"""
Глобальные константы проекта TemichevVetBot.

Здесь собраны:
- поддерживаемые виды животных;
- тарифные планы и квоты triage;
- отображаемые названия тарифов для кнопок;
- стоимость разового triage-запроса;
- карта env-переменных для выбора LLM-модели по тарифу.
"""

# Поддерживаемые виды животных.
# Ключи должны совпадать с текстом кнопок выбора вида питомца.
SUPPORTED_PETS = {
    "🐱 Кот/Кошка": "кошка",
    "🐶 Собака": "собака",
}

# Описание подписок (логика).
# Значения синхронизированы с docs/plans_matrix.md:
#   free — 5 triage-запросов в месяц (gpt-4o-mini)
#   plus — 10 triage-запросов в месяц (gpt-5-mini)
#   pro  — 30 triage-запросов в месяц (gpt-5-mini)
#   vip  — 25 triage-запросов в месяц (gpt-5 + gpt-5-mini, один общий лимит)
SUBSCRIPTION_PLANS = {
    "free": {
        "title": "Free — первый месяц",
        "quota_total": 5,   # 5 запросов triage в месяц
        "price": 0,
    },
    "plus": {
        "title": "Plus — 200 ₽/мес",
        "quota_total": 10,  # 10 запросов triage в месяц
        "price": 200,
    },
    "pro": {
        "title": "Pro — 300 ₽/мес",
        "quota_total": 30,  # 30 запросов triage в месяц
        "price": 300,
    },
    "vip": {
        "title": "VIP — 2500 ₽/мес",
        # В системе сейчас один общий лимит triage-запросов на тариф.
        # Для VIP закладываем повышенный лимит (15 GPT-5 + 10 GPT-5-mini условно).
        "quota_total": 25,
        # Дополнительные поля — на будущее под учёт консультаций.
        "has_consultation": True,
        "consultations_per_period": 1,
        "price": 2500,
    },
}

# Карта текстов кнопок → внутренний код тарифа.
# Используется в handlers/подписки и keyboards.py.
SUBSCRIPTION_BUTTONS = {
    "🆓 Free • первый месяц": "free",
    "🔹 Plus • 200 ₽/мес": "plus",
    "🔺 Pro • 300 ₽/мес": "pro",
    "👑 VIP • 2500 ₽/мес": "vip",
}


# Invert labels mapping for display (emoji + price etc.)
PLAN_LABEL_BY_CODE = {code: label for label, code in SUBSCRIPTION_BUTTONS.items()}


def build_subscription_text(sub: dict) -> str:
    """
    Единый источник текста для экрана подписки (используется в menu.py и knowledge.py).

    Требования UX:
      - эмодзи у тарифов;
      - единый текст и цены из SUBSCRIPTION_PLANS;
    """
    plan_code = sub.get("plan", "free")
    quota_total = int(sub.get("quota_total", 0) or 0)
    quota_used = int(sub.get("quota_used", 0) or 0)

    plan_meta = SUBSCRIPTION_PLANS.get(plan_code, SUBSCRIPTION_PLANS["free"])
    plan_label = PLAN_LABEL_BY_CODE.get(plan_code) or plan_meta.get("title", plan_code)

    lines: list[str] = []
    lines.append("💳 Ваша подписка")
    lines.append("")
    lines.append(f"Текущий тариф: <b>{plan_label}</b>")
    lines.append(f"Использовано запросов: <b>{quota_used}</b> / <b>{quota_total}</b>")
    lines.append("")

    if plan_code == "free":
        lines.append("Что даёт Free:")
        lines.append("• до <b>5 запросов по здоровью</b> в месяц;")
        lines.append("• базовый интеллект: аккуратный разбор жалобы и оценка срочности;")
        lines.append("• материалы по уходу и FAQ (базовый доступ);")
        lines.append("• до <b>10 активных напоминаний</b> в течение первых 30 дней после регистрации;")
        lines.append("• после 30 дней новые напоминания можно создавать только на платных тарифах.")
    elif plan_code == "plus":
        lines.append("Что даёт Plus:")
        lines.append("• до <b>10 запросов по здоровью</b> в месяц;")
        lines.append("• усиленный интеллект: более развёрнутые разборы жалоб и аккуратная оценка срочности;")
        lines.append("• расширенные материалы по уходу и FAQ;")
        lines.append("• до <b>20 активных напоминаний</b> по питомцам.")
    elif plan_code == "pro":
        lines.append("Что даёт Pro:")
        lines.append("• до <b>30 запросов по здоровью</b> в месяц;")
        lines.append("• ещё более мощный интеллект: глубокие разборы сложных случаев и более точная оценка срочности;")
        lines.append("• расширенные материалы и рекомендации;")
        lines.append("• до <b>50 активных напоминаний</b> по питомцам.")
    elif plan_code == "vip":
        lines.append("Что даёт VIP:")
        lines.append("• до <b>25 запросов по здоровью</b> в месяц;")
        lines.append("• максимальный интеллект и приоритетные разборы;")
        lines.append("• расширенные материалы + доступ к VIP-разделам (если включены);")
        lines.append("• до <b>100 активных напоминаний</b> по питомцам.")
    else:
        # fallback на title
        lines.append(f"Описание тарифа: {plan_meta.get('title', plan_code)}")

    return "\n".join(lines)

# Стоимость разового triage-запроса, ₽.
# Используется в keyboards.py и текстах upsell.
EXTRA_REQUEST_PRICE_RUB = 50

# Названия env-переменных для выбора LLM-модели triage по тарифу.
# Значения этих переменных в .env должны содержать точные идентификаторы моделей OpenAI.
TRIAGE_MODEL_ENV_BY_PLAN = {
    "free": "OPENAI_MODEL_FREE",   # например: gpt-4o-mini
    "plus": "OPENAI_MODEL_PLUS",   # например: gpt-5-mini
    "pro":  "OPENAI_MODEL_PRO",    # например: gpt-5-mini
    "vip":  "OPENAI_MODEL_VIP",    # например: gpt-5
}


# Лимиты питомцев по тарифам. Единый источник для legacy pets и Pets v2.
PETS_LIMIT_BY_PLAN = {
    "free": 1,
    "plus": 3,
    "pro": 10,
    "vip": 10,
}
