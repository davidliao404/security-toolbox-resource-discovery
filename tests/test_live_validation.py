import json

from resource_discovery.live_validation import build_live_seed_payload, build_summary, validate_live_config


def test_validate_live_config_requires_key_and_base_url():
    try:
        validate_live_config({"FOFA_API_KEY": "", "FOFA_BASE_URL": ""})
    except ValueError as exc:
        assert "FOFA_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing key to fail validation")

    try:
        validate_live_config({"FOFA_API_KEY": "secret", "FOFA_BASE_URL": ""})
    except ValueError as exc:
        assert "FOFA_BASE_URL" in str(exc)
    else:
        raise AssertionError("Expected missing base URL to fail validation")


def test_build_live_seed_payload_scopes_to_authorized_domain():
    payload = build_live_seed_payload("china-entercom.com")

    assert payload["tenant_id"] == "tenant_live_validation"
    assert payload["seeds"] == [
        {
            "seed_id": "seed_001",
            "type": "root_domain",
            "value": "china-entercom.com",
            "authorization_note": "Live validation domain explicitly authorized by customer.",
        }
    ]


def test_build_summary_never_includes_api_key():
    payload = {
        "task": {"status": "success"},
        "assets": [{"asset_id": "asset_1"}],
        "services": [
            {"freshness": {"status": "fresh"}},
            {"freshness": {"status": "stale"}},
            {"freshness": {"status": "unknown"}},
        ],
    }

    summary = build_summary(payload, snapshot_path="artifacts/live-validation/snapshot.json")
    rendered = json.dumps(summary, ensure_ascii=False)

    assert summary == {
        "status": "success",
        "asset_count": 1,
        "service_count": 3,
        "freshness_counts": {"fresh": 1, "stale": 1, "unknown": 1},
        "snapshot_path": "artifacts/live-validation/snapshot.json",
    }
    assert "secret" not in rendered
