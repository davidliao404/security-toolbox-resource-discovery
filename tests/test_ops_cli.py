import json
import sys
from types import SimpleNamespace

import pytest

import resource_discovery.ops_cli as ops_cli
from resource_discovery.ops_cli import main
from resource_discovery.sqlite_store import SQLiteScopeProfileRepository


def test_verify_config_accepts_sqlite_settings(tmp_path, capsys):
    secrets_path = tmp_path / "client-secrets.json"
    secrets_path.write_text('{"tenant_poc": {"toolbox": "secret"}}', encoding="utf-8")

    exit_code = main(
        [
            "verify-config",
            "--sqlite-path",
            str(tmp_path / "gateway.sqlite3"),
            "--client-secrets-file",
            str(secrets_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_seed_scope_profile_writes_sqlite_profile(tmp_path):
    profile_path = tmp_path / "scope.json"
    profile_path.write_text(
        json.dumps(
            {
                "tenant_id": "tenant_a",
                "profile_id": "scope_profile_001",
                "status": "active",
                "allowed_root_domains": ["example.com"],
                "allowed_domains": [],
                "allowed_ip_cidrs": [],
                "allowed_org_names": [],
                "allowed_engines": ["fofa"],
                "default_scope": {"root_domains": ["example.com"]},
                "limits": {"max_results_per_task": 100, "max_queries_per_task": 10},
                "authorization_note": "approval",
            }
        ),
        encoding="utf-8",
    )
    sqlite_path = tmp_path / "gateway.sqlite3"

    assert main(["seed-scope-profile", "--sqlite-path", str(sqlite_path), "--profile-json", str(profile_path)]) == 0

    repo = SQLiteScopeProfileRepository(sqlite_path)
    assert repo.load_active("tenant_a", "scope_profile_001").allowed_root_domains == ["example.com"]


def test_cleanup_retention_removes_expired_sqlite_rows(tmp_path, capsys):
    sqlite_path = tmp_path / "gateway.sqlite3"
    from resource_discovery.sqlite_store import _connect, initialize_sqlite

    initialize_sqlite(sqlite_path)
    with _connect(sqlite_path) as conn:
        conn.execute(
            "insert into tasks (tenant_id, task_id, status, payload, updated_at) values (?, ?, ?, ?, ?)",
            ("tenant_a", "old_task", "success", '{"task": {"tenant_id": "tenant_a", "task_id": "old_task"}}', "2000-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "insert into results (tenant_id, task_id, result_type, position, payload) values (?, ?, ?, ?, ?)",
            ("tenant_a", "old_task", "assets", 0, '{"asset_id": "asset_old"}'),
        )
    assert main(["cleanup-retention", "--sqlite-path", str(sqlite_path), "--older-than-days", "0"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert "deleted" in payload
    assert payload["deleted"]["tasks"] == 1
    assert payload["deleted"]["results"] == 1


def test_verify_config_rejects_missing_required_files_and_backend_urls(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        main(["verify-config", "--client-secrets-file", str(tmp_path / "missing.json")])

    secrets_path = tmp_path / "client-secrets.json"
    secrets_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="DATABASE_URL"):
        main(["verify-config", "--storage-backend", "postgres", "--client-secrets-file", str(secrets_path)])

    monkeypatch.setenv("RESOURCE_DISCOVERY_REDIS_URL", "")
    with pytest.raises(ValueError, match="REDIS_URL"):
        main(
            [
                "verify-config",
                "--queue-backend",
                "redis",
                "--redis-url",
                "",
                "--client-secrets-file",
                str(secrets_path),
            ]
        )


def test_migrate_sets_database_url_and_runs_alembic(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(ops_cli.command, "upgrade", lambda config, target: calls.setdefault("target", target))

    assert main(["migrate", "--database-url", "postgresql://example", "--alembic-ini", "alembic.ini"]) == 0

    assert calls["target"] == "head"
    assert json.loads(capsys.readouterr().out) == {"status": "ok", "migration": "head"}


def test_seed_rejects_postgres_backend_and_cleanup_requires_tenant_for_postgres(tmp_path):
    profile_path = tmp_path / "scope.json"
    profile_path.write_text('{"tenant_id": "tenant_a", "profile_id": "scope_1"}', encoding="utf-8")

    with pytest.raises(ValueError, match="sqlite"):
        main(["seed-scope-profile", "--storage-backend", "postgres", "--database-url", "postgresql://example", "--profile-json", str(profile_path)])

    with pytest.raises(ValueError, match="tenant-id"):
        main(["cleanup-retention", "--storage-backend", "postgres", "--database-url", "postgresql://example"])


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, base_url, timeout):
        self.base_url = base_url
        self.timeout = timeout
        self.posts = []
        self.gets = []

    def get(self, path, headers):
        self.gets.append((path, headers))
        if path == "/api/v1/discovery/scope-profile":
            return FakeResponse({"profile_id": "scope_profile_001", "default_scope": {"root_domains": ["example.com"]}})
        if path.endswith("/results?result_type=assets&limit=20"):
            return FakeResponse({"assets": [{"asset_id": "asset_1"}]})
        return FakeResponse({"status": "success"})

    def post(self, path, content, headers):
        self.posts.append((path, content, headers))
        return FakeResponse({"task_id": "task_1"})


def test_smoke_test_polls_task_and_fetches_results(monkeypatch, capsys):
    fake_client = FakeHttpClient("http://example", 10)
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(Client=lambda base_url, timeout: fake_client),
    )

    assert main(["smoke-test", "--base-url", "http://example", "--client-id", "toolbox", "--secret", "secret", "--timeout-seconds", "0.1"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"status": "success", "task_id": "task_1", "asset_count": 1}
    assert fake_client.posts
    assert fake_client.gets[-1][0] == "/api/v1/discovery/tasks/task_1/results?result_type=assets&limit=20"
