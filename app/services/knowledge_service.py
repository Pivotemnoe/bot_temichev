# app/services/knowledge_service.py

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional


# ===== Пути к файлам данных =====

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FOODS_FILE = DATA_DIR / "foods.json"
FAQ_FILE = DATA_DIR / "faq.json"
CARE_FILE = DATA_DIR / "care.json"


# ===== Кэширование загруженных данных =====

_FOODS_CACHE: Optional[List[Dict[str, Any]]] = None
_FAQ_CACHE: Optional[List[Dict[str, Any]]] = None
_CARE_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return []


def get_foods() -> List[Dict[str, Any]]:
    global _FOODS_CACHE
    if _FOODS_CACHE is None:
        _FOODS_CACHE = _load_json(FOODS_FILE)
    return _FOODS_CACHE


def get_faq_items() -> List[Dict[str, Any]]:
    global _FAQ_CACHE
    if _FAQ_CACHE is None:
        _FAQ_CACHE = _load_json(FAQ_FILE)
    return _FAQ_CACHE


def get_care_items() -> List[Dict[str, Any]]:
    global _CARE_CACHE
    if _CARE_CACHE is None:
        _CARE_CACHE = _load_json(CARE_FILE)
    return _CARE_CACHE


# ===== Вспомогательные функции фильтрации по тарифу и виду =====

def _match_plan(item: Dict[str, Any], plan: Optional[str]) -> bool:
    """
    Если у элемента есть поле for_plans (список кодов тарифов),
    то считаем элемент доступным только на этих тарифах.
    Если поля нет или список пустой — доступно всем тарифам.
    Если plan=None — не режем по тарифу.
    """
    if plan is None:
        return True
    allowed_plans = item.get("for_plans")
    if not allowed_plans:
        return True
    return plan in allowed_plans


def _match_species(item: Dict[str, Any], species: Optional[str]) -> bool:
    """
    Опциональная фильтрация по виду:
    - если у элемента есть поле species (строка или список строк),
      то при заданном species оставляем только совпадающие.
    - если species=None — не фильтруем.
    - если у элемента вида нет — считаем универсальным.
    """
    if species is None:
        return True

    v = item.get("species")
    if not v:
        return True

    if isinstance(v, str):
        return v == species

    if isinstance(v, list):
        return species in v

    return True


def _filter_items(
    items: List[Dict[str, Any]],
    plan: Optional[str],
    species: Optional[str],
) -> List[Dict[str, Any]]:
    return [
        it
        for it in items
        if _match_plan(it, plan) and _match_species(it, species)
    ]


# ===== Токенизация и "умный" поиск =====

_STOP_WORDS = {
    # общие
    "и", "или", "но", "что", "это", "как", "когда", "нужно", "надо",
    "по", "про", "при", "для", "без", "со", "на", "в", "из", "от", "до", "у",
    "же", "бы", "ещё", "еще", "ли", "то",
    # общие для домена
    "кошка", "кошки", "кошке", "кошку",
    "кот", "кота", "коту", "котенок", "котёнок", "котенка", "котёнка",
    "собака", "собаки", "собаке", "собаку",
    "щенок", "щенка", "щенку",
    "щенки", "котята", "котенку", "котёнку",
    "животное", "животные", "питомец", "питомца", "питомцу",
    "уход", "уходу", "уходом", "ухода",
    "вопрос", "ответ", "здоровье",
}


_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


def _tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    return _WORD_RE.findall(text)


def _content_tokens(text: str) -> List[str]:
    return [t for t in _tokenize(text) if t not in _STOP_WORDS]


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _score_item(
    query: str,
    item_text_main: str,
    item_text_extra: str = "",
    keywords: Optional[List[str]] = None,
) -> int:
    """
    Универсальный скоринг:
    - сильное совпадение подстроки;
    - пересечение содержательных токенов;
    - лёгкий учёт опечаток через SequenceMatcher.
    """
    q = (query or "").strip().lower()
    if not q:
        return 0

    score = 0

    # 1) Прямое вхождение строки в ключевые поля
    haystack_main = (item_text_main or "").lower()
    haystack_extra = (item_text_extra or "").lower()
    haystack_keywords = " ".join(keywords or []).lower()

    if q in haystack_main:
        score += 6
    elif q in haystack_keywords:
        score += 5
    elif q in haystack_extra:
        score += 3

    # 2) Токены запроса vs токены объекта
    query_tokens = set(_content_tokens(q))
    if not query_tokens:
        return score

    item_tokens_main = set(_content_tokens(haystack_main))
    item_tokens_extra = set(_content_tokens(haystack_extra))
    item_tokens_keywords = set(_content_tokens(haystack_keywords))

    # Совпадения по "главным" токенам
    common_main = query_tokens & item_tokens_main
    score += 2 * len(common_main)

    # Совпадения по keywords
    common_kw = query_tokens & item_tokens_keywords
    score += 2 * len(common_kw)

    # Совпадения по "вспомогательному" тексту
    common_extra = query_tokens & item_tokens_extra
    score += 1 * len(common_extra)

    # 3) Лёгкий fuzzy-match по токенам (для опечаток)
    # Делаем только если базовый скоринг нулевой
    if score == 0:
        item_all_tokens = (
            item_tokens_main | item_tokens_keywords | item_tokens_extra
        )
        for qt in query_tokens:
            for it in item_all_tokens:
                if len(qt) >= 4 and len(it) >= 4:
                    if _similar(qt, it) >= 0.8:
                        score += 1
                        break

    return score


# ===== Питание (FOODS) =====

def find_food(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Поиск продуктов.
    Сейчас без деления по тарифам и видам: питание доступно всем.
    """
    query = (query or "").strip()
    if not query:
        return []

    items = get_foods()
    q_lower = query.lower()

    # Простой скоринг, чтобы хотя бы упорядочить результаты
    scored: List[tuple[int, Dict[str, Any]]] = []

    for item in items:
        name = item.get("name", "")
        category = item.get("category", "")
        keywords = item.get("keywords") or []

        text_main = name
        text_extra = category
        kw_text = " ".join(keywords)

        score = _score_item(q_lower, text_main, text_extra, keywords)
        # Для FOODS дополнительно чуть усилим прямое вхождение
        if q_lower in name.lower():
            score += 3
        if q_lower in kw_text.lower():
            score += 2

        if score > 0:
            scored.append((score, item))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:limit]]


# ===== FAQ =====

def get_faq_for_plan(
    plan: Optional[str],
    species: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Простой список FAQ для конкретного тарифа (например, для популярного списка).
    """
    items = _filter_items(get_faq_items(), plan=plan, species=species)
    return items[:limit]


def search_faq(
    query: str,
    species: Optional[str] = None,
    plan: Optional[str] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    "Умный" поиск по FAQ с учётом:
    - тарифа (plan),
    - вида (species),
    - токенов, keywords и лёгкого fuzzy-match.
    Если query пустой — возвращает первые N подходящих вопросов (для популярного списка).
    """
    items = _filter_items(get_faq_items(), plan=plan, species=species)

    query = (query or "").strip()
    if not query:
        return items[:limit]

    scored: List[tuple[int, Dict[str, Any]]] = []

    for item in items:
        qtext = item.get("question", "") or ""
        short = item.get("short_answer", "") or ""
        detailed = item.get("detailed_answer", "") or ""
        keywords = item.get("keywords") or []

        text_main = qtext
        text_extra = short + " " + detailed

        score = _score_item(query, text_main, text_extra, keywords)
        if score > 0:
            scored.append((score, item))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:limit]]


# ===== Уход и привычки (CARE) =====

def get_care_for_plan(
    plan: Optional[str],
    species: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Список карточек по уходу для конкретного тарифа.
    Используется для демонстрации примеров.
    """
    items = _filter_items(get_care_items(), plan=plan, species=species)
    return items[:limit]


def search_care(
    query: str,
    species: Optional[str] = None,
    plan: Optional[str] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    "Умный" поиск по карточкам ухода с учётом:
    - тарифа (plan),
    - вида (species),
    - токенов, keywords и fuzzy-match.
    Если query пустой — возвращаем первые N карточек (для списка примеров).
    """
    items = _filter_items(get_care_items(), plan=plan, species=species)

    query = (query or "").strip()
    if not query:
        return items[:limit]

    scored: List[tuple[int, Dict[str, Any]]] = []

    for item in items:
        title = item.get("title", "") or ""
        category = item.get("category", "") or ""
        summary = item.get("summary", "") or ""
        details = item.get("details", "") or ""
        keywords = item.get("keywords") or []

        text_main = f"{title} {category}"
        text_extra = summary + " " + details

        score = _score_item(query, text_main, text_extra, keywords)
        if score > 0:
            scored.append((score, item))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:limit]]