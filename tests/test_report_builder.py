from resource_discovery.models import DiscoveredAsset, ExposedService, RiskHint
from resource_discovery.report_builder import build_exposure_report


def test_builds_manager_summary_report():
    assets = [DiscoveredAsset(asset_id="asset_1", task_id="dt_001", asset_type="domain", domain="vpn.example.org")]
    services = [
        ExposedService(
            service_id="svc_1",
            asset_id="asset_1",
            task_id="dt_001",
            ip="203.0.113.10",
            domain="vpn.example.org",
            port=443,
            protocol="https",
            service="vpn",
        )
    ]
    risks = [
        RiskHint(
            risk_hint_id="risk_1",
            task_id="dt_001",
            asset_id="asset_1",
            service_id="svc_1",
            category="remote_access",
            severity="high",
            title="发现疑似互联网暴露的远程访问入口",
            manager_summary="需要复核。",
            technical_evidence=["port: 443"],
            recommended_action="确认访问控制。",
            confidence=0.78,
        )
    ]

    report = build_exposure_report("dt_001", "tenant_001", assets, services, risks)

    assert report.report_type == "manager_summary"
    assert report.executive_summary["asset_count"] == 1
    assert report.executive_summary["high_risk_hint_count"] == 1
    assert "被动发现" in report.executive_summary["summary_text"]
    assert "asset_list" in report.appendix_refs
