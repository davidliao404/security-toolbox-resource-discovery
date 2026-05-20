import json

import pytest

from resource_discovery.execution import run_discovery
from resource_discovery.task_store import FileTaskStore, SnapshotStoreError


def test_file_task_store_saves_and_loads_snapshot(tmp_path):
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )
    store = FileTaskStore(tmp_path)

    saved_path = store.save(payload)
    loaded = store.load("tenant_poc", "dt_poc_001")

    assert saved_path.name == "dt_poc_001.json"
    assert loaded["task"]["task_id"] == "dt_poc_001"
    assert loaded["task"]["tenant_id"] == "tenant_poc"
    assert loaded["task"]["status"] == "success"
    assert loaded["snapshot"]["summary"]["asset_count"] == 4


def test_file_task_store_lists_snapshot_summaries(tmp_path):
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )
    store = FileTaskStore(tmp_path)
    store.save(payload)

    summaries = store.list("tenant_poc")

    assert summaries == [
        {
            "tenant_id": "tenant_poc",
            "task_id": "dt_poc_001",
            "status": "success",
            "asset_count": 4,
            "service_count": 4,
            "risk_hint_count": 6,
            "analysis_mode": "rules_only",
            "llm_enabled": False,
        }
    ]


def test_file_task_store_rejects_unsafe_identifiers(tmp_path):
    store = FileTaskStore(tmp_path)
    payload = {
        "task": {
            "tenant_id": "../tenant",
            "task_id": "dt_poc_001",
            "status": "success",
            "quota_usage": {},
            "errors": [],
        },
        "snapshot": {"summary": {}},
    }

    with pytest.raises(SnapshotStoreError, match="Unsafe"):
        store.save(payload)


def test_file_task_store_raises_for_missing_snapshot(tmp_path):
    store = FileTaskStore(tmp_path)

    with pytest.raises(SnapshotStoreError, match="not found"):
        store.load("tenant_poc", "missing")
