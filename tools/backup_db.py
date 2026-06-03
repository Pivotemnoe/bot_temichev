#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backups"


def _default_db_path() -> Path:
    load_dotenv(PROJECT_ROOT / ".env")
    return Path(os.getenv("DB_PATH", "bot.db"))


def _resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _safe_label(label: str | None) -> str:
    if not label:
        return ""
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label.strip())
    return f"_{safe}" if safe else ""


def _unique_backup_path(destination_dir: Path, filename_stem: str) -> Path:
    candidate = destination_dir / f"{filename_stem}.db"
    if not candidate.exists():
        return candidate
    for index in range(1, 1000):
        candidate = destination_dir / f"{filename_stem}_{index}.db"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot allocate unique backup filename in {destination_dir}")


def verify_sqlite_db(db_path: str | Path) -> None:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")

    with sqlite3.connect(path) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    result = row[0] if row else ""
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed for {path}: {result}")


def backup_sqlite_db(
    source_path: str | Path,
    *,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
    label: str | None = None,
) -> Path:
    source = _resolve_project_path(source_path)
    destination_dir = _resolve_project_path(backup_dir)
    verify_sqlite_db(source)

    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    destination = _unique_backup_path(destination_dir, f"bot_{stamp}{_safe_label(label)}")

    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)

    verify_sqlite_db(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a verified SQLite backup for TemichevVet bot.db.")
    parser.add_argument("--db", default=str(_default_db_path()), help="Path to SQLite DB. Defaults to DB_PATH or bot.db.")
    parser.add_argument("--out-dir", default=str(DEFAULT_BACKUP_DIR), help="Directory for backup files.")
    parser.add_argument("--label", default=None, help="Optional filename label, for example before_release.")
    args = parser.parse_args()

    backup_path = backup_sqlite_db(args.db, backup_dir=args.out_dir, label=args.label)
    print(f"backup created: {backup_path}")


if __name__ == "__main__":
    main()
