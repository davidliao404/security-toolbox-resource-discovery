import json
import sys

import pytest

import resource_discovery.cli as cli_module
from resource_discovery.cli import run_fixture_demo
from resource_discovery.cli import export_report, format_json_payload, fofa_credentials_from_env, run_and_maybe_save


def test_cli_fixture_demo_returns_report_payload():
    payload = run_fixture_demo("examples/seeds.json", "tests/fixtures/fofa_results.json")

    assert payload["report"]["report_type"] == "manager_summary"
    assert payload["assets"]
    assert payload["services"]
    assert payload["risk_hints"]
    assert payload["source_evidence"]


def test_format_json_payload_preserves_non_gbk_characters():
    text = format_json_payload({"title": "Example™ Service"})

    assert "Example™ Service" in text


def test_run_and_maybe_save_records_audit_events(tmp_path, monkeypatch):
    def fake_run_discovery(**kwargs):
        return {
            "task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "success"},
            "assets": [{"asset_id": "asset_1"}],
            "risk_hints": [{"risk_id": "risk_1"}],
            "analysis": {
                "analysis_mode": "rules_plus_llm",
                "llm_enabled": True,
                "provider": "test-provider",
                "model": "test-model",
                "web_search_enabled": True,
                "data_sharing_level": "minimal",
                "authorization_id": "auth_1",
                "usage": {"total_tokens": 10},
            },
        }

    monkeypatch.setattr(cli_module, "run_discovery", fake_run_discovery)
    audit_log = tmp_path / "audit.jsonl"
    payload = run_and_maybe_save(
        "examples/seeds.json",
        save_dir=tmp_path / "snapshots",
        audit_log=audit_log,
        analysis_mode="rules_plus_llm",
        web_search_enabled=True,
        data_sharing_level="minimal",
    )

    assert payload["saved_snapshot_path"].endswith(".json")
    events = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == [
        "task_started",
        "snapshot_saved",
        "llm_analysis_used",
        "task_completed",
    ]


def test_export_report_supports_html_and_rejects_unknown_format(tmp_path):
    payload = run_fixture_demo("examples/seeds.json", "tests/fixtures/fofa_results.json")
    output_path = export_report(payload, tmp_path / "report.html", "html")

    assert output_path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        export_report(payload, tmp_path / "report.txt", "txt")


def test_main_lists_and_shows_saved_snapshots(tmp_path, monkeypatch, capsys):
    payload = run_and_maybe_save(
        "examples/seeds.json",
        fixture_path="tests/fixtures/fofa_results.json",
        save_dir=tmp_path / "snapshots",
    )
    task_id = payload["task"]["task_id"]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resource-discovery",
            "--seeds",
            "examples/seeds.json",
            "--save-dir",
            str(tmp_path / "snapshots"),
            "--tenant-id",
            payload["task"]["tenant_id"],
            "--list-snapshots",
        ],
    )

    cli_module.main()
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["task_id"] == task_id

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resource-discovery",
            "--seeds",
            "examples/seeds.json",
            "--save-dir",
            str(tmp_path / "snapshots"),
            "--tenant-id",
            payload["task"]["tenant_id"],
            "--show-snapshot",
            task_id,
        ],
    )

    cli_module.main()
    shown = json.loads(capsys.readouterr().out)
    assert shown["task"]["task_id"] == task_id


def test_main_runs_fixture_and_exports_report(tmp_path, monkeypatch, capsys):
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resource-discovery",
            "--seeds",
            "examples/seeds.json",
            "--fixture",
            "tests/fixtures/fofa_results.json",
            "--export-report",
            str(report_path),
        ],
    )

    cli_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["exported_report_path"] == report_path.as_posix()
    assert report_path.exists()


def test_required_cli_arguments_raise_system_exit():
    with pytest.raises(SystemExit):
        cli_module._required_save_dir("")
    with pytest.raises(SystemExit):
        cli_module._required_tenant_id("")


def test_fofa_credentials_from_env(monkeypatch):
    monkeypatch.setenv("FOFA_API_EMAIL", "user@example.com")
    monkeypatch.setenv("FOFA_API_KEY", "secret")
    monkeypatch.setenv("FOFA_BASE_URL", "https://fofa.example/api")

    assert fofa_credentials_from_env() == {
        "fofa_email": "user@example.com",
        "fofa_key": "secret",
        "fofa_base_url": "https://fofa.example/api",
    }
