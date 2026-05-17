from resource_discovery.cli import run_fixture_demo


def test_cli_fixture_demo_returns_report_payload():
    payload = run_fixture_demo("examples/seeds.json", "tests/fixtures/fofa_results.json")

    assert payload["report"]["report_type"] == "manager_summary"
    assert payload["assets"]
    assert payload["services"]
    assert payload["risk_hints"]
    assert payload["source_evidence"]
