# app/keyboards.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from app.constants import SUBSCRIPTION_BUTTONS, EXTRA_REQUEST_PRICE_RUB
from app.ux import BTN_BACK, BTN_DONE, BTN_MENU

PLUS_PAY_BUTTON = "💳 Оплатить Plus — 200 ₽"
PLUS_BACK_BUTTON = BTN_BACK


def main_menu_kb() -> ReplyKeyboardMarkup:
    """
    Главное меню бота TemichevVet.

    Вариант для Pets v2:
      - отдельный раздел «🐾 Мои животные»;
      - добавление питомца идёт из раздела «Мои животные»;
      - добавлены кнопки «ℹ️ О боте» и «✉️ Обратная связь».
    """
    keyboard = [
        [
            KeyboardButton(text="🩺 Разобрать жалобу"),
            KeyboardButton(text="📜 История здоровья"),
        ],
        [
            KeyboardButton(text="📊 Наблюдения"),
            KeyboardButton(text="🐾 Мои животные"),
        ],
        [
            KeyboardButton(text="🍽️ Питание"),
            KeyboardButton(text="🧴 Уход и привычки"),
        ],
        [
            KeyboardButton(text="❓ Вопросы и ответы"),
            KeyboardButton(text="⏰ Напоминания"),
        ],
        [
            KeyboardButton(text="👤 Моя подписка"),
            KeyboardButton(text="🚀 Быстрый старт"),
        ],
        [
            KeyboardButton(text="🏥 Найти клинику"),
            KeyboardButton(text="ℹ️ О боте"),
        ],
        [
            KeyboardButton(text="✉️ Обратная связь"),
        ],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ===== ПОДМЕНЮ ПИТАНИЯ (СТАРЫЙ ВАРИАНТ, МОЖЕТ ИСПОЛЬЗОВАТЬСЯ ДРУГИМИ ХЕНДЛЕРАМИ) =====


def nutrition_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти продукт")],
            [
                KeyboardButton(text="✅ Что можно"),
                KeyboardButton(text="⛔ Что нельзя"),
            ],
            [KeyboardButton(text=BTN_MENU)],
        ],
        resize_keyboard=True,
    )


def pet_type_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🐱 Кот/Кошка"), KeyboardButton(text="🐶 Собака")],
            [KeyboardButton(text=BTN_MENU)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def subscription_kb() -> ReplyKeyboardMarkup:
    """
    Клавиатура подписки:
      - тарифы;
      - проверка оплаты;
      - доп. запрос;
      - отписка.
    """
    plan_buttons = [
        [KeyboardButton(text=text)] for text in SUBSCRIPTION_BUTTONS.keys()
    ]

    plan_buttons.append([KeyboardButton(text="📋 Все тарифы")])
    plan_buttons.append([KeyboardButton(text="✅ Я оплатил (проверить)")])

    extra_and_unsubscribe = [
        KeyboardButton(
            text=f"➕ Купить 1 доп. запрос ({EXTRA_REQUEST_PRICE_RUB} ₽)"
        ),
        KeyboardButton(text="🚪 Отписаться и удалить доступ"),
    ]
    plan_buttons.append(extra_and_unsubscribe)
    plan_buttons.append([KeyboardButton(text=BTN_MENU)])

    return ReplyKeyboardMarkup(
        keyboard=plan_buttons,
        resize_keyboard=True,
    )


def choose_pet_kb(labels: list[str]) -> ReplyKeyboardMarkup:
    """
    Клавиатура выбора питомца для triage.
    """
    rows = [[KeyboardButton(text=label)] for label in labels]
    rows.append([KeyboardButton(text=BTN_MENU)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def age_group_kb() -> ReplyKeyboardMarkup:
    """
    Клавиатура для выбора возрастной группы перед triage.
    Тексты согласованы с обработчиком triage.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="До 1 года (котёнок/щенок)")],
            [KeyboardButton(text="1–7 лет (взрослый)")],
            [KeyboardButton(text="Старше 7 лет (возрастной)")],
            [KeyboardButton(text="Не знаю / пропустить")],
            [KeyboardButton(text=BTN_MENU)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def duration_kb() -> ReplyKeyboardMarkup:
    """
    Клавиатура для выбора длительности проблемы перед triage.
    Тексты согласованы с обработчиком triage.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="< 24 часов")],
            [KeyboardButton(text="1–3 дня")],
            [KeyboardButton(text="Больше 3 дней")],
            [KeyboardButton(text="Давно, периодами")],
            [KeyboardButton(text="Не помню / пропустить")],
            [KeyboardButton(text=BTN_MENU)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def subscription_inline_kb(current_plan: str | None = None) -> InlineKeyboardMarkup:
    """Inline витрина подписки (не конфликтует с reply keyboard)."""
    current_plan = (current_plan or "").strip().lower()
    rows: list[list[InlineKeyboardButton]] = []

    plan_meta = [
        ("free", "🆓 FREE"),
        ("plus", "➕ PLUS"),
        ("pro", "👑 PRO"),
    ]
    for code, title in plan_meta:
        label = f"{title}{' ✅' if current_plan == code else ''}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"sub:choose:{code}")])

    rows.append([InlineKeyboardButton(text=f"➕ Купить 1 доп. запрос ({EXTRA_REQUEST_PRICE_RUB} ₽)", callback_data="sub:buy_extra")])
    rows.append([InlineKeyboardButton(text="🚪 Отписаться и удалить доступ", callback_data="sub:unsubscribe")])
    rows.append([InlineKeyboardButton(text=BTN_MENU, callback_data="open:main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def subscription_unsubscribe_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, отключить", callback_data="sub:unsubscribe:confirm")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data="sub:unsubscribe:cancel")],
        ]
    )


def subscription_cta_inline_kb(show_back: bool = True) -> InlineKeyboardMarkup:
    """Legacy-compatible CTA keyboard used by paywall screens."""
    rows = [[InlineKeyboardButton(text="💳 Подписка", callback_data="open:subscription")]]
    if show_back:
        rows.append([InlineKeyboardButton(text=BTN_MENU, callback_data="open:main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plus_paywall_inline_kb(back_callback_data: str = "open:main_menu") -> InlineKeyboardMarkup:
    """Unified Plus CTA keyboard for paywall screens."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Перейти на Plus", callback_data="open:subscription")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data=f"paywall_back:{back_callback_data}")],
        ]
    )


def plus_checkout_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить Plus — 200 ₽", callback_data="pay:plus")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data="sub:back")],
        ]
    )


def payment_created_kb(pay_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Открыть оплату", url=pay_url)],
            [InlineKeyboardButton(text="✅ Я оплатил (проверить)", callback_data="pay:check")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data="sub:back")],
        ]
    )


def pro_vip_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BTN_BACK, callback_data="sub:back")],
        ]
    )


def onb_step1_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить питомца", callback_data="onb:add_pet")],
            [InlineKeyboardButton(text=BTN_MENU, callback_data="open:main_menu")],
        ]
    )


def onb_step2_kb(pets: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for pet in pets:
        pet_id = pet.get("id")
        if pet_id is None:
            continue
        pet_type = pet.get("pet_type") or "питомец"
        pet_name = pet.get("pet_name") or "(без имени)"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⭐ {pet_type} — {pet_name}",
                    callback_data=f"onb:set_main:{pet_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Пропустить", callback_data="onb:skip_main")])
    rows.append([InlineKeyboardButton(text=BTN_MENU, callback_data="open:main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onb_step3_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🩺 Разобрать жалобу", callback_data="onb:start_triage")],
            [InlineKeyboardButton(text=BTN_DONE, callback_data="onb:done")],
            [InlineKeyboardButton(text=BTN_MENU, callback_data="open:main_menu")],
        ]
    )


def triage_done_kb(pet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🐾 Открыть карточку питомца", callback_data=f"petcard:overview:{pet_id}")],
            [InlineKeyboardButton(text="➕ Добавить напоминание", callback_data=f"petrem:add:{pet_id}")],
            [InlineKeyboardButton(text="🩺 Новый разбор", callback_data="onb:start_triage")],
            [InlineKeyboardButton(text=BTN_MENU, callback_data="open:main_menu")],
        ]
    )
