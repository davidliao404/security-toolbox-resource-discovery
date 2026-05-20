from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_freshness(
    provider_time: str | None,
    now: str | None = None,
    fresh_days: int = 90,
    stale_after_days: int = 180,
) -> dict[str, Any]:
    observed_at = _parse_time(provider_time)
    if observed_at is None:
        return {
            "status": "unknown",
            "last_observed_at": None,
            "age_days": None,
            "stale_after_days": stale_after_days,
            "meaning": "provider_observation_time_not_liveness_proof",
        }
    current = _parse_time(now) or datetime.now(timezone.utc)
    age_days = max((current - observed_at).days, 0)
    if age_days <= fresh_days:
        status = "fresh"
    elif age_days <= stale_after_days:
        status = "aging"
    else:
        status = "stale"
    return {
        "status": status,
        "last_observed_at": observed_at.isoformat(),
        "age_days": age_days,
        "stale_after_days": stale_after_days,
        "meaning": "provider_observation_time_not_liveness_proof",
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in formats:
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
