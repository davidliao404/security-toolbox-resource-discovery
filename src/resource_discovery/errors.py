from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    recoverable: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "details": self.details,
        }


def profile_id_mismatch_error(expected: str, actual: str | None) -> ApiError:
    return ApiError(
        code="profile_id_mismatch",
        message="Requested scope profile does not match the active tenant profile.",
        recoverable=False,
        details={"expected_profile_id": expected, "actual_profile_id": actual},
    )


def scope_out_of_bounds_error(profile_id: str, rejected_scope: list[dict[str, str]]) -> ApiError:
    return ApiError(
        code="scope_out_of_bounds",
        message="Requested scope is outside the tenant authorized scope.",
        recoverable=False,
        details={"profile_id": profile_id, "rejected_scope": rejected_scope},
    )


def invalid_discovery_strategy_error(strategy: str) -> ApiError:
    return ApiError(
        code="invalid_discovery_strategy",
        message="Requested discovery strategy is not supported.",
        recoverable=False,
        details={"strategy": strategy, "supported_strategies": ["baseline", "easm"]},
    )


def query_plan_budget_exceeded_error(max_query_plans: int, planned_queries: int) -> ApiError:
    return ApiError(
        code="query_plan_budget_exceeded",
        message="Requested discovery strategy exceeds the tenant query plan budget.",
        recoverable=False,
        details={"max_query_plans": max_query_plans, "planned_queries": planned_queries},
    )
