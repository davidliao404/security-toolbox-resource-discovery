from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .freshness import build_freshness
from .models import DiscoveredAsset, ExposedService, SourceEvidence, SourceQueryPlan
from .ownership import score_ownership


DEFAULT_SEEN_AT = "2026-05-17T10:00:00+08:00"


@dataclass(frozen=True)
class NormalizedBatch:
    assets: list[DiscoveredAsset]
    services: list[ExposedService]
    evidences: list[SourceEvidence]


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def normalize_fofa_results(
    task_id: str,
    plan: SourceQueryPlan,
    rows: list[dict],
    authorized_scope: dict[str, list[str]] | None = None,
) -> NormalizedBatch:
    assets: list[DiscoveredAsset] = []
    services: list[ExposedService] = []
    evidences: list[SourceEvidence] = []

    for index, row in enumerate(rows, start=1):
        ip = row.get("ip")
        domain = row.get("host") or row.get("domain")
        port = int(row.get("port") or 0)
        protocol = (row.get("protocol") or "unknown").lower()
        service_name = (row.get("service") or row.get("product") or protocol or "unknown").lower()
        seen_at = row.get("last_seen") or row.get("lastupdatetime") or DEFAULT_SEEN_AT
        freshness = build_freshness(row.get("lastupdatetime") or row.get("last_seen"))

        asset_id = _stable_id("asset", task_id, domain or ip)
        service_id = _stable_id("svc", task_id, domain or ip, port, protocol, service_name)
        evidence_id = _stable_id("ev", task_id, plan.plan_id, index)

        normalized_field_names = [
            "ip",
            "host",
            "domain",
            "port",
            "protocol",
            "service",
            "title",
            "product",
            "version",
            "server",
            "url",
            "link",
            "asn",
            "org",
            "country",
            "country_name",
            "header_hash",
            "banner_hash",
            "cname",
            "lastupdatetime",
        ]
        normalized_fields = [
            field for field in normalized_field_names if row.get(field) not in (None, "")
        ]

        evidences.append(
            SourceEvidence(
                evidence_id=evidence_id,
                task_id=task_id,
                source=plan.source,
                source_query=plan.source_query,
                raw_reference=f"{plan.source}:fixture:{plan.plan_id}:{index}",
                first_seen=row.get("first_seen") or seen_at,
                last_seen=seen_at,
                confidence=float(row.get("confidence", 0.7)),
                evidence={
                    key: value
                    for key, value in {
                        "ip": ip,
                        "domain": domain,
                        "port": port,
                        "protocol": protocol,
                        "title": row.get("title"),
                        "product": row.get("product"),
                        "version": row.get("version"),
                        "server": row.get("server"),
                        "asn": row.get("asn"),
                        "org": row.get("org"),
                        "country": row.get("country"),
                        "country_name": row.get("country_name"),
                        "header_hash": row.get("header_hash"),
                        "banner_hash": row.get("banner_hash"),
                        "cname": row.get("cname"),
                        "freshness": freshness,
                    }.items()
                    if value not in (None, "")
                },
                normalized_fields=normalized_fields,
            )
        )

        assets.append(
            DiscoveredAsset(
                asset_id=asset_id,
                task_id=task_id,
                asset_type="domain" if domain else "ip",
                domain=domain,
                ip=ip,
                root_domain=row.get("root_domain"),
                asn=row.get("asn"),
                country_or_region=row.get("country_or_region")
                or row.get("country_name")
                or row.get("country"),
                ownership_confidence=score_ownership(row, authorized_scope)
                if authorized_scope is not None
                else float(row.get("confidence", 0.7)),
                first_seen=row.get("first_seen") or seen_at,
                last_seen=seen_at,
                sources=[plan.source],
                evidence_ids=[evidence_id],
            )
        )

        services.append(
            ExposedService(
                service_id=service_id,
                asset_id=asset_id,
                task_id=task_id,
                ip=ip,
                domain=domain,
                port=port,
                protocol=protocol,
                service=service_name,
                title=row.get("title"),
                product=row.get("product"),
                version=row.get("version"),
                url=row.get("url") or row.get("link"),
                banner_hash=row.get("banner_hash"),
                tls=row.get("tls"),
                first_seen=row.get("first_seen") or seen_at,
                last_seen=seen_at,
                freshness=freshness,
                sources=[plan.source],
                evidence_ids=[evidence_id],
            )
        )

    return NormalizedBatch(assets=assets, services=services, evidences=evidences)
