import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from resource_discovery.config import GatewaySettings
from resource_discovery.http_app import create_app, create_app_from_settings
from resource_discovery.quota import TenantQuotaPolicy
from resource_discovery.request_auth import build_signature
from resource_discovery.scope_guard import TenantScopeProfile


def _headers(secret, method, path, body=b"", nonce="nonce-1", tenant_id="tenant_poc"):
    timestamp = "2026-05-22T10:00:00+00:00"
    return {
        "X-Tenant-Id": tenant_id,
        "X-Client-Id": "toolbox",
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": build_signature(
            secret=secret,
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        ),
    }


def test_healthz_returns_ok(tmp_path):
    app = create_app(sqlite_path=tmp_path / "gateway.sqlite3", client_secrets={"tenant_poc": {"toolbox": "secret"}})
    client = TestClient(app)

    assert client.get("/healthz").json()["status"] == "ok"


def test_readyz_returns_backend_names(tmp_path):
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        storage_backend="sqlite",
        queue_backend="sqlite",
    )
    client = TestClient(app)

    assert client.get("/readyz").json() == {"status": "ok", "storage": "sqlite", "queue": "sqlite"}


def test_scope_profile_requires_signature(tmp_path):
    app = create_app(sqlite_path=tmp_path / "gateway.sqlite3", client_secrets={"tenant_poc": {"toolbox": "secret"}})
    client = TestClient(app)

    response = client.get("/api/v1/discovery/scope-profile")

    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "missing_auth_header"


def test_scope_profile_rejects_unknown_client(tmp_path):
    path = "/api/v1/discovery/scope-profile"
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)

    response = client.get(path, headers=_headers("secret", "GET", path))

    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "unknown_client"


def test_scope_profile_with_valid_signature(tmp_path):
    path = "/api/v1/discovery/scope-profile"
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)

    response = client.get(path, headers=_headers("secret", "GET", path))

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant_poc"


def test_scope_profile_rejects_credentials_for_another_tenant(tmp_path):
    path = "/api/v1/discovery/scope-profile"
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_b": {"toolbox": "other-secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)

    response = client.get(
        path,
        headers=_headers("other-secret", "GET", path, tenant_id="tenant_b"),
    )

    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "tenant_mismatch"


def test_results_query_string_is_covered_by_signature(tmp_path):
    signed_path = "/api/v1/discovery/tasks/task_1/results"
    requested_path = f"{signed_path}?limit=500&result_type=services"
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)

    response = client.get(
        requested_path,
        headers=_headers("secret", "GET", signed_path),
    )

    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "invalid_signature"


def test_create_task_rejects_out_of_scope_request(tmp_path):
    path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["other.com"]},
            "engines": ["fofa"],
            "result_limit": 100,
            "purpose": "toolbox_asset_discovery",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)

    response = client.post(path, content=body, headers=_headers("secret", "POST", path, body))

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["errors"][0]["code"] == "scope_out_of_bounds"


def test_task_status_and_results_endpoints_require_and_accept_auth(tmp_path):
    task_path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "task_id": "task_1",
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.com"]},
            "engines": ["fofa"],
            "result_limit": 100,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)

    created = client.post(task_path, content=body, headers=_headers("secret", "POST", task_path, body))
    assert created.status_code == 200

    status_path = "/api/v1/discovery/tasks/task_1"
    assert client.get(status_path).status_code == 401
    status_response = client.get(status_path, headers=_headers("secret", "GET", status_path, nonce="nonce-status"))
    assert status_response.json()["task_id"] == "task_1"

    result_path = "/api/v1/discovery/tasks/task_1/results?limit=10&result_type=assets"
    assert client.get(result_path).status_code == 401
    result_response = client.get(result_path, headers=_headers("secret", "GET", result_path, nonce="nonce-results"))
    assert result_response.json()["page"]["type"] == "assets"


def test_create_task_returns_structured_rejection_for_scope_validation_error(tmp_path):
    path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.com"]},
            "engines": ["quake"],
            "result_limit": 100,
            "purpose": "toolbox_asset_discovery",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
        profile=TenantScopeProfile(
            tenant_id="tenant_poc",
            profile_id="scope_profile_001",
            status="active",
            allowed_root_domains=["example.com"],
            default_scope={"root_domains": ["example.com"]},
            allowed_engines=["fofa"],
            limits={"max_results_per_task": 200, "max_queries_per_task": 10},
        ),
    )
    client = TestClient(app)

    response = client.post(path, content=body, headers=_headers("secret", "POST", path, body))

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["errors"][0]["code"] == "scope_validation_failed"


def test_create_task_returns_429_when_tenant_quota_exceeded(tmp_path):
    path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.com"]},
            "engines": ["fofa"],
            "result_limit": 100,
            "purpose": "toolbox_asset_discovery",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
        quota_policy=TenantQuotaPolicy(max_tasks_per_day=0, max_provider_queries_per_day=100, max_concurrent_tasks=2),
    )
    client = TestClient(app)

    response = client.post(path, content=body, headers=_headers("secret", "POST", path, body))

    assert response.status_code == 429
    assert response.json()["status"] == "rejected"
    assert response.json()["errors"][0]["code"] == "tenant_daily_task_quota_exceeded"


def test_create_app_from_settings_uses_configured_secret_file_and_sqlite_nonce(tmp_path):
    secrets_path = tmp_path / "client-secrets.json"
    secrets_path.write_text(json.dumps({"tenant_poc": {"toolbox": "file-secret"}}), encoding="utf-8")
    settings = GatewaySettings(
        sqlite_path=str(tmp_path / "gateway.sqlite3"),
        client_secrets_file=str(secrets_path),
        scope_profile_seed="examples/scope_profile.json",
    )
    path = "/api/v1/discovery/scope-profile"
    app = create_app_from_settings(
        settings,
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)
    headers = _headers("file-secret", "GET", path)

    first = client.get(path, headers=headers)
    replay = client.get(path, headers=headers)

    assert first.status_code == 200
    assert first.json()["tenant_id"] == "tenant_poc"
    assert replay.status_code == 401
    assert replay.json()["errors"][0]["code"] == "replay_detected"
