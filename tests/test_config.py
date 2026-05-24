from resource_discovery.config import GatewaySettings, load_settings
import pytest


def test_load_settings_uses_defaults(monkeypatch):
    monkeypatch.delenv("RESOURCE_DISCOVERY_SQLITE_PATH", raising=False)
    monkeypatch.delenv("RESOURCE_DISCOVERY_STORAGE_BACKEND", raising=False)
    settings = load_settings()
    assert settings.api_prefix == "/api/v1/discovery"
    assert settings.sqlite_path == "artifacts/integration/resource-discovery.sqlite3"
    assert settings.storage_backend == "sqlite"
    assert settings.queue_backend == "sqlite"
    assert settings.database_url == ""
    assert settings.nonce_window_seconds == 300
    assert settings.worker_max_attempts == 3
    assert settings.worker_retry_delay_seconds == 30
    assert settings.dead_letter_enabled is True
    assert settings.metrics_enabled is False
    assert settings.log_format == "text"


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("RESOURCE_DISCOVERY_SQLITE_PATH", "artifacts/test.sqlite3")
    monkeypatch.setenv("RESOURCE_DISCOVERY_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("RESOURCE_DISCOVERY_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/rd")
    monkeypatch.setenv("RESOURCE_DISCOVERY_QUEUE_BACKEND", "redis")
    monkeypatch.setenv("RESOURCE_DISCOVERY_REDIS_URL", "redis://localhost:6379/3")
    monkeypatch.setenv("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX", "250")
    monkeypatch.setenv("RESOURCE_DISCOVERY_WORKER_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("RESOURCE_DISCOVERY_WORKER_RETRY_DELAY_SECONDS", "45")
    monkeypatch.setenv("RESOURCE_DISCOVERY_DEAD_LETTER_ENABLED", "false")
    monkeypatch.setenv("RESOURCE_DISCOVERY_METRICS_ENABLED", "true")
    monkeypatch.setenv("RESOURCE_DISCOVERY_LOG_FORMAT", "json")
    settings = load_settings()
    assert settings.sqlite_path == "artifacts/test.sqlite3"
    assert settings.storage_backend == "postgres"
    assert settings.database_url == "postgresql+psycopg://postgres:postgres@localhost:5432/rd"
    assert settings.queue_backend == "redis"
    assert settings.redis_url == "redis://localhost:6379/3"
    assert settings.result_limit_max == 250
    assert settings.worker_max_attempts == 5
    assert settings.worker_retry_delay_seconds == 45
    assert settings.dead_letter_enabled is False
    assert settings.metrics_enabled is True
    assert settings.log_format == "json"


def test_gateway_settings_rejects_unknown_queue_backend():
    try:
        GatewaySettings(queue_backend="filesystem")
    except ValueError as exc:
        assert "Unsupported queue backend" in str(exc)
    else:
        raise AssertionError("Expected unsupported queue backend to be rejected")


def test_gateway_settings_rejects_unknown_storage_backend():
    try:
        GatewaySettings(storage_backend="filesystem")
    except ValueError as exc:
        assert "Unsupported storage backend" in str(exc)
    else:
        raise AssertionError("Expected unsupported storage backend to be rejected")


def test_gateway_settings_rejects_unknown_log_format():
    try:
        GatewaySettings(log_format="xml")
    except ValueError as exc:
        assert "Unsupported log format" in str(exc)
    else:
        raise AssertionError("Expected unsupported log format to be rejected")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"result_limit_default": 0}, "RESULT_LIMIT_DEFAULT"),
        ({"result_limit_default": 100, "result_limit_max": 50}, "RESULT_LIMIT_MAX"),
        ({"nonce_window_seconds": 0}, "NONCE_WINDOW_SECONDS"),
        ({"worker_max_attempts": 0}, "WORKER_MAX_ATTEMPTS"),
        ({"worker_retry_delay_seconds": -1}, "WORKER_RETRY_DELAY_SECONDS"),
    ],
)
def test_gateway_settings_rejects_invalid_numeric_limits(kwargs, message):
    with pytest.raises(ValueError, match=message):
        GatewaySettings(**kwargs)
