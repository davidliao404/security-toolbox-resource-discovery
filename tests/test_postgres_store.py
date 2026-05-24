import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect

from resource_discovery.db import metadata
from resource_discovery.postgres_store import (
    PostgresAuditRepository,
    PostgresNonceRepository,
    PostgresResultRepository,
    PostgresScopeProfileRepository,
    PostgresTaskRepository,
    create_postgres_engine,
)
from resource_discovery.scope_guard import TenantScopeProfile


EXPECTED_TABLES = {
    "tasks",
    "task_results",
    "scope_profiles",
    "request_nonces",
    "audit_events",
    "queue_jobs",
    "client_secrets",
    "retention_policies",
    "rate_limit_buckets",
}


def test_postgres_metadata_declares_production_tables():
    assert EXPECTED_TABLES.issubset(metadata.tables)
    task_columns = metadata.tables["tasks"].c
    assert "tenant_id" in task_columns
    assert "client_id" in task_columns
    assert "status" in task_columns
    assert "created_at" in task_columns


def test_postgres_metadata_has_tenant_and_pagination_indexes():
    index_names = {index.name for table in metadata.tables.values() for index in table.indexes}
    assert "ix_tasks_tenant_status_created" in index_names
    assert "ix_results_tenant_task_type_position" in index_names
    assert "ix_nonces_expires_at" in index_names


class FakeScalarResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeRowsResult:
    def __init__(self, *, first=None, rows=None):
        self._first = first
        self._rows = rows or []

    def first(self):
        return self._first

    def all(self):
        return self._rows

    def mappings(self):
        return self


class FakeConnection:
    def __init__(self, results):
        self.results = results
        self.statements = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        if self.results:
            return self.results.pop(0)
        return FakeRowsResult()


class FakeBegin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def __init__(self, results=None):
        self.connection = FakeConnection(results or [])

    def begin(self):
        return FakeBegin(self.connection)


def test_create_postgres_engine_requires_database_url(monkeypatch):
    with pytest.raises(ValueError):
        create_postgres_engine("")

    created = {}
    monkeypatch.setattr(
        "resource_discovery.postgres_store.create_engine",
        lambda url, **kwargs: created.setdefault("args", (url, kwargs)) or "engine",
    )

    assert create_postgres_engine("postgresql://example") == ("postgresql://example", {"pool_pre_ping": True, "future": True})


def test_postgres_task_repository_uses_tenant_scoped_payloads():
    payload = {"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "queued"}, "request": {}}
    engine = FakeEngine(
        [
            FakeRowsResult(),
            FakeRowsResult(),
            FakeRowsResult(first=SimpleNamespace(payload=payload)),
            FakeRowsResult(rows=[{"task_id": "task_1", "status": "queued", "updated_at": "now"}]),
        ]
    )
    repo = PostgresTaskRepository(engine)

    repo.create(payload)
    payload["task"]["status"] = "success"
    repo.update(payload)

    assert repo.load("tenant_a", "task_1")["task"]["status"] == "success"
    assert repo.list("tenant_a") == [{"task_id": "task_1", "status": "queued", "updated_at": "now"}]
    assert len(engine.connection.statements) == 4


def test_postgres_task_repository_raises_for_missing_task():
    repo = PostgresTaskRepository(FakeEngine([FakeRowsResult(first=None)]))

    with pytest.raises(FileNotFoundError):
        repo.load("tenant_a", "missing")


def test_postgres_result_repository_paginates_by_result_type():
    engine = FakeEngine(
        [
            FakeRowsResult(),
            FakeRowsResult(),
            FakeRowsResult(
                rows=[
                    SimpleNamespace(payload={"asset_id": "asset_1"}),
                    SimpleNamespace(payload={"asset_id": "asset_2"}),
                ]
            )
        ]
    )
    repo = PostgresResultRepository(engine, max_page_limit=1)

    repo.save_results(
        "tenant_a",
        "task_1",
        {
            "assets": [{"asset_id": "asset_1"}],
            "services": [{"service_id": "svc_1"}],
            "source_evidence": [{"source": "fofa"}],
        },
    )
    page = repo.load_results("tenant_a", "task_1", None, 10, result_type="assets")

    assert page["assets"] == [{"asset_id": "asset_1"}]
    assert page["page"] == {"next_cursor": "1", "limit": 1, "type": "assets"}


def test_postgres_result_repository_rejects_unsupported_type():
    repo = PostgresResultRepository(FakeEngine())

    with pytest.raises(ValueError):
        repo.load_results("tenant_a", "task_1", None, 10, result_type="reports")


def test_postgres_scope_profile_repository_round_trip_and_inactive():
    profile = TenantScopeProfile(
        tenant_id="tenant_a",
        profile_id="scope_profile_001",
        status="active",
        allowed_root_domains=["example.com"],
    )
    engine = FakeEngine([FakeRowsResult(), FakeRowsResult(first=SimpleNamespace(payload=profile.__dict__))])
    repo = PostgresScopeProfileRepository(engine)

    repo.save(profile)
    assert repo.load_active("tenant_a", "scope_profile_001").tenant_id == "tenant_a"

    inactive_payload = {**profile.__dict__, "status": "inactive"}
    inactive_repo = PostgresScopeProfileRepository(FakeEngine([FakeRowsResult(first=SimpleNamespace(payload=inactive_payload))]))
    with pytest.raises(ValueError):
        inactive_repo.load_active("tenant_a", "scope_profile_001")


def test_postgres_scope_profile_repository_raises_for_missing_profile():
    repo = PostgresScopeProfileRepository(FakeEngine([FakeRowsResult(first=None)]))

    with pytest.raises(FileNotFoundError):
        repo.load_active("tenant_a", "missing")


def test_postgres_nonce_repository_tracks_replay_result():
    timestamp = datetime(2026, 5, 24, tzinfo=timezone.utc)
    first = PostgresNonceRepository(FakeEngine([FakeRowsResult(), FakeScalarResult("nonce-1")]))
    replay = PostgresNonceRepository(FakeEngine([FakeRowsResult(), FakeScalarResult(None)]))

    assert first.remember_once("nonce-1", timestamp)
    assert not replay.remember_once("nonce-1", timestamp)


def test_postgres_audit_repository_records_and_lists_events():
    engine = FakeEngine(
        [
            FakeRowsResult(),
            FakeRowsResult(
                rows=[
                    {
                        "tenant_id": "tenant_a",
                        "task_id": "task_1",
                        "event_type": "task_checked",
                        "details": {"ok": True},
                        "created_at": "now",
                    }
                ]
            )
        ]
    )
    repo = PostgresAuditRepository(engine)

    repo.record_event("tenant_a", "task_1", "task_checked", {"ok": True})

    assert repo.list_events("tenant_a")[0]["event_type"] == "task_checked"


@pytest.fixture()
def database_url():
    url = os.getenv("RESOURCE_DISCOVERY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RESOURCE_DISCOVERY_TEST_DATABASE_URL is not set")
    return url


@pytest.fixture()
def engine(database_url):
    engine = create_postgres_engine(database_url)
    metadata.drop_all(engine)
    metadata.create_all(engine)
    yield engine
    metadata.drop_all(engine)
    engine.dispose()


def test_postgres_repositories_round_trip_task_results_scope_nonce_and_audit(engine):
    assert "tasks" in inspect(engine).get_table_names()
    task_repo = PostgresTaskRepository(engine)
    result_repo = PostgresResultRepository(engine)
    scope_repo = PostgresScopeProfileRepository(engine)
    nonce_repo = PostgresNonceRepository(engine, window_seconds=300)
    audit_repo = PostgresAuditRepository(engine)

    profile = TenantScopeProfile(
        tenant_id="tenant_a",
        profile_id="scope_profile_001",
        status="active",
        allowed_root_domains=["example.com"],
        allowed_domains=[],
        allowed_ip_cidrs=[],
        allowed_org_names=[],
        allowed_engines=["fofa"],
        default_scope={"root_domains": ["example.com"]},
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        authorization_note="approval",
    )
    scope_repo.save(profile)
    assert scope_repo.load_active("tenant_a", "scope_profile_001").tenant_id == "tenant_a"

    payload = {"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "queued"}, "request": {}}
    task_repo.create(payload)
    payload["task"]["status"] = "success"
    task_repo.update(payload)
    assert task_repo.load("tenant_a", "task_1")["task"]["status"] == "success"

    result_repo.save_results("tenant_a", "task_1", {"assets": [{"asset_id": "asset_1"}]})
    assert result_repo.load_results("tenant_a", "task_1", None, 10)["assets"] == [{"asset_id": "asset_1"}]

    timestamp = datetime.now(timezone.utc)
    assert nonce_repo.remember_once("nonce-1", timestamp)
    assert not nonce_repo.remember_once("nonce-1", timestamp)

    audit_repo.record_event("tenant_a", "task_1", "task_checked", {"ok": True})
    assert audit_repo.list_events("tenant_a")[0]["event_type"] == "task_checked"
