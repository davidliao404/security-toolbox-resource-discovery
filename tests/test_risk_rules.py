from resource_discovery.models import ExposedService
from resource_discovery.risk_hints import generate_risk_hints
from resource_discovery.risk_rules import load_risk_rules


def test_loads_default_risk_rules_from_yaml():
    ruleset = load_risk_rules()

    categories = [rule.category for rule in ruleset.rules]

    assert categories == [
        "remote_access",
        "admin_portal",
        "test_environment",
        "database_exposure",
        "middleware_exposure",
    ]
    assert ruleset.default_confidence == 0.78
    assert ruleset.rules[0].match.ports == [22, 3389, 5900, 8443]
    assert "vpn" in ruleset.rules[0].match.keywords


def test_generate_risk_hints_uses_yaml_rule_metadata():
    service = ExposedService(
        service_id="svc_1",
        asset_id="asset_1",
        task_id="dt_001",
        ip="203.0.113.10",
        domain="db.example.org",
        port=3306,
        protocol="mysql",
        service="mysql",
        title="MySQL",
    )

    hints = generate_risk_hints("dt_001", [service])

    assert len(hints) == 1
    assert hints[0].category == "database_exposure"
    assert hints[0].severity == "high"
    assert hints[0].title == "发现疑似数据库或检索服务暴露"
    assert hints[0].confidence == 0.78
