import json

import pytest

from resource_discovery.live_validation import run_live_fofa_regression
from resource_discovery.ops_cli import main


def test_live_fofa_regression_requires_explicit_env_gate():
    with pytest.raises(ValueError, match="RESOURCE_DISCOVERY_LIVE_FOFA"):
        run_live_fofa_regression(env={})


def test_live_fofa_regression_requires_credentials_and_authorized_domain():
    with pytest.raises(ValueError, match="FOFA_EMAIL"):
        run_live_fofa_regression(env={"RESOURCE_DISCOVERY_LIVE_FOFA": "1"})
    with pytest.raises(ValueError, match="FOFA_KEY"):
        run_live_fofa_regression(env={"RESOURCE_DISCOVERY_LIVE_FOFA": "1", "FOFA_EMAIL": "user@example.com"})
    with pytest.raises(ValueError, match="RESOURCE_DISCOVERY_LIVE_AUTHORIZED_DOMAIN"):
        run_live_fofa_regression(env={"RESOURCE_DISCOVERY_LIVE_FOFA": "1", "FOFA_EMAIL": "user@example.com", "FOFA_KEY": "secret"})


def test_live_fofa_regression_summary_redacts_secret(monkeypatch):
    def fake_run_live_validation(domain, **kwargs):
        assert domain == "example.com"
        assert kwargs["env"]["FOFA_API_KEY"] == "secret"
        return {"status": "success", "asset_count": 1, "service_count": 2, "snapshot_path": "snapshot.json"}

    monkeypatch.setattr("resource_discovery.live_validation.run_live_validation", fake_run_live_validation)

    summary = run_live_fofa_regression(
        env={
            "RESOURCE_DISCOVERY_LIVE_FOFA": "1",
            "FOFA_EMAIL": "user@example.com",
            "FOFA_KEY": "secret",
            "RESOURCE_DISCOVERY_LIVE_AUTHORIZED_DOMAIN": "example.com",
        }
    )

    rendered = json.dumps(summary, ensure_ascii=False)
    assert summary["status"] == "success"
    assert "secret" not in rendered


def test_live_fofa_regression_cli_reports_not_run_without_gate(monkeypatch, capsys):
    monkeypatch.delenv("RESOURCE_DISCOVERY_LIVE_FOFA", raising=False)

    assert main(["live-fofa-regression"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "not_run"
    assert payload["reason"] == "RESOURCE_DISCOVERY_LIVE_FOFA is required"
