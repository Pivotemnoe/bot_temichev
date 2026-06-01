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
from app.handlers.onboarding import maybe_show_onboarding_after_start, show_step3

from app.db import (
    get_user_by_telegram_id,
    create_user,
    create_pet,
    get_pets_for_user,
)
from app.keyboards import main_menu_kb, pet_type_kb, skip_kb
from app.states import RegistrationStates
from app.constants import SUPPORTED_PETS

router = Router()
logger = logging.getLogger(__name__)

# Абсолютный путь к каталогу static рядом с app/
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "static")


def _welcome_kb() -> ReplyKeyboardMarkup:
    """Клавиатура первого экрана: регистрация или сразу в меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Зарегистрироваться и добавить питомца")],
            [KeyboardButton(text="📋 Открыть главное меню")],
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
    Найти логотип в STATIC_DIR.
    1) Пытаемся по ожидаемым именам.
    2) Если не нашли — берём любой .png/.jpg/.jpeg из каталога.
    """
    if not os.path.isdir(STATIC_DIR):
        print(f"[start] STATIC_DIR не найден: {STATIC_DIR}")
        logger.warning("STATIC_DIR not found: %s", STATIC_DIR)
        return None

    # 1. Ожидаемые имена файлов
    candidates = [
        os.path.join(STATIC_DIR, "logo_temichevvet.png"),
        os.path.join(STATIC_DIR, "logo_temichevvet.jpg"),
        os.path.join(STATIC_DIR, "temichevvet_logo.png"),
        os.path.join(STATIC_DIR, "temichevvet_logo.jpg"),
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"[start] Найден логотип по ожидаемому пути: {path}")
            return path

    # 2. Любой картинкой из static
    exts = (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG")
    try:
        for fname in sorted(os.listdir(STATIC_DIR)):
            if fname.endswith(exts):
                path = os.path.join(STATIC_DIR, fname)
                print(f"[start] Найден логотип по авто-поиску: {path}")
                return path
    except Exception as e:
        print(f"[start] Ошибка чтения STATIC_DIR: {e}")
        logger.error("Error listing STATIC_DIR: %s", e)

    print(f"[start] Логотип не найден в каталоге: {STATIC_DIR}")
    logger.warning("Logo not found in %s", STATIC_DIR)
    return None


async def _send_logo(message: Message) -> None:
    """
    Отправить логотип TemichevVet, если файл найден.
    Не ломает дальнейшую работу /start при ошибках.
    """
    logo_path = _find_logo_path()
    if not logo_path:
        return

    try:
        await message.answer_photo(
            photo=FSInputFile(logo_path),
            caption="TemichevVetBot — интеллектуальный помощник по здоровью питомца.",
        )
        print(f"[start] Логотип отправлен: {logo_path}")
        logger.info("Logo sent: %s", logo_path)
    except Exception as e:
        print(f"[start] Не удалось отправить логотип: {e}")
        logger.error("Failed to send logo: %s", e)


def _faq_after_start_text() -> str:
    """
    Короткий блок «Вопросы и ответы» после онбординга.
    Не использует английских слов типа FAQ/triage.
    """
    lines: list[str] = []

    lines.append("<b>Частые вопросы</b>\n")

    lines.append(
        "❓ <b>Как пользоваться ботом?</b>\n"
        "Опишите, что происходит с вашим питомцем, — бот оценит состояние, "
        "подскажет, насколько ситуация серьёзна, и предложит понятные шаги.\n"
    )

    lines.append(
        "❓ <b>Что такое лимиты запросов?</b>\n"
        "В тарифе есть определённое количество обращений за интеллектуальной оценкой "
        "состояния. Остальные разделы (питание, уход, знания) работают без ограничений.\n"
    )

    lines.append(
        "❓ <b>Зачем добавлять питомца?</b>\n"
        "Чтобы рекомендации учитывали вид, возраст и историю состояний именно вашего "
        "питомца, а не были «в среднем по больнице».\n"
    )

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
    from_channel = start_arg in {"promo", "channel", "from_channel"}

    # Пытаемся отправить логотип (для всех пользователей)
    await _send_logo(message)

    # Вариант для уже зарегистрированных пользователей
    if user:
        if from_channel:
            await message.answer(
                f"Снова привет, {user['name']} 👋\n"
                "Вы перешли из нашего канала TemichevVet.\n\n"
                "Все ваши данные и питомцы сохранены. "
                "Можно сразу перейти к разделам в главном меню:",
                reply_markup=main_menu_kb(),
            )
        else:
            await message.answer(
                f"С возвращением, {user['name']} 👋\n\n"
                "Я помогу вам разобраться с состоянием питомца, напомню о важных процедурах и сохраню историю его здоровья.\n\n"
                "Выберите, с чего начнём 👇",
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

    intro_lines.append(START_WELCOME)
    intro_lines.append(START_NEED_REGISTER)
    intro_lines.append(
        "Для старта нажмите «👤 Зарегистрироваться и добавить питомца» — это займёт пару минут.\n"
        "Если хотите сначала посмотреть разделы, выберите «📋 Открыть главное меню»."
    )

    text = "\n\n".join(intro_lines)

    await message.answer(text, reply_markup=_welcome_kb())
    # Дополнительный короткий блок «Вопросы и ответы» сразу после онбординга
    await message.answer(_faq_after_start_text())

    await state.clear()


@router.message(F.text == "👤 Зарегистрироваться и добавить питомца")
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


@router.message(F.text.in_({"📋 Открыть главное меню", "🏠 Меню", "🏠 Главное меню"}))
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
        "Главное меню. Вы можете изучить разделы. "
        "Для точных рекомендаций по здоровью потребуется регистрация и добавление питомца.",
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
    if low in {"отменить", "⬅️ в главное меню", "📋 открыть главное меню"}:
        await message.answer("Ок.", reply_markup=main_menu_kb())
        await state.clear()
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("Пожалуйста, напишите имя одним словом.")
        return

    await state.update_data(name=name)
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

    if text.lower() == "отменить":
        await message.answer(
            "Регистрация прервана. Вы можете начать сначала командой /start.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    if text not in SUPPORTED_PETS:
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
    if low in {"отменить", "⬅️ в главное меню", "📋 открыть главное меню"}:
        await message.answer("Ок.", reply_markup=main_menu_kb())
        await state.clear()
        return

    pet_name_raw = (message.text or "").strip()
    pet_name = None if pet_name_raw.lower() == "пропустить" else pet_name_raw

    data = await state.get_data()
    name = data["name"]
    pet_type = data["pet_type"]

    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if user is None:
        user_id = create_user(tg_id, name)
    else:
        user_id = user["id"]

    create_pet(user_id, pet_type, pet_name)

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
