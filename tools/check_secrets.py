#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_FILE_BYTES = 1_000_000

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "telegram_bot_token",
        re.compile(r"\b\d{7,12}:[A-Za-z0-9_-]{30,}\b"),
    ),
    (
        "openai_api_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    ),
    (
        "bot_token_assignment",
        re.compile(
            r"\bBOT_TOKEN\s*=\s*"
            r"(?!$|<|os\.getenv|os\.environ|telegram_bot_token_from_botfather|токен_бота_из_BotFather|your_|example)"
            r"[^\s#]+",
            re.IGNORECASE,
        ),
    ),
    (
        "openai_key_assignment",
        re.compile(
            r"\bOPENAI_API_KEY\s*=\s*"
            r"(?!$|<|os\.getenv|os\.environ|openai_or_compatible_api_key|ключ_OpenAI_или_совместимого_API|your_|example)"
            r"[^\s#]+",
            re.IGNORECASE,
        ),
    ),
    (
        "yookassa_secret_assignment",
        re.compile(
            r"\bYOOKASSA_SECRET_KEY\s*=\s*"
            r"(?!$|<|os\.getenv|os\.environ|test_or_live_secret|your_|example|placeholder)"
            r"[^\s#]+",
            re.IGNORECASE,
        ),
    ),
]


def _git_visible_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    files: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        files.append(ROOT / raw.decode("utf-8"))
    return files


def _is_scannable(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        return False
    return True


def _redacted_line(line: str) -> str:
    if "=" in line:
        key, _sep, _value = line.partition("=")
        return f"{key.strip()}=<redacted>"
    return "<redacted>"


def main() -> int:
    findings: list[str] = []
    for path in _git_visible_files():
        rel = path.relative_to(ROOT)
        if rel.name == ".env":
            findings.append(f"{rel}: tracked .env file is forbidden")
            continue
        if not _is_scannable(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(f"{rel}:{line_no}: {name}: {_redacted_line(line)}")

    if findings:
        print("Potential secrets found in git-visible files:")
        for item in findings:
            print(f"- {item}")
        print("\nRemove the secret, rotate the credential, and rerun make security-check.")
        return 1

    print("secret scan ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
