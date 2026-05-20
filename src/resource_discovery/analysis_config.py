from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AnalysisConfigError(ValueError):
    """Raised when tenant analysis configuration is invalid or unsafe."""


@dataclass(frozen=True)
class TenantAnalysisConfig:
    tenant_id: str
    llm_enabled: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    web_search_enabled: bool = False
    data_sharing_level: str = "none"
    authorization_id: str | None = None
    authorized_at: str | None = None
    authorized_by: str | None = None
    revoked_at: str | None = None

    def resolve_options(self, tenant_id: str) -> dict[str, Any]:
        if self.tenant_id != tenant_id:
            raise AnalysisConfigError(
                f"tenant_id mismatch: config is {self.tenant_id}, task is {tenant_id}"
            )
        if self.data_sharing_level not in {"none", "minimal"}:
            raise AnalysisConfigError("data_sharing_level must be one of: none, minimal")
        if not self.llm_enabled:
            return {
                "analysis_mode": "rules_only",
                "web_search_enabled": False,
                "data_sharing_level": "none",
                "llm_provider": None,
                "llm_model": None,
                "llm_authorization_id": None,
            }
        if self.data_sharing_level != "minimal":
            raise AnalysisConfigError("LLM analysis requires data_sharing_level=minimal")
        if not self.llm_provider or not self.llm_model:
            raise AnalysisConfigError("LLM analysis requires llm_provider and llm_model")
        self._validate_authorization()
        return {
            "analysis_mode": "rules_plus_llm",
            "web_search_enabled": bool(self.web_search_enabled),
            "data_sharing_level": self.data_sharing_level,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_authorization_id": self.authorization_id,
        }

    def _validate_authorization(self) -> None:
        if self.revoked_at:
            raise AnalysisConfigError("LLM authorization has been revoked")
        if not self.authorization_id or not self.authorized_at or not self.authorized_by:
            raise AnalysisConfigError(
                "LLM analysis requires authorization_id, authorized_at, and authorized_by"
            )


def load_tenant_analysis_config(path: str | Path) -> TenantAnalysisConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = {
        "tenant_id",
        "llm_enabled",
        "llm_provider",
        "llm_model",
        "web_search_enabled",
        "data_sharing_level",
        "authorization_id",
        "authorized_at",
        "authorized_by",
        "revoked_at",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise AnalysisConfigError(f"Unknown tenant analysis config fields: {', '.join(unknown)}")
    return TenantAnalysisConfig(**payload)
