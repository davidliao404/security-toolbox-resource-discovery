from resource_discovery.config import GatewaySettings, load_settings


def test_load_settings_uses_defaults(monkeypatch):
    monkeypatch.delenv("RESOURCE_DISCOVERY_SQLITE_PATH", raising=False)
    settings = load_settings()
    assert settings.api_prefix == "/api/v1/discovery"
    assert settings.sqlite_path == "artifacts/integration/resource-discovery.sqlite3"
    assert settings.queue_backend == "sqlite"
    assert settings.nonce_window_seconds == 300


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("RESOURCE_DISCOVERY_SQLITE_PATH", "artifacts/test.sqlite3")
    monkeypatch.setenv("RESOURCE_DISCOVERY_QUEUE_BACKEND", "redis")
    monkeypatch.setenv("RESOURCE_DISCOVERY_REDIS_URL", "redis://localhost:6379/3")
    monkeypatch.setenv("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX", "250")
    settings = load_settings()
    assert settings.sqlite_path == "artifacts/test.sqlite3"
    assert settings.queue_backend == "redis"
    assert settings.redis_url == "redis://localhost:6379/3"
    assert settings.result_limit_max == 250


def test_gateway_settings_rejects_unknown_queue_backend():
    try:
        GatewaySettings(queue_backend="filesystem")
    except ValueError as exc:
        assert "Unsupported queue backend" in str(exc)
    else:
        raise AssertionError("Expected unsupported queue backend to be rejected")
