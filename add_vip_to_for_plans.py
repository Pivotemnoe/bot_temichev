#!/usr/bin/env python
import json
from pathlib import Path
from typing import Any, List, Dict

# Жёстко заданные пути к файлам, как вы описали
CARE_PATH = Path("app/data/care.json")
FAQ_PATH = Path("app/data/faq.json")

FIELD_NAME = "for_plans"
VIP_CODE = "vip"
PRO_CODE = "pro"


def _patch_for_plans_in_obj(obj: Any) -> int:
    """
    Рекурсивно проходит по структуре JSON и:
    - для каждого dict, у которого есть for_plans (list),
    - если в списке есть 'pro' и нет 'vip',
    - добавляет 'vip'.

    Возвращает количество изменённых блоков for_plans.
    """
    changed = 0

    if isinstance(obj, dict):
        # Обрабатываем поле for_plans в текущем объекте
        if FIELD_NAME in obj and isinstance(obj[FIELD_NAME], list):
            plans: List[Any] = obj[FIELD_NAME]
            normalized: List[str] = [str(p).lower() for p in plans]

            if PRO_CODE in normalized and VIP_CODE not in normalized:
                plans.append(VIP_CODE)
                changed += 1

        # Рекурсия по значениям словаря
        for v in obj.values():
            changed += _patch_for_plans_in_obj(v)

    elif isinstance(obj, list):
        # Рекурсия по элементам списка
        for item in obj:
            changed += _patch_for_plans_in_obj(item)

    return changed


def _process_file(path: Path) -> int:
    """
    Загружает JSON из файла, добавляет 'vip' в for_plans там, где нужно,
    и при наличии изменений перезаписывает файл.

    Возвращает количество изменённых блоков for_plans.
    """
    if not path.exists():
        print(f"[WARN] Файл не найден: {path}")
        return 0

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERR]  Не удалось прочитать JSON из {path}: {e}")
        return 0

    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    changed_blocks = _patch_for_plans_in_obj(data)
    after = json.dumps(data, ensure_ascii=False, sort_keys=True)

    if changed_blocks > 0 and before != after:
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[OK]   {path} — обновлено блоков for_plans: {changed_blocks}")
        except Exception as e:
            print(f"[ERR]  Не удалось записать файл {path}: {e}")
    else:
        print(f"[=]    {path} — изменений нет")

    return changed_blocks


def main() -> None:
    total_changed = 0

    print("=== Обработка JSON для VIP-доступа (for_plans) ===\n")

    total_changed += _process_file(CARE_PATH)
    total_changed += _process_file(FAQ_PATH)

    print("\n=== ИТОГО ===")
    print(f"Всего блоков for_plans с добавленным 'vip': {total_changed}")


if __name__ == "__main__":
    main()