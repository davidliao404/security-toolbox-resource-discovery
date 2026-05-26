from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest


class GatewayMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "resource_discovery_requests_total",
            "Total resource discovery HTTP requests.",
            ["method", "path", "status"],
            registry=self.registry,
        )
        self.auth_failures = Counter(
            "resource_discovery_auth_failures_total",
            "Total authentication failures.",
            ["code"],
            registry=self.registry,
        )
        self.tasks_created = Counter(
            "resource_discovery_tasks_created_total",
            "Total discovery tasks created.",
            ["tenant"],
            registry=self.registry,
        )
        self.tasks_completed = Counter(
            "resource_discovery_tasks_completed_total",
            "Total discovery tasks completed.",
            ["status"],
            registry=self.registry,
        )
        self.provider_errors = Counter(
            "resource_discovery_provider_errors_total",
            "Total provider errors.",
            ["provider", "code"],
            registry=self.registry,
        )
        self.dead_letters = Counter(
            "resource_discovery_dead_letters_total",
            "Total dead-lettered tasks.",
            ["queue"],
            registry=self.registry,
        )
        self.quota_rejections = Counter(
            "resource_discovery_quota_rejections_total",
            "Total quota rejected requests.",
            ["code"],
            registry=self.registry,
        )
        self.request_seconds = Histogram(
            "resource_discovery_request_seconds",
            "Resource discovery HTTP request latency.",
            ["method", "path"],
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)
