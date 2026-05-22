from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewaySettings:
    env: str = "local"
    api_prefix: str = "/api/v1/discovery"
    sqlite_path: str = "artifacts/integration/resource-discovery.sqlite3"
    queue_backend: str = "sqlite"
    redis_url: str = "redis://localhost:6379/0"
    client_secrets_file: str = "config/client-secrets.json"
    scope_profile_seed: str = "examples/scope_profile.json"
    fixture_path: str = "tests/fixtures/fofa_results.json"
    result_limit_default: int = 100
    result_limit_max: int = 500
    nonce_window_seconds: int = 300
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.queue_backend not in {"memory", "sqlite", "redis"}:
            raise ValueError(f"Unsupported queue backend: {self.queue_backend}")
        if self.result_limit_default < 1:
            raise ValueError("RESOURCE_DISCOVERY_RESULT_LIMIT_DEFAULT must be positive")
        if self.result_limit_max < self.result_limit_default:
            raise ValueError("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX must be >= default")
        if self.nonce_window_seconds < 1:
            raise ValueError("RESOURCE_DISCOVERY_NONCE_WINDOW_SECONDS must be positive")


def load_settings() -> GatewaySettings:
    return GatewaySettings(
        env=os.getenv("RESOURCE_DISCOVERY_ENV", "local"),
        api_prefix=os.getenv("RESOURCE_DISCOVERY_API_PREFIX", "/api/v1/discovery"),
        sqlite_path=os.getenv(
            "RESOURCE_DISCOVERY_SQLITE_PATH",
            "artifacts/integration/resource-discovery.sqlite3",
        ),
        queue_backend=os.getenv("RESOURCE_DISCOVERY_QUEUE_BACKEND", "sqlite"),
        redis_url=os.getenv("RESOURCE_DISCOVERY_REDIS_URL", "redis://localhost:6379/0"),
        client_secrets_file=os.getenv(
            "RESOURCE_DISCOVERY_CLIENT_SECRETS_FILE",
            "config/client-secrets.json",
        ),
        scope_profile_seed=os.getenv("RESOURCE_DISCOVERY_SCOPE_PROFILE_SEED", "examples/scope_profile.json"),
        fixture_path=os.getenv("RESOURCE_DISCOVERY_FIXTURE_PATH", "tests/fixtures/fofa_results.json"),
        result_limit_default=int(os.getenv("RESOURCE_DISCOVERY_RESULT_LIMIT_DEFAULT", "100")),
        result_limit_max=int(os.getenv("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX", "500")),
        nonce_window_seconds=int(os.getenv("RESOURCE_DISCOVERY_NONCE_WINDOW_SECONDS", "300")),
        log_level=os.getenv("RESOURCE_DISCOVERY_LOG_LEVEL", "INFO"),
    )
