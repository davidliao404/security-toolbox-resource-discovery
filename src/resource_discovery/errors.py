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
