from resource_discovery.freshness import build_freshness


def test_build_freshness_marks_recent_updates_as_fresh():
    freshness = build_freshness("2026-05-19 12:00:00", now="2026-05-20T00:00:00+00:00")

    assert freshness == {
        "status": "fresh",
        "last_observed_at": "2026-05-19T12:00:00+00:00",
        "age_days": 0,
        "stale_after_days": 180,
        "meaning": "provider_observation_time_not_liveness_proof",
    }


def test_build_freshness_marks_six_month_old_updates_as_stale():
    freshness = build_freshness("2025-08-01 10:00:00", now="2026-05-20T00:00:00+00:00")

    assert freshness["status"] == "stale"
    assert freshness["age_days"] > 180


def test_build_freshness_marks_middle_age_updates_as_aging():
    freshness = build_freshness("2026-01-01", now="2026-05-20T00:00:00+00:00")

    assert freshness["status"] == "aging"
    assert freshness["last_observed_at"] == "2026-01-01T00:00:00+00:00"


def test_build_freshness_accepts_zulu_time_and_clamps_future_age():
    freshness = build_freshness("2026-05-21T00:00:00Z", now="2026-05-20T00:00:00+00:00")

    assert freshness["status"] == "fresh"
    assert freshness["age_days"] == 0


def test_build_freshness_marks_invalid_time_as_unknown():
    freshness = build_freshness("not-a-time", now="2026-05-20T00:00:00+00:00")

    assert freshness["status"] == "unknown"


def test_build_freshness_marks_missing_time_as_unknown():
    freshness = build_freshness(None, now="2026-05-20T00:00:00+00:00")

    assert freshness["status"] == "unknown"
    assert freshness["age_days"] is None
