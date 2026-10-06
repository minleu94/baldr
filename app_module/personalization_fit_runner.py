"""受控的 personal calibration offline fit 入口。

這個模組只把既有 ``PersonalizationReadService`` 的唯讀 report 接到既有
``PersonalizationCalibrationEvaluator``。它不建立 recommendation、Journal 或
Evidence writer，不產生 scope/action/outcome，也不改 global pointer、scheduler、
broker 或正式策略。

fit artifact 本身仍是既有 frozen contract；此模組只在外層保存一個
hash-bound source-binding envelope，讓 source fingerprint、scope、cutoff 及
train/evaluation split 可以一起重載驗證。資料不足、來源不完整或時間／cohort
contract 不合時只回傳 blocked，絕不落盤成合格 artifact。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from app_module.personalization_calibration import (
    DEFAULT_PROBABILITY_BIN_EDGES_BP,
    DEFAULT_SHRINKAGE_STRENGTH,
    PersonalizationCalibrationError,
    PersonalizationCalibrationEvaluation,
    PersonalizationCalibrationEvaluator,
    PersonalizationCalibrationFitArtifact,
    PersonalizationCalibrationPolicy,
)
from app_module.personalization_contract import (
    PersonalizationEvaluationRow,
    canonical_payload_hash,
    parse_aware_datetime,
)
from app_module.personalization_read_service import (
    PersonalizationReadReport,
    PersonalizationReadService,
)


PERSONALIZATION_FIT_RUNNER_SCHEMA_VERSION = "personalization-fit-runner.v1"
PERSONALIZATION_FIT_ARTIFACT_ENVELOPE_SCHEMA_VERSION = (
    "personalization-fit-artifact-envelope.v1"
)
DEFAULT_MIN_FIT_ROWS = 2
DEFAULT_MIN_FIT_DECISION_DATES = 2
_MARKET_TIMEZONE = ZoneInfo("Asia/Taipei")


class PersonalizationFitArtifactError(PersonalizationCalibrationError):
    """fit runner、source binding 或 immutable artifact 儲存失敗。"""


def _text(value: object) -> str:
    return str(value or "").strip()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _date(value: object, field_name: str) -> str:
    text = _text(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise PersonalizationFitArtifactError(
            f"{field_name} must be ISO date"
        ) from exc


def _aware_datetime(value: object, field_name: str) -> str:
    try:
        return parse_aware_datetime(value, field_name).isoformat(
            timespec="microseconds"
        )
    except ValueError as exc:
        raise PersonalizationFitArtifactError(str(exc)) from exc


def _row_from_mapping(value: Mapping[str, Any]) -> PersonalizationEvaluationRow:
    """Rehydrate only the row contract emitted by ``to_dict``."""

    if not isinstance(value, Mapping):
        raise PersonalizationFitArtifactError("evaluation row must be an object")
    names = {item.name for item in fields(PersonalizationEvaluationRow)}
    payload = {name: value[name] for name in names if name in value}
    try:
        return PersonalizationEvaluationRow(**payload)
    except (TypeError, ValueError) as exc:
        raise PersonalizationFitArtifactError(
            f"evaluation row is invalid: {type(exc).__name__}"
        ) from exc


def _hash_rows(rows: Sequence[PersonalizationEvaluationRow]) -> str:
    return canonical_payload_hash(
        {
            "rows": [
                row.to_dict()
                for row in sorted(
                    rows,
                    key=lambda item: (
                        item.effective_row_id,
                        item.prediction_id,
                    ),
                )
            ]
        }
    )


def _deduplicate_rows_for_runner(
    rows: Sequence[PersonalizationEvaluationRow],
    *,
    phase: str,
) -> tuple[PersonalizationEvaluationRow, ...]:
    """鏡像既有 evaluator 的精確 retry／identity 語意。

    evaluator 仍是 fit／evaluation 合約的唯一權威；runner 只在將 row id
    記入 durable envelope 前套用同一套 exact duplicate 規則，避免 envelope
    記錄 evaluator 已經靜默去除的重複 evaluation identity。
    """

    seen: dict[tuple[str, str], PersonalizationEvaluationRow] = {}
    output: list[PersonalizationEvaluationRow] = []
    for row in rows:
        identities = (
            ("row_id", row.effective_row_id),
            ("prediction_id", row.prediction_id),
            ("statistical_id", row.effective_statistical_id),
        )
        duplicate_exact = False
        for key, identity in identities:
            previous = seen.get((key, identity))
            if previous is None:
                continue
            if previous.to_dict() == row.to_dict():
                duplicate_exact = True
                continue
            raise PersonalizationFitArtifactError(
                f"{phase} duplicate identity conflict at {key}={identity}"
            )
        if duplicate_exact:
            continue
        output.append(row)
        for key, identity in identities:
            seen[(key, identity)] = row
    return tuple(output)


def _request_binding(
    request: "PersonalizationFitRequest",
    *,
    created_at: str,
    effective_embargo_days: int,
) -> dict[str, Any]:
    """保存所有會改變 fit 或唯讀範圍的 request 欄位。"""

    return {
        "scope_id": request.scope_id,
        "fit_as_of": request.fit_as_of,
        "evaluated_as_of": request.evaluated_as_of,
        "evaluation_cutoff_at": request.evaluation_cutoff_at,
        "output_path": str(request.output_path),
        "result_id": request.result_id,
        "stock_code": request.stock_code,
        "artifact_id": request.artifact_id,
        # 這是 immutable artifact 的有效建立時鐘，不是歷史 availability
        # 時鐘；caller 省略時只由 runtime clock 填入一次，retry 直接重用。
        "created_at": created_at,
        "shrinkage_strength": request.shrinkage_strength,
        "embargo_days": request.embargo_days,
        "effective_embargo_days": effective_embargo_days,
        "min_fit_rows": request.min_fit_rows,
        "min_fit_decision_dates": request.min_fit_decision_dates,
        "max_results": request.max_results,
        "max_candidates_per_result": request.max_candidates_per_result,
        "max_evidence_events": request.max_evidence_events,
        "max_journal_rows": request.max_journal_rows,
        "fit_gate_semantics": "research_minimum_only",
    }


def _canonical_envelope_bytes(
    envelope: "PersonalizationFitArtifactEnvelope",
) -> bytes:
    return (
        json.dumps(
            envelope.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _stable_created_at(
    *,
    now: Callable[[], datetime] | None = None,
    evaluated_as_of: str | None = None,
    fit_rows: Sequence[PersonalizationEvaluationRow] = (),
) -> str:
    """取得 fit 程序實際建立時鐘。

    舊 draft 從 ``evaluated_as_of`` 與來源 dependency 時鐘推導
    ``created_at``，會讓歷史 fit 看起來像是在評估日結束時已存在。保留
    私有名稱以相容早期 caller，但刻意忽略那些歷史輸入，改用注入的
    runtime clock；retry 的 idempotency 由重新讀取 immutable artifact 提供，
    不製造歷史 timestamp。
    """

    del evaluated_as_of, fit_rows
    clock = now or (lambda: datetime.now(timezone.utc))
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PersonalizationFitArtifactError(
            "fit 建立時鐘必須回傳帶時區的 datetime"
        )
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _fit_row_reasons(
    row: PersonalizationEvaluationRow,
    *,
    fit_as_of: str,
) -> tuple[str, ...]:
    """Check the exact fit cutoff before invoking the frozen evaluator."""

    fit_day = date.fromisoformat(fit_as_of)
    reasons: list[str] = []
    if date.fromisoformat(row.decision_date) > fit_day:
        reasons.append("decision_after_fit_as_of")
        return tuple(reasons)
    if date.fromisoformat(row.label_available_date) > fit_day:
        reasons.append("label_date_after_fit_as_of")
    if row.label_available_at is None:
        reasons.append("label_availability_timestamp_missing")
    else:
        label_at = parse_aware_datetime(
            row.label_available_at,
            "label_available_at",
        )
        if label_at.astimezone(_MARKET_TIMEZONE).date() > fit_day:
            reasons.append("label_timestamp_after_fit_as_of")
    if row.outcome_recorded_at is None:
        reasons.append("outcome_recorded_timestamp_missing")
    else:
        outcome_at = parse_aware_datetime(
            row.outcome_recorded_at,
            "outcome_recorded_at",
        )
        if outcome_at.astimezone(_MARKET_TIMEZONE).date() > fit_day:
            reasons.append("outcome_timestamp_after_fit_as_of")
    if row.receipt_created_at is None:
        reasons.append("receipt_created_timestamp_missing")
    if row.outcome_status != "ready":
        reasons.append(f"outcome_{row.outcome_status}")
    if row.label not in {0, 1}:
        reasons.append("label_missing_or_invalid")
    if row.delivery_status != "delivered":
        reasons.append("delivery_not_delivered")
    if row.late_delivery:
        reasons.append("late_delivery_no_natural_credit")
    required_fields = (
        "scope_id",
        "source_id",
        "model_id",
        "dataset_id",
        "dataset_hash",
        "universe_policy_hash",
        "label_contract_id",
        "return_basis",
        "prediction_receipt_hash",
        "prediction_receipt_schema_version",
        "cost_scenario_hash",
    )
    for field_name in required_fields:
        if not _text(getattr(row, field_name)):
            reasons.append(f"{field_name}_missing")
    return tuple(dict.fromkeys(reasons))


def _source_manifest_hash(source_fingerprints: Sequence[Mapping[str, Any]]) -> str:
    return canonical_payload_hash(
        [
            {
                "path": item.get("path"),
                "before": item.get("before"),
            }
            for item in source_fingerprints
        ]
    )


def _envelope_hash(
    *,
    artifact: PersonalizationCalibrationFitArtifact,
    source_binding: Mapping[str, Any],
    schema_version: str,
) -> str:
    return canonical_payload_hash(
        {
            "schema_version": schema_version,
            "artifact": artifact.to_dict(),
            "source_binding": _thaw(source_binding),
        }
    )


@dataclass(frozen=True)
class PersonalizationFitRequest:
    """One explicit offline fit invocation."""

    scope_id: str
    fit_as_of: str
    evaluated_as_of: str
    evaluation_cutoff_at: str
    output_path: Path
    result_id: str | None = None
    stock_code: str | None = None
    artifact_id: str | None = None
    created_at: str | None = None
    shrinkage_strength: int = DEFAULT_SHRINKAGE_STRENGTH
    embargo_days: int | None = None
    min_fit_rows: int = DEFAULT_MIN_FIT_ROWS
    min_fit_decision_dates: int = DEFAULT_MIN_FIT_DECISION_DATES
    max_results: int = 100
    max_candidates_per_result: int = 100
    max_evidence_events: int = 500
    max_journal_rows: int = 50_000

    def __post_init__(self) -> None:
        scope_id = _text(self.scope_id)
        if not scope_id:
            raise PersonalizationFitArtifactError("scope_id is required")
        fit_as_of = _date(self.fit_as_of, "fit_as_of")
        evaluated_as_of = _date(self.evaluated_as_of, "evaluated_as_of")
        if evaluated_as_of < fit_as_of:
            raise PersonalizationFitArtifactError(
                "evaluated_as_of must not precede fit_as_of"
            )
        cutoff = _aware_datetime(
            self.evaluation_cutoff_at,
            "evaluation_cutoff_at",
        )
        if date.fromisoformat(cutoff[:10]) > date.fromisoformat(evaluated_as_of):
            raise PersonalizationFitArtifactError(
                "evaluation_cutoff_at cannot follow evaluated_as_of"
            )
        # 保留 lexical final path，讓 _persist_create_only 在 resolve 前拒絕
        # caller 提供的 symlink。
        output_path = Path(os.path.abspath(os.fspath(Path(self.output_path).expanduser())))
        if not _text(output_path):
            raise PersonalizationFitArtifactError("output_path is required")
        for field_name in (
            "shrinkage_strength",
            "min_fit_rows",
            "min_fit_decision_dates",
            "max_results",
            "max_candidates_per_result",
            "max_evidence_events",
            "max_journal_rows",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PersonalizationFitArtifactError(
                    f"{field_name} must be a positive integer"
                )
        if self.embargo_days is not None and (
            isinstance(self.embargo_days, bool)
            or not isinstance(self.embargo_days, int)
            or self.embargo_days < 0
        ):
            raise PersonalizationFitArtifactError(
                "embargo_days must be a non-negative integer"
            )
        created_at = (
            _aware_datetime(self.created_at, "created_at")
            if self.created_at is not None
            else None
        )
        object.__setattr__(self, "scope_id", scope_id)
        object.__setattr__(self, "fit_as_of", fit_as_of)
        object.__setattr__(self, "evaluated_as_of", evaluated_as_of)
        object.__setattr__(self, "evaluation_cutoff_at", cutoff)
        object.__setattr__(self, "output_path", output_path)
        object.__setattr__(self, "result_id", _text(self.result_id) or None)
        object.__setattr__(self, "stock_code", _text(self.stock_code) or None)
        object.__setattr__(self, "artifact_id", _text(self.artifact_id) or None)
        object.__setattr__(self, "created_at", created_at)


@dataclass(frozen=True)
class PersonalizationFitArtifactEnvelope:
    """Existing frozen artifact plus immutable read/source custody."""

    artifact: PersonalizationCalibrationFitArtifact
    source_binding: Mapping[str, Any]
    artifact_hash: str
    schema_version: str = PERSONALIZATION_FIT_ARTIFACT_ENVELOPE_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        artifact: PersonalizationCalibrationFitArtifact,
        source_binding: Mapping[str, Any],
    ) -> "PersonalizationFitArtifactEnvelope":
        return cls(
            artifact=artifact,
            source_binding=source_binding,
            artifact_hash=_envelope_hash(
                artifact=artifact,
                source_binding=source_binding,
                schema_version=PERSONALIZATION_FIT_ARTIFACT_ENVELOPE_SCHEMA_VERSION,
            ),
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "PersonalizationFitArtifactEnvelope":
        if not isinstance(value, Mapping):
            raise PersonalizationFitArtifactError(
                "fit artifact envelope must be an object"
            )
        schema_version = _text(value.get("schema_version"))
        if schema_version != PERSONALIZATION_FIT_ARTIFACT_ENVELOPE_SCHEMA_VERSION:
            raise PersonalizationFitArtifactError(
                "unsupported fit artifact envelope schema"
            )
        raw_artifact = value.get("artifact")
        raw_binding = value.get("source_binding")
        if not isinstance(raw_artifact, Mapping):
            raise PersonalizationFitArtifactError("fit artifact envelope artifact is missing")
        if not isinstance(raw_binding, Mapping):
            raise PersonalizationFitArtifactError(
                "fit artifact envelope source_binding is missing"
            )
        artifact = PersonalizationCalibrationFitArtifact.from_mapping(raw_artifact)
        return cls(
            artifact=artifact,
            source_binding=dict(raw_binding),
            artifact_hash=_text(value.get("artifact_hash")),
            schema_version=schema_version,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, PersonalizationCalibrationFitArtifact):
            raise PersonalizationFitArtifactError("fit artifact type is invalid")
        if self.schema_version != PERSONALIZATION_FIT_ARTIFACT_ENVELOPE_SCHEMA_VERSION:
            raise PersonalizationFitArtifactError(
                "unsupported fit artifact envelope schema"
            )
        if not _text(self.artifact_hash).startswith("sha256:"):
            raise PersonalizationFitArtifactError("artifact_hash is invalid")
        if not isinstance(self.source_binding, Mapping):
            raise PersonalizationFitArtifactError("source_binding must be an object")
        binding = dict(_thaw(self.source_binding))
        self._validate_source_binding(binding)
        expected = _envelope_hash(
            artifact=self.artifact,
            source_binding=binding,
            schema_version=self.schema_version,
        )
        if expected != self.artifact_hash:
            raise PersonalizationFitArtifactError("fit artifact envelope hash mismatch")
        object.__setattr__(self, "source_binding", _freeze(binding))

    def _validate_source_binding(self, binding: Mapping[str, Any]) -> None:
        required = (
            "scope_id",
            "fit_as_of",
            "evaluated_as_of",
            "evaluation_cutoff_at",
            "request",
            "fit_creation_clock",
            "evaluation_temporal_semantics",
            "source_manifest_hash",
            "source_fingerprints",
            "source_bytes_unchanged",
            "source_consistency_status",
            "source_completeness_status",
            "fit_row_ids",
            "fit_row_fingerprint",
            "evaluation_row_ids",
            "evaluation_row_fingerprint",
            "fit_row_count",
            "fit_decision_date_count",
            "evaluation_row_count",
        )
        if any(key not in binding for key in required):
            raise PersonalizationFitArtifactError(
                "fit artifact source binding is incomplete"
            )
        if _text(binding["scope_id"]) != self.artifact.fit_scope_id:
            raise PersonalizationFitArtifactError("fit source scope mismatch")
        if _date(binding["fit_as_of"], "fit_as_of") != self.artifact.fit_as_of:
            raise PersonalizationFitArtifactError("fit source cutoff mismatch")
        evaluated_as_of = _date(binding["evaluated_as_of"], "evaluated_as_of")
        evaluation_cutoff_at = _aware_datetime(
            binding["evaluation_cutoff_at"],
            "evaluation_cutoff_at",
        )
        request = binding["request"]
        if not isinstance(request, Mapping):
            raise PersonalizationFitArtifactError("fit request binding is invalid")
        request_required = (
            "scope_id",
            "fit_as_of",
            "evaluated_as_of",
            "evaluation_cutoff_at",
            "output_path",
            "result_id",
            "stock_code",
            "artifact_id",
            "created_at",
            "shrinkage_strength",
            "embargo_days",
            "effective_embargo_days",
            "min_fit_rows",
            "min_fit_decision_dates",
            "max_results",
            "max_candidates_per_result",
            "max_evidence_events",
            "max_journal_rows",
            "fit_gate_semantics",
        )
        if any(key not in request for key in request_required):
            raise PersonalizationFitArtifactError(
                "fit request binding is incomplete"
            )
        if _text(request["scope_id"]) != self.artifact.fit_scope_id:
            raise PersonalizationFitArtifactError("fit request scope mismatch")
        if _date(request["fit_as_of"], "request.fit_as_of") != self.artifact.fit_as_of:
            raise PersonalizationFitArtifactError("fit request cutoff mismatch")
        if _date(request["evaluated_as_of"], "request.evaluated_as_of") != evaluated_as_of:
            raise PersonalizationFitArtifactError(
                "fit request evaluated_as_of mismatch"
            )
        if _aware_datetime(
            request["evaluation_cutoff_at"],
            "request.evaluation_cutoff_at",
        ) != evaluation_cutoff_at:
            raise PersonalizationFitArtifactError(
                "fit request evaluation cutoff mismatch"
            )
        if not _text(request["output_path"]):
            raise PersonalizationFitArtifactError(
                "fit request output path is invalid"
            )
        for field_name in ("result_id", "stock_code"):
            value = request[field_name]
            if value is not None and not _text(value):
                raise PersonalizationFitArtifactError(
                    f"fit request {field_name} is invalid"
                )
        if _aware_datetime(request["created_at"], "request.created_at") != _aware_datetime(
            self.artifact.created_at,
            "artifact.created_at",
        ):
            raise PersonalizationFitArtifactError(
                "fit request creation clock mismatch"
            )
        if request["fit_gate_semantics"] != "research_minimum_only":
            raise PersonalizationFitArtifactError(
                "fit request gate semantics are unsupported"
            )
        requested_artifact_id = _text(request["artifact_id"])
        if requested_artifact_id and requested_artifact_id != self.artifact.artifact_id:
            raise PersonalizationFitArtifactError("fit request artifact id mismatch")
        for field_name in (
            "shrinkage_strength",
            "min_fit_rows",
            "min_fit_decision_dates",
            "max_results",
            "max_candidates_per_result",
            "max_evidence_events",
            "max_journal_rows",
        ):
            value = request[field_name]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PersonalizationFitArtifactError(
                    f"fit request {field_name} is invalid"
                )
        if (
            isinstance(request["effective_embargo_days"], bool)
            or not isinstance(request["effective_embargo_days"], int)
            or request["effective_embargo_days"] < 0
        ):
            raise PersonalizationFitArtifactError(
                "fit request effective_embargo_days is invalid"
            )
        if request["embargo_days"] is not None and (
            isinstance(request["embargo_days"], bool)
            or not isinstance(request["embargo_days"], int)
            or request["embargo_days"] < 0
        ):
            raise PersonalizationFitArtifactError(
                "fit request embargo_days is invalid"
            )
        if (
            request["effective_embargo_days"]
            != self.artifact.embargo_days
        ):
            raise PersonalizationFitArtifactError(
                "fit request effective embargo mismatch"
            )
        clock_source = _text(binding["fit_creation_clock"])
        if clock_source not in {"runtime_utc", "caller_supplied"}:
            raise PersonalizationFitArtifactError(
                "fit creation clock source is unsupported"
            )
        temporal = binding["evaluation_temporal_semantics"]
        if not isinstance(temporal, Mapping):
            raise PersonalizationFitArtifactError(
                "evaluation temporal semantics are invalid"
            )
        if temporal.get("mode") != "retrospective_offline":
            raise PersonalizationFitArtifactError(
                "fit evaluation must be explicitly retrospective_offline"
            )
        if temporal.get("prospective") is not False:
            raise PersonalizationFitArtifactError(
                "retrospective fit cannot claim prospective semantics"
            )
        if temporal.get("natural_forward_credit") is not False:
            raise PersonalizationFitArtifactError(
                "retrospective fit cannot claim natural forward credit"
            )
        created_datetime = parse_aware_datetime(
            self.artifact.created_at,
            "artifact.created_at",
        )
        cutoff_datetime = parse_aware_datetime(
            evaluation_cutoff_at,
            "evaluation_cutoff_at",
        )
        if temporal.get("evaluated_as_of") != evaluated_as_of:
            raise PersonalizationFitArtifactError(
                "retrospective evaluation date binding mismatch"
            )
        if temporal.get("evaluation_cutoff_at") != evaluation_cutoff_at:
            raise PersonalizationFitArtifactError(
                "retrospective evaluation cutoff binding mismatch"
            )
        if temporal.get("created_after_evaluation_cutoff") != (
            created_datetime > cutoff_datetime
        ):
            raise PersonalizationFitArtifactError(
                "retrospective creation clock diagnostic mismatch"
            )
        if binding["source_bytes_unchanged"] is not True:
            raise PersonalizationFitArtifactError("fit source bytes are not verified")
        if binding["source_consistency_status"] != "verified":
            raise PersonalizationFitArtifactError(
                "fit source consistency is not verified"
            )
        if binding["source_completeness_status"] != "verified":
            raise PersonalizationFitArtifactError(
                "fit source completeness is not verified"
            )
        source_manifest = _text(binding["source_manifest_hash"])
        if not source_manifest.startswith("sha256:"):
            raise PersonalizationFitArtifactError("source_manifest_hash is invalid")
        raw_fingerprints = binding["source_fingerprints"]
        if not isinstance(raw_fingerprints, (list, tuple)):
            raise PersonalizationFitArtifactError(
                "source_fingerprints must be an array"
            )
        fingerprints: list[Mapping[str, Any]] = []
        for item in raw_fingerprints:
            if not isinstance(item, Mapping):
                raise PersonalizationFitArtifactError(
                    "source fingerprint must be an object"
                )
            path = _text(item.get("path"))
            before = item.get("before")
            after = item.get("after")
            if not path or not isinstance(before, Mapping) or not isinstance(after, Mapping):
                raise PersonalizationFitArtifactError(
                    "source fingerprint is incomplete"
                )
            if _text(before.get("path")) != path or _text(after.get("path")) != path:
                raise PersonalizationFitArtifactError(
                    "source fingerprint path mismatch"
                )
            if item.get("unchanged") is not True or dict(before) != dict(after):
                raise PersonalizationFitArtifactError(
                    "source fingerprint is not unchanged"
                )
            fingerprints.append(dict(item))
        if _source_manifest_hash(fingerprints) != source_manifest:
            raise PersonalizationFitArtifactError(
                "source manifest fingerprint mismatch"
            )
        fit_ids = tuple(str(item) for item in binding["fit_row_ids"])
        if fit_ids != self.artifact.fit_row_ids:
            raise PersonalizationFitArtifactError("fit row identity binding mismatch")
        if (
            isinstance(binding["fit_row_count"], bool)
            or not isinstance(binding["fit_row_count"], int)
            or binding["fit_row_count"] != self.artifact.fit_row_count
        ):
            raise PersonalizationFitArtifactError("fit row count binding mismatch")
        for field_name in ("fit_decision_date_count", "evaluation_row_count"):
            value = binding[field_name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PersonalizationFitArtifactError(
                    f"{field_name} binding is invalid"
                )
        if _text(binding["fit_row_fingerprint"]) != self.artifact.fit_row_fingerprint:
            raise PersonalizationFitArtifactError("fit row fingerprint binding mismatch")
        eval_ids_raw = binding["evaluation_row_ids"]
        if not isinstance(eval_ids_raw, (list, tuple)):
            raise PersonalizationFitArtifactError(
                "evaluation_row_ids must be an array"
            )
        eval_ids = tuple(str(item) for item in eval_ids_raw)
        if binding["evaluation_row_count"] != len(eval_ids):
            raise PersonalizationFitArtifactError(
                "evaluation row count binding mismatch"
            )
        if len(set(eval_ids)) != len(eval_ids):
            raise PersonalizationFitArtifactError(
                "evaluation row identity binding is duplicated"
            )
        if set(fit_ids).intersection(eval_ids):
            raise PersonalizationFitArtifactError(
                "fit/evaluation row identity binding overlaps"
            )
        if not _text(binding["evaluation_row_fingerprint"]).startswith("sha256:"):
            raise PersonalizationFitArtifactError(
                "evaluation_row_fingerprint is invalid"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_hash": self.artifact_hash,
            "artifact": self.artifact.to_dict(),
            "source_binding": _thaw(self.source_binding),
        }


@dataclass(frozen=True)
class PersonalizationFitRunResult:
    """Machine-readable created/retry/blocked result; no blocked artifact path."""

    status: str
    blocked_reason: str
    scope_id: str
    fit_as_of: str
    evaluated_as_of: str
    evaluation_cutoff_at: str
    output_path: str
    artifact_path: str | None
    artifact_id: str | None
    artifact_hash: str | None
    source_manifest_hash: str | None
    source_row_count: int
    fit_candidate_row_count: int
    fit_row_count: int
    fit_decision_date_count: int
    evaluation_row_count: int
    diagnostics: tuple[str, ...] = ()
    evaluation: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PERSONALIZATION_FIT_RUNNER_SCHEMA_VERSION,
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "scope_id": self.scope_id,
            "fit_as_of": self.fit_as_of,
            "evaluated_as_of": self.evaluated_as_of,
            "evaluation_cutoff_at": self.evaluation_cutoff_at,
            "output_path": self.output_path,
            "artifact_path": self.artifact_path,
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "source_row_count": self.source_row_count,
            "fit_candidate_row_count": self.fit_candidate_row_count,
            "fit_row_count": self.fit_row_count,
            "fit_decision_date_count": self.fit_decision_date_count,
            "evaluation_row_count": self.evaluation_row_count,
            "diagnostics": list(self.diagnostics),
            "evaluation": dict(self.evaluation) if self.evaluation is not None else None,
        }


def _blocked_result(
    request: PersonalizationFitRequest,
    *,
    reason: str,
    source_manifest_hash: str | None = None,
    source_row_count: int = 0,
    fit_candidate_row_count: int = 0,
    fit_row_count: int = 0,
    fit_decision_date_count: int = 0,
    evaluation_row_count: int = 0,
    diagnostics: Sequence[str] = (),
) -> PersonalizationFitRunResult:
    return PersonalizationFitRunResult(
        status="blocked",
        blocked_reason=reason,
        scope_id=request.scope_id,
        fit_as_of=request.fit_as_of,
        evaluated_as_of=request.evaluated_as_of,
        evaluation_cutoff_at=request.evaluation_cutoff_at,
        output_path=str(request.output_path),
        artifact_path=None,
        artifact_id=None,
        artifact_hash=None,
        source_manifest_hash=source_manifest_hash,
        source_row_count=source_row_count,
        fit_candidate_row_count=fit_candidate_row_count,
        fit_row_count=fit_row_count,
        fit_decision_date_count=fit_decision_date_count,
        evaluation_row_count=evaluation_row_count,
        diagnostics=tuple(dict.fromkeys(str(item) for item in diagnostics if str(item))),
    )


def _output_path(path: Path) -> Path:
    """Normalize a final path without following a final symlink."""

    candidate = Path(os.path.abspath(os.fspath(Path(path).expanduser())))
    if candidate.is_symlink():
        raise PersonalizationFitArtifactError(
            "fit artifact output path must not be a symlink"
        )
    return candidate


def _load_envelope_file(path: Path) -> PersonalizationFitArtifactEnvelope:
    """Read one canonical envelope and reject partial/non-canonical files."""

    resolved = _output_path(path)
    if not resolved.is_file():
        raise PersonalizationFitArtifactError(
            "fit artifact output is not a regular file"
        )
    try:
        raw = resolved.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        envelope = PersonalizationFitArtifactEnvelope.from_mapping(value)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PersonalizationFitArtifactError(
            f"fit artifact output is invalid: {type(exc).__name__}"
        ) from exc
    if raw != _canonical_envelope_bytes(envelope):
        raise PersonalizationFitArtifactError(
            "fit artifact output is not canonical"
        )
    return envelope


class PersonalizationFitArtifactReader:
    """供下游唯讀 consumer 使用的 hash 驗證 reader envelope。"""

    @staticmethod
    def read(
        path: str | Path,
        *,
        expected_scope_id: str | None = None,
        expected_artifact_hash: str | None = None,
    ) -> PersonalizationFitArtifactEnvelope:
        resolved = _output_path(Path(path))
        before = resolved.stat()
        envelope = _load_envelope_file(resolved)
        after = resolved.stat()
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise PersonalizationFitArtifactError(
                "fit artifact changed during readback"
            )
        if expected_scope_id is not None and _text(expected_scope_id) != _text(
            envelope.source_binding.get("scope_id")
        ):
            raise PersonalizationFitArtifactError(
                "fit artifact reader scope mismatch"
            )
        if expected_artifact_hash is not None and _text(expected_artifact_hash) != envelope.artifact_hash:
            raise PersonalizationFitArtifactError(
                "fit artifact reader hash mismatch"
            )
        return envelope


def read_personalization_fit_artifact(
    path: str | Path,
    *,
    expected_scope_id: str | None = None,
    expected_artifact_hash: str | None = None,
) -> PersonalizationFitArtifactEnvelope:
    """供 CLI 與唯讀整合 caller 使用的便利 reader。"""

    return PersonalizationFitArtifactReader.read(
        path,
        expected_scope_id=expected_scope_id,
        expected_artifact_hash=expected_artifact_hash,
    )


def _persist_create_only(
    path: Path,
    envelope: PersonalizationFitArtifactEnvelope,
) -> str:
    """以 atomic、不可覆寫方式發布一份完整 envelope。"""

    resolved = _output_path(path)
    payload = _canonical_envelope_bytes(envelope)
    if resolved.exists():
        existing = _load_envelope_file(resolved)
        if existing.to_dict() == envelope.to_dict():
            return "idempotent_retry"
        raise PersonalizationFitArtifactError(
            "fit artifact output exists with a different hash-bound payload"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            dir=str(resolved.parent),
        )
        temporary = Path(temporary_name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            # 完整 bytes 在 temporary inode 完成 durable fsync 前，不發布 final name。
            os.fsync(stream.fileno())
        temp_envelope = _load_envelope_file(temporary)
        if temp_envelope.to_dict() != envelope.to_dict():
            raise PersonalizationFitArtifactError(
                "fit artifact temporary readback mismatch"
            )
        try:
            # hard-link 發布是 atomic 且 create-only；與 os.replace 不同，
            # 不會覆寫並行建立的 final artifact。
            os.link(temporary, resolved)
        except FileExistsError:
            existing = _load_envelope_file(resolved)
            if existing.to_dict() == envelope.to_dict():
                return "idempotent_retry"
            raise PersonalizationFitArtifactError(
                "fit artifact output was concurrently created with a different payload"
            )
        # POSIX 額外 flush directory entry；Windows 沒有可攜式 directory fsync，
        # 仍先完成 file fsync 再發布，最後以 readback 驗證 final bytes。
        if os.name != "nt":
            try:
                directory_fd = os.open(str(resolved.parent), os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        final_envelope = PersonalizationFitArtifactReader.read(
            resolved,
            expected_artifact_hash=envelope.artifact_hash,
        )
        if final_envelope.to_dict() != envelope.to_dict():
            raise PersonalizationFitArtifactError(
                "fit artifact final readback mismatch"
            )
        return "created"
    except OSError as exc:
        raise PersonalizationFitArtifactError(
            f"fit artifact publication failed: {type(exc).__name__}"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


class PersonalizationFitRunner:
    """Run one bounded real-source fit against injected read-only adapters."""

    def __init__(
        self,
        read_service: PersonalizationReadService,
        *,
        evaluator: PersonalizationCalibrationEvaluator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.read_service = read_service
        self.evaluator = evaluator or PersonalizationCalibrationEvaluator()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, request: PersonalizationFitRequest) -> PersonalizationFitRunResult:
        try:
            report = self.read_service.inspect_scope(
                scope_id=request.scope_id,
                evaluated_as_of=request.evaluated_as_of,
                evaluation_cutoff_at=request.evaluation_cutoff_at,
                result_id=request.result_id,
                stock_code=request.stock_code,
            )
        except Exception as exc:  # noqa: BLE001 - blocked source diagnostics are the contract
            return _blocked_result(
                request,
                reason="read_source_failed",
                diagnostics=(f"read_source_failed:{type(exc).__name__}",),
            )

        base_diagnostics = list(report.diagnostics)
        if report.source_consistency_status != "verified" or not report.source_bytes_unchanged:
            return _blocked_result(
                request,
                reason="source_consistency_invalidated",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(report.evaluation_rows),
                diagnostics=(*base_diagnostics, "fit_not_persisted:source_consistency_invalidated"),
            )
        if report.source_completeness_status != "verified":
            return _blocked_result(
                request,
                reason="source_completeness_incomplete",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(report.evaluation_rows),
                diagnostics=(*base_diagnostics, "fit_not_persisted:source_completeness_incomplete"),
            )
        if report.inventory.get("truncated") is True or any(
            item.get("truncated") is True
            for item in report.candidate_inventory.values()
        ):
            return _blocked_result(
                request,
                reason="source_inventory_truncated",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(report.evaluation_rows),
                diagnostics=(*base_diagnostics, "fit_not_persisted:source_inventory_truncated"),
            )

        rows: list[PersonalizationEvaluationRow] = []
        row_errors: list[str] = []
        for index, raw in enumerate(report.evaluation_rows):
            try:
                row = _row_from_mapping(raw)
            except PersonalizationFitArtifactError as exc:
                row_errors.append(f"evaluation_row_invalid:{index}:{type(exc).__name__}")
                continue
            if row.scope_id != request.scope_id:
                row_errors.append(f"scope_mismatch:{row.effective_row_id}")
                continue
            rows.append(row)
        if row_errors:
            return _blocked_result(
                request,
                reason="source_row_contract_invalid",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(report.evaluation_rows),
                diagnostics=(*base_diagnostics, *row_errors),
            )

        fit_candidates = [
            row
            for row in rows
            if date.fromisoformat(row.decision_date)
            <= date.fromisoformat(request.fit_as_of)
        ]
        fit_excluded: Counter[str] = Counter()
        fit_rows: list[PersonalizationEvaluationRow] = []
        for row in fit_candidates:
            reasons = _fit_row_reasons(row, fit_as_of=request.fit_as_of)
            if reasons:
                fit_excluded.update(reasons)
            else:
                fit_rows.append(row)
        if not fit_rows:
            diagnostics = [
                *base_diagnostics,
                "fit_sample_insufficient:no_eligible_rows",
                *(
                    f"fit_excluded:{key}={value}"
                    for key, value in sorted(fit_excluded.items())
                ),
            ]
            return _blocked_result(
                request,
                reason="fit_sample_insufficient",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                diagnostics=diagnostics,
            )

        try:
            fit_rows_resolved = _deduplicate_rows_for_runner(
                fit_rows,
                phase="fit",
            )
        except PersonalizationFitArtifactError as exc:
            return _blocked_result(
                request,
                reason="fit_contract_blocked",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=len(fit_rows),
                diagnostics=(
                    *base_diagnostics,
                    f"fit_contract_blocked:{type(exc).__name__}",
                ),
            )
        if not fit_rows_resolved:
            return _blocked_result(
                request,
                reason="fit_sample_insufficient",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                diagnostics=(*base_diagnostics, "fit_sample_insufficient:no_unique_eligible_rows"),
            )

        first = fit_rows_resolved[0]
        policy = PersonalizationCalibrationPolicy(
            horizon_days=first.horizon_days,
            cost_scenario_hash=first.cost_scenario_hash,
            shrinkage_strength=request.shrinkage_strength,
            probability_bin_edges_bp=DEFAULT_PROBABILITY_BIN_EDGES_BP,
            universe_policy_hash=first.universe_policy_hash,
            label_contract_id=first.label_contract_id,
            embargo_days=request.embargo_days,
            scope_id=request.scope_id,
            source_id=first.source_id,
            model_id=first.model_id,
            dataset_id=first.dataset_id,
            dataset_hash=first.dataset_hash,
            receipt_schema_version=first.prediction_receipt_schema_version,
            return_basis=first.return_basis,
            allowed_outcome_tiers=(first.outcome_tier,),
        )
        embargo_days = int(policy.embargo_days or 0)
        purge_cutoff = date.fromisoformat(request.fit_as_of) + timedelta(
            days=embargo_days
        )
        evaluation_rows = [
            row
            for row in rows
            if date.fromisoformat(row.decision_date) > purge_cutoff
        ]
        fit_ids = {
            row.effective_row_id
            for row in fit_rows_resolved
        }
        evaluation_rows = [
            row for row in evaluation_rows if row.effective_row_id not in fit_ids
        ]
        try:
            evaluation_rows_resolved = _deduplicate_rows_for_runner(
                evaluation_rows,
                phase="evaluation",
            )
        except PersonalizationFitArtifactError as exc:
            return _blocked_result(
                request,
                reason="fit_contract_blocked",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=len(fit_rows_resolved),
                fit_decision_date_count=len(
                    {row.decision_date for row in fit_rows_resolved}
                ),
                diagnostics=(
                    *base_diagnostics,
                    f"fit_contract_blocked:{type(exc).__name__}",
                ),
            )
        if any(
            date.fromisoformat(row.decision_date)
            > date.fromisoformat(request.evaluated_as_of)
            for row in evaluation_rows_resolved
        ):
            return _blocked_result(
                request,
                reason="evaluation_scope_after_as_of",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=len(fit_rows_resolved),
                fit_decision_date_count=len(
                    {row.decision_date for row in fit_rows_resolved}
                ),
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=(
                    *base_diagnostics,
                    "fit_not_persisted:evaluation_decision_after_evaluated_as_of",
                ),
            )

        # final file 永不覆寫；若它有效且所有 bound input 完全相同，直接回傳
        # 原 artifact，不以新的 runtime clock 重跑 evaluator。
        existing: PersonalizationFitArtifactEnvelope | None = None
        output_candidate = Path(request.output_path)
        if output_candidate.is_symlink() or output_candidate.exists():
            try:
                existing = _load_envelope_file(output_candidate)
            except PersonalizationFitArtifactError as exc:
                return _blocked_result(
                    request,
                    reason="artifact_output_invalid",
                    source_manifest_hash=report.source_manifest_hash,
                    source_row_count=len(rows),
                    fit_candidate_row_count=len(fit_candidates),
                    fit_row_count=len(fit_rows_resolved),
                    fit_decision_date_count=len(
                        {row.decision_date for row in fit_rows_resolved}
                    ),
                    evaluation_row_count=len(evaluation_rows_resolved),
                    diagnostics=(
                        *base_diagnostics,
                        f"artifact_output_invalid:{type(exc).__name__}",
                    ),
                )

        fit_decision_date_count = len(
            {row.decision_date for row in fit_rows_resolved}
        )
        if existing is not None:
            stored_binding = dict(_thaw(existing.source_binding))
            stored_request = stored_binding.get("request")
            expected_request = _request_binding(
                request,
                created_at=(request.created_at or existing.artifact.created_at),
                effective_embargo_days=int(policy.embargo_days or 0),
            )
            if not isinstance(stored_request, Mapping) or any(
                stored_request.get(key) != value
                for key, value in expected_request.items()
            ):
                return _blocked_result(
                    request,
                    reason="artifact_output_conflict",
                    source_manifest_hash=report.source_manifest_hash,
                    source_row_count=len(rows),
                    fit_candidate_row_count=len(fit_candidates),
                    fit_row_count=existing.artifact.fit_row_count,
                    fit_decision_date_count=fit_decision_date_count,
                    evaluation_row_count=len(evaluation_rows_resolved),
                    diagnostics=(
                        *base_diagnostics,
                        "fit_not_persisted:existing_artifact_request_conflict",
                    ),
                )
            if (
                stored_binding.get("source_manifest_hash")
                != report.source_manifest_hash
                or stored_binding.get("source_fingerprints")
                != [dict(item) for item in report.source_fingerprints]
                or tuple(stored_binding.get("fit_row_ids", ()))
                != tuple(existing.artifact.fit_row_ids)
                or stored_binding.get("fit_row_fingerprint")
                != _hash_rows(fit_rows_resolved)
                or tuple(stored_binding.get("evaluation_row_ids", ()))
                != tuple(row.effective_row_id for row in evaluation_rows_resolved)
                or stored_binding.get("evaluation_row_fingerprint")
                != _hash_rows(evaluation_rows_resolved)
            ):
                return _blocked_result(
                    request,
                    reason="artifact_source_conflict",
                    source_manifest_hash=report.source_manifest_hash,
                    source_row_count=len(rows),
                    fit_candidate_row_count=len(fit_candidates),
                    fit_row_count=existing.artifact.fit_row_count,
                    fit_decision_date_count=fit_decision_date_count,
                    evaluation_row_count=len(evaluation_rows_resolved),
                    diagnostics=(
                        *base_diagnostics,
                        "fit_not_persisted:existing_artifact_source_conflict",
                    ),
                )
            stored_evaluation = stored_binding.get("evaluation")
            stored_fit_decision_date_count = stored_binding.get(
                "fit_decision_date_count"
            )
            if (
                isinstance(stored_fit_decision_date_count, bool)
                or not isinstance(stored_fit_decision_date_count, int)
            ):
                return _blocked_result(
                    request,
                    reason="artifact_output_invalid",
                    source_manifest_hash=report.source_manifest_hash,
                    source_row_count=len(rows),
                    fit_candidate_row_count=len(fit_candidates),
                    fit_row_count=existing.artifact.fit_row_count,
                    fit_decision_date_count=fit_decision_date_count,
                    evaluation_row_count=len(evaluation_rows_resolved),
                    diagnostics=(
                        *base_diagnostics,
                        "fit_not_persisted:existing_artifact_fit_date_count_invalid",
                    ),
                )
            return PersonalizationFitRunResult(
                status="idempotent_retry",
                blocked_reason="",
                scope_id=request.scope_id,
                fit_as_of=request.fit_as_of,
                evaluated_as_of=request.evaluated_as_of,
                evaluation_cutoff_at=request.evaluation_cutoff_at,
                output_path=str(request.output_path),
                artifact_path=str(request.output_path),
                artifact_id=existing.artifact.artifact_id,
                artifact_hash=existing.artifact_hash,
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=existing.artifact.fit_row_count,
                fit_decision_date_count=stored_fit_decision_date_count,
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=tuple(
                    dict.fromkeys(
                        [
                            *base_diagnostics,
                            "retrospective_evaluation_only",
                            "immutable_artifact_reused",
                        ]
                    )
                ),
                evaluation=(
                    dict(stored_evaluation)
                    if isinstance(stored_evaluation, Mapping)
                    else None
                ),
            )

        created_at = request.created_at or _stable_created_at(now=self.clock)
        try:
            artifact = self.evaluator.fit(
                fit_rows_resolved,
                fit_as_of=request.fit_as_of,
                policy=policy,
                artifact_id=request.artifact_id,
                created_at=created_at,
            )
            evaluation = self.evaluator.evaluate(
                artifact,
                evaluation_rows_resolved,
                evaluated_as_of=request.evaluated_as_of,
                evaluation_cutoff_at=request.evaluation_cutoff_at,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed before persistence
            return _blocked_result(
                request,
                reason="fit_contract_blocked",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=len(fit_rows_resolved),
                fit_decision_date_count=fit_decision_date_count,
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=(
                    *base_diagnostics,
                    *(
                        f"fit_excluded:{key}={value}"
                        for key, value in sorted(fit_excluded.items())
                    ),
                    f"fit_contract_blocked:{type(exc).__name__}",
                ),
            )

        # 只用 evaluator 實際接受並寫入 artifact 的 row 計算日期數，避免
        # 被候選列或 evaluator 內部拒絕的 cohort 影響 research gate。
        accepted_fit_rows = {
            row.effective_row_id: row for row in fit_rows_resolved
        }
        accepted_fit_ids = tuple(
            row_id
            for row_id in artifact.fit_row_ids
            if row_id in accepted_fit_rows
        )
        accepted_fit_decision_dates = {
            accepted_fit_rows[row_id].decision_date for row_id in accepted_fit_ids
        }
        if len(accepted_fit_ids) != artifact.fit_row_count:
            return _blocked_result(
                request,
                reason="fit_contract_blocked",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=artifact.fit_row_count,
                fit_decision_date_count=len(accepted_fit_decision_dates),
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=(
                    *base_diagnostics,
                    "fit_contract_blocked:artifact_fit_row_not_in_source",
                ),
            )
        fit_decision_date_count = len(accepted_fit_decision_dates)

        if artifact.fit_row_count < request.min_fit_rows:
            return _blocked_result(
                request,
                reason="fit_sample_insufficient",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=artifact.fit_row_count,
                fit_decision_date_count=fit_decision_date_count,
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=(
                    *base_diagnostics,
                    *(
                        f"fit_excluded:{key}={value}"
                        for key, value in sorted(fit_excluded.items())
                    ),
                    f"fit_min_rows:{request.min_fit_rows}",
                    f"fit_actual_rows:{artifact.fit_row_count}",
                ),
            )
        if fit_decision_date_count < request.min_fit_decision_dates:
            return _blocked_result(
                request,
                reason="fit_sample_insufficient",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=artifact.fit_row_count,
                fit_decision_date_count=fit_decision_date_count,
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=(
                    *base_diagnostics,
                    *(
                        f"fit_excluded:{key}={value}"
                        for key, value in sorted(fit_excluded.items())
                    ),
                    f"fit_min_decision_dates:{request.min_fit_decision_dates}",
                    f"fit_actual_decision_dates:{fit_decision_date_count}",
                ),
            )

        source_fingerprints = [dict(item) for item in report.source_fingerprints]
        effective_created_at = artifact.created_at
        evaluation_cutoff_datetime = parse_aware_datetime(
            request.evaluation_cutoff_at,
            "evaluation_cutoff_at",
        )
        created_datetime = parse_aware_datetime(
            effective_created_at,
            "created_at",
        )
        source_binding: dict[str, Any] = {
            "schema_version": PERSONALIZATION_FIT_ARTIFACT_ENVELOPE_SCHEMA_VERSION,
            "scope_id": request.scope_id,
            "fit_as_of": request.fit_as_of,
            "evaluated_as_of": request.evaluated_as_of,
            "evaluation_cutoff_at": request.evaluation_cutoff_at,
            "request": _request_binding(
                request,
                created_at=effective_created_at,
                effective_embargo_days=int(policy.embargo_days or 0),
            ),
            "fit_creation_clock": (
                "runtime_utc" if request.created_at is None else "caller_supplied"
            ),
            "evaluation_temporal_semantics": {
                "mode": "retrospective_offline",
                "prospective": False,
                "natural_forward_credit": False,
                "evaluated_as_of": request.evaluated_as_of,
                "evaluation_cutoff_at": request.evaluation_cutoff_at,
                "created_after_evaluation_cutoff": created_datetime
                > evaluation_cutoff_datetime,
            },
            "source_manifest_hash": report.source_manifest_hash,
            "source_fingerprints": source_fingerprints,
            "source_bytes_unchanged": report.source_bytes_unchanged,
            "source_consistency_status": report.source_consistency_status,
            "source_completeness_status": report.source_completeness_status,
            "read_report_hash": canonical_payload_hash(report.to_dict()),
            "read_report_denominators": dict(report.denominators),
            "read_report_cohort": dict(report.cohort),
            "read_report_inventory": dict(report.inventory),
            "read_report_diagnostics": list(report.diagnostics),
            "source_row_count": len(rows),
            "fit_candidate_row_count": len(fit_candidates),
            "fit_row_count": artifact.fit_row_count,
            "fit_decision_date_count": fit_decision_date_count,
            "fit_row_ids": list(artifact.fit_row_ids),
            "fit_prediction_ids": list(artifact.fit_prediction_ids),
            "fit_statistical_ids": list(artifact.fit_statistical_ids),
            "fit_receipt_hashes": list(artifact.fit_receipt_hashes),
            "fit_row_fingerprint": artifact.fit_row_fingerprint,
            "evaluation_row_ids": [
                row.effective_row_id for row in evaluation_rows_resolved
            ],
            "evaluation_row_count": len(evaluation_rows_resolved),
            "evaluation_prediction_ids": [
                row.prediction_id for row in evaluation_rows_resolved
            ],
            "evaluation_statistical_ids": [
                row.effective_statistical_id for row in evaluation_rows_resolved
            ],
            "evaluation_row_fingerprint": _hash_rows(evaluation_rows_resolved),
            "evaluation": evaluation.to_dict(),
            "fit_excluded_reason_counts": dict(fit_excluded),
        }
        envelope = PersonalizationFitArtifactEnvelope.create(
            artifact=artifact,
            source_binding=source_binding,
        )
        try:
            persistence_status = _persist_create_only(request.output_path, envelope)
            readback = PersonalizationFitArtifactReader.read(
                request.output_path,
                expected_scope_id=request.scope_id,
                expected_artifact_hash=envelope.artifact_hash,
            )
        except PersonalizationFitArtifactError as exc:
            return _blocked_result(
                request,
                reason="artifact_persistence_blocked",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=artifact.fit_row_count,
                fit_decision_date_count=fit_decision_date_count,
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=(
                    *base_diagnostics,
                    f"artifact_persistence_blocked:{type(exc).__name__}",
                ),
            )
        if readback.to_dict() != envelope.to_dict():
            return _blocked_result(
                request,
                reason="artifact_readback_mismatch",
                source_manifest_hash=report.source_manifest_hash,
                source_row_count=len(rows),
                fit_candidate_row_count=len(fit_candidates),
                fit_row_count=artifact.fit_row_count,
                fit_decision_date_count=fit_decision_date_count,
                evaluation_row_count=len(evaluation_rows_resolved),
                diagnostics=(*base_diagnostics, "fit_not_persisted:artifact_readback_mismatch"),
            )
        return PersonalizationFitRunResult(
            status=persistence_status,
            blocked_reason="",
            scope_id=request.scope_id,
            fit_as_of=request.fit_as_of,
            evaluated_as_of=request.evaluated_as_of,
            evaluation_cutoff_at=request.evaluation_cutoff_at,
            output_path=str(request.output_path),
            artifact_path=str(request.output_path),
            artifact_id=artifact.artifact_id,
            artifact_hash=envelope.artifact_hash,
            source_manifest_hash=report.source_manifest_hash,
            source_row_count=len(rows),
            fit_candidate_row_count=len(fit_candidates),
            fit_row_count=artifact.fit_row_count,
            fit_decision_date_count=fit_decision_date_count,
            evaluation_row_count=len(evaluation_rows_resolved),
            diagnostics=tuple(
                dict.fromkeys(
                    [
                        *base_diagnostics,
                        "retrospective_evaluation_only",
                        *(
                            f"fit_excluded:{key}={value}"
                            for key, value in sorted(fit_excluded.items())
                        ),
                    ]
                )
            ),
            evaluation=evaluation.to_dict(),
        )


def run_personalization_fit(
    request: PersonalizationFitRequest,
    *,
    read_service: PersonalizationReadService,
) -> PersonalizationFitRunResult:
    """Convenience wrapper used by tests and the explicit CLI."""

    return PersonalizationFitRunner(read_service).run(request)


__all__ = [
    "DEFAULT_MIN_FIT_DECISION_DATES",
    "DEFAULT_MIN_FIT_ROWS",
    "PERSONALIZATION_FIT_ARTIFACT_ENVELOPE_SCHEMA_VERSION",
    "PERSONALIZATION_FIT_RUNNER_SCHEMA_VERSION",
    "PersonalizationFitArtifactEnvelope",
    "PersonalizationFitArtifactReader",
    "PersonalizationFitArtifactError",
    "PersonalizationFitRequest",
    "PersonalizationFitRunResult",
    "PersonalizationFitRunner",
    "read_personalization_fit_artifact",
    "run_personalization_fit",
]
