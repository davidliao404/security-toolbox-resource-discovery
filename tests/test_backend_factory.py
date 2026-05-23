from pathlib import Path

import pytest

from resource_discovery.backend_factory import build_queue, build_repositories
from resource_discovery.config import GatewaySettings
from resource_discovery.http_app import create_app_from_settings
from resource_discovery.queue_backends import SQLiteTaskQueue
from resource_discovery.redis_queue import RedisTaskQueue
from resource_discovery.sqlite_store import SQLiteTaskRepository


def test_backend_factory_builds_sqlite_defaults(tmp_path):
    settings = GatewaySettings(sqlite_path=str(tmp_path / "gateway.sqlite3"))

    repositories = build_repositories(settings)
    queue = build_queue(settings)

    assert isinstance(repositories.task_repository, SQLiteTaskRepository)
    assert isinstance(queue, SQLiteTaskQueue)


def test_backend_factory_requires_postgres_database_url():
    settings = GatewaySettings(storage_backend="postgres", database_url="")

    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_repositories(settings)


def test_backend_factory_builds_redis_queue():
    settings = GatewaySettings(queue_backend="redis", redis_url="redis://localhost:6379/9")

    queue = build_queue(settings)

    assert isinstance(queue, RedisTaskQueue)
    assert queue.redis_url == "redis://localhost:6379/9"


def test_create_app_from_settings_exposes_configured_backend_names(tmp_path):
    secrets_path = tmp_path / "client-secrets.json"
    secrets_path.write_text('{"tenant_poc": {"toolbox": "secret"}}', encoding="utf-8")
    settings = GatewaySettings(
        sqlite_path=str(tmp_path / "gateway.sqlite3"),
        client_secrets_file=str(secrets_path),
        scope_profile_seed="examples/scope_profile.json",
        storage_backend="sqlite",
        queue_backend="sqlite",
    )

    app = create_app_from_settings(settings)

    assert app.state.storage_backend == "sqlite"
    assert app.state.queue_backend == "sqlite"
