from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_network
from typing import Any


class ScopeValidationError(ValueError):
    """Raised when a toolbox discovery request violates tenant scope limits."""


@dataclass(frozen=True)
class TenantScopeProfile:
    tenant_id: str
    profile_id: str
    allowed_root_domains: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    allowed_ip_cidrs: list[str] = field(default_factory=list)
    allowed_org_names: list[str] = field(default_factory=list)
    default_scope: dict[str, list[str]] = field(default_factory=dict)
    allowed_engines: list[str] = field(default_factory=lambda: ["fofa"])
    provider_profile_id: str | None = None
    limits: dict[str, int] = field(default_factory=dict)
    created_by: str | None = None
    authorization_note: str | None = None
    status: str = "active"

    def to_toolbox_summary(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "profile_id": self.profile_id,
            "allowed_scope_summary": {
                "root_domains": self.allowed_root_domains,
                "domains": self.allowed_domains,
                "ip_cidrs": self.allowed_ip_cidrs,
                "org_names": self.allowed_org_names,
            },
            "default_scope": self.default_scope,
            "allowed_engines": self.allowed_engines,
            "limits": self.limits,
        }


@dataclass(frozen=True)
class ScopeValidationResult:
    accepted_scope: dict[str, list[str]]
    rejected_scope: list[dict[str, str]]


def validate_requested_scope(
    profile: TenantScopeProfile,
    requested_scope: dict[str, list[str]] | None,
    engines: list[str],
    result_limit: int,
) -> ScopeValidationResult:
    if profile.status != "active":
        raise ScopeValidationError(f"Scope profile is not active: {profile.profile_id}")
    _validate_engines(profile, engines)
    _validate_result_limit(profile, result_limit)

    scope = requested_scope or {}
    if not any(scope.values()):
        scope = profile.default_scope

    accepted: dict[str, list[str]] = {}
    rejected: list[dict[str, str]] = []
    checks = [
        ("root_domains", "root_domain", _root_domain_allowed),
        ("domains", "domain", _domain_allowed),
        ("ip_cidrs", "ip_cidr", _cidr_allowed),
        ("org_names", "organization_name", _org_allowed),
    ]
    for scope_key, item_type, checker in checks:
        for value in scope.get(scope_key, []):
            normalized = value.strip()
            if checker(profile, normalized):
                accepted.setdefault(scope_key, []).append(normalized)
            else:
                rejected.append(
                    {
                        "type": item_type,
                        "value": normalized,
                        "reason": "outside_tenant_allowed_scope",
                    }
                )
    return ScopeValidationResult(accepted_scope=accepted, rejected_scope=rejected)


def _validate_engines(profile: TenantScopeProfile, engines: list[str]) -> None:
    disallowed = sorted(set(engines) - set(profile.allowed_engines))
    if disallowed:
        raise ScopeValidationError(f"Requested engine is not allowed: {', '.join(disallowed)}")


def _validate_result_limit(profile: TenantScopeProfile, result_limit: int) -> None:
    max_results = int(profile.limits.get("max_results_per_task", result_limit))
    if result_limit > max_results:
        raise ScopeValidationError(
            f"result_limit {result_limit} exceeds tenant limit {max_results}"
        )


def _root_domain_allowed(profile: TenantScopeProfile, value: str) -> bool:
    return _lower(value) in {_lower(domain) for domain in profile.allowed_root_domains}


def _domain_allowed(profile: TenantScopeProfile, value: str) -> bool:
    normalized = _lower(value)
    explicit = {_lower(domain) for domain in profile.allowed_domains}
    if normalized in explicit:
        return True
    return any(
        normalized == root or normalized.endswith(f".{root}")
        for root in (_lower(domain) for domain in profile.allowed_root_domains)
    )


def _cidr_allowed(profile: TenantScopeProfile, value: str) -> bool:
    try:
        requested = ip_network(value, strict=False)
        allowed_networks = [ip_network(cidr, strict=False) for cidr in profile.allowed_ip_cidrs]
    except ValueError:
        return False
    return any(requested.subnet_of(allowed) for allowed in allowed_networks)


def _org_allowed(profile: TenantScopeProfile, value: str) -> bool:
    return _lower(value) in {_lower(org) for org in profile.allowed_org_names}


def _lower(value: str) -> str:
    return value.strip().lower().rstrip(".")
