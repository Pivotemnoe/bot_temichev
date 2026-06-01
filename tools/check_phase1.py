from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("BOT_TOKEN", "phase1-dummy-token")
os.environ.setdefault("OPENAI_API_KEY", "phase1-dummy-key")
os.environ.setdefault("ADMIN_CHAT_ID", "0")
os.environ.setdefault("DB_PATH", ":memory:")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.constants import SUPPORTED_PETS
from app.db import init_db
from app.handlers.triage import _extract_urgency, _urgency_level_from_emoji


def check_supported_pet_values() -> None:
    assert SUPPORTED_PETS["🐱 Кот/Кошка"] == "кошка"
    assert SUPPORTED_PETS["🐶 Собака"] == "собака"


def check_urgency_parser() -> None:
    cases = [
        ("2) Уровень срочности: 🟢 наблюдаем дома", "🟢", "green"),
        ("2) Уровень срочности: 🟡 планово к врачу", "🟡", "yellow"),
        ("2) Уровень срочности: 🟥 срочно в клинику", "🟥", "red"),
        ("Срочность: 🔴 срочно в клинику", "🔴", "red"),
    ]
    for text, expected_emoji, expected_level in cases:
        emoji, label = _extract_urgency(text)
        assert emoji == expected_emoji
        assert label
        assert _urgency_level_from_emoji(emoji) == expected_level


def check_schema() -> None:
    init_db()


def main() -> None:
    check_supported_pet_values()
    check_urgency_parser()
    check_schema()
    print("phase1 checks ok")


if __name__ == "__main__":
    main()
