import json

from resource_discovery.live_validation import build_live_seed_payload, build_summary, run_live_validation, validate_live_config


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


def test_validate_live_config_accepts_optional_email():
    config = validate_live_config(
        {
            "FOFA_API_KEY": " secret ",
            "FOFA_BASE_URL": " https://fofa.example/api ",
            "FOFA_API_EMAIL": " user@example.com ",
        }
    )

    assert config == {
        "fofa_key": "secret",
        "fofa_base_url": "https://fofa.example/api",
        "fofa_email": "user@example.com",
    }


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


def test_run_live_validation_writes_seed_and_snapshot_without_printing_secret(tmp_path, monkeypatch):
    captured = {}

    def fake_run_discovery(**kwargs):
        captured.update(kwargs)
        return {
            "task": {"status": "success"},
            "assets": [{"asset_id": "asset_1"}],
            "services": [{"freshness": {"status": "fresh"}}],
        }

    monkeypatch.setattr("resource_discovery.live_validation.run_discovery", fake_run_discovery)

    summary = run_live_validation(
        " china-entercom.com ",
        output_dir=tmp_path,
        env={"FOFA_API_KEY": "secret", "FOFA_BASE_URL": "https://fofa.example/api", "FOFA_API_EMAIL": ""},
        page_limit=1,
        result_limit=2,
    )

    assert summary["status"] == "success"
    assert summary["asset_count"] == 1
    assert captured["mode"] == "live"
    assert captured["allow_live_fofa"] is True
    assert captured["fofa_key"] == "secret"
    assert list(tmp_path.glob("seeds-*.json"))
    assert list(tmp_path.glob("snapshot-*.json"))
