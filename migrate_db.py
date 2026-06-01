import sqlite3
from pathlib import Path

DB_PATH = Path("bot.db")


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def add_column(cursor, table_name: str, column_name: str, ddl: str):
    if column_exists(cursor, table_name, column_name):
        print(f"[SKIP] {table_name}.{column_name} уже существует")
        return
    ddl_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"
    print(f"[ADD]  {table_name}.{column_name} → {ddl_sql}")
    cursor.execute(ddl_sql)


def migrate():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Файл БД {DB_PATH} не найден")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- triage_logs: токены LLM ---
    try:
        add_column(cur, "triage_logs", "prompt_tokens", "INTEGER DEFAULT 0")
        add_column(cur, "triage_logs", "completion_tokens", "INTEGER DEFAULT 0")
        add_column(cur, "triage_logs", "total_tokens", "INTEGER DEFAULT 0")
    except Exception as e:
        print(f"[ERROR] triage_logs: {e}")

    # --- users: тариф и квота ---
    try:
        add_column(cur, "users", "tariff", "TEXT DEFAULT 'free'")
        add_column(cur, "users", "quota", "INTEGER DEFAULT 5")
    except Exception as e:
        print(f"[ERROR] users: {e}")

    conn.commit()
    conn.close()
    print("Миграция завершена.")


if __name__ == "__main__":
    migrate()