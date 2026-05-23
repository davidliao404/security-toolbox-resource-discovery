from resource_discovery.config import GatewaySettings
from resource_discovery.http_app import create_app_from_settings


def test_prodlike_configuration_selects_postgres_and_redis_without_changing_api_paths():
    settings = GatewaySettings(
        storage_backend="postgres",
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery",
        queue_backend="redis",
        redis_url="redis://localhost:6379/0",
        client_secrets_file="config/client-secrets.example.json",
        scope_profile_seed="examples/scope_profile.json",
    )

    try:
        app = create_app_from_settings(settings)
    except Exception as exc:
        assert "DATABASE_URL" not in str(exc)
    else:
        paths = {route.path for route in app.routes}
        assert "/api/v1/discovery/scope-profile" in paths
        assert "/api/v1/discovery/tasks" in paths
        assert "/api/v1/discovery/tasks/{task_id}" in paths
        assert "/api/v1/discovery/tasks/{task_id}/results" in paths
