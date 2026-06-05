from __future__ import annotations

import asyncio
import logging
import socket
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

import aiohttp

from app.config import (
    CORE_API_TOKEN,
    CORE_API_URL,
    CORE_PULL_BATCH_SIZE,
    CORE_PULL_ENABLED,
    CORE_PULL_INTERVAL_SECONDS,
    CORE_SYNC_BATCH_SIZE,
    CORE_SYNC_ENABLED,
    CORE_SYNC_INTERVAL_SECONDS,
    DB_PATH,
)


logger = logging.getLogger(__name__)


SYNC_TABLES = (
    "users",
    "pets",
    "subscriptions",
    "payments",
    "triage_logs",
    "reminders",
    "feedback",
    "admin_audit_log",
    "pet_history",
    "pet_measurements",
    "pet_vaccinations",
    "pet_observations",
    "user_events",
    "subscription_offer_logs",
    "triage_followups",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_name() -> str:
    return f"telegram-nl:{socket.gethostname()}"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_exists(cur: sqlite3.Cursor, table_name: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1", (table_name,))
    return cur.fetchone() is not None


def ensure_core_sync_schema() -> None:
    """Create local outbox and DB triggers used to mirror Telegram data to RU Core API."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS core_sync_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                row_id INTEGER,
                operation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_core_sync_outbox_pending
            ON core_sync_outbox(sent_at, id)
            """
        )
        for table_name in SYNC_TABLES:
            if not _table_exists(cur, table_name):
                continue
            safe_table = _quote_identifier(table_name)
            prefix = f"core_sync_{table_name}"
            cur.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {prefix}_ai
                AFTER INSERT ON {safe_table}
                BEGIN
                    INSERT INTO core_sync_outbox (table_name, row_id, operation, created_at)
                    VALUES ('{table_name}', NEW.id, 'upsert', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
                END
                """
            )
            cur.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {prefix}_au
                AFTER UPDATE ON {safe_table}
                BEGIN
                    INSERT INTO core_sync_outbox (table_name, row_id, operation, created_at)
                    VALUES ('{table_name}', NEW.id, 'upsert', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
                END
                """
            )
            cur.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS {prefix}_ad
                AFTER DELETE ON {safe_table}
                BEGIN
                    INSERT INTO core_sync_outbox (table_name, row_id, operation, created_at)
                    VALUES ('{table_name}', OLD.id, 'delete', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
                END
                """
            )
        conn.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _fetch_pending_events(limit: int) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, table_name, row_id, operation, created_at
            FROM core_sync_outbox
            WHERE sent_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(limit),),
        )
        events = []
        for event in cur.fetchall():
            table_name = str(event["table_name"])
            operation = str(event["operation"])
            row_id = event["row_id"]
            row: dict[str, Any] | None = None
            if operation == "upsert" and row_id is not None and table_name in SYNC_TABLES:
                safe_table = _quote_identifier(table_name)
                cur.execute(f"SELECT * FROM {safe_table} WHERE id = ? LIMIT 1", (int(row_id),))
                row = _row_to_dict(cur.fetchone())
                if row is None:
                    operation = "delete"
            events.append(
                {
                    "outbox_id": int(event["id"]),
                    "event_id": str(event["id"]),
                    "table_name": table_name,
                    "row_id": int(row_id) if row_id is not None else None,
                    "operation": operation,
                    "row": row,
                    "created_at": event["created_at"],
                }
            )
        return events


def _mark_sent(outbox_ids: list[int]) -> None:
    if not outbox_ids:
        return
    placeholders = ",".join("?" for _ in outbox_ids)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            f"UPDATE core_sync_outbox SET sent_at = ?, last_error = NULL WHERE id IN ({placeholders})",
            (_utc_now_iso(), *outbox_ids),
        )
        conn.commit()


def _mark_failed(outbox_ids: list[int], error: str) -> None:
    if not outbox_ids:
        return
    placeholders = ",".join("?" for _ in outbox_ids)
    clean_error = " ".join(str(error).split())[:500]
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            f"""
            UPDATE core_sync_outbox
            SET attempts = attempts + 1, last_error = ?
            WHERE id IN ({placeholders})
            """,
            (clean_error, *outbox_ids),
        )
        conn.commit()


async def _post_batch(events: list[dict[str, Any]]) -> None:
    payload_events = []
    outbox_ids = []
    for event in events:
        outbox_ids.append(int(event["outbox_id"]))
        payload_events.append({key: value for key, value in event.items() if key != "outbox_id"})

    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"Authorization": f"Bearer {CORE_API_TOKEN}"}
    payload = {"source": _source_name(), "events": payload_events}
    url = f"{CORE_API_URL}/api/internal/telegram-sync/batch"
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(f"core_api_http_{response.status}: {body[:300]}")
                data = await response.json()
                if not data.get("ok"):
                    raise RuntimeError(f"core_api_not_ok: {data}")
    except Exception as exc:
        _mark_failed(outbox_ids, str(exc))
        raise
    else:
        _mark_sent(outbox_ids)


def _ensure_core_inbox_schema(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS core_sync_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            event_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_id INTEGER,
            operation TEXT NOT NULL,
            payload TEXT,
            received_at TEXT NOT NULL,
            UNIQUE(source, event_id)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_core_sync_inbox_received
        ON core_sync_inbox(received_at)
        """
    )


def _table_columns(cur: sqlite3.Cursor, table_name: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
    return {str(row[1]) for row in cur.fetchall()}


def _apply_pulled_event(cur: sqlite3.Cursor, event: dict[str, Any]) -> None:
    table_name = str(event.get("table_name") or "")
    if table_name not in SYNC_TABLES:
        raise RuntimeError(f"pull_table_not_allowed:{table_name}")
    if not _table_exists(cur, table_name):
        raise RuntimeError(f"pull_table_missing:{table_name}")

    operation = str(event.get("operation") or "upsert")
    row_id = event.get("row_id")
    safe_table = _quote_identifier(table_name)

    if operation == "delete":
        if row_id is None:
            raise RuntimeError("pull_delete_requires_row_id")
        cur.execute(f"DELETE FROM {safe_table} WHERE id = ?", (int(row_id),))
        return

    row = event.get("row") or {}
    if not isinstance(row, dict) or "id" not in row:
        raise RuntimeError("pull_upsert_requires_row_id")

    allowed_columns = _table_columns(cur, table_name)
    columns = [key for key in row.keys() if key in allowed_columns]
    if "id" not in columns:
        columns.insert(0, "id")
    values = [row.get(column) for column in columns]
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    update_columns = [column for column in columns if column != "id"]
    if update_columns:
        update_sql = ", ".join(
            f"{_quote_identifier(column)}=excluded.{_quote_identifier(column)}"
            for column in update_columns
        )
        sql = (
            f"INSERT INTO {safe_table} ({column_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_sql}"
        )
    else:
        sql = f"INSERT OR IGNORE INTO {safe_table} ({column_sql}) VALUES ({placeholders})"
    cur.execute(sql, values)


def _apply_pulled_events(events: list[dict[str, Any]], *, source: str) -> list[int]:
    if not events:
        return []

    ack_ids: list[int] = []
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        ensure_core_sync_schema()
        _ensure_core_inbox_schema(cur)
        conn.commit()
        max_outbox_id = int(
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM core_sync_outbox").fetchone()[0] or 0
        )
        conn.isolation_level = None
        cur.execute("BEGIN IMMEDIATE")
        try:
            for event in events:
                outbox_id = event.get("outbox_id")
                event_id = str(event.get("event_id") or outbox_id or "")
                if not event_id:
                    raise RuntimeError("pull_event_id_missing")
                cur.execute(
                    """
                    INSERT OR IGNORE INTO core_sync_inbox (
                        source, event_id, table_name, row_id, operation, payload, received_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source,
                        event_id,
                        str(event.get("table_name") or ""),
                        event.get("row_id"),
                        str(event.get("operation") or "upsert"),
                        str(event),
                        _utc_now_iso(),
                    ),
                )
                if cur.rowcount:
                    _apply_pulled_event(cur, event)
                if outbox_id is not None:
                    ack_ids.append(int(outbox_id))

            # Applying RU events to NL fires local mirror triggers. These rows
            # are generated by the pull transaction itself and must not be sent
            # back to RU as new NL-originated changes.
            cur.execute(
                "DELETE FROM core_sync_outbox WHERE id > ? AND sent_at IS NULL",
                (max_outbox_id,),
            )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
    return ack_ids


async def _fetch_ru_outbound_events(limit: int) -> tuple[str, list[dict[str, Any]]]:
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"Authorization": f"Bearer {CORE_API_TOKEN}"}
    url = f"{CORE_API_URL}/api/internal/telegram-sync/outbound"
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params={"limit": int(limit)}, headers=headers) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(f"core_pull_http_{response.status}: {body[:300]}")
            data = await response.json()
            if not data.get("ok"):
                raise RuntimeError(f"core_pull_not_ok: {data}")
            return str(data.get("source") or "ru-core"), list(data.get("events") or [])


async def _ack_ru_outbound_events(event_ids: list[int]) -> None:
    if not event_ids:
        return
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"Authorization": f"Bearer {CORE_API_TOKEN}"}
    url = f"{CORE_API_URL}/api/internal/telegram-sync/outbound/ack"
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json={"event_ids": event_ids}, headers=headers) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(f"core_ack_http_{response.status}: {body[:300]}")
            data = await response.json()
            if not data.get("ok"):
                raise RuntimeError(f"core_ack_not_ok: {data}")


async def run_core_sync_worker() -> None:
    """Background NL->RU data mirror worker.

    The Telegram bot keeps running on NL. This worker mirrors changed SQLite rows
    to a closed RU Core API, where they are applied to the RU bot DB mirror.
    """
    if not CORE_SYNC_ENABLED:
        logger.info("[core_sync] disabled")
        return
    if not CORE_API_URL or not CORE_API_TOKEN:
        logger.warning("[core_sync] enabled but CORE_API_URL/CORE_API_TOKEN are not configured")
        return

    logger.info("[core_sync] starting, api=%s interval=%ss", CORE_API_URL, CORE_SYNC_INTERVAL_SECONDS)
    try:
        ensure_core_sync_schema()
    except Exception as exc:
        logger.exception("[core_sync] failed to initialize local outbox: %s", exc)
        return

    while True:
        try:
            events = _fetch_pending_events(CORE_SYNC_BATCH_SIZE)
            if events:
                await _post_batch(events)
                logger.info("[core_sync] sent events=%d", len(events))
        except Exception as exc:
            logger.warning("[core_sync] sync failed: %s", exc)
        await asyncio.sleep(CORE_SYNC_INTERVAL_SECONDS)


async def run_core_pull_worker() -> None:
    """Pull RU Core-originated Telegram DB events back into the NL bot DB."""
    if not CORE_PULL_ENABLED:
        logger.info("[core_pull] disabled")
        return
    if not CORE_API_URL or not CORE_API_TOKEN:
        logger.warning("[core_pull] enabled but CORE_API_URL/CORE_API_TOKEN are not configured")
        return

    logger.info("[core_pull] starting, api=%s interval=%ss", CORE_API_URL, CORE_PULL_INTERVAL_SECONDS)
    try:
        ensure_core_sync_schema()
    except Exception as exc:
        logger.exception("[core_pull] failed to initialize local schema: %s", exc)
        return

    while True:
        try:
            source, events = await _fetch_ru_outbound_events(CORE_PULL_BATCH_SIZE)
            if events:
                ack_ids = _apply_pulled_events(events, source=source)
                await _ack_ru_outbound_events(ack_ids)
                logger.info("[core_pull] applied events=%d acked=%d", len(events), len(ack_ids))
        except Exception as exc:
            logger.warning("[core_pull] pull failed: %s", exc)
        await asyncio.sleep(CORE_PULL_INTERVAL_SECONDS)
