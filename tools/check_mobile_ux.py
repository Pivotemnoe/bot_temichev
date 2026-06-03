#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.handlers.start import _faq_after_start_text, _welcome_kb  # noqa: E402
from app.keyboards import main_menu_kb, subscription_kb  # noqa: E402
from app.keyboards_knowledge import care_menu_kb, faq_menu_kb, nutrition_menu_kb  # noqa: E402
from app.keyboards_reminders import reminders_menu_kb  # noqa: E402
from app.knowledge_texts import NUTRITION_SEARCH_PROMPT  # noqa: E402
from app.texts import FEEDBACK_INTRO_TEXT, HELP_TEXT, NEXT_STEPS_TEXT  # noqa: E402


PHONE_WIDTH = 34
MAX_REPLY_BUTTON_LEN = 34
MAX_REPLY_BUTTONS_PER_ROW = 2
MAX_START_TEXT_CHARS = 1500


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _button_rows(markup) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in getattr(markup, "keyboard", []) or []:
        rows.append([str(getattr(btn, "text", btn)) for btn in row])
    return rows


def _render_text(title: str, text: str) -> None:
    print(f"\n=== {title} ===")
    for paragraph in _strip_html(text).splitlines():
        if not paragraph:
            print()
            continue
        print(textwrap.fill(paragraph, width=PHONE_WIDTH))


def _render_keyboard(title: str, rows: list[list[str]]) -> None:
    print(f"\n--- {title} ---")
    for row in rows:
        print(" | ".join(f"[{text}]" for text in row))


def _check_keyboard(name: str, rows: list[list[str]]) -> list[str]:
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        if len(row) > MAX_REPLY_BUTTONS_PER_ROW:
            errors.append(f"{name}: row {idx} has {len(row)} buttons")
        for text in row:
            if len(text) > MAX_REPLY_BUTTON_LEN:
                errors.append(f"{name}: long button {text!r} ({len(text)} chars)")
    return errors


def _check_text(name: str, text: str, *, max_chars: int | None = None) -> list[str]:
    text_plain = _strip_html(text)
    if max_chars is not None and len(text_plain) > max_chars:
        return [f"{name}: too long for first mobile screen ({len(text_plain)} chars)"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Check mobile Telegram UX texts and keyboards.")
    parser.add_argument("--quiet", action="store_true", help="run checks without rendering the phone preview")
    args = parser.parse_args()

    start_help = _faq_after_start_text()
    keyboards = {
        "welcome": _button_rows(_welcome_kb()),
        "main_menu": _button_rows(main_menu_kb()),
        "nutrition": _button_rows(nutrition_menu_kb()),
        "care": _button_rows(care_menu_kb()),
        "faq": _button_rows(faq_menu_kb()),
        "reminders": _button_rows(reminders_menu_kb()),
        "subscription": _button_rows(subscription_kb()),
    }
    texts = {
        "start_help": start_help,
        "next_steps": NEXT_STEPS_TEXT,
        "nutrition_search": NUTRITION_SEARCH_PROMPT,
        "feedback_intro": FEEDBACK_INTRO_TEXT,
        "help": HELP_TEXT,
    }

    errors: list[str] = []
    errors.extend(_check_text("start_help", start_help, max_chars=MAX_START_TEXT_CHARS))
    for name, rows in keyboards.items():
        errors.extend(_check_keyboard(name, rows))

    if not args.quiet:
        _render_text("Стартовый блок после /start", texts["start_help"])
        _render_keyboard("Главное меню", keyboards["main_menu"])
        _render_text("Что дальше", texts["next_steps"])
        _render_text("Питание: поиск", texts["nutrition_search"])
        _render_text("Обратная связь", texts["feedback_intro"])

    if errors:
        print("\nMobile UX issues:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("\nmobile ux check ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
