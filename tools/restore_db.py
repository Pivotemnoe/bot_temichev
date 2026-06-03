#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from backup_db import DEFAULT_BACKUP_DIR, PROJECT_ROOT, backup_sqlite_db, verify_sqlite_db


def _default_db_path() -> Path:
    load_dotenv(PROJECT_ROOT / ".env")
    return Path(os.getenv("DB_PATH", "bot.db"))


def _resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def restore_sqlite_db(
    backup_path: str | Path,
    target_path: str | Path,
    *,
    prebackup_dir: str | Path = DEFAULT_BACKUP_DIR,
) -> Path | None:
    source = _resolve_project_path(backup_path)
    target = _resolve_project_path(target_path)
    verify_sqlite_db(source)

    pre_restore_backup: Path | None = None
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        pre_restore_backup = backup_sqlite_db(
            target,
            backup_dir=prebackup_dir,
            label=f"pre_restore_{stamp}",
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_target = target.with_suffix(f"{target.suffix}.restore_tmp")
    shutil.copy2(source, tmp_target)
    verify_sqlite_db(tmp_target)
    os.replace(tmp_target, target)
    verify_sqlite_db(target)
    return pre_restore_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore TemichevVet bot.db from a verified SQLite backup.")
    parser.add_argument("backup", help="Backup file path, for example backups/bot_20260603_120000.db.")
    parser.add_argument("--db", default=str(_default_db_path()), help="Target SQLite DB. Defaults to DB_PATH or bot.db.")
    parser.add_argument("--prebackup-dir", default=str(DEFAULT_BACKUP_DIR), help="Directory for automatic pre-restore backup.")
    parser.add_argument("--yes", action="store_true", help="Required confirmation flag.")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to restore without --yes. Stop the bot first, then rerun with --yes.")

    pre_restore_backup = restore_sqlite_db(args.backup, args.db, prebackup_dir=args.prebackup_dir)
    if pre_restore_backup:
        print(f"pre-restore backup created: {pre_restore_backup}")
    print(f"database restored from: {_resolve_project_path(args.backup)}")
    print(f"target database: {_resolve_project_path(args.db)}")


if __name__ == "__main__":
    main()
