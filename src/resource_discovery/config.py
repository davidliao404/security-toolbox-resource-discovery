from __future__ import annotations

import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class GatewaySettings:
    env: str = "local"
    api_prefix: str = "/api/v1/discovery"
    storage_backend: str = "sqlite"
    database_url: str = ""
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
    worker_max_attempts: int = 3
    worker_retry_delay_seconds: int = 30
    dead_letter_enabled: bool = True
    metrics_enabled: bool = False
    log_format: str = "text"

    def __post_init__(self) -> None:
        if self.storage_backend not in {"sqlite", "postgres"}:
            raise ValueError(f"Unsupported storage backend: {self.storage_backend}")
        if self.queue_backend not in {"memory", "sqlite", "redis"}:
            raise ValueError(f"Unsupported queue backend: {self.queue_backend}")
        if self.result_limit_default < 1:
            raise ValueError("RESOURCE_DISCOVERY_RESULT_LIMIT_DEFAULT must be positive")
        if self.result_limit_max < self.result_limit_default:
            raise ValueError("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX must be >= default")
        if self.nonce_window_seconds < 1:
            raise ValueError("RESOURCE_DISCOVERY_NONCE_WINDOW_SECONDS must be positive")
        if self.worker_max_attempts < 1:
            raise ValueError("RESOURCE_DISCOVERY_WORKER_MAX_ATTEMPTS must be positive")
        if self.worker_retry_delay_seconds < 0:
            raise ValueError("RESOURCE_DISCOVERY_WORKER_RETRY_DELAY_SECONDS must be non-negative")
        if self.log_format not in {"text", "json"}:
            raise ValueError(f"Unsupported log format: {self.log_format}")


def load_settings() -> GatewaySettings:
    return GatewaySettings(
        env=os.getenv("RESOURCE_DISCOVERY_ENV", "local"),
        api_prefix=os.getenv("RESOURCE_DISCOVERY_API_PREFIX", "/api/v1/discovery"),
        storage_backend=os.getenv("RESOURCE_DISCOVERY_STORAGE_BACKEND", "sqlite"),
        database_url=os.getenv("RESOURCE_DISCOVERY_DATABASE_URL", ""),
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
        worker_max_attempts=int(os.getenv("RESOURCE_DISCOVERY_WORKER_MAX_ATTEMPTS", "3")),
        worker_retry_delay_seconds=int(os.getenv("RESOURCE_DISCOVERY_WORKER_RETRY_DELAY_SECONDS", "30")),
        dead_letter_enabled=_bool_env("RESOURCE_DISCOVERY_DEAD_LETTER_ENABLED", True),
        metrics_enabled=_bool_env("RESOURCE_DISCOVERY_METRICS_ENABLED", False),
        log_format=os.getenv("RESOURCE_DISCOVERY_LOG_FORMAT", "text"),
    )
