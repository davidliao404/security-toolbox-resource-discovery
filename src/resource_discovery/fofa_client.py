from __future__ import annotations

import base64
import json
from json import JSONDecodeError
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen


class FofaApiError(RuntimeError):
    """Raised when FOFA returns an API-level error."""

    def __init__(self, message: str, *, code: str = "provider_bad_response", recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


class FofaApiClient:
    def __init__(
        self,
        key: str,
        email: str | None = None,
        base_url: str = "https://fofa.info/api/v1/search/all",
        opener: Callable | None = None,
        timeout: int = 30,
        full: bool = False,
    ) -> None:
        if not key.strip():
            raise ValueError("FOFA key is required")
        self.email = email
        self.key = key
        self.base_url = base_url
        self.opener = opener or urlopen
        self.timeout = timeout
        self.full = full

    def build_search_url(
        self,
        source_query: str,
        fields: list[str],
        page: int = 1,
        size: int = 100,
    ) -> str:
        qbase64 = base64.b64encode(source_query.encode("utf-8")).decode("ascii")
        params = {
            "key": self.key,
            "qbase64": qbase64,
            "fields": ",".join(fields),
            "page": str(page),
            "size": str(size),
            "full": "true" if self.full else "false",
        }
        if self.email:
            params["email"] = self.email
        return f"{self.base_url}?{urlencode(params)}"

    def search(
        self,
        source_query: str,
        fields: list[str],
        page: int = 1,
        size: int = 100,
    ) -> list[dict]:
        url = self.build_search_url(source_query, fields=fields, page=page, size=size)
        try:
            with self.opener(url, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                raw_body = response.read().decode("utf-8")
        except TimeoutError as exc:
            raise FofaApiError(
                "FOFA provider request timed out",
                code="provider_timeout",
                recoverable=True,
            ) from exc
        try:
            payload = json.loads(raw_body)
        except (JSONDecodeError, UnicodeDecodeError):
            raise FofaApiError(
                "FOFA provider returned a malformed response",
                code="provider_bad_response",
                recoverable=True,
            ) from None
        if status == 429:
            raise FofaApiError(
                payload.get("errmsg") or "FOFA provider rate limit exceeded",
                code="provider_rate_limited",
                recoverable=True,
            )
        if payload.get("error"):
            message = payload.get("errmsg") or "FOFA API returned an error"
            raise FofaApiError(
                message,
                code=_classify_provider_error(message),
                recoverable=True,
            )
        return [dict(zip(fields, row)) for row in payload.get("results", [])]


def _classify_provider_error(message: str) -> str:
    normalized = message.lower()
    if "rate" in normalized and "limit" in normalized:
        return "provider_rate_limited"
    if "auth" in normalized or "key" in normalized or "unauthorized" in normalized:
        return "provider_auth_failed"
    return "provider_bad_response"
