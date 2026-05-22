from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .auth_http import ClientSecretResolver, FileClientSecretResolver, authenticate_http_request
from .config import GatewaySettings, load_settings
from .gateway_api import DiscoveryGatewayApi
from .queue_backends import SQLiteTaskQueue
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
) -> FastAPI:
    initialize_sqlite(sqlite_path)
    app = FastAPI(title="Resource Discovery Gateway", version="0.1.0")
    task_repository = SQLiteTaskRepository(sqlite_path)
    result_repository = SQLiteResultRepository(sqlite_path)
    queue = SQLiteTaskQueue(sqlite_path)
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

    async def require_auth(request: Request) -> dict[str, str] | JSONResponse:
        body = await request.body()
        try:
            return authenticate_http_request(
                method=request.method,
                path=request.url.path,
                body=body,
                headers=request.headers,
                resolver=resolver,
                nonce_store=nonce_store,
                now=clock(),
            )
        except AuthError as exc:
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
        return {"status": "ok", "storage": "sqlite", "queue": "sqlite"}

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
        return gateway_api.create_task(await request.json())

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
    return create_app(
        sqlite_path=resolved.sqlite_path,
        client_secret_resolver=FileClientSecretResolver(resolved.client_secrets_file),
        nonce_store=SQLiteNonceRepository(resolved.sqlite_path, window_seconds=resolved.nonce_window_seconds),
        now=now,
        profile=_load_profile(resolved.scope_profile_seed),
        source_client=FixtureSourceClient(Path(resolved.fixture_path)),
    )


app = create_app_from_settings()