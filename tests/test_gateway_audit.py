import json

from resource_discovery.audit import JsonlAuditLogger
from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.repositories import FileResultRepository, FileTaskRepository
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient
from resource_discovery.task_queue import InMemoryTaskQueue
from resource_discovery.worker import TaskWorker


def _profile():
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        allowed_root_domains=["example.org"],
        allowed_domains=["vpn.example.org"],
        allowed_ip_cidrs=["203.0.113.0/24"],
        allowed_org_names=["Example Organization"],
        default_scope={"root_domains": ["example.org"]},
        allowed_engines=["fofa"],
        provider_profile_id="provider_fofa_poc",
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        created_by="security_operator_hash",
        authorization_note="Confirmed by customer interview.",
    )


def _events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_gateway_records_profile_task_and_result_audit_events(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    task_repo = FileTaskRepository(tmp_path / "tasks")
    result_repo = FileResultRepository(tmp_path / "results")
    queue = InMemoryTaskQueue()
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        audit_logger=JsonlAuditLogger(audit_path),
    )

    api.get_scope_profile()
    created = api.create_task(
        {
            "task_id": "dt_audit_001",
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )
    TaskWorker(
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        audit_logger=JsonlAuditLogger(audit_path),
    ).run_once()
    api.get_results(created["task_id"], limit=2, result_type="assets")

    events = _events(audit_path)
    assert [event["event_type"] for event in events] == [
        "scope_profile_viewed",
        "discovery_task_requested",
        "discovery_task_queued",
        "discovery_task_started",
        "discovery_task_completed",
        "discovery_results_fetched",
    ]
    assert events[0]["task_id"] == "-"
    assert events[1]["task_id"] == "dt_audit_001"
    assert events[2]["details"]["planned_queries"] == 1
    assert events[-1]["details"] == {"result_type": "assets", "cursor": None, "limit": 2}


def test_gateway_records_rejected_scope_audit_event(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        snapshot_dir=tmp_path,
        audit_logger=JsonlAuditLogger(audit_path),
    )

    response = api.create_task(
        {
            "task_id": "dt_rejected_001",
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["outside.example"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )

    events = _events(audit_path)
    assert response["status"] == "rejected"
    assert [event["event_type"] for event in events] == [
        "discovery_task_requested",
        "discovery_scope_rejected",
    ]
    assert events[-1]["details"]["reason"] == "scope_out_of_bounds"
    assert events[-1]["details"]["rejected_count"] == 1
