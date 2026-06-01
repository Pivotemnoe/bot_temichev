#!/usr/bin/env python
"""
TemichevVetBot LLM — консольный просмотрщик баз знаний.

Поддерживаемые разделы:
- Питание     (app/data/foods.json)
- Вопрос–Ответ (app/data/faq.json)
- Уход и забота (app/data/care.json)

Возможности:
- Статистика по разделам.
- Поиск по тексту в каждом разделе (кейсы: питание / FAQ / уход).
"""

import json
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"

FOODS_PATH = DATA_DIR / "foods.json"
FAQ_PATH = DATA_DIR / "faq.json"
CARE_PATH = DATA_DIR / "care.json"


# ===== Служебные функции =====

def _load_json(path: Path):
    if not path.exists():
        print(f"[ОШИБКА] Файл не найден: {path}")
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ОШИБКА] Не удалось прочитать JSON {path}: {e}")
        return []
    if not isinstance(data, list):
        print(f"[ОШИБКА] Ожидался список объектов в корне файла: {path}")
        return []
    return data


def _pause():
    input("\nНажмите Enter, чтобы продолжить...")


# ===== Питание =====

def foods_stats(foods: list[dict]) -> None:
    print("=== Раздел: Питание ===")
    print(f"Всего записей: {len(foods)}")

    if not foods:
        return

    # allowed: true/false
    allowed_counter = Counter()
    cat_counter = Counter()

    for item in foods:
        allowed = item.get("allowed")
        if isinstance(allowed, bool):
            allowed_counter["разрешено" if allowed else "запрещено"] += 1
        cat = item.get("category") or "без категории"
        cat_counter[cat] += 1

    print("\nРазрешено/запрещено:")
    for k, v in allowed_counter.most_common():
        print(f"  - {k}: {v}")

    print("\nКатегории:")
    for cat, cnt in cat_counter.most_common():
        print(f"  - {cat}: {cnt}")


def foods_search(foods: list[dict], query: str) -> None:
    q = query.lower()
    results = []

    for item in foods:
        name = (item.get("name") or "").lower()
        category = (item.get("category") or "").lower()
        why = item.get("why") or {}
        why_text = " ".join(
            str(why.get(k, "")) for k in ("toxicity", "effects", "risk_level")
        ).lower()

        if q in name or q in category or q in why_text:
            results.append(item)

    print(f"\nНайдено записей в разделе Питание: {len(results)}\n")

    for idx, item in enumerate(results, start=1):
        name = item.get("name") or "(без названия)"
        allowed = item.get("allowed")
        allowed_str = (
            "✅ можно" if allowed is True
            else "⛔ нельзя" if allowed is False
            else "не указано"
        )
        category = item.get("category") or "без категории"
        why = item.get("why") or {}
        effects = why.get("effects") or ""
        risk = why.get("risk_level") or ""

        print(f"{idx}. {name} — {allowed_str}")
        print(f"   Категория: {category}")
        if effects:
            print(f"   Влияние: {effects}")
        if risk:
            print(f"   Уровень риска: {risk}")
        advice = item.get("advice") or ""
        if advice:
            print(f"   Совет: {advice}")
        print()


# ===== FAQ =====

def faq_stats(faq: list[dict]) -> None:
    print("=== Раздел: Вопрос–Ответ ===")
    print(f"Всего записей: {len(faq)}")
    if not faq:
        return

    cat_counter = Counter()
    species_counter = Counter()
    plans_counter = Counter()

    for item in faq:
        cat = item.get("category") or "без категории"
        cat_counter[cat] += 1

        species = item.get("species") or []
        for s in species:
            species_counter[s] += 1

        plans = item.get("for_plans") or []
        for p in plans:
            plans_counter[p] += 1

    print("\nКатегории:")
    for cat, cnt in cat_counter.most_common():
        print(f"  - {cat}: {cnt}")

    print("\nВиды (species):")
    for s, cnt in species_counter.most_common():
        print(f"  - {s}: {cnt}")

    print("\nТарифы (for_plans):")
    for p, cnt in plans_counter.most_common():
        print(f"  - {p}: {cnt}")


def faq_search(faq: list[dict], query: str) -> None:
    q = query.lower()
    results = []

    for item in faq:
        q_text = (item.get("question") or "").lower()
        short = (item.get("short_answer") or "").lower()
        detailed = (item.get("detailed_answer") or "").lower()
        tags = " ".join(item.get("tags") or []).lower()
        keywords = " ".join(item.get("keywords") or []).lower()
        item_id = (item.get("id") or "").lower()
        category = (item.get("category") or "").lower()

        haystack = " ".join([q_text, short, detailed, tags, keywords, item_id, category])

        if q in haystack:
            results.append(item)

    print(f"\nНайдено записей в разделе Вопрос–Ответ: {len(results)}\n")

    for idx, item in enumerate(results, start=1):
        item_id = item.get("id") or "(без id)"
        question = item.get("question") or "(без вопроса)"
        short = item.get("short_answer") or ""
        species = ", ".join(item.get("species") or [])
        plans = ", ".join(item.get("for_plans") or [])
        category = item.get("category") or "без категории"

        print(f"{idx}. [{item_id}] {question}")
        print(f"   Категория: {category}")
        if species:
            print(f"   Виды: {species}")
        if plans:
            print(f"   Тарифы: {plans}")
        if short:
            print(f"   Краткий ответ: {short}")
        print()


# ===== Уход и забота =====

def care_stats(care: list[dict]) -> None:
    print("=== Раздел: Уход и забота ===")
    print(f"Всего записей: {len(care)}")
    if not care:
        return

    cat_counter = Counter()
    species_counter = Counter()
    plans_counter = Counter()

    for item in care:
        cat = item.get("category") or "без категории"
        cat_counter[cat] += 1

        species = item.get("species") or []
        for s in species:
            species_counter[s] += 1

        plans = item.get("for_plans") or []
        for p in plans:
            plans_counter[p] += 1

    print("\nКатегории:")
    for cat, cnt in cat_counter.most_common():
        print(f"  - {cat}: {cnt}")

    print("\nВиды (species):")
    for s, cnt in species_counter.most_common():
        print(f"  - {s}: {cnt}")

    print("\nТарифы (for_plans):")
    for p, cnt in plans_counter.most_common():
        print(f"  - {p}: {cnt}")


def care_search(care: list[dict], query: str) -> None:
    q = query.lower()
    results = []

    for item in care:
        title = (item.get("title") or "").lower()
        summary = (item.get("summary") or "").lower()
        details = (item.get("details") or "").lower()
        warning = (item.get("warning") or "").lower()
        keywords = " ".join(item.get("keywords") or []).lower()
        item_id = (item.get("id") or "").lower()
        category = (item.get("category") or "").lower()

        haystack = " ".join([title, summary, details, warning, keywords, item_id, category])

        if q in haystack:
            results.append(item)

    print(f"\nНайдено записей в разделе Уход и забота: {len(results)}\n")

    for idx, item in enumerate(results, start=1):
        item_id = item.get("id") or "(без id)"
        title = item.get("title") or "(без заголовка)"
        summary = item.get("summary") or ""
        species = ", ".join(item.get("species") or [])
        plans = ", ".join(item.get("for_plans") or [])
        category = item.get("category") or "без категории"

        print(f"{idx}. [{item_id}] {title}")
        print(f"   Категория: {category}")
        if species:
            print(f"   Виды: {species}")
        if plans:
            print(f"   Тарифы: {plans}")
        if summary:
            print(f"   Кратко: {summary}")
        print()


# ===== Главное меню =====

def main():
    print("=== TemichevVetBot LLM — CLI просмотрщик баз знаний ===")

    foods = _load_json(FOODS_PATH)
    faq = _load_json(FAQ_PATH)
    care = _load_json(CARE_PATH)

    while True:
        print("\nВыберите действие:")
        print("  1 — Показать статистику по всем разделам")
        print("  2 — Поиск по разделу Питание")
        print("  3 — Поиск по разделу Вопрос–Ответ")
        print("  4 — Поиск по разделу Уход и забота")
        print("  0 — Выход")

        choice = input("> ").strip()

        if choice == "0":
            print("Выход.")
            break

        if choice == "1":
            print()
            foods_stats(foods)
            print()
            faq_stats(faq)
            print()
            care_stats(care)
            _pause()
            continue

        if choice == "2":
            q = input("Введите строку для поиска по Питанию: ").strip()
            if q:
                foods_search(foods, q)
            else:
                print("Пустой запрос, поиск отменён.")
            _pause()
            continue

        if choice == "3":
            q = input("Введите строку для поиска по Вопрос–Ответ: ").strip()
            if q:
                faq_search(faq, q)
            else:
                print("Пустой запрос, поиск отменён.")
            _pause()
            continue

        if choice == "4":
            q = input("Введите строку для поиска по Уход и забота: ").strip()
            if q:
                care_search(care, q)
            else:
                print("Пустой запрос, поиск отменён.")
            _pause()
            continue

        print("Неизвестная команда. Введите 0–4.")


if __name__ == "__main__":
    main()