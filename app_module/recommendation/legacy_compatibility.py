"""Private invocation-local snapshots for the legacy recommendation façade."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


LEGACY_COMPATIBILITY_FIELDS = (
    "last_calibration_projections",
    "last_screening_matrix",
    "last_excluded_candidates_json",
    "last_why_not_payload_json",
    "last_liquidity_gate_payload_json",
    "last_exclusion_quality",
    "last_exclusion_warnings_json",
    "last_run_context",
)

_SNAPSHOT_SEAL = object()


def _validate_state(state: object, *, complete: bool = True) -> dict[str, Any]:
    if type(state) is not dict:
        raise TypeError("legacy compatibility state 必須是 dict")
    if tuple(state) != LEGACY_COMPATIBILITY_FIELDS:
        raise ValueError("legacy compatibility state 欄位或順序不符")
    if not complete:
        return state
    projections = state["last_calibration_projections"]
    if type(projections) is not dict or any(
        type(stock_code) is not str for stock_code in projections
    ):
        raise TypeError("last_calibration_projections 必須是 dict")
    for name in (
        "last_screening_matrix",
        "last_excluded_candidates_json",
        "last_why_not_payload_json",
        "last_liquidity_gate_payload_json",
    ):
        value = state[name]
        if type(value) is not list or any(type(row) is not dict for row in value):
            raise TypeError(f"{name} 必須是 list[dict]")
    if type(state["last_exclusion_quality"]) is not str:
        raise TypeError("last_exclusion_quality 必須是 str")
    warnings = state["last_exclusion_warnings_json"]
    if type(warnings) is not list or any(type(item) is not str for item in warnings):
        raise TypeError("last_exclusion_warnings_json 必須是 list[str]")
    if type(state["last_run_context"]) is not dict:
        raise TypeError("last_run_context 必須是 dict")
    return state


@dataclass(frozen=True, slots=True, init=False, repr=False)
class LegacyCompatibilitySnapshot:
    """App-local private deep copy with copy-out access to legacy state.

    The payload is intentionally kept out of ``RecommendationExecution`` and
    is never exposed directly.  Keeping one copied graph preserves nested and
    cross-field aliases; each consumer receives a fresh whole-graph copy.
    """

    capture_id: str
    result_id: str
    body_invocation_id: str | None
    __payload: dict[str, Any] = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        capture_id: str,
        result_id: str,
        body_invocation_id: str | None,
        state: dict[str, Any],
        allow_partial_state: bool,
        _seal: object,
    ) -> None:
        if _seal is not _SNAPSHOT_SEAL:
            raise TypeError("snapshot 必須由 capture_from_invocation 建立")
        for name, value in (("capture_id", capture_id), ("result_id", result_id)):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if body_invocation_id is not None and (
            type(body_invocation_id) is not str or not body_invocation_id.strip()
        ):
            raise ValueError("body_invocation_id 必須是非空 str 或 None")
        validated = _validate_state(state, complete=not allow_partial_state)
        object.__setattr__(self, "capture_id", capture_id)
        object.__setattr__(self, "result_id", result_id)
        object.__setattr__(self, "body_invocation_id", body_invocation_id)
        object.__setattr__(self, "_LegacyCompatibilitySnapshot__payload", deepcopy(validated))

    @classmethod
    def capture_from_invocation(
        cls,
        invocation: object,
        *,
        capture_id: str,
        result_id: str,
        body_invocation_id: str | None,
        allow_partial_state: bool = False,
    ) -> LegacyCompatibilitySnapshot:
        state = {
            name: getattr(invocation, name)
            for name in LEGACY_COMPATIBILITY_FIELDS
        }
        return cls(
            capture_id=capture_id,
            result_id=result_id,
            body_invocation_id=body_invocation_id,
            state=state,
            allow_partial_state=allow_partial_state,
            _seal=_SNAPSHOT_SEAL,
        )

    def validate_complete_state(self) -> None:
        """Fail closed when a completed body is about to publish an execution."""

        _validate_state(self.materialize(), complete=True)

    def materialize(self) -> dict[str, Any]:
        """Return one detached copy of the complete state graph."""

        return deepcopy(self.__payload)
