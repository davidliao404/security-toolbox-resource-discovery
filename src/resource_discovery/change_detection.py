from __future__ import annotations


def compare_snapshots(before: dict, after: dict) -> dict:
    before_assets = _by_id(before.get("assets", []), "asset_id")
    after_assets = _by_id(after.get("assets", []), "asset_id")
    before_services = _by_id(before.get("services", []), "service_id")
    after_services = _by_id(after.get("services", []), "service_id")
    return {
        "new_assets": _sorted_values(after_assets, set(after_assets) - set(before_assets)),
        "removed_assets": _sorted_values(before_assets, set(before_assets) - set(after_assets)),
        "new_services": _sorted_values(after_services, set(after_services) - set(before_services)),
        "removed_services": _sorted_values(
            before_services, set(before_services) - set(after_services)
        ),
    }


def _by_id(items: list[dict], key: str) -> dict[str, dict]:
    return {str(item[key]): item for item in items if item.get(key)}


def _sorted_values(items: dict[str, dict], ids: set[str]) -> list[dict]:
    return [items[item_id] for item_id in sorted(ids)]
