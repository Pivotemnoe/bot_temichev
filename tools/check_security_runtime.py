#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


tmp = tempfile.NamedTemporaryFile(prefix="temichevvet_security_", suffix=".db", delete=False)
tmp.close()

os.environ["DB_PATH"] = tmp.name
os.environ.setdefault("BOT_TOKEN", "123456:test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ADMIN_CHAT_ID", "100500")
os.environ.setdefault("ADMIN_IDS", "100500")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import init_db, list_admin_audit_events, log_admin_audit_event  # noqa: E402
from app.handlers.admin import render_admin_status_report  # noqa: E402
from app.middlewares.rate_limit import RateLimitMiddleware, RULES  # noqa: E402


def check_admin_audit() -> None:
    init_db()
    event_id = log_admin_audit_event(
        telegram_id=100500,
        username="admin",
        action="admin_open",
        target="test",
        details={"ok": True},
    )
    assert event_id > 0
    events = list_admin_audit_events(limit=5)
    assert events
    assert events[0]["telegram_id"] == 100500
    assert events[0]["action"] == "admin_open"
    assert events[0]["target"] == "test"


def check_admin_status_has_no_secrets() -> None:
    report = render_admin_status_report()
    assert "BOT_TOKEN" not in report
    assert "OPENAI_API_KEY" not in report
    assert "YOOKASSA_SECRET_KEY" not in report
    assert "123456:test" not in report
    assert "Секреты" in report


def check_rate_limit() -> None:
    limiter = RateLimitMiddleware()
    rule = RULES["start"]
    for i in range(rule.limit):
        allowed, _ = limiter.check_allowed(42, "start", now=float(i))
        assert allowed
    allowed, _ = limiter.check_allowed(42, "start", now=float(rule.limit))
    assert not allowed

    allowed, _ = limiter.check_allowed(42, "start", now=float(rule.window_sec + rule.limit + 1))
    assert allowed


def main() -> None:
    check_admin_audit()
    check_admin_status_has_no_secrets()
    check_rate_limit()
    print("security runtime checks ok")


if __name__ == "__main__":
    main()
