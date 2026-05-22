import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from resource_discovery.config import GatewaySettings
from resource_discovery.http_app import create_app, create_app_from_settings
from resource_discovery.request_auth import build_signature


def _headers(secret, method, path, body=b"", nonce="nonce-1"):
    timestamp = "2026-05-22T10:00:00+00:00"
    return {
        "X-Tenant-Id": "tenant_poc",
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


def test_scope_profile_requires_signature(tmp_path):
    app = create_app(sqlite_path=tmp_path / "gateway.sqlite3", client_secrets={"tenant_poc": {"toolbox": "secret"}})
    client = TestClient(app)

    response = client.get("/api/v1/discovery/scope-profile")

    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "missing_auth_header"


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