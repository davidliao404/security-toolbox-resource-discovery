from resource_discovery.models import ExposedService
from resource_discovery.risk_hints import generate_risk_hints


def _service(port: int, service: str, title: str = "") -> ExposedService:
    return ExposedService(
        service_id=f"svc_{port}",
        asset_id="asset_1",
        task_id="dt_001",
        ip="203.0.113.10",
        domain=f"{service}.example.org",
        port=port,
        protocol="https",
        service=service,
        title=title,
    )


def test_generates_passive_risk_hints_for_key_categories():
    services = [
        _service(443, "vpn", "VPN Portal"),
        _service(8443, "admin", "Admin Console"),
        _service(8080, "tomcat", "Staging Tomcat"),
        _service(3306, "mysql", "MySQL"),
    ]

    hints = generate_risk_hints("dt_001", services)
    categories = {hint.category for hint in hints}

    assert {"remote_access", "admin_portal", "test_environment", "database_exposure", "middleware_exposure"} <= categories
    assert all(hint.verification_required for hint in hints)
