from pathlib import Path

from resource_discovery.execution import run_discovery
from resource_discovery.models import TaskStatus
from resource_discovery.task_state import build_report_snapshot


def test_fixture_execution_returns_success_task_envelope():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )

    task = payload["task"]
    assert task["status"] == TaskStatus.SUCCESS.value
    assert task["task_id"] == "dt_poc_001"
    assert task["tenant_id"] == "tenant_poc"
    assert task["quota_usage"]["planned_queries"] == 3
    assert task["quota_usage"]["completed_queries"] == 3
    assert task["quota_usage"]["failed_queries"] == 0
    assert task["errors"] == []
    assert payload["snapshot"]["report"]["report_id"] == "report_dt_poc_001"


class PartiallyFailingClient:
    def fetch(self, plan):
        if plan.query_type == "organization":
            raise RuntimeError("provider timeout")
        return [
            {
                "ip": "203.0.113.10",
                "host": "vpn.example.org",
                "root_domain": "example.org",
                "port": 443,
                "protocol": "https",
                "service": "vpn",
                "title": "Example VPN Portal",
                "confidence": 0.86,
            }
        ]


def test_partial_provider_failure_returns_partial_success_envelope():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        source_client=PartiallyFailingClient(),
    )

    task = payload["task"]
    assert task["status"] == TaskStatus.PARTIAL_SUCCESS.value
    assert task["quota_usage"]["planned_queries"] == 3
    assert task["quota_usage"]["completed_queries"] == 2
    assert task["quota_usage"]["failed_queries"] == 1
    assert task["errors"][0]["source"] == "fofa"
    assert task["errors"][0]["query_type"] == "organization"
    assert "provider timeout" in task["errors"][0]["message"]
    assert payload["assets"]
    assert payload["report"]["executive_summary"]["asset_count"] == 1


def test_report_snapshot_is_json_serializable_and_contains_task_summary():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )

    snapshot = build_report_snapshot(payload)

    assert snapshot["task"]["status"] == "success"
    assert snapshot["summary"]["asset_count"] == 4
    assert snapshot["summary"]["service_count"] == 4
    assert snapshot["summary"]["risk_hint_count"] == 6
