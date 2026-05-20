from resource_discovery.execution import run_discovery
from resource_discovery.repositories import FileResultRepository


def _payload():
    return run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )


def test_file_result_repository_paginates_services_by_type(tmp_path):
    repo = FileResultRepository(tmp_path / "results")
    repo.save_results("tenant_poc", "dt_poc_001", _payload())

    page = repo.load_results(
        "tenant_poc",
        "dt_poc_001",
        cursor=None,
        limit=2,
        result_type="services",
    )

    assert page["assets"] == []
    assert len(page["services"]) == 2
    assert page["source_evidence"] == []
    assert page["page"] == {"next_cursor": "2", "limit": 2, "type": "services"}


def test_file_result_repository_paginates_evidence_by_type(tmp_path):
    repo = FileResultRepository(tmp_path / "results")
    repo.save_results("tenant_poc", "dt_poc_001", _payload())

    page = repo.load_results(
        "tenant_poc",
        "dt_poc_001",
        cursor="2",
        limit=2,
        result_type="source_evidence",
    )

    assert page["assets"] == []
    assert page["services"] == []
    assert len(page["source_evidence"]) == 2
    assert page["page"]["type"] == "source_evidence"


def test_file_result_repository_rejects_unknown_result_type(tmp_path):
    repo = FileResultRepository(tmp_path / "results")
    repo.save_results("tenant_poc", "dt_poc_001", _payload())

    try:
        repo.load_results("tenant_poc", "dt_poc_001", cursor=None, limit=2, result_type="bad")
    except ValueError as exc:
        assert "result_type" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid result_type")
