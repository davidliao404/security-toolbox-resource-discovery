from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping
from urllib.parse import parse_qs, urlparse

from .gateway_api import DiscoveryGatewayApi
from .request_auth import AuthError, NonceStore, verify_signature


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    json: dict


class GatewayHttpHandler:
    def __init__(
        self,
        api: DiscoveryGatewayApi,
        client_secrets: Mapping[str, str],
        nonce_store: NonceStore,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.api = api
        self.client_secrets = client_secrets
        self.nonce_store = nonce_store
        self.now = now

    def handle(self, method: str, path: str, headers: Mapping[str, str], body: bytes) -> HttpResponse:
        try:
            self._verify(method, path, headers, body)
            return self._route(method.upper(), path, body)
        except AuthError as exc:
            return _error_response(401, exc.code, str(exc), recoverable=False)
        except ValueError as exc:
            return _error_response(400, "bad_request", str(exc), recoverable=False)
        except Exception:
            return _error_response(500, "internal_error", "Gateway request failed", recoverable=True)

    def _verify(self, method: str, path: str, headers: Mapping[str, str], body: bytes) -> None:
        client_id = headers.get("X-Client-Id")
        if not client_id or client_id not in self.client_secrets:
            raise AuthError("Unknown client", code="unknown_client")
        verify_signature(
            secret=self.client_secrets[client_id],
            method=method,
            path=path,
            timestamp=_required_header(headers, "X-Timestamp"),
            nonce=_required_header(headers, "X-Nonce"),
            body=body,
            signature=_required_header(headers, "X-Signature"),
            now=self.now() if self.now else None,
            nonce_store=self.nonce_store,
        )

    def _route(self, method: str, path: str, body: bytes) -> HttpResponse:
        parsed = urlparse(path)
        route = parsed.path
        if method == "GET" and route == "/api/v1/discovery/scope-profile":
            return HttpResponse(200, self.api.get_scope_profile())
        if method == "POST" and route == "/api/v1/discovery/tasks":
            payload = json.loads(body.decode("utf-8") or "{}")
            response = self.api.create_task(payload)
            return HttpResponse(202 if response.get("status") == "queued" else 400, response)
        if method == "GET" and route.startswith("/api/v1/discovery/tasks/"):
            parts = route.removeprefix("/api/v1/discovery/tasks/").split("/")
            task_id = parts[0]
            if len(parts) == 1:
                return HttpResponse(200, self.api.get_task(task_id))
            if len(parts) == 2 and parts[1] == "results":
                query = parse_qs(parsed.query)
                return HttpResponse(
                    200,
                    self.api.get_results(
                        task_id,
                        cursor=_first(query, "cursor"),
                        limit=int(_first(query, "limit") or 100),
                        result_type=_first(query, "result_type") or "assets",
                    ),
                )
        return _error_response(404, "not_found", "Route not found", recoverable=False)


def _required_header(headers: Mapping[str, str], name: str) -> str:
    value = headers.get(name)
    if not value:
        raise AuthError(f"Missing required header: {name}", code="missing_auth_header")
    return value


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _error_response(status_code: int, code: str, message: str, recoverable: bool) -> HttpResponse:
    return HttpResponse(
        status_code,
        {
            "errors": [
                {
                    "code": code,
                    "message": message,
                    "recoverable": recoverable,
                    "details": {},
                }
            ]
        },
    )
