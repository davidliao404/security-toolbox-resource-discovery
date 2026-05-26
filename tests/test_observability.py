import logging

from fastapi.testclient import TestClient

from resource_discovery.config import GatewaySettings
from resource_discovery.http_app import create_app_from_settings
from resource_discovery.logging_config import configure_logging


def _settings(tmp_path, metrics_enabled=True, log_format="json"):
    secrets_path = tmp_path / "client-secrets.json"
    secrets_path.write_text('{"tenant_poc": {"toolbox": "secret"}}', encoding="utf-8")
    return GatewaySettings(
        sqlite_path=str(tmp_path / "gateway.sqlite3"),
        client_secrets_file=str(secrets_path),
        scope_profile_seed="examples/scope_profile.json",
        metrics_enabled=metrics_enabled,
        log_format=log_format,
    )


def test_http_responses_include_request_id(tmp_path):
    app = create_app_from_settings(_settings(tmp_path))
    client = TestClient(app)

    response = client.get("/healthz", headers={"X-Request-Id": "req-123"})

    assert response.headers["X-Request-Id"] == "req-123"


def test_metrics_endpoint_can_be_enabled(tmp_path):
    app = create_app_from_settings(_settings(tmp_path, metrics_enabled=True))
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "resource_discovery_requests_total" in response.text
    assert "resource_discovery_tasks_created_total" in response.text
    assert "resource_discovery_tasks_completed_total" in response.text
    assert "resource_discovery_provider_errors_total" in response.text
    assert "resource_discovery_dead_letters_total" in response.text
    assert "resource_discovery_quota_rejections_total" in response.text


def test_metrics_endpoint_can_be_disabled(tmp_path):
    app = create_app_from_settings(_settings(tmp_path, metrics_enabled=False))
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 404


def test_configure_logging_sets_json_formatter():
    configure_logging(log_format="json", level="INFO")

    formatter = logging.getLogger().handlers[0].formatter

    assert formatter is not None
    assert formatter.__class__.__name__ == "JsonLogFormatter"
