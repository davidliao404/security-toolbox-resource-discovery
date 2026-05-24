import json
from datetime import datetime, timezone

from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.gateway_http import GatewayHttpHandler
from resource_discovery.repositories import FileResultRepository, FileTaskRepository
from resource_discovery.request_auth import InMemoryNonceStore, build_signature
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


def _handler(tmp_path):
    queue = InMemoryTaskQueue()
    task_repo = FileTaskRepository(tmp_path / "tasks")
    result_repo = FileResultRepository(tmp_path / "results")
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
    )
    handler = GatewayHttpHandler(
        api=api,
        client_secrets={"client_001": "client-secret"},
        nonce_store=InMemoryNonceStore(),
        now=lambda: datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
    )
    return handler, queue, task_repo, result_repo


def _headers(method, path, body=b"", nonce="nonce-001"):
    timestamp = "2026-05-20T12:00:00+00:00"
    return {
        "X-Client-Id": "client_001",
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": build_signature(
            secret="client-secret",
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        ),
    }


def test_http_handler_returns_scope_profile_with_signature(tmp_path):
    handler, *_ = _handler(tmp_path)
    path = "/api/v1/discovery/scope-profile"

    response = handler.handle("GET", path, headers=_headers("GET", path), body=b"")

    assert response.status_code == 200
    assert response.json["profile_id"] == "scope_profile_001"


def test_http_handler_creates_task_and_fetches_results(tmp_path):
    handler, queue, task_repo, result_repo = _handler(tmp_path)
    path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "task_id": "dt_http_001",
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    ).encode("utf-8")

    created = handler.handle("POST", path, headers=_headers("POST", path, body=body), body=body)
    TaskWorker(
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
    ).run_once()
    result_path = "/api/v1/discovery/tasks/dt_http_001/results?result_type=services&limit=1"
    results = handler.handle(
        "GET",
        result_path,
        headers=_headers("GET", result_path, nonce="nonce-002"),
        body=b"",
    )

    assert created.status_code == 202
    assert created.json["status"] == "queued"
    assert results.status_code == 200
    assert len(results.json["services"]) == 1
    assert results.json["page"]["type"] == "services"


def test_http_handler_rejects_bad_signature(tmp_path):
    handler, *_ = _handler(tmp_path)
    path = "/api/v1/discovery/scope-profile"

    response = handler.handle(
        "GET",
        path,
        headers={
            "X-Client-Id": "client_001",
            "X-Timestamp": "2026-05-20T12:00:00+00:00",
            "X-Nonce": "nonce-001",
            "X-Signature": "bad",
        },
        body=b"",
    )

    assert response.status_code == 401
    assert response.json["errors"][0]["code"] == "invalid_signature"


def test_http_handler_rejects_unknown_client_and_missing_header(tmp_path):
    handler, *_ = _handler(tmp_path)
    path = "/api/v1/discovery/scope-profile"

    unknown = handler.handle("GET", path, headers={"X-Client-Id": "missing"}, body=b"")
    missing = handler.handle("GET", path, headers={"X-Client-Id": "client_001"}, body=b"")

    assert unknown.status_code == 401
    assert unknown.json["errors"][0]["code"] == "unknown_client"
    assert missing.status_code == 401
    assert missing.json["errors"][0]["code"] == "missing_auth_header"


def test_http_handler_returns_bad_request_for_invalid_json(tmp_path):
    handler, *_ = _handler(tmp_path)
    path = "/api/v1/discovery/tasks"

    response = handler.handle("POST", path, headers=_headers("POST", path, body=b"{"), body=b"{")

    assert response.status_code == 400
    assert response.json["errors"][0]["code"] == "bad_request"


def test_http_handler_returns_not_found_for_unknown_route(tmp_path):
    handler, *_ = _handler(tmp_path)
    path = "/api/v1/unknown"

    response = handler.handle("GET", path, headers=_headers("GET", path), body=b"")

    assert response.status_code == 404
    assert response.json["errors"][0]["code"] == "not_found"


def test_http_handler_wraps_unexpected_errors(tmp_path):
    handler, *_ = _handler(tmp_path)
    path = "/api/v1/discovery/scope-profile"
    handler.api.get_scope_profile = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

    response = handler.handle("GET", path, headers=_headers("GET", path), body=b"")

    assert response.status_code == 500
    assert response.json["errors"][0]["code"] == "internal_error"


def test_http_handler_fetches_task_status(tmp_path):
    handler, queue, task_repo, _ = _handler(tmp_path)
    path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "task_id": "dt_http_status",
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
        }
    ).encode("utf-8")
    handler.handle("POST", path, headers=_headers("POST", path, body=body), body=body)

    response = handler.handle(
        "GET",
        "/api/v1/discovery/tasks/dt_http_status",
        headers=_headers("GET", "/api/v1/discovery/tasks/dt_http_status", nonce="nonce-003"),
        body=b"",
    )

    assert response.status_code == 200
    assert response.json["task_id"] == "dt_http_status"
