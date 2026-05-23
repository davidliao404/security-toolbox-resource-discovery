from __future__ import annotations

from dataclasses import dataclass

from .config import GatewaySettings
from .postgres_store import (
    PostgresNonceRepository,
    PostgresResultRepository,
    PostgresTaskRepository,
    create_postgres_engine,
)
from .queue_backends import SQLiteTaskQueue
from .redis_queue import RedisTaskQueue
from .repositories import ResultRepository, TaskRepository
from .request_auth import NonceStore
from .sqlite_store import SQLiteNonceRepository, SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from .task_queue import InMemoryTaskQueue


@dataclass(frozen=True)
class RepositoryBundle:
    task_repository: TaskRepository
    result_repository: ResultRepository
    nonce_store: NonceStore
    storage_backend: str


def build_repositories(settings: GatewaySettings) -> RepositoryBundle:
    if settings.storage_backend == "sqlite":
        initialize_sqlite(settings.sqlite_path)
        return RepositoryBundle(
            task_repository=SQLiteTaskRepository(settings.sqlite_path),
            result_repository=SQLiteResultRepository(settings.sqlite_path, max_page_limit=settings.result_limit_max),
            nonce_store=SQLiteNonceRepository(settings.sqlite_path, window_seconds=settings.nonce_window_seconds),
            storage_backend="sqlite",
        )
    if not settings.database_url:
        raise ValueError("RESOURCE_DISCOVERY_DATABASE_URL is required for postgres storage")
    engine = create_postgres_engine(settings.database_url)
    return RepositoryBundle(
        task_repository=PostgresTaskRepository(engine),
        result_repository=PostgresResultRepository(engine, max_page_limit=settings.result_limit_max),
        nonce_store=PostgresNonceRepository(engine, window_seconds=settings.nonce_window_seconds),
        storage_backend="postgres",
    )


def build_queue(settings: GatewaySettings):
    if settings.queue_backend == "memory":
        return InMemoryTaskQueue()
    if settings.queue_backend == "sqlite":
        initialize_sqlite(settings.sqlite_path)
        return SQLiteTaskQueue(settings.sqlite_path)
    if settings.queue_backend == "redis":
        if not settings.redis_url:
            raise ValueError("RESOURCE_DISCOVERY_REDIS_URL is required for redis queue")
        return RedisTaskQueue(settings.redis_url)
    raise ValueError(f"Unsupported queue backend: {settings.queue_backend}")
