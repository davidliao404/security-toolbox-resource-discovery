import json

from resource_discovery.cli import list_snapshots, load_snapshot, run_and_maybe_save


def test_run_and_maybe_save_persists_snapshot(tmp_path):
    payload = run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        save_dir=tmp_path,
    )

    assert payload["saved_snapshot_path"].endswith("tenant_poc/dt_poc_001.json")
    loaded = json.loads((tmp_path / "tenant_poc" / "dt_poc_001.json").read_text(encoding="utf-8"))
    assert loaded["task"]["status"] == "success"


def test_list_and_load_snapshot_helpers(tmp_path):
    run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        save_dir=tmp_path,
    )

    summaries = list_snapshots(tmp_path, "tenant_poc")
    loaded = load_snapshot(tmp_path, "tenant_poc", "dt_poc_001")

    assert summaries[0]["task_id"] == "dt_poc_001"
    assert loaded["task"]["task_id"] == "dt_poc_001"
