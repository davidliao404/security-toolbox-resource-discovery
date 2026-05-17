from __future__ import annotations

from dataclasses import replace

from .models import DiscoveredAsset, ExposedService


def _merge_unique(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


def deduplicate_assets(assets: list[DiscoveredAsset]) -> list[DiscoveredAsset]:
    merged: dict[str, DiscoveredAsset] = {}
    for asset in assets:
        key = asset.domain or asset.ip or asset.asset_id
        current = merged.get(key)
        if current is None:
            merged[key] = asset
            continue
        merged[key] = replace(
            current,
            sources=_merge_unique(current.sources, asset.sources),
            evidence_ids=_merge_unique(current.evidence_ids, asset.evidence_ids),
            ownership_confidence=max(current.ownership_confidence, asset.ownership_confidence),
            last_seen=max(current.last_seen or "", asset.last_seen or "") or current.last_seen,
        )
    return list(merged.values())


def service_dedupe_key(service: ExposedService) -> str:
    domain_or_ip = service.domain or service.ip or "unknown"
    return f"{domain_or_ip}|{service.port}|{service.protocol}|{service.service}"


def deduplicate_services(services: list[ExposedService]) -> list[ExposedService]:
    merged: dict[str, ExposedService] = {}
    for service in services:
        key = service_dedupe_key(service)
        current = merged.get(key)
        if current is None:
            merged[key] = service
            continue
        merged[key] = replace(
            current,
            sources=_merge_unique(current.sources, service.sources),
            evidence_ids=_merge_unique(current.evidence_ids, service.evidence_ids),
            title=current.title or service.title,
            product=current.product or service.product,
            version=current.version or service.version,
            last_seen=max(current.last_seen or "", service.last_seen or "") or current.last_seen,
        )
    return list(merged.values())
