#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from backup_db import backup_sqlite_db, verify_sqlite_db
from restore_db import restore_sqlite_db


def _read_value(db_path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT value FROM smoke WHERE id = 1").fetchone()
    return str(row[0])


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="temichevvet_backup_restore_") as tmp:
        root = Path(tmp)
        db_path = root / "bot.db"
        backup_dir = root / "backups"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO smoke (id, value) VALUES (1, 'before')")
            conn.commit()

        backup_path = backup_sqlite_db(db_path, backup_dir=backup_dir, label="check")
        verify_sqlite_db(backup_path)

        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE smoke SET value = 'after' WHERE id = 1")
            conn.commit()

        pre_restore_backup = restore_sqlite_db(backup_path, db_path, prebackup_dir=backup_dir)

        assert _read_value(db_path) == "before"
        assert pre_restore_backup is not None
        assert pre_restore_backup.exists()
        verify_sqlite_db(pre_restore_backup)

    print("backup/restore checks ok")


if __name__ == "__main__":
    main()
