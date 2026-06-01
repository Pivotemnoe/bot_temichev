import os
from typing import List, Dict, Optional

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Ты — TemichevVetBot v3, ветеринарный ассистент для владельцев собак и кошек.

Отвечаешь только на русском языке, спокойным профессиональным тоном, без паники и без сюсюканья.
Твоя задача — помочь владельцу оценить состояние питомца и понять срочность обращения к врачу.

Жёсткие ограничения:
- Не ставь диагнозы и не называй конкретные болезни.
- Не назначай лекарства, дозировки и схемы лечения.
- Не советуй человеческие препараты и «домашние схемы лечения».
- Всегда подчёркивай, что очный осмотр врача обязателен.

Учитывай:
- вид животного (собака или кошка);
- возрастную группу (щенок/котёнок, взрослый, пожилой), если она указана;
- длительность проблемы (часы, дни, «давно, периодически»), если указана;
- текст жалобы владельца.

При прочих равных:
- у щенков/котят и пожилых животных при сомнениях выбирай более высокий уровень срочности;
- если проблема длится больше суток, повторяется или состояние ухудшается — тоже склоняйся к более высокой срочности.

Если информации мало — задай 1–3 уточняющих вопроса строго по делу.

Уровни срочности (выбери один):
- 🟢 Наблюдаем дома.
- 🟡 Планово показать питомца врачу.
- 🟥 Срочно в клинику.

Во 2-м пункте ответа обязательно используй формат:
«2) Уровень срочности: 🟢 ...»
или
«2) Уровень срочности: 🟡 ...»
или
«2) Уровень срочности: 🟥 ...»

Структура ответа владельцу:
1) Кратко: что по симптомам может происходить (без диагноза и названий болезней).
2) Уровень срочности и короткое объяснение «почему».
3) Что делать сейчас — 3–4 чётких шага.
4) Чего делать нельзя — до 3 пунктов.
5) Тревожные признаки (до 3 пунктов), при которых нужно срочно в клинику.
6) Фраза: «Этот ответ не заменяет очный осмотр ветеринарного врача».

Пиши короткими абзацами и списками, без лишних рассуждений и повторов.
"""

# ===== МОДЕЛИ И ТАРИФЫ =====

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

MODEL_FREE = os.getenv("OPENAI_MODEL_FREE", DEFAULT_MODEL)
MODEL_PLUS = os.getenv("OPENAI_MODEL_PLUS", DEFAULT_MODEL)
MODEL_PRO = os.getenv("OPENAI_MODEL_PRO", DEFAULT_MODEL)
MODEL_VIP = os.getenv("OPENAI_MODEL_VIP", MODEL_PRO or DEFAULT_MODEL)


def _get_model_for_plan(plan_code: Optional[str]) -> str:
    """
    Выбор имени модели в зависимости от тарифа.
    План приходит из БД (free / plus / pro / vip).
    """
    plan = (plan_code or "").lower()
    if plan == "free":
        return MODEL_FREE
    if plan == "plus":
        return MODEL_PLUS
    if plan == "pro":
        return MODEL_PRO
    if plan == "vip":
        return MODEL_VIP
    return DEFAULT_MODEL


# ===== УНИФИЦИРОВАННАЯ ЛОГИКА TEMPERATURE =====

def _supports_temperature(model_name: str) -> bool:
    """
    Определяем, можно ли передавать temperature для данной модели.

    - reasoning-модели o1 / o3 → без temperature (API не принимает кастомные значения);
    - gpt-5.1-chat-latest по логам также не принимает temperature (только дефолт);
    - остальные GPT-модели (4.x / 4o / mini / 5-mini и т.п.) → temperature поддерживают.
    """
    if not model_name:
        return True

    base = model_name.lower().split(":", 1)[0]

    # reasoning-модели
    if base.startswith("o1") or base.startswith("o3"):
        return False

    # специфика текущего API: gpt-5.1-chat-latest не принимает кастомный temperature
    if base == "gpt-5.1-chat-latest":
        return False

    # остальные GPT-модели — OK
    if base.startswith("gpt"):
        return True

    # по умолчанию считаем, что temperature допустим
    return True


# ===== PROMPT BUILDER =====

def _format_pets_for_prompt(pets: List[Dict], main_pet: Optional[Dict]) -> str:
    """
    Формирует блок с информацией о сохранённых питомцах для промпта.
    """
    if not pets:
        return "У пользователя пока нет сохранённых питомцев."

    lines: List[str] = []
    for p in pets:
        p_type = p.get("pet_type") or "питомец"
        name = p.get("pet_name") or "(без имени)"
        marker = ""
        if main_pet and main_pet.get("id") == p.get("id"):
            marker = " [основной питомец для этого запроса]"
        lines.append(f"- {p_type} — {name}{marker}")

    return "Сохранённые питомцы:\n" + "\n".join(lines)


def build_triage_prompt(
    user: Dict,
    pets: List[Dict],
    complaint_text: str,
    main_pet: Optional[Dict] = None,
    age_info: Optional[str] = None,
    duration_info: Optional[str] = None,
) -> str:
    """
    Собрать текстовый prompt для LLM на основе данных пользователя и питомца.
    """
    owner_name = user.get("name") or "владелец"
    pets_block = _format_pets_for_prompt(pets, main_pet)

    if main_pet:
        mp_type = main_pet.get("pet_type") or "питомец"
        mp_name = main_pet.get("pet_name") or "(без имени)"
        pet_block = f"Основной питомец: {mp_type} — {mp_name}.\n"
    else:
        pet_block = "Основной питомец для этой жалобы не выбран.\n"

    extra: List[str] = []
    if age_info:
        extra.append(f"Возрастная группа: {age_info}.")
    if duration_info:
        extra.append(f"Длительность проблемы: {duration_info}.")

    extra_block = ("\n" + "\n".join(extra) + "\n") if extra else ""

    return (
        f"Владелец: {owner_name}\n"
        f"{pets_block}\n\n"
        f"{pet_block}"
        f"{extra_block}\n"
        f"Жалоба владельца:\n{complaint_text}\n\n"
        "Сформируй ответ строго по структуре системной инструкции."
    )


# ===== LLM CALLER =====

def call_triage_llm(
    user: Dict,
    pets: List[Dict],
    complaint_text: str,
    main_pet: Optional[Dict] = None,
    age_info: Optional[str] = None,
    duration_info: Optional[str] = None,
    plan_code: Optional[str] = None,
) -> str:
    """
    Синхронный вызов LLM для анализа жалобы.
    Используется из async-кода через asyncio.to_thread.
    Возвращает только текст ответа.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY не указан в .env")

    model_name = _get_model_for_plan(plan_code)

    user_prompt = build_triage_prompt(
        user=user,
        pets=pets,
        complaint_text=complaint_text,
        main_pet=main_pet,
        age_info=age_info,
        duration_info=duration_info,
    )

    req: Dict = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_prompt},
        ],
    }

    # temperature передаём только тем моделям, которые его поддерживают
    if _supports_temperature(model_name):
        req["temperature"] = 1  # исправлено: без запятой, передаём число, а не массив

    response = client.chat.completions.create(**req)

    msg = response.choices[0].message.content
    return msg.strip() if msg else "Не удалось сформировать ответ."