# app/handlers/start.py

import os
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
)

from app.start_texts import START_WELCOME, START_NEED_REGISTER, START_RETURNING_USER
from app.texts import MAIN_MENU_QUICK_GUIDE_TEXT, NEXT_STEPS_TEXT
from app.handlers.onboarding import maybe_show_onboarding_after_start, show_step3

from app.db import (
    get_user_by_telegram_id,
    create_user,
    create_pet,
    get_pets_for_user,
    set_user_clinic_id_if_empty,
)
from app.keyboards import main_menu_kb, pet_type_kb, skip_kb
from app.states import RegistrationStates
from app.constants import SUPPORTED_PETS
from app.services.analytics import (
    EVENT_APP_START,
    EVENT_PET_CREATED,
    EVENT_REGISTRATION_STARTED,
    EVENT_USER_REGISTERED,
    parse_start_payload,
    track_event,
    track_fsm_cancel,
    track_fsm_invalid_input,
)
from app.services.clinic import get_clinic_profile, render_clinic_start_note
from app.ux import BTN_MENU, is_cancel_text

router = Router()
logger = logging.getLogger(__name__)

# Абсолютный путь к каталогу static рядом с app/
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "static")


def _welcome_kb() -> ReplyKeyboardMarkup:
    """Клавиатура первого экрана: регистрация или сразу в меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Зарегистрироваться")],
            [KeyboardButton(text=BTN_MENU)],
        ],
        resize_keyboard=True,
    )


def _get_start_arg(message: Message) -> str:
    """Получить аргумент deep-link для /start (например: /start promo)."""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()
    return ""


def _find_logo_path() -> str | None:
    """
    Найти приветственный баннер в STATIC_DIR.
    1) Пытаемся по ожидаемым именам.
    2) Если не нашли — берём любой .png/.jpg/.jpeg из каталога.
    """
    if not os.path.isdir(STATIC_DIR):
        print(f"[start] STATIC_DIR не найден: {STATIC_DIR}")
        logger.warning("STATIC_DIR not found: %s", STATIC_DIR)
        return None

    # 1. Ожидаемые имена файлов. Для первого экрана лучше подходит баннер,
    # который сразу объясняет основную задачу бота, а не просто логотип.
    candidates = [
        os.path.join(STATIC_DIR, "welcome_banner.jpg"),
        os.path.join(STATIC_DIR, "welcome_banner.png"),
        os.path.join(STATIC_DIR, "triage_banner.jpg"),
        os.path.join(STATIC_DIR, "triage_banner.png"),
        os.path.join(STATIC_DIR, "logo_temichevvet.png"),
        os.path.join(STATIC_DIR, "logo_temichevvet.jpg"),
        os.path.join(STATIC_DIR, "temichevvet_logo.png"),
        os.path.join(STATIC_DIR, "temichevvet_logo.jpg"),
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"[start] Найден приветственный баннер: {path}")
            return path

    # 2. Любой картинкой из static
    exts = (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG")
    try:
        for fname in sorted(os.listdir(STATIC_DIR)):
            if fname.endswith(exts):
                path = os.path.join(STATIC_DIR, fname)
                print(f"[start] Найден приветственный баннер по авто-поиску: {path}")
                return path
    except Exception as e:
        print(f"[start] Ошибка чтения STATIC_DIR: {e}")
        logger.error("Error listing STATIC_DIR: %s", e)

    print(f"[start] Приветственный баннер не найден в каталоге: {STATIC_DIR}")
    logger.warning("Welcome banner not found in %s", STATIC_DIR)
    return None


async def _send_logo(message: Message) -> None:
    """
    Отправить приветственный баннер TemichevVet, если файл найден.
    Не ломает дальнейшую работу /start при ошибках.
    """
    logo_path = _find_logo_path()
    if not logo_path:
        return

    try:
        await message.answer_photo(
            photo=FSInputFile(logo_path),
            caption="TemichevVet помогает быстро оценить срочность ситуации и сохранить историю здоровья питомца.",
        )
        print(f"[start] Приветственный баннер отправлен: {logo_path}")
        logger.info("Welcome banner sent: %s", logo_path)
    except Exception as e:
        print(f"[start] Не удалось отправить логотип: {e}")
        logger.error("Failed to send logo: %s", e)


def _faq_after_start_text() -> str:
    """
    Короткий блок «Вопросы и ответы» после онбординга.
    Не использует английских слов типа FAQ/triage.
    """
    lines: list[str] = []

    lines.append("<b>Как пользоваться ботом</b>\n")

    lines.append(
        "1. Добавьте питомца, чтобы рекомендации были привязаны к его карточке.\n"
        "2. Если питомцу плохо — нажмите «🩺 Разобрать жалобу» и опишите симптомы обычными словами.\n"
        "3. После ответа сохраните событие в историю и следите за динамикой через наблюдения.\n"
    )

    lines.append(
        "<b>Когда нужно срочно к врачу</b>\n"
        "Если есть тяжёлое дыхание, судороги, сильное кровотечение, потеря сознания, "
        "подозрение на отравление или резкое ухудшение — не ждите ответа бота, обращайтесь в клинику.\n"
    )

    lines.append(
        "<b>Что можно делать без регистрации</b>\n"
        "Можно посмотреть питание, уход и ответы на частые вопросы. Для разборов, истории "
        "и напоминаний лучше добавить питомца."
    )

    lines.append(MAIN_MENU_QUICK_GUIDE_TEXT)

    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/start.py:cmd_start user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """
    /start:
    - если пользователь уже есть в БД — показываем краткое приветствие и меню;
    - если нет — показываем онбординг с выбором:
        • зарегистрироваться и добавить питомца;
        • открыть главное меню.
    deep-link параметр (например, /start promo) учитываем в тексте приветствия.
    """
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    start_arg = _get_start_arg(message).lower()
    start_payload = parse_start_payload(start_arg)
    from_channel = start_arg in {"promo", "channel", "from_channel"}

    # Пытаемся отправить логотип (для всех пользователей)
    await _send_logo(message)

    # Вариант для уже зарегистрированных пользователей
    if user:
        if start_payload.get("clinic_id") is not None:
            set_user_clinic_id_if_empty(user["id"], start_payload.get("clinic_id"))
            user = get_user_by_telegram_id(tg_id) or user
        track_event(user["id"], EVENT_APP_START, start_payload)
        clinic_profile = get_clinic_profile(user.get("clinic_id")) if user.get("clinic_id") else None
        if from_channel:
            await message.answer(
                f"Снова привет, {user['name']} 👋\n"
                "Вы перешли из нашего канала TemichevVet.\n\n"
                "Все ваши данные и питомцы сохранены. "
                "Можно сразу перейти к разделам в главном меню:",
                reply_markup=main_menu_kb(),
            )
        else:
            returning_text = (
                f"С возвращением, {user['name']} 👋\n\n"
                "Что нужно сделать сейчас?\n\n"
                "• 🩺 Разобрать жалобу — если питомцу плохо.\n"
                "• 🐾 Мои животные — открыть карточку и историю.\n"
                "• ⏰ Напоминания — процедуры, обработки, осмотры.\n"
                "• 🍽️ Питание — проверить продукт или блюдо.\n\n"
                "Выберите раздел ниже."
            )
            if clinic_profile and start_payload.get("clinic_id") is not None:
                returning_text = f"{render_clinic_start_note(clinic_profile)}\n\n{returning_text}"
            await message.answer(
                returning_text,
                reply_markup=main_menu_kb(),
            )
        await state.clear()
        await maybe_show_onboarding_after_start(message, state, user)
        return

    # Новый пользователь: приветствие и онбординг
    intro_lines: list[str] = []

    if from_channel:
        intro_lines.append(
            "Вы перешли в TemichevVetBot из нашего канала — здесь собрана практическая часть: "
            "не посты, а конкретные шаги, когда с питомцем что-то происходит."
        )

    if start_payload.get("clinic_id") is not None:
        intro_lines.append(render_clinic_start_note(get_clinic_profile(start_payload.get("clinic_id"))))

    intro_lines.append(START_WELCOME)
    intro_lines.append(START_NEED_REGISTER)
    intro_lines.append(
        "Нажмите «👤 Зарегистрироваться и добавить питомца», чтобы бот сразу работал точнее.\n"
        "Или выберите «⬅️ В меню», если хотите сначала осмотреть разделы."
    )

    text = "\n\n".join(intro_lines)

    await state.clear()
    await state.update_data(start_payload=start_payload)
    await message.answer(text, reply_markup=_welcome_kb())
    # Дополнительный короткий блок «Вопросы и ответы» сразу после онбординга
    await message.answer(_faq_after_start_text())


@router.message(F.text.in_({"👤 Зарегистрироваться", "👤 Зарегистрироваться и добавить питомца"}))
async def start_registration(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/start.py:start_registration user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """Запуск регистрации из приветственного экрана."""
    await message.answer(
        "Для начала давайте познакомимся.\n\n"
        "Как к вам обращаться? Напишите ваше имя.",
    )
    await state.set_state(RegistrationStates.waiting_for_name)


@router.message(F.text.in_({BTN_MENU, "📋 Главное меню", "📋 Открыть главное меню", "🏠 Меню", "🏠 Главное меню"}))
async def open_main_menu_from_start(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/start.py:open_main_menu_from_start user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    """Открыть главное меню без немедленной регистрации."""
    await state.clear()
    await message.answer(
        "Главное меню открыто.\n\n"
        "Можно посмотреть питание, уход и ответы на вопросы. "
        "Для разборов состояния, истории и напоминаний добавьте питомца.\n\n"
        f"{NEXT_STEPS_TEXT}",
        reply_markup=main_menu_kb(),
    )


@router.message(RegistrationStates.waiting_for_name)
async def reg_get_name(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/start.py:reg_get_name user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()
    low = text.lower()
    if is_cancel_text(text) or low == "📋 открыть главное меню":
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="registration")
        await message.answer("Ок.", reply_markup=main_menu_kb())
        await state.clear()
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("Пожалуйста, напишите имя одним словом.")
        return

    await state.update_data(name=name)
    data = await state.get_data()
    start_payload = data.get("start_payload") or parse_start_payload("")
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        user_id = create_user(tg_id, name, clinic_id=start_payload.get("clinic_id"))
        track_event(user_id, EVENT_APP_START, start_payload)
        track_event(user_id, EVENT_REGISTRATION_STARTED, {"source": "welcome"})
        track_event(user_id, EVENT_USER_REGISTERED, {"source": "welcome"})
    else:
        user_id = int(user["id"])
        if start_payload.get("clinic_id") is not None:
            set_user_clinic_id_if_empty(user_id, start_payload.get("clinic_id"))
        track_event(user_id, EVENT_REGISTRATION_STARTED, {"source": "welcome_existing"})
    await state.update_data(user_id=user_id)
    await message.answer(
        f"Спасибо, {name}!\nТеперь скажите, какое у вас животное:",
        reply_markup=pet_type_kb(),
    )
    await state.set_state(RegistrationStates.waiting_for_pet_type)


@router.message(RegistrationStates.waiting_for_pet_type)
async def reg_pet_type(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/start.py:reg_pet_type user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()

    if is_cancel_text(text):
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="registration")
        await message.answer(
            "Регистрация прервана. Вы можете начать сначала командой /start.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    if text not in SUPPORTED_PETS:
        track_fsm_invalid_input(
            message.from_user.id,
            await state.get_state(),
            scenario="registration",
            reason="unsupported_pet_type",
            text=text,
        )
        await message.answer(
            "Сейчас бот работает только с кошками и собаками.\n"
            "Пожалуйста, выберите вариант:\n"
            "🐱 Кот/Кошка или 🐶 Собака.",
            reply_markup=pet_type_kb(),
        )
        return

    pet_type = SUPPORTED_PETS[text]
    await state.update_data(pet_type=pet_type)

    await message.answer(
        f"Вы выбрали: {text}.\n"
        "Если хотите, укажите кличку питомца (например: Барсик).\n"
        "Если не хотите — напишите «Пропустить».",
        reply_markup=skip_kb(),
    )
    await state.set_state(RegistrationStates.waiting_for_pet_name)


@router.message(RegistrationStates.waiting_for_pet_name)
async def reg_pet_name(message: Message, state: FSMContext):
    _state = None
    try:
        _state = await state.get_state()
    except Exception:
        _state = None
    logger.info("[HANDLER] app/handlers/start.py:reg_pet_name user=%s text=%r state=%s", getattr(message.from_user, 'id', None), getattr(message, 'text', None), _state)
    text = (message.text or "").strip()
    low = text.lower()
    if is_cancel_text(text) or low == "📋 открыть главное меню":
        track_fsm_cancel(message.from_user.id, await state.get_state(), scenario="registration")
        await message.answer("Ок.", reply_markup=main_menu_kb())
        await state.clear()
        return

    pet_name_raw = (message.text or "").strip()
    pet_name = None if pet_name_raw.lower() == "пропустить" else pet_name_raw

    data = await state.get_data()
    name = data["name"]
    pet_type = data["pet_type"]
    start_payload = data.get("start_payload") or parse_start_payload("")

    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    user_id = int(data.get("user_id") or (user or {}).get("id") or 0)
    if user is None:
        user_id = create_user(tg_id, name, clinic_id=start_payload.get("clinic_id"))
        track_event(user_id, EVENT_APP_START, start_payload)
        track_event(user_id, EVENT_USER_REGISTERED, {"source": "registration_fallback"})
    else:
        user_id = int(user["id"])
        if start_payload.get("clinic_id") is not None:
            set_user_clinic_id_if_empty(user_id, start_payload.get("clinic_id"))

    pet_id = create_pet(user_id, pet_type, pet_name)
    track_event(
        user_id,
        EVENT_PET_CREATED,
        {"pet_id": int(pet_id), "pet_type": pet_type},
    )

    pets = get_pets_for_user(user_id)

    pets_descriptions = []
    for p in pets:
        n = p["pet_name"] or "(без имени)"
        pets_descriptions.append(f"• {p['pet_type']} — {n}")
    pets_block = "\n".join(pets_descriptions)

    await message.answer(
        "Регистрация завершена ✅\n\n"
        f"Владелец: {name}\n"
        f"Питомцы:\n{pets_block}\n\n"
        "Сейчас для вас активирован базовый бесплатный тариф <b>Free</b>:\n"
        "• до <b>5 запросов по здоровью</b> питомцев в первый месяц;\n"
        "• безлимитный доступ к разделам «Можно / нельзя», «Уход и привычки» и «Вопросы и ответы»;\n"
        "• до <b>10 активных напоминаний</b> в течение первых 30 дней после регистрации.\n\n"
        "Подробные условия и смена тарифа — в разделе «👤 Моя подписка».\n\n"
        "Теперь вы можете пользоваться ботом. Выберите раздел в меню:",
        reply_markup=main_menu_kb(),
    )

    await state.clear()
    await show_step3(message)
