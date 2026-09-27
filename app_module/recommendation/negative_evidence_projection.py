"""將 canonical assessment 投影成凍結的 v1 推薦篩選列。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from app_module.recommendation_run_support import build_negative_evidence_buffers
from decision_module.recommendation.contracts import DecisionBatch, FilterOutcome


LEGACY_NEGATIVE_EVIDENCE_EVENT_TYPE = "legacy_negative_evidence_capture"
LEGACY_SCREENING_ROW_FIELDS_V1 = (
    "stock_code",
    "stock_name",
    "status",
    "reason_codes",
    "quality",
    "stage",
    "threshold_name",
    "observed_value",
    "required_value",
    "total_score",
    "score_bp",
    "score_percentile_bp",
    "eligible_universe_size",
    "threshold_mode",
    "warnings",
    "industry",
    "as_of_date",
    "data_fingerprint",
)
LEGACY_CAPTURE_FIELDS_V1 = (
    "screening_matrix",
    "excluded_candidates",
    "why_not_payload",
    "liquidity_gate_payload",
    "exclusion_quality",
    "exclusion_warnings",
)

_ROW_STRING_FIELDS = (
    "stock_code",
    "stock_name",
    "status",
    "quality",
    "stage",
    "threshold_name",
    "observed_value",
    "required_value",
    "total_score",
    "threshold_mode",
    "industry",
    "as_of_date",
    "data_fingerprint",
)
_ROW_OPTIONAL_INT_FIELDS = (
    "score_bp",
    "score_percentile_bp",
    "eligible_universe_size",
)


class NegativeEvidenceProjectionError(ValueError):
    """canonical assessment 無法證明完整 v1 篩選列時拋出。"""


@dataclass(frozen=True, slots=True)
class NegativeEvidenceProjection:
    """從 typed candidate assessments 衍生的唯讀 v1 相容檢視。"""

    screening_matrix: tuple[Mapping[str, object], ...]
    excluded_candidates: tuple[Mapping[str, object], ...]
    why_not_payload: tuple[Mapping[str, object], ...]
    liquidity_gate_payload: tuple[Mapping[str, object], ...]
    exclusion_quality: str
    exclusion_warnings: tuple[str, ...]

    def as_event_details(self) -> dict[str, object]:
        """回傳欄位形狀不變的 legacy event，供相容讀者使用。"""

        return {
            "screening_matrix": _thaw(self.screening_matrix),
            "excluded_candidates": _thaw(self.excluded_candidates),
            "why_not_payload": _thaw(self.why_not_payload),
            "liquidity_gate_payload": _thaw(self.liquidity_gate_payload),
            "exclusion_quality": self.exclusion_quality,
            "exclusion_warnings": list(self.exclusion_warnings),
        }

    def as_saved_capture_projection(self) -> dict[str, object]:
        """回傳既有 read-model 欄名與不可變值。"""

        return {
            "screening_matrix_json": self.screening_matrix,
            "excluded_candidates_json": self.excluded_candidates,
            "why_not_payload_json": self.why_not_payload,
            "liquidity_gate_payload_json": self.liquidity_gate_payload,
            "exclusion_quality": self.exclusion_quality,
            "exclusion_warnings_json": self.exclusion_warnings,
        }

    def as_scheduled_summary(self) -> dict[str, object]:
        """回傳排程消費端既有摘要欄名。"""

        return {
            "screening_matrix": self.screening_matrix,
            "excluded_candidates": self.excluded_candidates,
            "why_not_payload": self.why_not_payload,
            "liquidity_gate_payload": self.liquidity_gate_payload,
            "exclusion_quality": self.exclusion_quality,
            "exclusion_warnings": self.exclusion_warnings,
        }


def project_canonical_negative_evidence(
    decision: DecisionBatch,
    *,
    allow_empty: bool = False,
) -> NegativeEvidenceProjection:
    """投影精確的 ``legacy:<stage>`` evidence，不重新評估候選。

    evidence mapping 是 v1 screening row 的來源。每筆 assessment 必須含有且
    只能含有一筆相符資料；部分 typed 資料一律拒絕。只有 caller 能證明這次
    live invocation 成功且 assessments 數量為零時，才接受空批次。
    """

    if type(decision) is not DecisionBatch:
        raise NegativeEvidenceProjectionError("decision 必須是 DecisionBatch")

    assessments = decision.assessments
    if not assessments:
        if not allow_empty:
            raise NegativeEvidenceProjectionError("DecisionBatch 沒有 typed screening evidence")
        return _projection_from_rows(())

    rows: list[dict[str, object]] = []
    stock_codes: set[str] = set()
    for assessment in assessments:
        if assessment.stock_code in stock_codes:
            raise NegativeEvidenceProjectionError("typed assessments 有重複 stock_code")
        stock_codes.add(assessment.stock_code)
        outcomes = assessment.filter_outcomes or {}
        legacy_outcomes = tuple(
            (filter_id, outcome)
            for filter_id, outcome in outcomes.items()
            if filter_id.startswith("legacy:")
        )
        if len(legacy_outcomes) != 1:
            raise NegativeEvidenceProjectionError(
                f"{assessment.stock_code} 必須且只能有一筆 legacy:<stage> evidence"
            )
        filter_id, outcome = legacy_outcomes[0]
        rows.append(
            _validated_v1_row(
                assessment.stock_code,
                filter_id,
                outcome,
                expected_passed=assessment.eligible,
            )
        )

    return _projection_from_rows(tuple(rows))


def count_legacy_assessment_outcomes(decision: DecisionBatch | None) -> int:
    """計算明示的 legacy outcome，並拒絕只補齊部分 assessment 的批次。"""

    if decision is None:
        return 0
    counts = tuple(
        sum(
            filter_id.startswith("legacy:")
            for filter_id in (assessment.filter_outcomes or {})
        )
        for assessment in decision.assessments
    )
    total = sum(counts)
    if total and any(count != 1 for count in counts):
        raise NegativeEvidenceProjectionError(
            "typed legacy evidence 不可只覆蓋部分 assessments"
        )
    if any(count > 1 for count in counts):
        raise NegativeEvidenceProjectionError(
            "每個 assessment 只允許一筆 legacy:<stage> evidence"
        )
    return total


def legacy_history_event_projection(
    events: Sequence[object],
    *,
    schema_revision: int | None,
) -> dict[str, object]:
    """讀取明確支援的 event-only 歷史，不補造缺值。

    支援的保存格式 revision 為 1、2。為延續既有讀取語意，已知 v1 欄位缺漏時
    保留為 ``None``；未知欄位、重複 event 與格式錯誤的容器一律拒絕。
    """

    if type(schema_revision) is not int or schema_revision not in {1, 2}:
        raise NegativeEvidenceProjectionError(
            "event-only history 只支援 execution schema revision 1/2"
        )
    matches = tuple(
        event
        for event in events
        if getattr(event, "event_type", None) == LEGACY_NEGATIVE_EVIDENCE_EVENT_TYPE
    )
    if len(matches) > 1:
        raise NegativeEvidenceProjectionError("legacy negative-evidence event 重複")
    event = matches[0] if matches else None
    details = getattr(event, "details", None) if event is not None else None
    if details is None:
        details = {}
    if not isinstance(details, Mapping):
        raise NegativeEvidenceProjectionError("legacy event details 必須是 mapping")
    unknown_fields = set(details) - set(LEGACY_CAPTURE_FIELDS_V1)
    if unknown_fields:
        raise NegativeEvidenceProjectionError(
            "legacy event 含未知欄位: " + ", ".join(sorted(unknown_fields))
        )
    return {
        "screening_matrix_json": details.get("screening_matrix"),
        "excluded_candidates_json": details.get("excluded_candidates"),
        "why_not_payload_json": details.get("why_not_payload"),
        "liquidity_gate_payload_json": details.get("liquidity_gate_payload"),
        "exclusion_quality": details.get("exclusion_quality"),
        "exclusion_warnings_json": details.get("exclusion_warnings"),
    }


def assert_legacy_event_matches_projection(
    details: Mapping[str, object] | None,
    projection: NegativeEvidenceProjection,
) -> None:
    """typed rows 旁若有 v1 event，則拒絕已提供欄位與 typed 值不一致。"""

    if details is None:
        return
    unknown_fields = set(details) - set(LEGACY_CAPTURE_FIELDS_V1)
    if unknown_fields:
        raise NegativeEvidenceProjectionError(
            "legacy event 含未知欄位: " + ", ".join(sorted(unknown_fields))
        )
    expected = projection.as_event_details()
    actual = _thaw(details)
    for field_name, value in actual.items():
        if value != expected[field_name]:
            raise NegativeEvidenceProjectionError(
                f"typed assessment projection 與 event.{field_name} 不一致"
            )


def _validated_v1_row(
    stock_code: str,
    filter_id: str,
    outcome: FilterOutcome,
    *,
    expected_passed: bool | None,
) -> dict[str, object]:
    if type(outcome) is not FilterOutcome:
        raise NegativeEvidenceProjectionError("legacy filter outcome 型別不符")
    evidence = outcome.evidence
    if not isinstance(evidence, Mapping):
        raise NegativeEvidenceProjectionError("legacy outcome evidence 必須是 mapping")
    if set(evidence) != set(LEGACY_SCREENING_ROW_FIELDS_V1):
        raise NegativeEvidenceProjectionError(
            "legacy screening row 不符合 v1 欄位集合"
        )
    if any(type(evidence.get(name)) is not str for name in _ROW_STRING_FIELDS):
        raise NegativeEvidenceProjectionError("legacy screening row 的字串欄位型別錯誤")
    stage = evidence["stage"]
    if filter_id != f"legacy:{stage}" or evidence["stock_code"] != stock_code:
        raise NegativeEvidenceProjectionError(
            "legacy filter id、stage 與 assessment stock_code 不一致"
        )
    if outcome.passed is not expected_passed:
        raise NegativeEvidenceProjectionError(
            "legacy filter outcome passed 與 assessment eligibility 不一致"
        )
    reason_codes = _validated_string_sequence(evidence["reason_codes"], "reason_codes")
    expected_reason = reason_codes[0] if reason_codes else cast(str, evidence["status"])
    if outcome.reason != expected_reason:
        raise NegativeEvidenceProjectionError(
            "legacy filter outcome reason 與 typed evidence reason 不一致"
        )
    warnings = _validated_string_sequence(evidence["warnings"], "warnings")
    optional_ints = {
        name: _validated_optional_int(evidence[name], name)
        for name in _ROW_OPTIONAL_INT_FIELDS
    }
    score_percentile_bp = optional_ints["score_percentile_bp"]
    eligible_universe_size = optional_ints["eligible_universe_size"]
    if score_percentile_bp is not None and not 0 <= score_percentile_bp <= 10_000:
        raise NegativeEvidenceProjectionError("score_percentile_bp 超出 v1 範圍")
    if eligible_universe_size is not None and eligible_universe_size < 0:
        raise NegativeEvidenceProjectionError("eligible_universe_size 不可為負數")

    row = dict(evidence)
    row["reason_codes"] = reason_codes
    row["warnings"] = warnings
    row.update(optional_ints)
    return row


def _projection_from_rows(
    rows: Sequence[Mapping[str, object]],
) -> NegativeEvidenceProjection:
    if not rows:
        return NegativeEvidenceProjection(
            screening_matrix=(),
            excluded_candidates=(),
            why_not_payload=(),
            liquidity_gate_payload=(),
            exclusion_quality="unknown",
            exclusion_warnings=(),
        )
    materialized_rows = tuple(dict(row) for row in rows)
    buffers = build_negative_evidence_buffers(materialized_rows)
    exclusion_quality = buffers.exclusion_quality
    exclusion_warnings = list(buffers.exclusion_warnings)
    if any(row.get("quality") in {"missing", "degraded"} for row in materialized_rows):
        exclusion_quality = "degraded"
        if "screening_contains_unknown_evidence" not in exclusion_warnings:
            exclusion_warnings.append("screening_contains_unknown_evidence")
    return NegativeEvidenceProjection(
        screening_matrix=tuple(_freeze(row) for row in materialized_rows),
        excluded_candidates=tuple(_freeze(row) for row in buffers.excluded_candidates),
        why_not_payload=tuple(_freeze(row) for row in buffers.why_not_payload),
        liquidity_gate_payload=tuple(
            _freeze(row) for row in buffers.liquidity_gate_payload
        ),
        exclusion_quality=exclusion_quality,
        exclusion_warnings=tuple(exclusion_warnings),
    )


def _freeze(value: object) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _validated_string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) not in (tuple, list):
        raise NegativeEvidenceProjectionError(f"{field_name} 必須是 str sequence")
    sequence = cast(tuple[object, ...] | list[object], value)
    if any(type(item) is not str for item in sequence):
        raise NegativeEvidenceProjectionError(f"{field_name} 必須只含 str")
    return tuple(cast(str, item) for item in sequence)


def _validated_optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise NegativeEvidenceProjectionError(f"{field_name} 必須是 int 或 None")
    return cast(int, value)


__all__ = (
    "LEGACY_CAPTURE_FIELDS_V1",
    "LEGACY_NEGATIVE_EVIDENCE_EVENT_TYPE",
    "LEGACY_SCREENING_ROW_FIELDS_V1",
    "NegativeEvidenceProjection",
    "NegativeEvidenceProjectionError",
    "assert_legacy_event_matches_projection",
    "count_legacy_assessment_outcomes",
    "legacy_history_event_projection",
    "project_canonical_negative_evidence",
)
