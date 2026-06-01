# tools/check_knowledge_json.py

"""
Утилита для проверки JSON-баз знаний (Питание, Вопрос–Ответ и др.).

Запуск (из корня проекта):

    source .venv/bin/activate
    python tools/check_knowledge_json.py

Перед запуском проверь пути к JSON-файлам в списке KNOWLEDGE_FILES.
"""

import json
from pathlib import Path
from collections import Counter
from typing import Any


# === НАСТРОЙКА ПУТЕЙ ===========================================
# При необходимости поправь пути к файлам под фактическую структуру проекта.
# Примеры:
#   app/data/nutrition.json
#   app/data/faq.json
#
# Если имена другие — просто поменяй Path(...).

KNOWLEDGE_FILES = [
    ("Питание", Path("app/data/foods.json")),
    ("Вопрос–Ответ", Path("app/data/faq.json")),
    ("Уход и завбота", Path("app/data/care.json")),
]


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================================


def _load_json(path: Path) -> Any:
    if not path.exists():
        print(f"[ОШИБКА] Файл не найден: {path}")
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ОШИБКА] Не удалось прочитать {path}: {e}")
        return None


def _normalize_to_list(data: Any) -> list:
    """
    Унифицируем структуру:
    - если data — список, возвращаем как есть;
    - если dict с ключом 'items' или 'data', пробуем взять его;
    - иначе оборачиваем в список.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return data["items"]
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
    return [data]


def _check_empty_fields(items: list[dict], fields: list[str]) -> dict[str, int]:
    """
    Подсчитать количество пустых значений по указанным полям.
    Пустым считаем: None или пустую/пробельную строку.
    """
    result: dict[str, int] = {f: 0 for f in fields}
    for obj in items:
        if not isinstance(obj, dict):
            continue
        for f in fields:
            if f not in obj:
                continue
            v = obj.get(f)
            if v is None:
                result[f] += 1
            elif isinstance(v, str) and not v.strip():
                result[f] += 1
    return result


def _check_duplicates(items: list[dict], field: str) -> Counter:
    """
    Найти дубликаты по указанному полю (если оно есть).
    Возвращает Counter только для значений, которые встречаются > 1 раза.
    """
    values: list[Any] = []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        if field in obj:
            values.append(obj[field])
    cnt = Counter(values)
    return Counter({k: v for k, v in cnt.items() if v > 1})


def _print_header(title: str):
    print("\n" + "=" * 60)
    print(f"{title}")
    print("=" * 60)


# === ОСНОВНАЯ ЛОГИКА ===========================================


def analyze_file(label: str, path: Path) -> None:
    _print_header(f"Проверка раздела: {label} ({path})")

    data = _load_json(path)
    if data is None:
        return

    items = _normalize_to_list(data)
    total = len(items)
    print(f"Всего элементов: {total}")

    if total == 0:
        print("⚠️  Список пуст.")
        return

    # Соберём все ключи, которые встречаются в объектах
    all_keys: set[str] = set()
    for obj in items:
        if isinstance(obj, dict):
            all_keys.update(obj.keys())

    print(f"Найденные ключи в элементах ({len(all_keys)}): {', '.join(sorted(all_keys))}")

    # Проверка пустых полей по "типовым" возможным полям
    candidate_text_fields = [
        "title",
        "name",
        "question",
        "answer",
        "text",
        "description",
    ]
    # Оставим только те, которые реально присутствуют
    text_fields = [f for f in candidate_text_fields if f in all_keys]

    if text_fields:
        empty_stats = _check_empty_fields(items, text_fields)
        print("\nПроверка пустых значений в текстовых полях:")
        for f in text_fields:
            count = empty_stats.get(f, 0)
            print(f"  - {f}: пустых = {count}")
    else:
        print("\nТекстовые поля из известных не найдены (title/question/answer/text/description).")

    # Поиск дубликатов по id / slug (если есть)
    for key in ("id", "slug", "code"):
        if key in all_keys:
            dups = _check_duplicates(items, key)
            if dups:
                print(f"\n⚠️ Дубликаты по полю '{key}':")
                for val, cnt in dups.items():
                    print(f"  {val!r}: {cnt} раз(а)")
            else:
                print(f"\nДубликатов по полю '{key}' не найдено.")
        else:
            # поле отсутствует — просто информируем
            print(f"\nПоле '{key}' в элементах не обнаружено — пропускаем проверку дубликатов.")


def main():
    print("=== TemichevVetBot LLM — проверка JSON-баз знаний ===")
    for label, path in KNOWLEDGE_FILES:
        analyze_file(label, path)


if __name__ == "__main__":
    main()