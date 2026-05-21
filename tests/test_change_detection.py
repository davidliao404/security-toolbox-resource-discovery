from resource_discovery.change_detection import compare_snapshots


def test_detects_new_asset_and_service_between_snapshots():
    before = {"assets": [], "services": []}
    after = {
        "assets": [{"asset_id": "asset_1", "domain": "vpn.example.org"}],
        "services": [{"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}],
    }

    summary = compare_snapshots(before, after)

    assert summary["new_assets"] == [{"asset_id": "asset_1", "domain": "vpn.example.org"}]
    assert summary["new_services"] == [
        {"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}
    ]


def test_detects_removed_service():
    before = {
        "assets": [{"asset_id": "asset_1", "domain": "vpn.example.org"}],
        "services": [{"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}],
    }
    after = {"assets": [{"asset_id": "asset_1", "domain": "vpn.example.org"}], "services": []}

    summary = compare_snapshots(before, after)

    assert summary["removed_services"] == [
        {"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}
    ]
