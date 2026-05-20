import json

from resource_discovery.execution import run_discovery
from resource_discovery.repositories import (
    FileResultRepository,
    FileScopeProfileRepository,
    FileTaskRepository,
)


def _payload():
    return run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )


def test_file_task_repository_creates_updates_loads_and_lists_tasks(tmp_path):
    repo = FileTaskRepository(tmp_path / "tasks")
    payload = _payload()

    repo.create(payload)
    payload["task"]["status"] = "running"
    repo.update(payload)
    loaded = repo.load("tenant_poc", "dt_poc_001")
    summaries = repo.list("tenant_poc")

    assert loaded["task"]["status"] == "running"
    assert summaries[0]["task_id"] == "dt_poc_001"
    assert summaries[0]["analysis_mode"] == "rules_only"


def test_file_result_repository_saves_and_paginates_results(tmp_path):
    repo = FileResultRepository(tmp_path / "results")
    payload = _payload()

    repo.save_results("tenant_poc", "dt_poc_001", payload)
    page_1 = repo.load_results("tenant_poc", "dt_poc_001", cursor=None, limit=2)
    page_2 = repo.load_results("tenant_poc", "dt_poc_001", cursor=page_1["page"]["next_cursor"], limit=2)

    assert len(page_1["assets"]) == 2
    assert page_1["page"] == {"next_cursor": "2", "limit": 2, "type": "assets"}
    assert page_2["assets"][0]["asset_id"] != page_1["assets"][0]["asset_id"]
    assert "report" not in page_1


def test_file_scope_profile_repository_loads_active_profile(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "tenant_poc.scope_profile_001.json").write_text(
        json.dumps(
            {
                "tenant_id": "tenant_poc",
                "profile_id": "scope_profile_001",
                "status": "active",
                "allowed_root_domains": ["example.org"],
                "allowed_domains": ["vpn.example.org"],
                "allowed_ip_cidrs": ["203.0.113.0/24"],
                "allowed_org_names": ["Example Organization"],
                "default_scope": {"root_domains": ["example.org"]},
                "allowed_engines": ["fofa"],
                "provider_profile_id": "provider_fofa_poc",
                "limits": {"max_results_per_task": 100, "max_queries_per_task": 10},
                "created_by": "security_operator_hash",
                "authorization_note": "Confirmed by customer interview.",
            }
        ),
        encoding="utf-8",
    )

    repo = FileScopeProfileRepository(profile_dir)
    profile = repo.load_active("tenant_poc", "scope_profile_001")

    assert profile.tenant_id == "tenant_poc"
    assert profile.profile_id == "scope_profile_001"
    assert profile.allowed_engines == ["fofa"]
