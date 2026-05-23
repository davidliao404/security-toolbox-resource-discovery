import os
from datetime import datetime, timezone

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
