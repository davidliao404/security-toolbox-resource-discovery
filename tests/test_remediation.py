from resource_discovery.execution import run_discovery
from resource_discovery.remediation import build_remediation_plan


def test_build_remediation_plan_orders_high_priority_actions_first():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )

    plan = build_remediation_plan(payload["risk_hints"])

    assert plan["summary"]["total_actions"] == 6
    assert plan["actions"][0]["priority"] == 1
    assert plan["actions"][0]["severity"] == "high"
    assert plan["actions"][0]["category"] in {"database_exposure", "admin_portal", "remote_access"}
    assert plan["actions"][0]["owner_hint"] == "IT 管理员"
    assert plan["actions"][0]["verification_required"] is True


def test_execution_payload_includes_remediation_plan():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )

    remediation = payload["remediation"]

    assert remediation["summary"]["high_priority_actions"] == 4
    assert remediation["actions"]
    assert remediation["actions"][0]["recommended_action"]
