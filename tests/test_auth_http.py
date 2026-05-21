import json
from datetime import datetime, timezone

from resource_discovery.auth_http import FileClientSecretResolver, authenticate_http_request
from resource_discovery.request_auth import AuthError, InMemoryNonceStore, build_signature


def test_file_client_secret_resolver_loads_secret(tmp_path):
    path = tmp_path / "client-secrets.json"
    path.write_text(json.dumps({"tenant_a": {"toolbox": "secret-1"}}), encoding="utf-8")
    resolver = FileClientSecretResolver(path)

    assert resolver.resolve("tenant_a", "toolbox") == "secret-1"


def test_authenticate_http_request_accepts_valid_signature(tmp_path):
    path = tmp_path / "client-secrets.json"
    path.write_text(json.dumps({"tenant_a": {"toolbox": "secret-1"}}), encoding="utf-8")
    timestamp = "2026-05-22T10:00:00+00:00"
    body = b'{"profile_id":"profile_1"}'
    signature = build_signature(
        secret="secret-1",
        method="POST",
        path="/api/v1/discovery/tasks",
        timestamp=timestamp,
        nonce="nonce-1",
        body=body,
    )

    result = authenticate_http_request(
        method="POST",
        path="/api/v1/discovery/tasks",
        body=body,
        headers={
            "X-Tenant-Id": "tenant_a",
            "X-Client-Id": "toolbox",
            "X-Timestamp": timestamp,
            "X-Nonce": "nonce-1",
            "X-Signature": signature,
        },
        resolver=FileClientSecretResolver(path),
        nonce_store=InMemoryNonceStore(),
        now=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )

    assert result == {"tenant_id": "tenant_a", "client_id": "toolbox"}


def test_authenticate_http_request_rejects_missing_header(tmp_path):
    path = tmp_path / "client-secrets.json"
    path.write_text(json.dumps({"tenant_a": {"toolbox": "secret-1"}}), encoding="utf-8")

    try:
        authenticate_http_request(
            method="GET",
            path="/api/v1/discovery/scope-profile",
            body=b"",
            headers={"X-Tenant-Id": "tenant_a"},
            resolver=FileClientSecretResolver(path),
            nonce_store=InMemoryNonceStore(),
            now=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
        )
    except AuthError as exc:
        assert exc.code == "missing_auth_header"
    else:
        raise AssertionError("Expected missing auth header to be rejected")
