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

from app.db import create_user, get_subscription, init_db, list_admin_audit_events, log_admin_audit_event  # noqa: E402
from app.handlers.admin import (  # noqa: E402
    _parse_manual_plus_command,
    apply_manual_subscription_change,
    render_admin_status_report,
)
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


def check_manual_plus_change() -> None:
    user_id = create_user(telegram_id=777001, name="Plus Test")
    parsed = _parse_manual_plus_command("выдать плюс 777001 ручная выдача для теста")
    assert parsed == ("plus", 777001, "ручная выдача для теста")
    assert _parse_manual_plus_command("/grant_plus@TemichevVettest_bot 777001 paid invoice") == (
        "plus",
        777001,
        "paid invoice",
    )
    assert _parse_manual_plus_command("снять плюс 777001") is None

    grant_result = apply_manual_subscription_change(777001, "plus")
    assert grant_result is not None
    assert grant_result["user_id"] == user_id
    assert grant_result["old_plan"] == "free"
    assert grant_result["new_plan"] == "plus"
    assert (get_subscription(user_id) or {}).get("plan") == "plus"

    revoke_result = apply_manual_subscription_change(777001, "free")
    assert revoke_result is not None
    assert revoke_result["old_plan"] == "plus"
    assert revoke_result["new_plan"] == "free"
    assert (get_subscription(user_id) or {}).get("plan") == "free"


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
    check_manual_plus_change()
    check_rate_limit()
    print("security runtime checks ok")


if __name__ == "__main__":
    main()
