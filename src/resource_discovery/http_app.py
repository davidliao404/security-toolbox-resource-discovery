from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .auth_http import ClientSecretResolver, FileClientSecretResolver, authenticate_http_request
from .backend_factory import build_queue, build_repositories
from .config import GatewaySettings, load_settings
from .gateway_api import DiscoveryGatewayApi
from .logging_config import configure_logging
from .metrics import GatewayMetrics
from .queue_backends import SQLiteTaskQueue
from .quota import QuotaExceeded, TenantQuotaPolicy, check_task_quota
from .request_auth import AuthError, InMemoryNonceStore, NonceStore
from .scope_guard import TenantScopeProfile
from .source_client import FixtureSourceClient, SourceClient
from .sqlite_store import SQLiteNonceRepository, SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite


def _default_profile() -> TenantScopeProfile:
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        status="active",
        allowed_root_domains=["example.com"],
        allowed_domains=["vpn.example.com"],
        allowed_ip_cidrs=["203.0.113.0/24"],
        allowed_org_names=["Example Limited"],
        allowed_engines=["fofa"],
        default_scope={"root_domains": ["example.com"]},
        limits={"max_results_per_task": 200, "max_queries_per_task": 10},
        authorization_note="Customer approval for integration fixture scope.",
    )


class DictSecretResolver:
    def __init__(self, secrets: dict[str, dict[str, str]]) -> None:
        self.secrets = secrets

    def resolve(self, tenant_id: str, client_id: str) -> str:
        try:
            return self.secrets[tenant_id][client_id]
        except KeyError:
            raise AuthError("Unknown client credentials", code="unknown_client") from None


def _load_profile(path: str | Path) -> TenantScopeProfile:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return TenantScopeProfile(**payload)


def create_app(
    *,
    sqlite_path: str | Path,
    client_secrets: dict[str, dict[str, str]] | None = None,
    client_secret_resolver: ClientSecretResolver | None = None,
    nonce_store: NonceStore | None = None,
    now: Callable[[], datetime] | None = None,
    profile: TenantScopeProfile | None = None,
    source_client: SourceClient | None = None,
    task_repository: Any | None = None,
    result_repository: Any | None = None,
    queue: Any | None = None,
    storage_backend: str = "sqlite",
    queue_backend: str = "sqlite",
    metrics_enabled: bool = False,
    log_format: str = "text",
    log_level: str = "INFO",
    quota_policy: TenantQuotaPolicy | None = None,
    quota_usage: dict[str, int] | None = None,
) -> FastAPI:
    if task_repository is None or result_repository is None or queue is None:
        initialize_sqlite(sqlite_path)
        task_repository = task_repository or SQLiteTaskRepository(sqlite_path)
        result_repository = result_repository or SQLiteResultRepository(sqlite_path)
        queue = queue or SQLiteTaskQueue(sqlite_path)
    configure_logging(log_format=log_format, level=log_level)
    app = FastAPI(title="Resource Discovery Gateway", version="0.1.0")
    metrics = GatewayMetrics()
    gateway_api = DiscoveryGatewayApi(
        profile=profile or _default_profile(),
        source_client=source_client or FixtureSourceClient(Path("tests/fixtures/fofa_results.json")),
        task_repository=task_repository,
        result_repository=result_repository,
        queue=queue,
    )
    resolver = client_secret_resolver or DictSecretResolver(client_secrets or {})
    nonce_store = nonce_store or InMemoryNonceStore()
    clock = now or (lambda: datetime.now(timezone.utc))
    app.state.gateway_api = gateway_api
    app.state.queue = queue
    app.state.task_repository = task_repository
    app.state.result_repository = result_repository
    app.state.storage_backend = storage_backend
    app.state.queue_backend = queue_backend
    app.state.metrics = metrics
    app.state.quota_policy = quota_policy

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        metrics.requests.labels(request.method, request.url.path, str(response.status_code)).inc()
        metrics.request_seconds.labels(request.method, request.url.path).observe(time.perf_counter() - started)
        return response

    async def require_auth(request: Request) -> dict[str, str] | JSONResponse:
        body = await request.body()
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        try:
            auth = authenticate_http_request(
                method=request.method,
                path=path,
                body=body,
                headers=request.headers,
                resolver=resolver,
                nonce_store=nonce_store,
                now=clock(),
            )
            if auth["tenant_id"] != gateway_api.profile.tenant_id:
                return JSONResponse(
                    status_code=403,
                    content={
                        "status": "rejected",
                        "errors": [
                            {
                                "code": "tenant_mismatch",
                                "message": "Authenticated tenant does not match the active scope profile.",
                                "recoverable": False,
                                "details": {},
                            }
                        ],
                    },
                )
            return auth
        except AuthError as exc:
            metrics.auth_failures.labels(exc.code).inc()
            return JSONResponse(
                status_code=401,
                content={
                    "status": "rejected",
                    "errors": [
                        {
                            "code": exc.code,
                            "message": str(exc),
                            "recoverable": False,
                            "details": {},
                        }
                    ],
                },
            )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "resource-discovery-gateway"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ok", "storage": storage_backend, "queue": queue_backend}

    if metrics_enabled:
        @app.get("/metrics")
        def metrics_endpoint() -> Response:
            return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")

    @app.get("/api/v1/discovery/scope-profile")
    async def get_scope_profile(request: Request) -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        return gateway_api.get_scope_profile()

    @app.post("/api/v1/discovery/tasks")
    async def create_task(request: Request) -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        payload = await request.json()
        if quota_policy is not None:
            usage = quota_usage or {}
            try:
                check_task_quota(
                    tenant_id=auth["tenant_id"],
                    policy=quota_policy,
                    current_daily_tasks=int(usage.get("current_daily_tasks", 0)),
                    current_daily_provider_queries=int(usage.get("current_daily_provider_queries", 0)),
                    current_running_tasks=int(usage.get("current_running_tasks", 0)),
                    planned_provider_queries=max(1, len(payload.get("engines") or ["fofa"])),
                    now=clock(),
                )
            except QuotaExceeded as exc:
                metrics.quota_rejections.labels(exc.code).inc()
                return JSONResponse(
                    status_code=429,
                    content={
                        "status": "rejected",
                        "errors": [
                            {
                                "code": exc.code,
                                "message": str(exc),
                                "recoverable": True,
                                "details": {},
                            }
                        ],
                    },
                )
        result = gateway_api.create_task(payload)
        if result.get("status") == "queued":
            metrics.tasks_created.labels(auth["tenant_id"]).inc()
        return result

    @app.get("/api/v1/discovery/tasks/{task_id}")
    async def get_task(task_id: str, request: Request) -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        return gateway_api.get_task(task_id)

    @app.get("/api/v1/discovery/tasks/{task_id}/results")
    async def get_results(
        task_id: str,
        request: Request,
        cursor: str | None = None,
        limit: int = 100,
        result_type: str = "assets",
    ) -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        return gateway_api.get_results(task_id, cursor=cursor, limit=limit, result_type=result_type)

    return app


def create_app_from_settings(
    settings: GatewaySettings | None = None,
    *,
    now: Callable[[], datetime] | None = None,
) -> FastAPI:
    resolved = settings or load_settings()
    repositories = build_repositories(resolved)
    queue = build_queue(resolved)
    return create_app(
        sqlite_path=resolved.sqlite_path,
        client_secret_resolver=FileClientSecretResolver(resolved.client_secrets_file),
        nonce_store=repositories.nonce_store,
        now=now,
        profile=_load_profile(resolved.scope_profile_seed),
        source_client=FixtureSourceClient(Path(resolved.fixture_path)),
        task_repository=repositories.task_repository,
        result_repository=repositories.result_repository,
        queue=queue,
        storage_backend=resolved.storage_backend,
        queue_backend=resolved.queue_backend,
        metrics_enabled=resolved.metrics_enabled,
        log_format=resolved.log_format,
        log_level=resolved.log_level,
    )


app = create_app_from_settings()
