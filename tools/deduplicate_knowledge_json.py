#!/usr/bin/env python
"""
TemichevVetBot LLM — удаление дублей в JSON-базах знаний.

Правило:
- Для каждого файла с полем `id` оставляем ПЕРВОЕ вхождение каждого id.
- Все последующие записи с тем же id отбрасываются.
- Исходные файлы не трогаем — создаём новые *_dedup.json.

Обрабатываем:
- app/data/faq.json      → app/data/faq_dedup.json
- app/data/care.json     → app/data/care_dedup.json

foods.json не трогаем, т.к. там нет поля id.
"""

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"


def deduplicate_by_id(input_path: Path, output_path: Path) -> None:
    print(f"\nОбработка файла: {input_path}")

    if not input_path.exists():
        print(f"[ОШИБКА] Файл не найден: {input_path}")
        return

    with input_path.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ОШИБКА] Не удалось прочитать JSON: {e}")
            return

    if not isinstance(data, list):
        print("[ОШИБКА] Ожидался список объектов в корне файла.")
        return

    seen_ids: set[str] = set()
    result: list[dict] = []
    duplicates_count = 0

    for item in data:
        if not isinstance(item, dict):
            # на всякий случай пропускаем странные элементы
            continue

        item_id = item.get("id")
        if not item_id:
            # элементы без id пропускаем без изменений
            result.append(item)
            continue

        if item_id in seen_ids:
            duplicates_count += 1
            continue

        seen_ids.add(item_id)
        result.append(item)

    # сохраняем новый файл
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  Всего записей в исходном файле: {len(data)}")
    print(f"  Уникальных id:                  {len(seen_ids)}")
    print(f"  Дубликатов (удалено):           {duplicates_count}")
    print(f"  Результат сохранён в:           {output_path}")


def main():
    print("=== TemichevVetBot LLM — удаление дублей в базах знаний ===")

    faq_path = DATA_DIR / "faq.json"
    faq_out = DATA_DIR / "faq_dedup.json"
    deduplicate_by_id(faq_path, faq_out)

    care_path = DATA_DIR / "care.json"
    care_out = DATA_DIR / "care_dedup.json"
    deduplicate_by_id(care_path, care_out)

    print("\nГотово. Проверь содержимое *_dedup.json и при желании "
          "замени ими оригинальные файлы.")


if __name__ == "__main__":
    main()