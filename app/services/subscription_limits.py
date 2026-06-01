# Centralized subscription limits (INC6 stabilize)
from __future__ import annotations
from typing import Any, Dict, Optional

PLANS: Dict[str, Dict[str, Any]] = {
    "free": {"history_limit": 3, "analytics_enabled": False},
    "plus": {"history_limit": 100, "analytics_enabled": True},
    "pro": {"history_limit": None, "analytics_enabled": True},
    "vip": {"history_limit": None, "analytics_enabled": True},
}

def normalize_plan(plan: Optional[str]) -> str:
    p = (plan or "free").strip().lower()
    if p == "premium":
        return "vip"
    return p if p in PLANS else "free"

def get_plan_limits(plan: Optional[str]) -> Dict[str, Any]:
    return PLANS[normalize_plan(plan)]

def can_access_history(plan: Optional[str], current_count: int) -> bool:
    limit = get_plan_limits(plan).get("history_limit")
    if limit is None:
        return True
    try:
        return int(current_count) <= int(limit)
    except Exception:
        return True

def can_access_analytics(plan: Optional[str]) -> bool:
    return bool(get_plan_limits(plan).get("analytics_enabled", False))
