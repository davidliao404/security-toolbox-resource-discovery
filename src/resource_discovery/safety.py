from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from .models import DiscoverySeed, SourceQueryPlan


class SafetyViolation(ValueError):
    """Raised when a discovery request violates pre-execution safety policy."""


@dataclass(frozen=True)
class DiscoveryPolicy:
    max_seed_count: int = 20
    min_ipv4_prefix: int = 24
    max_total_pages: int = 30
    max_result_limit_per_plan: int = 1000
    require_authorization_note: bool = True


DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}$")


def validate_seeds(seeds: list[DiscoverySeed], policy: DiscoveryPolicy | None = None) -> None:
    policy = policy or DiscoveryPolicy()
    if len(seeds) > policy.max_seed_count:
        raise SafetyViolation(f"Seed count exceeds limit: {len(seeds)} > {policy.max_seed_count}")

    for seed in seeds:
        if policy.require_authorization_note and not (seed.authorization_note or "").strip():
            raise SafetyViolation(f"Seed {seed.seed_id} must include authorization_note")
        value = seed.value.strip()
        if not value:
            raise SafetyViolation(f"Seed {seed.seed_id} value is empty")
        if seed.type in {"root_domain", "email_domain"}:
            _validate_domain(seed.seed_id, value)
        elif seed.type == "organization_name":
            if len(value) < 3:
                raise SafetyViolation(f"Seed {seed.seed_id} organization name is too short")
        elif seed.type == "ip_cidr":
            _validate_ip_cidr(seed.seed_id, value, policy)
        else:
            raise SafetyViolation(f"Unsupported seed type: {seed.type}")


def enforce_plan_quota(plans: list[SourceQueryPlan], policy: DiscoveryPolicy | None = None) -> None:
    policy = policy or DiscoveryPolicy()
    total_pages = sum(plan.page_limit for plan in plans)
    if total_pages > policy.max_total_pages:
        raise SafetyViolation(f"Query plan exceeds page budget: {total_pages} > {policy.max_total_pages}")
    too_large = [plan.plan_id for plan in plans if plan.result_limit > policy.max_result_limit_per_plan]
    if too_large:
        raise SafetyViolation(
            f"Query plan result limit exceeds maximum for: {', '.join(too_large)}"
        )


def _validate_domain(seed_id: str, value: str) -> None:
    if not DOMAIN_RE.match(value):
        raise SafetyViolation(f"Seed {seed_id} is not a valid domain")


def _validate_ip_cidr(seed_id: str, value: str, policy: DiscoveryPolicy) -> None:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise SafetyViolation(f"Seed {seed_id} is not a valid IP CIDR") from exc
    if isinstance(network, ipaddress.IPv4Network) and network.prefixlen < policy.min_ipv4_prefix:
        raise SafetyViolation(
            f"Seed {seed_id} IP range is too broad: /{network.prefixlen} < /{policy.min_ipv4_prefix}"
        )
