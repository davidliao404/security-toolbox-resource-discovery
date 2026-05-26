import json
import os
import pytest

from resource_discovery.client_secrets import ClientSecretRecord
from resource_discovery.ops_cli import main
from resource_discovery.queue_backends import SQLiteTaskQueue
from resource_discovery.sqlite_store import SQLiteAuditRepository, SQLiteScopeProfileRepository, SQLiteTaskRepository, initialize_sqlite
from resource_discovery.task_queue import TaskWorkItem


class FakeClientSecretRepository:
    saved = []

    def __init__(self, engine):
        self.engine = engine

    def upsert(self, record):
        self.saved.append(record)


def test_rotate_client_secret_stores_secret_ref_only(monkeypatch, capsys):
    created = {}
    FakeClientSecretRepository.saved = []
    monkeypatch.setattr("resource_discovery.ops_cli.create_postgres_engine", lambda url: created.setdefault("url", url))
    monkeypatch.setattr("resource_discovery.ops_cli.PostgresClientSecretRepository", FakeClientSecretRepository)

    exit_code = main(
        [
            "rotate-client-secret",
            "--database-url",
            "postgresql://example",
            "--tenant-id",
            "tenant_a",
            "--client-id",
            "toolbox",
            "--secret-ref",
            "vault://tenant_a/toolbox/current",
        ]
    )

    assert exit_code == 0
    assert created["url"] == "postgresql://example"
    record = FakeClientSecretRepository.saved[0]
    assert isinstance(record, ClientSecretRecord)
    assert record.tenant_id == "tenant_a"
    assert record.client_id == "toolbox"
    assert record.secret_ref == "vault://tenant_a/toolbox/current"
    assert "secret-v2" not in capsys.readouterr().out


def test_rotate_client_secret_prints_redacted_summary(monkeypatch, capsys):
    FakeClientSecretRepository.saved = []
    monkeypatch.setattr("resource_discovery.ops_cli.create_postgres_engine", lambda url: object())
    monkeypatch.setattr("resource_discovery.ops_cli.PostgresClientSecretRepository", FakeClientSecretRepository)

    assert (
        main(
            [
                "rotate-client-secret",
                "--database-url",
                "postgresql://example",
                "--tenant-id",
                "tenant_a",
                "--client-id",
                "toolbox",
                "--secret-ref",
                "vault://tenant_a/toolbox/current",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "ok",
        "tenant_id": "tenant_a",
        "client_id": "toolbox",
        "secret_ref": "vault://tenant_a/toolbox/current",
        "active": True,
    }


def test_approve_scope_profile_writes_active_profile_and_redacted_audit(tmp_path, capsys):
    profile_path = tmp_path / "scope.json"
    profile_path.write_text(
        json.dumps(
            {
                "tenant_id": "tenant_a",
                "profile_id": "scope_profile_001",
                "status": "draft",
                "allowed_root_domains": ["example.com"],
                "allowed_domains": ["vpn.example.com"],
                "allowed_ip_cidrs": [],
                "allowed_org_names": [],
                "allowed_engines": ["fofa"],
                "default_scope": {"root_domains": ["example.com"]},
                "limits": {"max_results_per_task": 100, "max_queries_per_task": 10},
                "authorization_note": "customer authorization",
            }
        ),
        encoding="utf-8",
    )
    sqlite_path = tmp_path / "gateway.sqlite3"

    assert (
        main(
            [
                "approve-scope-profile",
                "--sqlite-path",
                str(sqlite_path),
                "--profile-file",
                str(profile_path),
                "--tenant-id",
                "tenant_a",
                "--profile-id",
                "scope_profile_001",
                "--approved-by",
                "security-admin",
                "--ticket-id",
                "SEC-2026-0525",
            ]
        )
        == 0
    )

    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "ok"
    profile = SQLiteScopeProfileRepository(sqlite_path).load_active("tenant_a", "scope_profile_001")
    assert profile.status == "active"
    assert profile.approval["approved_by"] == "security-admin"
    assert profile.approval["ticket_id"] == "SEC-2026-0525"

    events = SQLiteAuditRepository(sqlite_path).list_events("tenant_a")
    assert events[0]["event_type"] == "scope_profile_approved"
    assert events[0]["details"] == {
        "profile_id": "scope_profile_001",
        "approved_by": "security-admin",
        "ticket_id": "SEC-2026-0525",
    }


def test_approve_scope_profile_rejects_tenant_mismatch(tmp_path):
    profile_path = tmp_path / "scope.json"
    profile_path.write_text(
        json.dumps({"tenant_id": "tenant_b", "profile_id": "scope_profile_001"}),
        encoding="utf-8",
    )

    try:
        main(
            [
                "approve-scope-profile",
                "--sqlite-path",
                str(tmp_path / "gateway.sqlite3"),
                "--profile-file",
                str(profile_path),
                "--tenant-id",
                "tenant_a",
                "--profile-id",
                "scope_profile_001",
                "--approved-by",
                "security-admin",
                "--ticket-id",
                "SEC-2026-0525",
            ]
        )
    except ValueError as exc:
        assert "tenant" in str(exc)
    else:
        raise AssertionError("Expected tenant mismatch to be rejected")


def test_approve_scope_profile_rejects_profile_id_mismatch(tmp_path):
    profile_path = tmp_path / "scope.json"
    profile_path.write_text(
        json.dumps({"tenant_id": "tenant_a", "profile_id": "scope_other"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="profile"):
        main(
            [
                "approve-scope-profile",
                "--sqlite-path",
                str(tmp_path / "gateway.sqlite3"),
                "--profile-file",
                str(profile_path),
                "--tenant-id",
                "tenant_a",
                "--profile-id",
                "scope_profile_001",
                "--approved-by",
                "security-admin",
                "--ticket-id",
                "SEC-2026-0525",
            ]
        )


def test_approve_scope_profile_supports_postgres_backend(tmp_path, monkeypatch):
    profile_path = tmp_path / "scope.json"
    profile_path.write_text(
        json.dumps(
            {
                "tenant_id": "tenant_a",
                "profile_id": "scope_profile_001",
                "status": "draft",
                "allowed_root_domains": ["example.com"],
            }
        ),
        encoding="utf-8",
    )
    calls = {"profiles": [], "audits": []}

    class FakeScopeRepo:
        def __init__(self, engine):
            self.engine = engine

        def save(self, profile):
            calls["profiles"].append(profile)

    class FakeAuditRepo:
        def __init__(self, engine):
            self.engine = engine

        def record_event(self, tenant_id, task_id, event_type, details):
            calls["audits"].append((tenant_id, task_id, event_type, details))

    monkeypatch.setattr("resource_discovery.ops_cli.create_postgres_engine", lambda url: object())
    monkeypatch.setattr("resource_discovery.postgres_store.PostgresScopeProfileRepository", FakeScopeRepo)
    monkeypatch.setattr("resource_discovery.postgres_store.PostgresAuditRepository", FakeAuditRepo)

    assert (
        main(
            [
                "approve-scope-profile",
                "--storage-backend",
                "postgres",
                "--database-url",
                "postgresql://example",
                "--profile-file",
                str(profile_path),
                "--tenant-id",
                "tenant_a",
                "--profile-id",
                "scope_profile_001",
                "--approved-by",
                "security-admin",
                "--ticket-id",
                "SEC-2026-0525",
            ]
        )
        == 0
    )

    assert calls["profiles"][0].status == "active"
    assert calls["audits"][0][2] == "scope_profile_approved"


def test_cancel_task_command_cancels_sqlite_task(tmp_path, capsys):
    sqlite_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(sqlite_path)
    repo = SQLiteTaskRepository(sqlite_path)
    repo.create({"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "queued"}})

    assert (
        main(
            [
                "cancel-task",
                "--sqlite-path",
                str(sqlite_path),
                "--tenant-id",
                "tenant_a",
                "--task-id",
                "task_1",
                "--actor",
                "ops-user",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["status"] == "cancelled"
    assert repo.load("tenant_a", "task_1")["task"]["cancelled_by"] == "ops-user"


def test_cancel_task_command_returns_rejection_for_terminal_task(tmp_path, capsys):
    sqlite_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(sqlite_path)
    SQLiteTaskRepository(sqlite_path).create({"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "success"}})

    assert (
        main(
            [
                "cancel-task",
                "--sqlite-path",
                str(sqlite_path),
                "--tenant-id",
                "tenant_a",
                "--task-id",
                "task_1",
                "--actor",
                "ops-user",
            ]
        )
        == 1
    )

    assert json.loads(capsys.readouterr().out)["errors"][0]["code"] == "task_not_cancellable"


def test_cancel_task_command_rejects_non_sqlite_backend():
    with pytest.raises(ValueError, match="sqlite"):
        main(
            [
                "cancel-task",
                "--storage-backend",
                "postgres",
                "--database-url",
                "postgresql://example",
                "--tenant-id",
                "tenant_a",
                "--task-id",
                "task_1",
                "--actor",
                "ops-user",
            ]
        )


def test_list_dead_letters_command_prints_failed_sqlite_jobs(tmp_path, capsys):
    sqlite_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(sqlite_path)
    queue = SQLiteTaskQueue(sqlite_path)
    item = TaskWorkItem("tenant_a", "task_1")
    queue.enqueue(item)
    queue.dequeue()
    queue.mark_failed(item, "provider_timeout")

    assert main(["list-dead-letters", "--sqlite-path", str(sqlite_path)]) == 0

    assert json.loads(capsys.readouterr().out)["last_error"] == "provider_timeout"


def test_list_dead_letters_command_rejects_non_sqlite_queue():
    with pytest.raises(ValueError, match="sqlite"):
        main(["list-dead-letters", "--queue-backend", "redis", "--redis-url", "redis://localhost:6379/0"])


def test_search_audit_command_filters_sqlite_events(tmp_path, capsys):
    sqlite_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(sqlite_path)
    audit = SQLiteAuditRepository(sqlite_path)
    audit.record_event("tenant_a", "task_1", "scope_profile_approved", {"ok": True})
    audit.record_event("tenant_a", "task_2", "other", {"ok": False})

    assert (
        main(
            [
                "search-audit",
                "--sqlite-path",
                str(sqlite_path),
                "--tenant-id",
                "tenant_a",
                "--event-type",
                "scope_profile_approved",
                "--task-id",
                "task_1",
            ]
        )
        == 0
    )

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_type"] == "scope_profile_approved"


def test_search_audit_command_supports_postgres_backend(monkeypatch, capsys):
    class FakeAuditRepo:
        def __init__(self, engine):
            self.engine = engine

        def search_events(self, tenant_id, event_type, task_id, limit):
            return [{"tenant_id": tenant_id, "task_id": task_id, "event_type": event_type, "details": {}, "created_at": "now"}]

    monkeypatch.setattr("resource_discovery.ops_cli.create_postgres_engine", lambda url: object())
    monkeypatch.setattr("resource_discovery.postgres_store.PostgresAuditRepository", FakeAuditRepo)

    assert (
        main(
            [
                "search-audit",
                "--storage-backend",
                "postgres",
                "--database-url",
                "postgresql://example",
                "--tenant-id",
                "tenant_a",
                "--event-type",
                "scope_profile_approved",
                "--task-id",
                "task_1",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["tenant_id"] == "tenant_a"


def test_cleanup_retention_supports_postgres_backend(monkeypatch, capsys):
    class FakeRetentionRepo:
        def __init__(self, engine):
            self.engine = engine

        def cleanup_expired_rows(self, tenant_id, now):
            return {"tasks": 1, "results": 2, "audit_events": 0, "request_nonces": 3}

    monkeypatch.setattr("resource_discovery.ops_cli.create_postgres_engine", lambda url: object())
    monkeypatch.setattr("resource_discovery.postgres_store.PostgresRetentionRepository", FakeRetentionRepo)

    assert (
        main(
            [
                "cleanup-retention",
                "--storage-backend",
                "postgres",
                "--database-url",
                "postgresql://example",
                "--tenant-id",
                "tenant_a",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["deleted"]["request_nonces"] == 3


def test_live_fofa_regression_command_prints_summary(monkeypatch, capsys):
    monkeypatch.setenv("RESOURCE_DISCOVERY_LIVE_FOFA", "1")
    monkeypatch.setenv("FOFA_EMAIL", "user@example.com")
    monkeypatch.setenv("FOFA_KEY", "secret")
    monkeypatch.setenv("RESOURCE_DISCOVERY_LIVE_AUTHORIZED_DOMAIN", "example.com")
    monkeypatch.setattr(
        "resource_discovery.live_validation.run_live_fofa_regression",
        lambda **kwargs: {"status": "success", "asset_count": 1, "service_count": 1},
    )

    assert main(["live-fofa-regression"]) == 0

    rendered = capsys.readouterr().out
    assert json.loads(rendered)["status"] == "success"
    assert os.environ["FOFA_KEY"] not in rendered
