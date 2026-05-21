from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value


@dataclass(frozen=True)
class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


class TaskStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DiscoverySeed(Serializable):
    seed_id: str
    type: str
    value: str
    label: str | None = None
    authorization_note: str | None = None


@dataclass(frozen=True)
class SourceQueryPlan(Serializable):
    plan_id: str
    task_id: str
    source: str
    seed_id: str
    source_query: str
    query_type: str
    page_limit: int = 10
    result_limit: int = 1000
    stage: str = "seed"
    query_intent: str | None = None
    derived_from: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QuotaUsage(Serializable):
    planned_queries: int
    completed_queries: int = 0
    failed_queries: int = 0
    planned_pages: int = 0
    consumed_pages: int = 0
    result_count: int = 0


@dataclass(frozen=True)
class TaskError(Serializable):
    source: str
    query_type: str
    source_query: str
    message: str
    recoverable: bool = True
    code: str | None = None


@dataclass(frozen=True)
class TaskEnvelope(Serializable):
    task_id: str
    tenant_id: str
    mode: str
    status: TaskStatus
    quota_usage: QuotaUsage
    errors: list[TaskError] = field(default_factory=list)


@dataclass(frozen=True)
class SourceEvidence(Serializable):
    evidence_id: str
    task_id: str
    source: str
    source_query: str
    raw_reference: str
    first_seen: str
    last_seen: str
    confidence: float
    evidence: dict[str, Any]
    normalized_fields: list[str]


@dataclass(frozen=True)
class DiscoveredAsset(Serializable):
    asset_id: str
    task_id: str
    asset_type: str
    domain: str | None = None
    ip: str | None = None
    root_domain: str | None = None
    asn: str | None = None
    country_or_region: str | None = None
    ownership_confidence: float = 0.5
    first_seen: str | None = None
    last_seen: str | None = None
    sources: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExposedService(Serializable):
    service_id: str
    asset_id: str
    task_id: str
    ip: str | None
    domain: str | None
    port: int
    protocol: str
    service: str
    title: str | None = None
    product: str | None = None
    version: str | None = None
    url: str | None = None
    banner_hash: str | None = None
    tls: dict[str, Any] | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    freshness: dict[str, Any] | None = None
    sources: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskHint(Serializable):
    risk_hint_id: str
    task_id: str
    asset_id: str
    service_id: str
    category: str
    severity: str
    title: str
    manager_summary: str
    technical_evidence: list[str]
    recommended_action: str
    confidence: float
    verification_required: bool = True


@dataclass(frozen=True)
class ExposureReport(Serializable):
    report_id: str
    task_id: str
    tenant_id: str
    report_type: str
    generated_at: str
    executive_summary: dict[str, Any]
    sections: list[dict[str, Any]]
    appendix_refs: list[str]
