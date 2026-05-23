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
        self.request_seconds = Histogram(
            "resource_discovery_request_seconds",
            "Resource discovery HTTP request latency.",
            ["method", "path"],
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)
