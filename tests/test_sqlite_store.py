from datetime import datetime, timezone

from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.sqlite_store import (
    SQLiteAuditRepository,
    SQLiteNonceRepository,
    SQLiteResultRepository,
    SQLiteScopeProfileRepository,
    SQLiteTaskRepository,
    initialize_sqlite,
)


def test_sqlite_task_repository_round_trips_task(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteTaskRepository(db_path)
    payload = {"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "queued"}, "request": {}}

    repo.create(payload)
    payload["task"]["status"] = "running"
    repo.update(payload)

    assert repo.load("tenant_a", "task_1")["task"]["status"] == "running"
    assert repo.list("tenant_a")[0]["task_id"] == "task_1"


def test_sqlite_result_repository_paginates_by_type(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteResultRepository(db_path, max_page_limit=2)
    repo.save_results(
        "tenant_a",
        "task_1",
        {
            "assets": [{"asset_id": "a1"}, {"asset_id": "a2"}, {"asset_id": "a3"}],
            "services": [{"service_id": "s1"}],
            "source_evidence": [{"evidence_id": "e1"}],
        },
    )

    first = repo.load_results("tenant_a", "task_1", None, 2, result_type="assets")
    second = repo.load_results("tenant_a", "task_1", first["page"]["next_cursor"], 2, result_type="assets")

    assert [item["asset_id"] for item in first["assets"]] == ["a1", "a2"]
    assert [item["asset_id"] for item in second["assets"]] == ["a3"]
    assert second["page"]["next_cursor"] is None


def test_sqlite_scope_profile_repository_loads_active_profile(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteScopeProfileRepository(db_path)
    profile = TenantScopeProfile(
        tenant_id="tenant_a",
        profile_id="profile_1",
        status="active",
        allowed_root_domains=["example.com"],
        allowed_domains=[],
        allowed_ip_cidrs=[],
        allowed_org_names=[],
        allowed_engines=["fofa"],
        default_scope={"root_domains": ["example.com"]},
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        authorization_note="Customer approval for example.com.",
    )

    repo.save(profile)

    assert repo.load_active("tenant_a", "profile_1").allowed_root_domains == ["example.com"]


def test_sqlite_nonce_repository_rejects_replay(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteNonceRepository(db_path, window_seconds=300)
    timestamp = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)

    assert repo.remember_once("nonce-1", timestamp)
    assert not repo.remember_once("nonce-1", timestamp)


def test_sqlite_audit_repository_appends_events(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteAuditRepository(db_path)

    repo.record_event("tenant_a", "task_1", "discovery_task_started", {"worker": "local"})

    assert repo.list_events("tenant_a")[0]["event_type"] == "discovery_task_started"
