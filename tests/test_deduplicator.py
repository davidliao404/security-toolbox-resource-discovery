from dataclasses import replace

from resource_discovery.deduplicator import deduplicate_services
from resource_discovery.models import ExposedService


def test_deduplicates_services_and_merges_evidence_ids():
    service = ExposedService(
        service_id="svc_1",
        asset_id="asset_1",
        task_id="dt_001",
        ip="203.0.113.10",
        domain="vpn.example.org",
        port=443,
        protocol="https",
        service="vpn",
        sources=["fofa"],
        evidence_ids=["ev_1"],
    )
    duplicate = replace(service, service_id="svc_2", evidence_ids=["ev_2"])

    deduped = deduplicate_services([service, duplicate])

    assert len(deduped) == 1
    assert deduped[0].evidence_ids == ["ev_1", "ev_2"]
