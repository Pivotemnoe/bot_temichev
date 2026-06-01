# app/services/pet_observation_service.py
from __future__ import annotations

from typing import Optional, List, Dict, Any

from app.db import (
    add_pet_observation,
    get_pet_observations,
    list_pet_measurements,
    list_pet_history,
)


def add_observation(
    user_id: int,
    pet_id: int,
    obs_type: str,
    payload: Optional[Dict[str, Any]] = None,
    source: str = "system",
) -> int:
    """Store an observation linked to a pet."""
    return add_pet_observation(
        user_id=user_id,
        pet_id=pet_id,
        obs_type=obs_type,
        payload=payload or {},
        source=source,
    )


def get_observations(pet_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Return observations for a pet (newest first)."""
    return get_pet_observations(pet_id=pet_id, limit=limit)


def get_analytics_bundle(
    pet_id: int,
    triage_limit: int = 20,
    weights_limit: int = 10,
    insights_limit: int = 10,
) -> Dict[str, Any]:
    """Aggregated data for the 'Analytics / Observations' screen."""
    triage = get_pet_observations(pet_id=pet_id, limit=triage_limit) or []
    weights = list_pet_measurements(pet_id=pet_id, limit=weights_limit) or []
    history = list_pet_history(pet_id=pet_id, limit=50) or []

    insights: List[Dict[str, Any]] = []
    for e in history:
        if e.get("event_type") == "insight":
            insights.append(e)
            if len(insights) >= insights_limit:
                break

    weight_summary = build_weight_summary(weights)

    return {
        "triage": triage,
        "weights": weights,
        "insights": insights,
        "weight_summary": weight_summary,
    }


def build_weight_summary(weights: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute last weight and delta vs previous (if present)."""
    if not weights:
        return {"has_data": False}

    last = weights[0]
    prev = weights[1] if len(weights) > 1 else None

    try:
        last_w = float(last.get("weight_kg")) if last.get("weight_kg") is not None else None
    except (TypeError, ValueError):
        last_w = None
    try:
        prev_w = float(prev.get("weight_kg")) if prev and prev.get("weight_kg") is not None else None
    except (TypeError, ValueError):
        prev_w = None

    delta = None
    delta_pct = None
    if last_w is not None and prev_w is not None:
        delta = last_w - prev_w
        if prev_w != 0:
            delta_pct = (delta / prev_w) * 100.0

    return {
        "has_data": True,
        "last_weight": last_w,
        "last_at": (last.get("created_at") or ""),
        "prev_weight": prev_w,
        "delta": delta,
        "delta_pct": delta_pct,
    }
