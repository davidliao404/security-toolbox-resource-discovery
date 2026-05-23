import json

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
