import pytest

from resource_discovery.sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite


def test_task_repository_requires_matching_tenant(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteTaskRepository(db_path)
    repo.create({"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "success"}, "request": {}})

    with pytest.raises(FileNotFoundError):
        repo.load("tenant_b", "task_1")


def test_result_repository_requires_matching_tenant(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteResultRepository(db_path)
    repo.save_results("tenant_a", "task_1", {"assets": [{"asset_id": "asset_1"}]})

    assert repo.load_results("tenant_b", "task_1", None, 10)["assets"] == []
