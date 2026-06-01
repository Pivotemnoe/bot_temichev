#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TemichevVetBot LLM — расширенная проверка JSON-баз знаний (v2).

Проверяются файлы:
  - app/data/foods.json  (Питание)
  - app/data/faq.json    (Вопрос–Ответ)
  - app/data/care.json   (Уход и забота)

Скрипт учитывает фактическую структуру файлов:
  * foods.json — без поля id, ключевые поля: name, allowed, why, how_much_is_dangerous, advice, category
  * faq.json   — с полем id, уникальность id, ключевые поля: id, question, short_answer, detailed_answer, species, for_plans
  * care.json  — с полем id, уникальность id, ключевые поля: id, title, summary, details, species, for_plans
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"


def load_json(path: Path) -> List[Dict[str, Any]] | None:
    """Загрузить JSON-массив из файла. Вернуть None при ошибке."""
    if not path.exists():
        print(f"[ОШИБКА] Файл не найден: {path}")
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ОШИБКА] Ошибка парсинга JSON: {path}\n  → {e}")
        return None

    if not isinstance(data, list):
        print(f"[ОШИБКА] Ожидался JSON-массив (list), но в {path} другой тип: {type(data)}")
        return None

    return data


# ==========================
# 1. ПИТАНИЕ — foods.json
# ==========================

def check_foods():
    print("=" * 60)
    print("Проверка раздела: Питание (app/data/foods.json)")
    print("=" * 60)

    path = DATA_DIR / "foods.json"
    data = load_json(path)
    if data is None:
        return

    print(f"Всего элементов: {len(data)}")

    # Соберём все ключи
    keys_counter: Counter[str] = Counter()
    for item in data:
        if isinstance(item, dict):
            keys_counter.update(item.keys())

    print(f"Найденные ключи в элементах ({len(keys_counter)}): {', '.join(sorted(keys_counter.keys()))}")

    # Проверка на обязательные поля
    required_fields = ["name", "allowed", "why", "how_much_is_dangerous", "advice", "category"]
    missing_required = {field: 0 for field in required_fields}

    empty_name = 0
    empty_category = 0
    empty_advice = 0
    wrong_allowed_type = 0
    wrong_why_structure = 0

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Элемент #{idx} не dict, а {type(item)} — пропускаю детальную проверку.")
            continue

        for field in required_fields:
            if field not in item:
                missing_required[field] += 1

        name = (str(item.get("name", "")) or "").strip()
        if not name:
            empty_name += 1

        category = (str(item.get("category", "")) or "").strip()
        if not category:
            empty_category += 1

        advice = (str(item.get("advice", "")) or "").strip()
        if not advice:
            empty_advice += 1

        # allowed должен быть bool
        allowed = item.get("allowed", None)
        if not isinstance(allowed, bool):
            wrong_allowed_type += 1

        # why — словарь с toxicity, effects, risk_level
        why = item.get("why")
        if not isinstance(why, dict):
            wrong_why_structure += 1
        else:
            for sub_key in ["toxicity", "effects", "risk_level"]:
                if sub_key not in why:
                    wrong_why_structure += 1
                    break

    # Отчёт по обязательным полям
    print("\nПроверка обязательных полей:")
    for field, cnt in missing_required.items():
        if cnt == 0:
            print(f"  - {field}: ОК (присутствует во всех или почти всех записях)")
        else:
            print(f"  - {field}: отсутствует в {cnt} элемент(ах)")

    print("\nПроверка содержимого полей:")
    print(f"  - name: пустых = {empty_name}")
    print(f"  - category: пустых = {empty_category}")
    print(f"  - advice: пустых = {empty_advice}")
    print(f"  - allowed (тип не bool): элементов = {wrong_allowed_type}")
    print(f"  - why (не dict или отсутствуют ключи toxicity/effects/risk_level): элементов = {wrong_why_structure}")

    print()  # пустая строка для разделения


# ==========================
# 2. FAQ — faq.json
# ==========================

def check_faq():
    print("=" * 60)
    print("Проверка раздела: Вопрос–Ответ (app/data/faq.json)")
    print("=" * 60)

    path = DATA_DIR / "faq.json"
    data = load_json(path)
    if data is None:
        return

    print(f"Всего элементов: {len(data)}")

    keys_counter: Counter[str] = Counter()
    for item in data:
        if isinstance(item, dict):
            keys_counter.update(item.keys())

    print(f"Найденные ключи в элементах ({len(keys_counter)}): {', '.join(sorted(keys_counter.keys()))}")

    # Проверка обязательных полей
    required_fields = ["id", "question", "short_answer", "detailed_answer", "species", "for_plans"]
    missing_required = {field: 0 for field in required_fields}

    empty_question = 0
    empty_short = 0
    empty_detailed = 0

    ids: List[str] = []
    invalid_species_count = 0
    invalid_for_plans_count = 0

    allowed_species = {"dog", "cat"}
    allowed_plans = {"free", "plus", "pro"}

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Элемент #{idx} не dict, а {type(item)} — пропускаю детальную проверку.")
            continue

        for field in required_fields:
            if field not in item:
                missing_required[field] += 1

        q = (str(item.get("question", "")) or "").strip()
        if not q:
            empty_question += 1

        s = (str(item.get("short_answer", "")) or "").strip()
        if not s:
            empty_short += 1

        d = (str(item.get("detailed_answer", "")) or "").strip()
        if not d:
            empty_detailed += 1

        _id = item.get("id")
        if isinstance(_id, str):
            ids.append(_id)

        # species — список из dog/cat
        species = item.get("species")
        if not isinstance(species, list) or not species:
            invalid_species_count += 1
        else:
            for sp in species:
                if sp not in allowed_species:
                    invalid_species_count += 1
                    break

        # for_plans — список тарифов
        plans = item.get("for_plans")
        if not isinstance(plans, list) or not plans:
            invalid_for_plans_count += 1
        else:
            for p in plans:
                if p not in allowed_plans:
                    invalid_for_plans_count += 1
                    break

    # Отчёт по обязательным полям
    print("\nПроверка обязательных полей:")
    for field, cnt in missing_required.items():
        if cnt == 0:
            print(f"  - {field}: ОК")
        else:
            print(f"  - {field}: отсутствует в {cnt} элемент(ах)")

    print("\nПроверка пустых значений:")
    print(f"  - question: пустых = {empty_question}")
    print(f"  - short_answer: пустых = {empty_short}")
    print(f"  - detailed_answer: пустых = {empty_detailed}")

    # Дубликаты id
    counter_ids = Counter(ids)
    duplicates = {k: v for k, v in counter_ids.items() if v > 1}
    if duplicates:
        print("\n⚠️ Дубликаты по полю 'id':")
        for _id, cnt in sorted(duplicates.items()):
            print(f"  '{_id}': {cnt} раз(а)")
    else:
        print("\nДубликатов по полю 'id' не обнаружено.")

    # Species и for_plans
    print("\nПроверка species:")
    print(f"  - элементов с некорректным/пустым species: {invalid_species_count}")

    print("\nПроверка for_plans:")
    print(f"  - элементов с некорректным/пустым for_plans: {invalid_for_plans_count}")

    print()  # пустая строка


# ==========================
# 3. CARE — care.json
# ==========================

def check_care():
    print("=" * 60)
    print("Проверка раздела: Уход и забота (app/data/care.json)")
    print("=" * 60)

    path = DATA_DIR / "care.json"
    data = load_json(path)
    if data is None:
        return

    print(f"Всего элементов: {len(data)}")

    keys_counter: Counter[str] = Counter()
    for item in data:
        if isinstance(item, dict):
            keys_counter.update(item.keys())

    print(f"Найденные ключи в элементах ({len(keys_counter)}): {', '.join(sorted(keys_counter.keys()))}")

    required_fields = ["id", "title", "summary", "details", "species", "for_plans"]
    missing_required = {field: 0 for field in required_fields}

    empty_title = 0
    empty_summary = 0
    empty_details = 0

    ids: List[str] = []
    invalid_species_count = 0
    invalid_for_plans_count = 0

    allowed_species = {"dog", "cat"}
    allowed_plans = {"free", "plus", "pro"}

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Элемент #{idx} не dict, а {type(item)} — пропускаю детальную проверку.")
            continue

        for field in required_fields:
            if field not in item:
                missing_required[field] += 1

        title = (str(item.get("title", "")) or "").strip()
        if not title:
            empty_title += 1

        summary = (str(item.get("summary", "")) or "").strip()
        if not summary:
            empty_summary += 1

        details = (str(item.get("details", "")) or "").strip()
        if not details:
            empty_details += 1

        _id = item.get("id")
        if isinstance(_id, str):
            ids.append(_id)

        species = item.get("species")
        if not isinstance(species, list) or not species:
            invalid_species_count += 1
        else:
            for sp in species:
                if sp not in allowed_species:
                    invalid_species_count += 1
                    break

        plans = item.get("for_plans")
        if not isinstance(plans, list) or not plans:
            invalid_for_plans_count += 1
        else:
            for p in plans:
                if p not in allowed_plans:
                    invalid_for_plans_count += 1
                    break

    print("\nПроверка обязательных полей:")
    for field, cnt in missing_required.items():
        if cnt == 0:
            print(f"  - {field}: ОК")
        else:
            print(f"  - {field}: отсутствует в {cnt} элемент(ах)")

    print("\nПроверка пустых значений:")
    print(f"  - title: пустых = {empty_title}")
    print(f"  - summary: пустых = {empty_summary}")
    print(f"  - details: пустых = {empty_details}")

    counter_ids = Counter(ids)
    duplicates = {k: v for k, v in counter_ids.items() if v > 1}
    if duplicates:
        print("\n⚠️ Дубликаты по полю 'id':")
        for _id, cnt in sorted(duplicates.items()):
            print(f"  '{_id}': {cnt} раз(а)")
    else:
        print("\nДубликатов по полю 'id' не обнаружено.")

    print("\nПроверка species:")
    print(f"  - элементов с некорректным/пустым species: {invalid_species_count}")

    print("\nПроверка for_plans:")
    print(f"  - элементов с некорректным/пустым for_plans: {invalid_for_plans_count}")

    print()  # пустая строка


# ==========================
# MAIN
# ==========================

def main():
    print("=== TemichevVetBot LLM — проверка JSON-баз знаний v2 ===\n")
    check_foods()
    check_faq()
    check_care()


if __name__ == "__main__":
    main()