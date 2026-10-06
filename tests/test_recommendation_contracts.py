from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, dataclass, fields
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from types import MappingProxyType

import pytest

from app_module.recommendation.contracts import (
    EXECUTION_SCHEMA_REVISION,
    SUPPORTED_EXECUTION_SCHEMA_REVISIONS,
    Context,
    ExecutionEvent,
    ExecutionStatus,
    IndexStatus,
    MLAvailability,
    MLAvailabilityReason,
    MLAvailabilityStatus,
    MLReceiptBinding,
    RecommendationConfigSnapshot,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    RecommendationUniverseIdentity,
    QualityReport,
    QualityStatus,
    RecommendationExecution,
    ReferenceKind,
    Request,
    SaveReceipt,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
    StrategyConfigIdentity,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
    VersionReference,
    schema_version,
)
from data_module.contracts import SourceRef
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FactorContribution,
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
    RecommendationItem,
    RegimeStateTransition,
    UniverseReference,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESULT_ID = "rec_00000000-0000-0000-0000-000000000001"


class MutableHoursTZ(tzinfo):
    """測試可變時區別名在契約封存後不再影響結果。"""

    def __init__(self, hours: int) -> None:
        self.hours = hours

    def utcoffset(self, dt: datetime | None) -> timedelta:
        del dt
        return timedelta(hours=self.hours)

    def dst(self, dt: datetime | None) -> timedelta:
        del dt
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        del dt
        return f"mutable-{self.hours}"


class MutablePayloadDelta(timedelta):
    """帶 caller-owned 狀態的 timedelta 子類，用來檢查 offset 深複製。"""

    payload: list[str]

    @property
    def days(self) -> int:
        return -1

    def __new__(
        cls,
        hours: int,
        payload: list[str],
        *,
        seconds: int = 0,
        microseconds: int = 0,
    ) -> MutablePayloadDelta:
        value = super().__new__(
            cls,
            hours=hours,
            seconds=seconds,
            microseconds=microseconds,
        )
        value.payload = payload
        return value


class MutablePayloadTZ(tzinfo):
    def __init__(self, offset: timedelta) -> None:
        self.offset = offset

    def utcoffset(self, dt: datetime | None) -> timedelta:
        del dt
        return self.offset

    def dst(self, dt: datetime | None) -> timedelta:
        del dt
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        del dt
        return "mutable-payload"


class MutableTimezoneName(str):
    """可由 caller 修改附帶狀態的時區名稱子類。"""

    labels: list[str]

    def __new__(cls, value: str) -> MutableTimezoneName:
        name = super().__new__(cls, value)
        name.labels = []
        return name

    def __repr__(self) -> str:
        return f"MutableTimezoneName({str.__repr__(self)}, labels={self.labels!r})"


def _item(stock_code: str = "2330", score: Decimal | int | None = Decimal("9.250")) -> RecommendationItem:
    return RecommendationItem(
        stock_code=stock_code,
        rule_score=score,
        factor_contributions=(
            FactorContribution("trend", Decimal("1.2500"), "rule-score", "v1"),
        ),
        rank=1,
        universe_ref=UniverseReference(
            policy_id="listed-active-v1",
            snapshot_id="twse-20260921",
            as_of_date=date(2026, 9, 21),
        ),
        reasons=("趨勢條件成立",),
        confidence=Decimal("0.8750"),
    )


def _execution(
    *,
    result_id: str = RESULT_ID,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    decision: DecisionBatch | None = None,
    request: Request | None = None,
    context: Context | None = None,
    ml_availability: MLAvailability | None = None,
    ml_projection_refs: tuple[VersionReference, ...] = (),
    ml_receipt_refs: tuple[MLReceiptBinding, ...] = (),
    failure_reason: str | None = None,
) -> RecommendationExecution:
    return RecommendationExecution(
        result_id=result_id,
        request=request or Request(as_of_date=date(2026, 9, 21)),
        context=context
        or Context(
            as_of_date=date(2026, 9, 21),
            decision_at=datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc),
        ),
        status=status,
        decision=DecisionBatch(items=(_item(),)) if decision is None and status is ExecutionStatus.COMPLETED else decision,
        ml_availability=ml_availability if ml_availability is not None else MLAvailability(),
        ml_projection_refs=ml_projection_refs,
        ml_receipt_refs=ml_receipt_refs,
        failure_reason=failure_reason,
    )


def _receipt_binding(
    *,
    receipt_id: str = "receipt-1",
    receipt_hash: str = "sha256:" + "a" * 64,
    result_id: str = RESULT_ID,
    decision_date: date = date(2026, 9, 21),
    model_candidate_id: str = "model-candidate-1",
    projected_stock_codes: tuple[str, ...] = ("2330",),
    cost_scenario_hash: str | None = "sha256:" + "b" * 64,
) -> MLReceiptBinding:
    return MLReceiptBinding(
        receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, receipt_id),
        receipt_hash=receipt_hash,
        result_id=result_id,
        decision_date=decision_date,
        model_candidate_id=model_candidate_id,
        projected_stock_codes=projected_stock_codes,
        cost_scenario_hash=cost_scenario_hash,
    )


def test_decision_records_freeze_nested_inputs_and_keep_order() -> None:
    reason_rows = ["原始原因"]
    evidence_values = ["尚未公告"]
    backing = {"nested": {"reasons": evidence_values}}
    mapping_proxy = MappingProxyType(backing)
    filter_outcome = FilterOutcome("liquidity", None, evidence=mapping_proxy)
    assessment_filters = {"liquidity": filter_outcome}
    negative = NegativeEvidence(
        "missing-volume",
        "成交量資料未提供",
        source_refs=[SourceRef("market-db", "rev-2", "snapshot-20260921")],
        details={"missing": True},
    )
    candidate_reasons = ["資料不足，保留為未知"]
    missing_data = ["turnover"]
    assessments = [
        CandidateAssessment(
            stock_code="2330",
            eligible=None,
            filter_outcomes=assessment_filters,
            negative_evidence=[negative],
            reasons=candidate_reasons,
            liquidity=LiquidityAssessment(
                acceptable=None,
                reasons=["缺少流動性觀測"],
                missing_data=missing_data,
                observations={"amount": None, "samples": 0},
            ),
        )
    ]
    item_reasons = ["規則理由"]
    contributions = [FactorContribution("momentum", 0, "rule-score", "v1")]
    items = [
        RecommendationItem(
            "2330",
            rule_score=0,
            factor_contributions=contributions,
            reasons=item_reasons,
        ),
        RecommendationItem("2317", rule_score=Decimal("1.00"), reasons=["第二列"]),
    ]
    batch = DecisionBatch(
        items=items,
        assessments=assessments,
        regime="trend",
        state_transition=RegimeStateTransition(
            previous_state="range",
            next_state="trend",
            transition_date=date(2026, 9, 21),
            reasons=["連續確認"],
        ),
    )

    reason_rows.append("輸入後續追加")
    evidence_values[0] = "輸入後續改寫"
    backing["new"] = "輸入後續新增"
    assessment_filters.clear()
    candidate_reasons.append("輸入後續追加")
    missing_data.clear()
    assessments.clear()
    item_reasons.append("輸入後續追加")
    contributions.clear()
    items.clear()

    assert [item.stock_code for item in batch.items] == ["2330", "2317"]
    assert batch.items[0].reasons == ("規則理由",)
    assert batch.items[0].factor_contributions[0].value == 0
    assert batch.assessments[0].reasons == ("資料不足，保留為未知",)
    assert batch.assessments[0].filter_outcomes["liquidity"].evidence["nested"]["reasons"] == (
        "尚未公告",
    )
    assert batch.assessments[0].liquidity.observations["amount"] is None
    assert batch.assessments[0].liquidity.observations["samples"] == 0
    with pytest.raises(TypeError):
        batch.assessments[0].filter_outcomes["other"] = filter_outcome  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        batch.items[0].stock_code = "9999"  # type: ignore[misc]


def test_mappingproxy_input_is_copied_before_sealing() -> None:
    nested = {"sequence": ["before"]}
    backing = {"nested": nested}
    proxy = MappingProxyType(backing)
    quality = QualityReport(QualityStatus.DEGRADED, metrics=proxy)

    nested["sequence"].append("after")
    backing["added"] = "after"

    assert quality.metrics["nested"]["sequence"] == ("before",)
    assert "added" not in quality.metrics
    with pytest.raises(TypeError):
        quality.metrics["new"] = 1  # type: ignore[index]

    ml_outcome = MLAvailability(
        MLAvailabilityStatus.UNAVAILABLE,
        MLAvailabilityReason.SCHEMA_MISMATCH,
        "feature schema differs",
    )
    outcome_quality = QualityReport(metrics={"ml_outcome": ml_outcome})
    assert outcome_quality.metrics["ml_outcome"] is ml_outcome


def test_arbitrary_enum_with_mutable_payload_is_rejected() -> None:
    class MutablePayloadEnum(Enum):
        VALUE = "value"

        def __init__(self, _: str) -> None:
            self.payload = []

    member = MutablePayloadEnum.VALUE
    member.payload.append("mutable")

    with pytest.raises(TypeError, match="明示允許的 enum"):
        QualityReport(metrics={"enum": member})
    with pytest.raises(TypeError, match="明示允許的 enum"):
        ExecutionEvent("test", "測試", details={"enum": member})


def test_application_records_deep_freeze_inputs_and_delegate_decision_fields() -> None:
    request = Request(
        as_of_date=date(2026, 9, 21),
        config_ref=VersionReference(ReferenceKind.CONFIG, "config-1", "v3"),
        profile_ref=VersionReference(ReferenceKind.PROFILE, "profile-1", "v2"),
    )
    source_refs = [SourceRef("twse", 7, "close-20260921")]
    data_refs = [VersionReference(ReferenceKind.DATA_SNAPSHOT, "market-20260921")]
    warnings = ["一筆資料降級"]
    context = Context(
        as_of_date=date(2026, 9, 21),
        decision_at=datetime(2026, 9, 21, 14, 30, 0, 123456, tzinfo=timezone(timedelta(hours=8))),
        source_refs=source_refs,
        data_snapshot_refs=data_refs,
        config_ref=VersionReference(ReferenceKind.CONFIG, "config-1", "v3"),
        input_quality=QualityReport(QualityStatus.DEGRADED, warnings=warnings),
    )
    details = {"counts": [1, 0], "unknown": None}
    decision = DecisionBatch(
        items=[_item("2330", Decimal("0"))],
        assessments=[CandidateAssessment("2330", eligible=True)],
    )
    events = [ExecutionEvent("decision.completed", "完成", details=details)]
    execution = _execution(
        decision=decision,
        request=request,
        context=context,
    )
    execution = RecommendationExecution(
        result_id=execution.result_id,
        request=execution.request,
        context=execution.context,
        status=execution.status,
        decision=execution.decision,
        events=events,
        related_references=(
            VersionReference(ReferenceKind.REPLAY_PARENT, "rec_00000000-0000-0000-0000-000000000002"),
            VersionReference(ReferenceKind.PORTFOLIO_RESULT, "portfolio-1"),
        ),
        ml_projection_refs=(VersionReference(ReferenceKind.ML_PROJECTION, "projection-1"),),
        ml_receipt_refs=(_receipt_binding(),),
    )

    source_refs.clear()
    data_refs.clear()
    warnings.append("輸入後續追加")
    details["counts"].append(9)
    events.clear()

    assert request.config_ref == VersionReference(ReferenceKind.CONFIG, "config-1", "v3")
    assert request.profile_ref == VersionReference(ReferenceKind.PROFILE, "profile-1", "v2")
    assert context.source_refs == (SourceRef("twse", 7, "close-20260921"),)
    assert context.data_snapshot_refs[0].reference_id == "market-20260921"
    assert context.decision_at.microsecond == 123456
    assert context.input_quality.warnings == ("一筆資料降級",)
    assert execution.events[0].details["counts"] == (1, 0)
    assert execution.events[0].details["unknown"] is None
    assert execution.items is execution.decision.items
    assert execution.assessments is execution.decision.assessments
    assert execution.items[0].rule_score == Decimal("0")
    assert execution.ml_projection_refs[0].kind is ReferenceKind.ML_PROJECTION
    assert execution.related_references[0].kind is ReferenceKind.REPLAY_PARENT
    for disallowed_kind in (
        ReferenceKind.CONFIG,
        ReferenceKind.ML_PROJECTION,
        ReferenceKind.ML_RECEIPT,
    ):
        with pytest.raises(ValueError, match="related_references"):
            RecommendationExecution(
                result_id=RESULT_ID,
                request=request,
                context=context,
                status=ExecutionStatus.COMPLETED,
                decision=decision,
                related_references=(VersionReference(disallowed_kind, "reference-1"),),
            )
    with pytest.raises(TypeError):
        execution.events[0].details["counts"] = (5,)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        execution.context.decision_at = None  # type: ignore[misc]

    stored_fields = {item.name for item in fields(RecommendationExecution)}
    assert "items" not in stored_fields
    assert "assessments" not in stored_fields
    assert "options" not in {item.name for item in fields(Request)}


def test_application_contracts_snapshot_mutable_tzinfo_aliases_recursively() -> None:
    mutable_tz = MutableHoursTZ(0)
    input_clock = datetime(
        2026, 9, 21, 14, 30, 0, 654321, tzinfo=mutable_tz, fold=1
    )
    expected = {
        "offset": input_clock.utcoffset(),
        "iso": input_clock.isoformat(),
        "timestamp": input_clock.timestamp(),
        "wall_clock": (
            input_clock.year,
            input_clock.month,
            input_clock.day,
            input_clock.hour,
            input_clock.minute,
            input_clock.second,
            input_clock.microsecond,
        ),
        "fold": input_clock.fold,
    }

    quality = QualityReport(
        metrics={
            "clock": input_clock,
            "nested": [{"source_path": input_clock}],
        }
    )
    context = Context(decision_at=input_clock, input_quality=quality)
    event = ExecutionEvent(
        "source.loaded",
        "來源已載入",
        occurred_at=input_clock,
        details={"source_path": [{"clock": input_clock}]},
    )
    negative = NegativeEvidence(
        "source-clock",
        "來源時間快照",
        source_refs=[SourceRef("market", "revision-1")],
        observed_at=input_clock,
        details={"source_path": [{"clock": input_clock}]},
    )
    decision = DecisionBatch(
        assessments=[
            CandidateAssessment(
                "2330", eligible=False, negative_evidence=[negative]
            )
        ]
    )
    execution = _execution(decision=decision)
    receipt = SaveReceipt(
        result_id=RESULT_ID,
        payload_hash="sha256:" + "c" * 64,
        artifact_location="artifacts/recommendation/record.json",
        persisted_at=input_clock,
        index_status=IndexStatus.INDEXED,
    )

    sealed_clocks = (
        context.decision_at,
        context.input_quality.metrics["clock"],
        context.input_quality.metrics["nested"][0]["source_path"],
        event.occurred_at,
        event.details["source_path"][0]["clock"],
        execution.decision.assessments[0].negative_evidence[0].observed_at,
        execution.decision.assessments[0].negative_evidence[0].details[
            "source_path"
        ][0]["clock"],
        receipt.persisted_at,
    )

    mutable_tz.hours = 9

    assert input_clock.utcoffset() == timedelta(hours=9)
    for sealed_clock in sealed_clocks:
        assert sealed_clock is not input_clock
        assert sealed_clock.tzinfo is not mutable_tz
        assert type(sealed_clock.tzinfo) is timezone
        assert sealed_clock.utcoffset() == expected["offset"]
        assert sealed_clock.isoformat() == expected["iso"]
        assert sealed_clock.timestamp() == expected["timestamp"]
        assert (
            sealed_clock.year,
            sealed_clock.month,
            sealed_clock.day,
            sealed_clock.hour,
            sealed_clock.minute,
            sealed_clock.second,
            sealed_clock.microsecond,
        ) == expected["wall_clock"]
        assert sealed_clock.fold == expected["fold"]


def test_utc_and_fixed_offset_datetime_inputs_keep_their_existing_tzinfo() -> None:
    for existing_tz in (timezone.utc, timezone(timedelta(hours=8))):
        input_clock = datetime(2026, 9, 21, 14, 30, tzinfo=existing_tz)
        assert Context(decision_at=input_clock).decision_at is input_clock


def test_timedelta_subclass_payload_is_removed_from_sealed_clock_offsets() -> None:
    payload = ["封存前"]
    mutable_offset = MutablePayloadDelta(
        5, payload, seconds=17, microseconds=231
    )
    custom_clock = datetime(
        2026, 9, 21, 14, 30, 0, 654321,
        tzinfo=MutablePayloadTZ(mutable_offset),
        fold=1,
    )
    builtin_timezone_clock = datetime(
        2026, 9, 21, 14, 30, 0, 654321,
        tzinfo=timezone(mutable_offset, "named-fixed-offset"),
        fold=1,
    )
    expected_clock = datetime(
        2026,
        9,
        21,
        14,
        30,
        0,
        654321,
        tzinfo=timezone(timedelta(hours=5, seconds=17, microseconds=231)),
        fold=1,
    )
    expected_iso = expected_clock.isoformat()
    expected_timestamp = expected_clock.timestamp()
    assert mutable_offset.days == -1
    assert timedelta.days.__get__(mutable_offset) == 0

    context = Context(decision_at=custom_clock)
    event = ExecutionEvent("clock.observed", "觀測時間", occurred_at=custom_clock)
    quality = QualityReport(metrics={"clock": custom_clock})
    receipt = SaveReceipt(
        result_id=RESULT_ID,
        payload_hash="sha256:" + "d" * 64,
        artifact_location=None,
        persisted_at=builtin_timezone_clock,
        index_status=IndexStatus.INDEXED,
    )
    sealed_clocks = (
        context.decision_at,
        event.occurred_at,
        quality.metrics["clock"],
        receipt.persisted_at,
    )

    payload.append("封存後修改")

    assert mutable_offset.payload == ["封存前", "封存後修改"]
    assert receipt.persisted_at.tzname() == "named-fixed-offset"
    for sealed_clock in sealed_clocks:
        sealed_offset = sealed_clock.utcoffset()
        assert type(sealed_offset) is timedelta
        assert not hasattr(sealed_offset, "payload")
        assert sealed_offset == timedelta(hours=5, seconds=17, microseconds=231)
        assert sealed_clock.isoformat() == expected_iso
        assert sealed_clock.timestamp() == expected_timestamp
        assert sealed_clock.fold == 1


def test_timezone_name_subclass_is_copied_in_direct_and_nested_clocks() -> None:
    caller_name = MutableTimezoneName("caller-zone")
    source_timezone = timezone(timedelta(hours=5), caller_name)
    input_clock = datetime(
        2026, 9, 21, 14, 30, 0, 654321, tzinfo=source_timezone, fold=1
    )
    expected_clock = datetime(
        2026, 9, 21, 14, 30, 0, 654321,
        tzinfo=timezone(timedelta(hours=5), "caller-zone"),
        fold=1,
    )
    quality = QualityReport(
        metrics={
            "clock": input_clock,
            "source_path": [{"clock": input_clock}],
        }
    )
    context = Context(decision_at=input_clock, input_quality=quality)
    event = ExecutionEvent(
        "clock.observed",
        "觀測時間",
        occurred_at=input_clock,
        details={"source_path": [{"clock": input_clock}]},
    )
    receipt = SaveReceipt(
        result_id=RESULT_ID,
        payload_hash="sha256:" + "e" * 64,
        artifact_location=None,
        persisted_at=input_clock,
        index_status=IndexStatus.INDEXED,
    )
    sealed_clocks = (
        context.decision_at,
        quality.metrics["clock"],
        quality.metrics["source_path"][0]["clock"],
        event.occurred_at,
        event.details["source_path"][0]["clock"],
        receipt.persisted_at,
    )
    original_repr = repr(input_clock)
    sealed_reprs = tuple(repr(value) for value in sealed_clocks)

    assert source_timezone.tzname(None) is caller_name
    for sealed_clock in sealed_clocks:
        assert sealed_clock.tzname() == "caller-zone"
        assert type(sealed_clock.tzname()) is str
        assert sealed_clock.tzname() is not caller_name
        assert sealed_clock.utcoffset() == timedelta(hours=5)
        assert sealed_clock.isoformat() == expected_clock.isoformat()
        assert sealed_clock.timestamp() == expected_clock.timestamp()
        assert sealed_clock.fold == 1

    caller_name.labels.append("caller mutation")

    assert input_clock.tzname() is caller_name
    assert input_clock.tzname().labels == ["caller mutation"]
    assert repr(input_clock) != original_repr
    assert tuple(repr(value) for value in sealed_clocks) == sealed_reprs
    for sealed_clock in sealed_clocks:
        assert sealed_clock.tzname() == "caller-zone"
        assert type(sealed_clock.tzname()) is str
        assert not hasattr(sealed_clock.tzname(), "labels")
        assert sealed_clock.utcoffset() == timedelta(hours=5)
        assert sealed_clock.isoformat() == expected_clock.isoformat()
        assert sealed_clock.timestamp() == expected_clock.timestamp()
        assert sealed_clock.fold == 1


def test_execution_status_allows_empty_completion_and_failed_or_cancelled_without_decision() -> None:
    empty_completed = _execution(decision=DecisionBatch())
    assert empty_completed.status is ExecutionStatus.COMPLETED
    assert empty_completed.decision.items == ()
    assert empty_completed.items == ()
    assert empty_completed.ml_availability.status is MLAvailabilityStatus.UNKNOWN
    assert empty_completed.ml_receipt_refs == ()

    with pytest.raises(ValueError, match="completed execution"):
        RecommendationExecution(
            result_id=RESULT_ID,
            request=Request(),
            context=Context(),
            status=ExecutionStatus.COMPLETED,
        )

    for status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        reason = f"{status.value}：明示測試原因"
        outcome = _execution(status=status, decision=None, failure_reason=reason)
        assert outcome.decision is None
        assert outcome.items == ()
        assert outcome.failure_reason == reason

    for status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        with pytest.raises(ValueError, match="不得發布 DecisionBatch"):
            _execution(
                status=status,
                decision=DecisionBatch(items=(_item(),)),
                failure_reason="有原因，但仍不得發布 decision",
            )

    for status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        with pytest.raises(ValueError, match="必須包含非空白 failure_reason"):
            _execution(status=status)
        for blank_reason in ("", " \t\n"):
            with pytest.raises(ValueError, match="failure_reason 不可為空白"):
                _execution(status=status, failure_reason=blank_reason)

    for supplied_reason in ("失敗原因", ""):
        with pytest.raises(ValueError, match="不得包含 failure_reason"):
            _execution(failure_reason=supplied_reason)


def test_ml_availability_is_explicit_and_preserves_absence_reasons() -> None:
    zero_reference_outcomes = (
        MLAvailability(MLAvailabilityStatus.NOT_REQUESTED),
        MLAvailability(MLAvailabilityStatus.UNKNOWN),
        MLAvailability(
            MLAvailabilityStatus.UNAVAILABLE,
            MLAvailabilityReason.MISSING,
            "projection 與 receipt 缺失",
        ),
        MLAvailability(
            MLAvailabilityStatus.UNAVAILABLE,
            MLAvailabilityReason.SCHEMA_MISMATCH,
            "feature schema 不相容",
        ),
        MLAvailability(
            MLAvailabilityStatus.UNAVAILABLE,
            MLAvailabilityReason.QUARANTINED,
            "model release 已 quarantine",
        ),
        MLAvailability(
            MLAvailabilityStatus.UNAVAILABLE,
            MLAvailabilityReason.SOURCE_VERSION_UNAVAILABLE,
            "找不到固定來源版本",
        ),
        MLAvailability(
            MLAvailabilityStatus.BLOCKED,
            MLAvailabilityReason.CUTOFF_UNPROVEN,
            "無法證明來源版本符合 decision cutoff",
        ),
        MLAvailability(
            MLAvailabilityStatus.BLOCKED,
            MLAvailabilityReason.POLICY_BLOCKED,
            "目前 policy 不允許發布 ML projection",
        ),
    )
    for availability in zero_reference_outcomes:
        execution = _execution(decision=DecisionBatch(), ml_availability=availability)
        assert execution.ml_availability is availability
        assert execution.ml_projection_refs == ()
        assert execution.ml_receipt_refs == ()

    unavailable = _execution(decision=DecisionBatch(), ml_availability=zero_reference_outcomes[2])
    assert unavailable.ml_availability.status is MLAvailabilityStatus.UNAVAILABLE
    assert unavailable.ml_availability.reason is MLAvailabilityReason.MISSING
    assert unavailable.ml_availability.reason_detail == "projection 與 receipt 缺失"
    with pytest.raises(FrozenInstanceError):
        unavailable.ml_availability.reason_detail = "被改寫"  # type: ignore[misc]

    failed_with_unknown_availability = _execution(
        status=ExecutionStatus.FAILED,
        failure_reason="明示失敗原因",
    )
    assert failed_with_unknown_availability.ml_availability.status is MLAvailabilityStatus.UNKNOWN
    assert failed_with_unknown_availability.ml_projection_refs == ()
    assert failed_with_unknown_availability.ml_receipt_refs == ()

    projection_ref = VersionReference(ReferenceKind.ML_PROJECTION, "projection-2")
    receipt_binding = _receipt_binding(receipt_id="receipt-2")
    unknown_with_references = _execution(
        decision=DecisionBatch(items=(_item(),)),
        ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
        ml_projection_refs=(projection_ref,),
        ml_receipt_refs=(receipt_binding,),
    )
    assert unknown_with_references.ml_availability.status is MLAvailabilityStatus.UNKNOWN
    assert unknown_with_references.ml_receipt_refs == (receipt_binding,)


def test_ml_receipt_binding_freezes_values_and_checks_known_execution_identity() -> None:
    projected_codes = ["2330"]
    binding = MLReceiptBinding(
        receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, "receipt-valid"),
        receipt_hash="sha256:" + "c" * 64,
        result_id=RESULT_ID,
        decision_date=date(2026, 9, 21),
        model_candidate_id="candidate-exact-1",
        projected_stock_codes=projected_codes,
        cost_scenario_hash=None,
    )
    projected_codes.append("2317")

    assert binding.projected_stock_codes == ("2330",)
    assert binding.receipt_hash == "sha256:" + "c" * 64
    assert binding.cost_scenario_hash is None
    with pytest.raises(FrozenInstanceError):
        binding.model_candidate_id = "changed"  # type: ignore[misc]

    decision = DecisionBatch(
        items=(_item("2330"),),
        assessments=(CandidateAssessment("2317", eligible=None),),
    )
    execution = _execution(
        decision=decision,
        ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
        ml_projection_refs=(VersionReference(ReferenceKind.ML_PROJECTION, "projection-valid"),),
        ml_receipt_refs=(binding,),
    )
    assert execution.ml_availability.status is MLAvailabilityStatus.UNKNOWN
    assert execution.ml_receipt_refs == (binding,)

    unknown_context = Context(as_of_date=None)
    binding_with_known_receipt_date = _receipt_binding(receipt_id="receipt-context-unknown")
    unknown_date_execution = _execution(
        context=unknown_context,
        decision=DecisionBatch(items=(_item(),)),
        ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
        ml_receipt_refs=(binding_with_known_receipt_date,),
    )
    assert unknown_date_execution.context.as_of_date is None
    assert unknown_date_execution.ml_receipt_refs[0].decision_date == date(2026, 9, 21)

    cancelled_after_receipt = _execution(
        status=ExecutionStatus.CANCELLED,
        failure_reason="取消前已留下 receipt 摘要",
        ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
        ml_receipt_refs=(_receipt_binding(receipt_id="receipt-before-cancel"),),
    )
    assert cancelled_after_receipt.decision is None
    assert cancelled_after_receipt.ml_receipt_refs[0].receipt_ref.reference_id == (
        "receipt-before-cancel"
    )
    assert cancelled_after_receipt.ml_availability.status is MLAvailabilityStatus.UNKNOWN


def test_result_ids_preserve_opaque_generated_and_legacy_values_across_contracts(
) -> None:
    resolved_ids = (
        "r002-fixed-001",
        "rec_0123456789abcdef0123456789abcdef",
        "rec_20260921142530",
        "run-20260711",
        "result-1",
        "last-good-result",
        " r002-opaque-001 ",
    )
    for result_id in resolved_ids:
        binding = _receipt_binding(result_id=result_id)
        execution = _execution(
            result_id=result_id,
            ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
            ml_receipt_refs=(binding,),
        )
        receipt = SaveReceipt(
            result_id=result_id,
            payload_hash="sha256:" + "d" * 64,
            artifact_location="artifacts/recommendation/result.json",
            persisted_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
            index_status=IndexStatus.INDEXED,
        )

        assert binding.result_id == result_id
        assert execution.result_id == result_id
        assert execution.ml_receipt_refs[0].result_id == result_id
        assert receipt.result_id == result_id


def test_result_id_rejects_blank_and_non_exact_string_values() -> None:
    for invalid_id in ("", " \t\n"):
        with pytest.raises(ValueError, match="result_id 不可為空白"):
            _execution(result_id=invalid_id)
        with pytest.raises(ValueError, match="result_id 不可為空白"):
            _receipt_binding(result_id=invalid_id)
        with pytest.raises(ValueError, match="result_id 不可為空白"):
            SaveReceipt(
                result_id=invalid_id,
                payload_hash="hash",
                artifact_location=None,
                persisted_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
                index_status=IndexStatus.UNKNOWN,
            )

    for invalid_id in (None, 123, MutableTimezoneName("r002-fixed-001")):
        with pytest.raises(TypeError, match="result_id 必須是 str"):
            _execution(result_id=invalid_id)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="result_id 必須是 str"):
            _receipt_binding(result_id=invalid_id)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="result_id 必須是 str"):
            SaveReceipt(
                result_id=invalid_id,  # type: ignore[arg-type]
                payload_hash="hash",
                artifact_location=None,
                persisted_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
                index_status=IndexStatus.UNKNOWN,
            )


def test_ml_receipt_binding_rejects_invalid_hash_and_duplicate_stock_codes() -> None:
    with pytest.raises(TypeError, match="receipt_hash 必須是 str"):
        _receipt_binding(receipt_hash=None)  # type: ignore[arg-type]
    for empty_stock_codes in ((), []):
        with pytest.raises(ValueError, match="projected_stock_codes 不可為空"):
            MLReceiptBinding(
                receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, "empty-projection"),
                receipt_hash="sha256:" + "a" * 64,
                result_id=RESULT_ID,
                decision_date=date(2026, 9, 21),
                model_candidate_id="candidate-empty",
                projected_stock_codes=empty_stock_codes,  # type: ignore[arg-type]
            )
    for malformed_hash in (
        "",
        "SHA256:" + "a" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "g" * 64,
    ):
        with pytest.raises(ValueError, match="receipt_hash"):
            _receipt_binding(receipt_hash=malformed_hash)

    with pytest.raises(ValueError, match="cost_scenario_hash"):
        _receipt_binding(cost_scenario_hash="sha256:" + "B" * 64)
    with pytest.raises(ValueError, match="projected_stock_codes 不可重複"):
        _receipt_binding(projected_stock_codes=("2330", "2330"))
    with pytest.raises(ValueError, match="model_candidate_id 不可為空白"):
        _receipt_binding(model_candidate_id=" \t ")
    with pytest.raises(ValueError, match="receipt_ref 必須是 ML_RECEIPT"):
        MLReceiptBinding(
            receipt_ref=VersionReference(ReferenceKind.ML_PROJECTION, "wrong-kind"),
            receipt_hash="sha256:" + "a" * 64,
            result_id=RESULT_ID,
            decision_date=date(2026, 9, 21),
            model_candidate_id="candidate-1",
            projected_stock_codes=("2330",),
        )


def test_execution_rejects_receipt_binding_identity_mismatches() -> None:
    decision = DecisionBatch(items=(_item("2330"),))
    for binding, expected_message in (
        (
            _receipt_binding(
                receipt_id="wrong-result",
                result_id="r002-fixed-002",
            ),
            "result_id 必須符合",
        ),
        (
            _receipt_binding(
                receipt_id="wrong-date",
                decision_date=date(2026, 9, 20),
            ),
            "decision_date 必須符合已知 Context.as_of_date",
        ),
        (
            _receipt_binding(
                receipt_id="wrong-stock",
                projected_stock_codes=("2317",),
            ),
            "stock_code 必須屬於 DecisionBatch",
        ),
    ):
        with pytest.raises(ValueError, match=expected_message):
            _execution(
                decision=decision,
                ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
                ml_receipt_refs=(binding,),
            )

    with pytest.raises(ValueError, match="不可重複 receipt reference"):
        _execution(
            decision=decision,
            ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
            ml_receipt_refs=(_receipt_binding(), _receipt_binding()),
        )
    with pytest.raises(TypeError, match="ml_receipt_refs 含有不支援的 record"):
        _execution(
            decision=decision,
            ml_availability=MLAvailability(MLAvailabilityStatus.UNKNOWN),
            ml_receipt_refs=(VersionReference(ReferenceKind.ML_RECEIPT, "unbound"),),  # type: ignore[arg-type]
        )


def test_ml_availability_rejects_inconsistent_status_reason_and_reference_pairs() -> None:
    with pytest.raises(ValueError, match="absence reason"):
        MLAvailability(MLAvailabilityStatus.UNKNOWN, MLAvailabilityReason.MISSING)
    with pytest.raises(ValueError, match="unavailable 必須"):
        MLAvailability(MLAvailabilityStatus.UNAVAILABLE)
    with pytest.raises(ValueError, match="blocked 必須"):
        MLAvailability(MLAvailabilityStatus.BLOCKED)
    with pytest.raises(TypeError, match="MLAvailabilityReason"):
        MLAvailability(MLAvailabilityStatus.UNAVAILABLE, "missing")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not_requested"):
        _execution(
            decision=DecisionBatch(items=(_item(),)),
            ml_availability=MLAvailability(MLAvailabilityStatus.NOT_REQUESTED),
            ml_receipt_refs=(_receipt_binding(receipt_id="old-receipt"),),
        )
    with pytest.raises(ValueError, match="available 必須"):
        _execution(
            decision=DecisionBatch(),
            ml_availability=MLAvailability(MLAvailabilityStatus.AVAILABLE),
        )

    available = _execution(
        decision=DecisionBatch(items=(_item(),)),
        ml_availability=MLAvailability(MLAvailabilityStatus.AVAILABLE),
        ml_projection_refs=(VersionReference(ReferenceKind.ML_PROJECTION, "projection-3"),),
        ml_receipt_refs=(_receipt_binding(receipt_id="receipt-3"),),
    )
    assert available.ml_availability.status is MLAvailabilityStatus.AVAILABLE


def test_duplicate_stock_identity_is_rejected_per_execution_collection() -> None:
    with pytest.raises(ValueError, match="items.*stock_code"):
        DecisionBatch(items=(_item("2330"), _item("2330")))
    with pytest.raises(ValueError, match="assessments.*stock_code"):
        DecisionBatch(
            assessments=(
                CandidateAssessment("2330", True),
                CandidateAssessment("2330", False),
            )
        )


def test_aware_clock_and_schema_receipt_preserve_precision() -> None:
    decision_at = datetime(2026, 9, 21, 8, 1, 2, 456789, tzinfo=timezone(timedelta(hours=8)))
    context = Context(as_of_date=date(2026, 9, 21), decision_at=decision_at)
    assert context.decision_at is decision_at
    with pytest.raises(ValueError, match="時區"):
        Context(decision_at=datetime(2026, 9, 21, 8, 1, 2))
    with pytest.raises(ValueError, match="時區"):
        ExecutionEvent("x", "y", occurred_at=datetime(2026, 9, 21, 8, 1, 2))
    with pytest.raises(ValueError, match="時區"):
        NegativeEvidence(
            "negative-clock",
            "缺少可信時間",
            observed_at=datetime(2026, 9, 21, 8, 1, 2),
        )
    with pytest.raises(TypeError, match="observed_at"):
        NegativeEvidence(
            "invalid-clock",
            "不是 datetime",
            observed_at="2026-09-21T08:01:02+08:00",  # type: ignore[arg-type]
        )

    persisted_at = datetime(2026, 9, 21, 9, 0, 0, 42, tzinfo=timezone.utc)
    receipt = SaveReceipt(
        result_id=RESULT_ID,
        payload_hash="a" * 64,
        artifact_location="artifacts/recommendation/record.json",
        persisted_at=persisted_at,
        index_status=IndexStatus.PENDING,
    )
    assert receipt.persisted_at is persisted_at
    assert receipt.schema_version == "recommendation-execution.v1"
    assert receipt.schema_revision == 2
    assert schema_version == "recommendation-execution.v1"
    assert EXECUTION_SCHEMA_REVISION == 2
    assert SUPPORTED_EXECUTION_SCHEMA_REVISIONS == (1, 2)
    historical_receipt = SaveReceipt(
        result_id=RESULT_ID,
        payload_hash="legacy-hash",
        artifact_location=None,
        persisted_at=persisted_at,
        index_status=IndexStatus.UNKNOWN,
        schema_revision=1,
    )
    assert historical_receipt.schema_revision == 1
    with pytest.raises(ValueError, match="revision 1 或 2"):
        SaveReceipt(
            result_id=RESULT_ID,
            payload_hash="legacy-hash",
            artifact_location=None,
            persisted_at=persisted_at,
            index_status=IndexStatus.UNKNOWN,
            schema_revision=3,
        )
    with pytest.raises(ValueError, match="時區"):
        SaveReceipt(RESULT_ID, "hash", None, datetime(2026, 9, 21), IndexStatus.UNKNOWN)


def test_recommendation_item_captures_full_typed_legacy_values_without_second_total() -> None:
    first = RecommendationItem(
        "2330",
        rule_score=Decimal("18.37500"),
        close_price=Decimal("100.0100"),
        price_change=Decimal("-0.0005"),
        indicator_score=Decimal("5.2500"),
        pattern_score=0,
        volume_score=None,
        industry="半導體",
        reason_text="原始完整理由：突破整理區；維持風險揭露。\n第二行。",
    )
    second = RecommendationItem(
        "2317",
        rule_score=None,
        close_price=0,
        price_change=None,
        indicator_score=0,
        pattern_score=None,
        volume_score=Decimal("0.000"),
        industry=None,
        reason_text=None,
    )
    batch = DecisionBatch(items=(first, second))

    assert batch.items == (first, second)
    assert first.rule_score == Decimal("18.37500")
    assert first.close_price == Decimal("100.0100")
    assert first.price_change == Decimal("-0.0005")
    assert first.pattern_score == 0
    assert first.volume_score is None
    assert first.reason_text == "原始完整理由：突破整理區；維持風險揭露。\n第二行。"
    assert second.rule_score is None and second.close_price == 0
    assert second.industry is None and second.reason_text is None
    assert "total_score" not in {field.name for field in fields(RecommendationItem)}


@pytest.mark.parametrize(
    "field_name",
    (
        "close_price",
        "price_change",
        "indicator_score",
        "pattern_score",
        "volume_score",
    ),
)
def test_new_recommendation_item_numeric_fields_reject_float(field_name: str) -> None:
    with pytest.raises(TypeError, match="Decimal、int"):
        RecommendationItem("2330", **{field_name: 1.25})  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ("industry", "reason_text"))
def test_new_recommendation_item_text_fields_reject_non_strings(field_name: str) -> None:
    with pytest.raises(TypeError, match=field_name):
        RecommendationItem("2330", **{field_name: 0})  # type: ignore[arg-type]


def _config_snapshot(raw_json: str) -> RecommendationConfigSnapshot:
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    return RecommendationConfigSnapshot(raw_json, f"sha256:{digest}")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _result_config_snapshot(raw_json: str) -> RecommendationResultConfigSnapshot:
    from app_module.forward_position_thesis_candidate_producer import _sha256_json

    parsed = json.loads(raw_json)
    return RecommendationResultConfigSnapshot(raw_json, _sha256_json(dict(parsed)))


def test_request_config_snapshot_preserves_exact_raw_document_and_hash() -> None:
    raw_json = '{ "threshold" : "0.0100", "ratio": 1.2300, "enabled": true, "unset": null }\n'
    snapshot = _config_snapshot(raw_json)
    request = Request(config_snapshot=snapshot, max_stocks=20, top_n=7)

    assert request.config_snapshot is snapshot
    assert snapshot.raw_config_json == raw_json
    assert snapshot.raw_json_sha256 == "sha256:" + hashlib.sha256(
        raw_json.encode("utf-8")
    ).hexdigest()
    assert snapshot.schema_version == "recommendation-config-snapshot.v1"
    assert request.max_stocks == 20 and request.top_n == 7
    assert Request().max_stocks is None and Request().top_n is None
    with pytest.raises(FrozenInstanceError):
        snapshot.raw_config_json = "{}"  # type: ignore[misc]


@pytest.mark.parametrize(
    "raw_json",
    (
        '{"key": 1, "key": 2}',
        '{"threshold": NaN}',
        '{"threshold": Infinity}',
        '{"threshold": 1e999}',
        '{"threshold": 1e-9999}',
        '{"text": "\\ud800"}',
        '["not an object"]',
        '{"trailing": true} garbage',
    ),
)
def test_config_snapshot_rejects_invalid_nonfinite_or_duplicate_json(raw_json: str) -> None:
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError):
        RecommendationConfigSnapshot(raw_json, f"sha256:{digest}")


def test_config_snapshot_rejects_hash_mismatch_and_non_document_values() -> None:
    with pytest.raises(ValueError, match="raw_json_sha256"):
        RecommendationConfigSnapshot('{"x": 1}', "sha256:" + "0" * 64)
    with pytest.raises(TypeError, match="原始 JSON str"):
        RecommendationConfigSnapshot({"x": 1}, "sha256:" + "0" * 64)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="raw_json_sha256"):
        RecommendationConfigSnapshot('{"x": 1}', 1)  # type: ignore[arg-type]


def test_result_config_snapshot_matches_forward_producer_canonical_hash() -> None:
    from app_module.forward_position_thesis_candidate_producer import _sha256_json

    raw_json = (
        '{ "threshold" : "0.0100", "ratio": 1.2300, '
        '"ordinary_fraction": 0.1, "scheduled_snapshot": true, '
        '"decision_date": "2026-09-23" }\n'
    )
    producer_hash = _sha256_json(dict(json.loads(raw_json)))
    snapshot = RecommendationResultConfigSnapshot(raw_json, producer_hash)

    assert snapshot.raw_result_config_json == raw_json
    assert snapshot.config_sha256 == producer_hash
    assert json.loads(snapshot.raw_result_config_json)["threshold"] == "0.0100"
    assert json.loads(snapshot.raw_result_config_json)["ordinary_fraction"] == 0.1
    assert _result_config_snapshot(raw_json) == snapshot
    with pytest.raises(FrozenInstanceError):
        snapshot.config_sha256 = "sha256:" + "0" * 64  # type: ignore[misc]


@pytest.mark.parametrize(
    "raw_json",
    (
        '{"scheduled_snapshot": true, "scheduled_snapshot": false}',
        '{"threshold": NaN}',
        '{"threshold": 1e999}',
        '{"threshold": 1e-9999}',
        '["not an object"]',
    ),
)
def test_result_config_snapshot_rejects_invalid_source_json(raw_json: str) -> None:
    with pytest.raises(ValueError):
        RecommendationResultConfigSnapshot(raw_json, "sha256:" + "0" * 64)


def test_result_config_snapshot_rejects_hash_and_schema_mismatch() -> None:
    from app_module.forward_position_thesis_candidate_producer import _sha256_json

    payload = {"threshold": "0.0100", "scheduled_snapshot": True}
    raw_json = json.dumps(payload, ensure_ascii=False)
    with pytest.raises(ValueError, match="config_sha256"):
        RecommendationResultConfigSnapshot(raw_json, "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="schema_version"):
        RecommendationResultConfigSnapshot(
            raw_json,
            _sha256_json(payload),
            schema_version="recommendation-result-config-snapshot.v2",
        )


@pytest.mark.parametrize("kwargs", ({"max_stocks": 0}, {"top_n": 0}))
def test_request_limits_must_be_positive_integers(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="大於 0"):
        Request(**kwargs)


@pytest.mark.parametrize("value", (True, 1.5, "2"))
def test_request_limits_reject_bool_float_and_string(value: object) -> None:
    with pytest.raises(TypeError, match="max_stocks"):
        Request(max_stocks=value)  # type: ignore[arg-type]


def _valid_snapshot_cohort_inputs() -> dict[str, object]:
    return {
        "cohort_hash": "sha256:890a14de7735260bd99586a17608bc745e068e93de537aad4f83aec626292f67",
        "requested_symbols": ["2317", "2330", "2454"],
        "eligible_symbols": ["2330"],
        "missing_symbols": [],
        "degraded_symbols": ["2454"],
        "excluded_symbols": ["2317"],
        "requested_count": 3,
        "eligible_count": 1,
        "missing_count": 0,
        "degraded_count": 1,
        "excluded_count": 1,
        "coverage_status": SnapshotCohortCoverageStatus.DEGRADED,
        "coverage_by_symbol": {
            "2317": SnapshotCohortCoverage(
                "excluded", "good", "ranked", ["below_top_n"], []
            ),
            "2330": SnapshotCohortCoverage(
                "selected", "good", "recommendation", ["recommendation_selected"], ["screening_notice"]
            ),
            "2454": SnapshotCohortCoverage(
                "screened", "degraded", "data", ["source_partial"], ["price_gap"]
            ),
        },
    }


def test_snapshot_cohort_models_exact_v1_body_hash_and_deep_freezes_mutable_inputs() -> None:
    inputs = _valid_snapshot_cohort_inputs()
    requested = inputs["requested_symbols"]
    coverage = inputs["coverage_by_symbol"]
    cohort = SnapshotCohort(**inputs)  # type: ignore[arg-type]

    assert cohort.schema_version == "scheduled-recommendation-snapshot-cohort.v1"
    assert cohort.requested_symbols == ("2317", "2330", "2454")
    assert cohort.coverage_by_symbol["2330"].reason_codes == ("recommendation_selected",)
    assert cohort.coverage_by_symbol["2330"].warnings == ("screening_notice",)
    assert cohort.coverage_by_symbol is not coverage
    assert isinstance(requested, list)
    requested.append("9999")
    assert cohort.requested_symbols == ("2317", "2330", "2454")
    assert isinstance(coverage, dict)
    coverage["9999"] = SnapshotCohortCoverage("late", "good", "late")
    assert "9999" not in cohort.coverage_by_symbol
    with pytest.raises(TypeError):
        cohort.coverage_by_symbol["0000"] = SnapshotCohortCoverage()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        cohort.requested_symbols = ()  # type: ignore[misc]


def test_snapshot_cohort_rejects_hash_count_status_and_exact_body_drift() -> None:
    inputs = _valid_snapshot_cohort_inputs()
    with pytest.raises(ValueError, match="cohort_hash"):
        SnapshotCohort(**{**inputs, "cohort_hash": "sha256:" + "0" * 64})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="eligible_count"):
        SnapshotCohort(**{**inputs, "eligible_count": 0})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="coverage_status"):
        SnapshotCohort(
            **{**inputs, "coverage_status": SnapshotCohortCoverageStatus.COMPLETE}
        )  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="字典序排序"):
        SnapshotCohort(**{**inputs, "requested_symbols": ["2330", "2317", "2454"]})  # type: ignore[arg-type]


def test_snapshot_cohort_matches_scheduled_builder_exact_v1_body() -> None:
    from scripts.scheduled.run_scheduled_recommendation_snapshot import (
        _build_snapshot_cohort,
    )

    body = _build_snapshot_cohort(
        screening_matrix=[
            {
                "stock_code": "2317",
                "status": "excluded",
                "quality": "good",
                "stage": "ranked",
                "reason_codes": ["below_top_n"],
                "warnings": [],
            },
            {
                "stock_code": "2330",
                "status": "selected",
                "quality": "good",
                "stage": "recommendation",
                "reason_codes": ["recommendation_selected"],
                "warnings": ["screening_notice"],
            },
            {
                "stock_code": "2454",
                "status": "screened",
                "quality": "degraded",
                "stage": "data",
                "reason_codes": ["source_partial"],
                "warnings": ["price_gap"],
            },
        ],
        recommendations=[SimpleNamespace(stock_code="2330")],
    )
    fields_for_contract = dict(body)
    fields_for_contract["coverage_status"] = SnapshotCohortCoverageStatus(
        body["coverage_status"]
    )
    fields_for_contract["coverage_by_symbol"] = {
        symbol: SnapshotCohortCoverage(**row)
        for symbol, row in body["coverage_by_symbol"].items()
    }
    cohort = SnapshotCohort(**fields_for_contract)

    assert cohort.cohort_hash == body["cohort_hash"]
    assert cohort.requested_symbols == tuple(body["requested_symbols"])
    assert cohort.eligible_symbols == tuple(body["eligible_symbols"])
    assert cohort.missing_symbols == tuple(body["missing_symbols"])
    assert cohort.degraded_symbols == tuple(body["degraded_symbols"])
    assert cohort.excluded_symbols == tuple(body["excluded_symbols"])
    assert cohort.requested_count == body["requested_count"]
    assert cohort.coverage_status.value == body["coverage_status"]
    assert cohort.coverage_by_symbol["2330"].reason_codes == ("recommendation_selected",)


def test_context_stores_typed_same_run_identity_cohort_and_aware_clocks() -> None:
    strategy_spec_json = (
        '{"schema":"recommendation-strategy-config.v1","max_stocks":3,'
        '"top_n":1,"config":{"threshold":"0.0100"}}'
    )
    strategy_digest = _canonical_sha256(json.loads(strategy_spec_json))[7:]
    strategy = StrategyConfigIdentity(
        strategy_version_id="scheduled-recommendation-default-v1",
        strategy_config_id=f"recommendation-strategy-config-v1:{strategy_digest}",
        strategy_config_hash=f"sha256:{strategy_digest}",
        strategy_config_schema="recommendation-strategy-config.v1",
        strategy_config_spec_json=strategy_spec_json,
    )
    policy_spec = {
        "schema": "recommendation-universe-policy.v1",
        "selection_algorithm": "ordered-candidate-frame-v1",
        "selection_mode": "index",
        "industry_filter": "全部",
        "max_stocks": 3,
        "source_provider_id": "market-provider-v1",
        "requested_codes": ["2330"],
    }
    policy_digest = _canonical_sha256(policy_spec)[7:]
    policy = UniversePolicyIdentity(
        universe_policy_id=f"recommendation-universe-policy-v1:{policy_digest}",
        universe_policy_hash=f"sha256:{policy_digest}",
        universe_policy_schema="recommendation-universe-policy.v1",
        universe_policy_spec_json=json.dumps(policy_spec, ensure_ascii=False),
    )
    selected_codes = ["2330"]
    selected_codes_hash = _canonical_sha256({"selected_codes": selected_codes})
    snapshot_spec = {
        "schema": "recommendation-universe-snapshot.v1",
        "universe_policy_id": policy.universe_policy_id,
        "source_provider_id": "market-provider-v1",
        "decision_date": "2026-09-23",
        "selection_mode": "index",
        "selected_codes": selected_codes,
        "selected_count": 1,
        "selected_codes_hash": selected_codes_hash,
        "requested_codes": ["2330"],
    }
    snapshot_digest = _canonical_sha256(snapshot_spec)[7:]
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=f"recommendation-universe-snapshot-v1:{snapshot_digest}",
        universe_snapshot_hash=f"sha256:{snapshot_digest}",
        universe_snapshot_schema="recommendation-universe-snapshot.v1",
        universe_snapshot_source_provider_id="market-provider-v1",
        universe_snapshot_selected_codes_hash=selected_codes_hash,
        universe_snapshot_spec_json=json.dumps(snapshot_spec, ensure_ascii=False),
    )
    universe = RecommendationUniverseIdentity(
        universe_id=f"recommendation-universe-v1:{snapshot_digest}",
        universe_hash=f"sha256:{snapshot_digest}",
        universe_identity_schema="recommendation-universe-snapshot.v1",
        policy=policy,
        snapshot=snapshot,
    )
    evidence = RecommendationRunEvidenceIdentity(
        cost_model_id="gross-close-to-close-no-cost-v1",
        benchmark_id="TAIEX",
        industry_benchmark_id="industry-v1",
        horizon_days=Decimal("20.00"),
        evidence_tier="forward",
        return_basis="close_to_close_event_date",
    )
    cohort = SnapshotCohort(**_valid_snapshot_cohort_inputs())  # type: ignore[arg-type]
    created_at = datetime(2026, 9, 23, 8, 0, 0, 123456, tzinfo=timezone.utc)
    available_at = datetime(2026, 9, 23, 8, 0, 1, 234567, tzinfo=timezone(timedelta(hours=8)))
    decision_at = datetime(2026, 9, 23, 8, 0, 2, 345678, tzinfo=timezone.utc)

    context = Context(
        as_of_date=date(2026, 9, 23),
        created_at=created_at,
        available_at=available_at,
        decision_at=decision_at,
        strategy_identity=strategy,
        universe_identity=universe,
        snapshot_cohort=cohort,
        evidence_identity=evidence,
    )
    assert context.strategy_identity is strategy
    assert context.universe_identity is universe
    assert context.snapshot_cohort is cohort
    assert context.evidence_identity is evidence
    assert context.created_at == created_at and context.created_at.microsecond == 123456
    assert context.available_at == available_at and context.available_at.utcoffset() == timedelta(hours=8)
    assert context.decision_at == decision_at and context.decision_at.microsecond == 345678


def test_identity_contracts_match_v4_evidence_identity_builders() -> None:
    from app_module.v4_evidence_identity import (
        SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        build_recommendation_universe_identity,
        build_strategy_config_identity,
    )

    strategy_payload = build_strategy_config_identity(
        {
            "entry_threshold": Decimal("0.0100"),
            "turnover_limit": "1000.00",
            "as_of_date": "2026-09-23",
        },
        max_stocks=3,
        top_n=2,
    )
    strategy = StrategyConfigIdentity(
        strategy_version_id=SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        strategy_config_id=str(strategy_payload["strategy_config_id"]),
        strategy_config_hash=str(strategy_payload["strategy_config_hash"]),
        strategy_config_schema=str(strategy_payload["strategy_config_schema"]),
        strategy_config_spec_json=json.dumps(
            strategy_payload["strategy_config_spec"], ensure_ascii=False
        ),
    )
    assert json.loads(strategy.strategy_config_spec_json or "") == strategy_payload[
        "strategy_config_spec"
    ]
    assert strategy.strategy_config_hash == strategy_payload["strategy_config_hash"]

    changed_strategy_spec = dict(strategy_payload["strategy_config_spec"])
    changed_strategy_spec["config"] = {"entry_threshold": "0.0200"}
    with pytest.raises(ValueError, match="完整 strategy spec"):
        StrategyConfigIdentity(
            strategy_version_id=SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
            strategy_config_id=str(strategy_payload["strategy_config_id"]),
            strategy_config_hash=str(strategy_payload["strategy_config_hash"]),
            strategy_config_schema=str(strategy_payload["strategy_config_schema"]),
            strategy_config_spec_json=json.dumps(changed_strategy_spec, ensure_ascii=False),
        )

    universe_payload = build_recommendation_universe_identity(
        decision_date="2026-09-23",
        selection_mode="explicit",
        industry_filter="半導體",
        max_stocks=3,
        requested_codes=["2330", "2317"],
        selected_codes=["2330"],
        source_provider_id="market-provider-v1",
    )
    policy = UniversePolicyIdentity(
        universe_policy_id=str(universe_payload["universe_policy_id"]),
        universe_policy_hash=str(universe_payload["universe_policy_hash"]),
        universe_policy_schema=str(universe_payload["universe_policy_schema"]),
        universe_policy_spec_json=json.dumps(
            universe_payload["universe_policy_spec"], ensure_ascii=False
        ),
    )
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=str(universe_payload["universe_snapshot_id"]),
        universe_snapshot_hash=str(universe_payload["universe_snapshot_hash"]),
        universe_snapshot_schema=str(universe_payload["universe_snapshot_schema"]),
        universe_snapshot_source_provider_id=str(
            universe_payload["universe_snapshot_source_provider_id"]
        ),
        universe_snapshot_selected_codes_hash=str(
            universe_payload["universe_snapshot_selected_codes_hash"]
        ),
        universe_snapshot_spec_json=json.dumps(
            universe_payload["universe_snapshot_spec"], ensure_ascii=False
        ),
    )
    universe = RecommendationUniverseIdentity(
        universe_id=str(universe_payload["universe_id"]),
        universe_hash=str(universe_payload["universe_hash"]),
        universe_identity_schema=str(universe_payload["universe_identity_schema"]),
        policy=policy,
        snapshot=snapshot,
    )
    assert policy.universe_policy_hash == universe_payload["universe_policy_hash"]
    assert snapshot.universe_snapshot_hash == universe_payload["universe_snapshot_hash"]
    assert snapshot.universe_snapshot_selected_codes_hash == universe_payload[
        "universe_snapshot_selected_codes_hash"
    ]
    assert universe.universe_hash == universe_payload["universe_hash"]


@pytest.mark.parametrize("mismatch", ("policy", "snapshot", "selected_codes"))
def test_universe_identity_hash_mismatch_examples_are_rejected(mismatch: str) -> None:
    from app_module.v4_evidence_identity import build_recommendation_universe_identity

    payload = build_recommendation_universe_identity(
        decision_date="2026-09-23",
        selection_mode="explicit",
        industry_filter="半導體",
        max_stocks=3,
        requested_codes=["2330", "2317"],
        selected_codes=["2330"],
        source_provider_id="market-provider-v1",
    )
    policy_fields = {
        "universe_policy_id": payload["universe_policy_id"],
        "universe_policy_hash": payload["universe_policy_hash"],
        "universe_policy_schema": payload["universe_policy_schema"],
        "universe_policy_spec_json": json.dumps(
            payload["universe_policy_spec"], ensure_ascii=False
        ),
    }
    snapshot_fields = {
        "universe_snapshot_id": payload["universe_snapshot_id"],
        "universe_snapshot_hash": payload["universe_snapshot_hash"],
        "universe_snapshot_schema": payload["universe_snapshot_schema"],
        "universe_snapshot_source_provider_id": payload[
            "universe_snapshot_source_provider_id"
        ],
        "universe_snapshot_selected_codes_hash": payload[
            "universe_snapshot_selected_codes_hash"
        ],
        "universe_snapshot_spec_json": json.dumps(
            payload["universe_snapshot_spec"], ensure_ascii=False
        ),
    }

    if mismatch == "policy":
        with pytest.raises(ValueError, match="universe_policy_id"):
            UniversePolicyIdentity(
                **{
                    **policy_fields,
                    "universe_policy_hash": "sha256:" + "0" * 64,
                }
            )
    elif mismatch == "snapshot":
        with pytest.raises(ValueError, match="universe_snapshot_id"):
            UniverseSnapshotIdentity(
                **{
                    **snapshot_fields,
                    "universe_snapshot_hash": "sha256:" + "0" * 64,
                }
            )
    else:
        with pytest.raises(ValueError, match="universe_snapshot_spec selected hash"):
            UniverseSnapshotIdentity(
                **{
                    **snapshot_fields,
                    "universe_snapshot_selected_codes_hash": "sha256:" + "0" * 64,
                }
            )


def test_result_config_snapshot_cross_checks_full_scheduled_config_and_identity_builders() -> None:
    from app_module.forward_position_thesis_candidate_producer import _sha256_json
    from app_module.v4_evidence_identity import (
        DEFAULT_RETURN_BASIS,
        SCHEDULED_RECOMMENDATION_BENCHMARK_ID,
        SCHEDULED_RECOMMENDATION_COST_MODEL_ID,
        SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        build_recommendation_universe_identity,
        build_strategy_config_identity,
    )
    from scripts.scheduled.run_scheduled_recommendation_snapshot import (
        _build_snapshot_cohort,
    )

    strategy_payload = build_strategy_config_identity(
        {"entry_threshold": "0.0100", "as_of_date": "2026-09-22"},
        max_stocks=3,
        top_n=2,
    )
    strategy = StrategyConfigIdentity(
        strategy_version_id=SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        strategy_config_id=str(strategy_payload["strategy_config_id"]),
        strategy_config_hash=str(strategy_payload["strategy_config_hash"]),
        strategy_config_schema=str(strategy_payload["strategy_config_schema"]),
        strategy_config_spec_json=json.dumps(
            strategy_payload["strategy_config_spec"], ensure_ascii=False
        ),
    )
    universe_payload = build_recommendation_universe_identity(
        decision_date="2026-09-23",
        selection_mode="explicit",
        industry_filter="半導體",
        max_stocks=3,
        requested_codes=["2330", "2317"],
        selected_codes=["2330"],
        source_provider_id="market-provider-v1",
    )
    policy = UniversePolicyIdentity(
        universe_policy_id=str(universe_payload["universe_policy_id"]),
        universe_policy_hash=str(universe_payload["universe_policy_hash"]),
        universe_policy_schema=str(universe_payload["universe_policy_schema"]),
        universe_policy_spec_json=json.dumps(
            universe_payload["universe_policy_spec"], ensure_ascii=False
        ),
    )
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=str(universe_payload["universe_snapshot_id"]),
        universe_snapshot_hash=str(universe_payload["universe_snapshot_hash"]),
        universe_snapshot_schema=str(universe_payload["universe_snapshot_schema"]),
        universe_snapshot_source_provider_id=str(
            universe_payload["universe_snapshot_source_provider_id"]
        ),
        universe_snapshot_selected_codes_hash=str(
            universe_payload["universe_snapshot_selected_codes_hash"]
        ),
        universe_snapshot_spec_json=json.dumps(
            universe_payload["universe_snapshot_spec"], ensure_ascii=False
        ),
    )
    universe = RecommendationUniverseIdentity(
        universe_id=str(universe_payload["universe_id"]),
        universe_hash=str(universe_payload["universe_hash"]),
        universe_identity_schema=str(universe_payload["universe_identity_schema"]),
        policy=policy,
        snapshot=snapshot,
    )
    cohort_body = _build_snapshot_cohort(
        screening_matrix=[
            {
                "stock_code": "2317",
                "status": "excluded",
                "quality": "good",
                "stage": "ranked",
                "reason_codes": ["below_top_n"],
                "warnings": [],
            },
            {
                "stock_code": "2330",
                "status": "selected",
                "quality": "good",
                "stage": "recommendation",
                "reason_codes": ["recommendation_selected"],
                "warnings": ["screening_notice"],
            },
        ],
        recommendations=[SimpleNamespace(stock_code="2330")],
    )
    cohort_fields = dict(cohort_body)
    cohort_fields["coverage_status"] = SnapshotCohortCoverageStatus(
        cohort_body["coverage_status"]
    )
    cohort_fields["coverage_by_symbol"] = {
        symbol: SnapshotCohortCoverage(**row)
        for symbol, row in cohort_body["coverage_by_symbol"].items()
    }
    cohort = SnapshotCohort(**cohort_fields)
    evidence = RecommendationRunEvidenceIdentity(
        cost_model_id=SCHEDULED_RECOMMENDATION_COST_MODEL_ID,
        benchmark_id=SCHEDULED_RECOMMENDATION_BENCHMARK_ID,
        industry_benchmark_id="industry-benchmark-v1",
        horizon_days=20,
        evidence_tier="forward",
        return_basis=DEFAULT_RETURN_BASIS,
    )

    result_config: dict[str, object] = {
        "entry_threshold": "0.0100",
        "scheduled_snapshot": True,
        "research_only": True,
        "decision_date": "2026-09-23",
        "max_stocks": 3,
        "top_n": 2,
        "profile_id": "scheduled_daily_research_default_v1",
        "profile_name": "Scheduled daily research default v1",
        "look_ahead_check": "uses latest available data at scheduled run time only",
        "snapshot_cohort": cohort_body,
        "safety_boundary": {
            "confirm": False,
            "writes_evidence_db": False,
            "auto_trading": False,
            "lifecycle_action": False,
        },
        "strategy_version_id": SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        "strategy_config_id": strategy_payload["strategy_config_id"],
        "strategy_config_hash": strategy_payload["strategy_config_hash"],
        "strategy_config_schema": strategy_payload["strategy_config_schema"],
        "strategy_config_spec": strategy_payload["strategy_config_spec"],
        **universe_payload,
        "cost_model_id": evidence.cost_model_id,
        "benchmark_id": evidence.benchmark_id,
        "industry_benchmark_id": evidence.industry_benchmark_id,
        "horizon_days": evidence.horizon_days,
        "evidence_tier": evidence.evidence_tier,
        "return_basis": evidence.return_basis,
    }
    raw_config_json = json.dumps(
        result_config, ensure_ascii=False, separators=(",", ":")
    )
    result_snapshot = RecommendationResultConfigSnapshot(
        raw_config_json, _sha256_json(dict(result_config))
    )
    context_fields: dict[str, object] = {
        "as_of_date": date(2026, 9, 22),
        "created_at": datetime(2026, 9, 23, 7, 59, tzinfo=timezone.utc),
        "available_at": datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
        "decision_at": datetime(2026, 9, 23, 8, 1, tzinfo=timezone.utc),
        "strategy_identity": strategy,
        "universe_identity": universe,
        "snapshot_cohort": cohort,
        "evidence_identity": evidence,
        "result_config_snapshot": result_snapshot,
    }
    context = Context(**context_fields)  # type: ignore[arg-type]
    execution = RecommendationExecution(
        result_id=RESULT_ID,
        request=Request(
            config_snapshot=_config_snapshot('{"entry_threshold":"0.0100"}'),
            max_stocks=3,
            top_n=2,
        ),
        context=context,
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(),
    )
    with pytest.raises(ValueError, match="Context.snapshot_cohort"):
        Context(result_config_snapshot=result_snapshot)
    with pytest.raises(ValueError, match="Request.max_stocks.*必須明示"):
        RecommendationExecution(
            result_id=RESULT_ID,
            request=Request(config_snapshot=_config_snapshot('{"entry_threshold":"0.0100"}')),
            context=context,
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(),
        )
    with pytest.raises(ValueError, match="Request.config_snapshot"):
        RecommendationExecution(
            result_id=RESULT_ID,
            request=Request(max_stocks=3, top_n=2),
            context=context,
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(),
        )
    with pytest.raises(ValueError, match="不可是空 caller config"):
        RecommendationExecution(
            result_id=RESULT_ID,
            request=Request(
                config_snapshot=_config_snapshot("{}"), max_stocks=3, top_n=2
            ),
            context=context,
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(),
        )
    for owner in ("strategy_identity", "universe_identity", "evidence_identity"):
        with pytest.raises(ValueError, match=f"Context.{owner}"):
            Context(**{**context_fields, owner: None})  # type: ignore[arg-type]

    missing_required_key_config = dict(result_config)
    del missing_required_key_config["benchmark_id"]
    with pytest.raises(ValueError, match="缺少必要鍵.*benchmark_id"):
        Context(
            **{
                **context_fields,
                "result_config_snapshot": _result_config_snapshot(
                    json.dumps(missing_required_key_config, ensure_ascii=False)
                ),
            }
        )  # type: ignore[arg-type]

    non_string_decision_date_config = dict(result_config)
    non_string_decision_date_config["decision_date"] = 20260923
    with pytest.raises(TypeError, match="result_config.decision_date 必須是 str"):
        Context(
            **{
                **context_fields,
                "result_config_snapshot": _result_config_snapshot(
                    json.dumps(non_string_decision_date_config, ensure_ascii=False)
                ),
            }
        )  # type: ignore[arg-type]

    missing_typed_benchmark = RecommendationRunEvidenceIdentity(
        cost_model_id=SCHEDULED_RECOMMENDATION_COST_MODEL_ID,
        benchmark_id=None,
        industry_benchmark_id="industry-benchmark-v1",
        horizon_days=20,
        evidence_tier="forward",
        return_basis=DEFAULT_RETURN_BASIS,
    )
    mismatched_benchmark_config = dict(result_config)
    mismatched_benchmark_config["benchmark_id"] = "SPY"
    with pytest.raises(ValueError, match="result_config.benchmark_id.*須省略"):
        Context(
            **{
                **context_fields,
                "evidence_identity": missing_typed_benchmark,
                "result_config_snapshot": _result_config_snapshot(
                    json.dumps(mismatched_benchmark_config, ensure_ascii=False)
                ),
            }
        )  # type: ignore[arg-type]
    blank_typed_benchmark = RecommendationRunEvidenceIdentity(
        cost_model_id=SCHEDULED_RECOMMENDATION_COST_MODEL_ID,
        benchmark_id="",
        industry_benchmark_id="industry-benchmark-v1",
        horizon_days=20,
        evidence_tier="forward",
        return_basis=DEFAULT_RETURN_BASIS,
    )
    with pytest.raises(ValueError, match="result_config.benchmark_id.*須省略"):
        Context(
            **{**context_fields, "evidence_identity": blank_typed_benchmark}
        )  # type: ignore[arg-type]

    missing_typed_optional_industry = RecommendationRunEvidenceIdentity(
        cost_model_id=SCHEDULED_RECOMMENDATION_COST_MODEL_ID,
        benchmark_id=SCHEDULED_RECOMMENDATION_BENCHMARK_ID,
        industry_benchmark_id=None,
        horizon_days=20,
        evidence_tier="forward",
        return_basis=DEFAULT_RETURN_BASIS,
    )
    with pytest.raises(ValueError, match="result_config.industry_benchmark_id.*須省略"):
        Context(
            **{
                **context_fields,
                "evidence_identity": missing_typed_optional_industry,
            }
        )  # type: ignore[arg-type]

    assert context.result_config_snapshot is result_snapshot
    assert json.loads(result_snapshot.raw_result_config_json)["entry_threshold"] == "0.0100"
    assert result_snapshot.config_sha256 == _sha256_json(dict(result_config))
    assert execution.request.max_stocks == 3 and execution.request.top_n == 2
    assert context.as_of_date == date(2026, 9, 22)
    assert json.loads(result_snapshot.raw_result_config_json)["decision_date"] == "2026-09-23"

    for key in (
        "strategy_config_hash",
        "universe_policy_hash",
        "universe_snapshot_hash",
        "universe_snapshot_selected_codes_hash",
    ):
        mismatched_config = dict(result_config)
        mismatched_config[key] = "sha256:" + "0" * 64
        bad_fields = {
            **context_fields,
            "result_config_snapshot": _result_config_snapshot(
                json.dumps(mismatched_config, ensure_ascii=False)
            ),
        }
        with pytest.raises(ValueError, match=key):
            Context(**bad_fields)  # type: ignore[arg-type]

    changed_cohort_config = dict(result_config)
    changed_cohort_config["snapshot_cohort"] = {
        **cohort_body,
        "excluded_definition": "altered definition",
    }
    with pytest.raises(ValueError, match="snapshot_cohort.*符合"):
        Context(
            **{
                **context_fields,
                "result_config_snapshot": _result_config_snapshot(
                    json.dumps(changed_cohort_config, ensure_ascii=False)
                ),
            }
        )  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="result_config.max_stocks"):
        RecommendationExecution(
            result_id=RESULT_ID,
            request=Request(
                config_snapshot=_config_snapshot('{"entry_threshold":"0.0100"}'),
                max_stocks=4,
                top_n=2,
            ),
            context=context,
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(),
        )


@pytest.mark.parametrize("field_name", ("created_at", "available_at", "decision_at"))
def test_context_rejects_naive_capture_clocks(field_name: str) -> None:
    with pytest.raises(ValueError, match="時區"):
        Context(**{field_name: datetime(2026, 9, 23, 8, 0)})  # type: ignore[arg-type]


def test_context_rejects_available_clock_after_decision_but_keeps_legacy_absence() -> None:
    decision_at = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 9, 23, 8, 0, 1, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="available_at.*decision_at"):
        Context(decision_at=decision_at, available_at=available_at)
    assert Context(decision_at=decision_at, available_at=None).available_at is None
    assert Context(decision_at=None, available_at=available_at).decision_at is None


def test_identity_contracts_reject_conflicting_ids_and_untyped_specs() -> None:
    bad_strategy_spec = {
        "schema": "recommendation-strategy-config.v1",
        "max_stocks": 3,
        "top_n": 1,
        "config": {},
    }
    bad_strategy_hash = _canonical_sha256(bad_strategy_spec)
    with pytest.raises(ValueError, match="strategy_config_id"):
        StrategyConfigIdentity(
            strategy_config_id="recommendation-strategy-config-v1:" + "a" * 64,
            strategy_config_hash=bad_strategy_hash,
            strategy_config_schema="recommendation-strategy-config.v1",
            strategy_config_spec_json=json.dumps(bad_strategy_spec),
        )
    with pytest.raises(ValueError, match="有效 JSON object"):
        StrategyConfigIdentity(
            strategy_config_id="recommendation-strategy-config-v1:" + "a" * 64,
            strategy_config_hash="sha256:" + "a" * 64,
            strategy_config_schema="recommendation-strategy-config.v1",
            strategy_config_spec_json='{"a":1,"a":2}',
        )
    with pytest.raises(ValueError, match="alias、policy 與 snapshot"):
        RecommendationUniverseIdentity(
            universe_id="recommendation-universe-v1:" + "a" * 64,
            universe_hash="sha256:" + "b" * 64,
            universe_identity_schema="recommendation-universe-snapshot.v1",
        )


def test_null_zero_and_existing_decimal_integer_types_remain_distinct() -> None:
    missing = RecommendationItem("2330", rule_score=None, confidence=None)
    zero_decimal = RecommendationItem("2317", rule_score=Decimal("0.000"), confidence=0)
    batch = DecisionBatch(items=(missing, zero_decimal))

    assert batch.items[0].rule_score is None
    assert batch.items[1].rule_score == Decimal("0.000")
    assert type(batch.items[1].rule_score) is Decimal
    assert batch.items[1].confidence == 0
    assert type(batch.items[1].confidence) is int

    quality = QualityReport(metrics={"missing": None, "zero": 0})
    assert quality.metrics["missing"] is None
    assert quality.metrics["zero"] == 0


def test_legacy_float_values_are_not_quantized_or_moved_into_domain_contract() -> None:
    from app_module.dtos import RecommendationDTO

    legacy = RecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        close_price=Decimal("100.10"),
        price_change=0.125,
        total_score=18.375,
        indicator_score=5.25,
        pattern_score=6.75,
        volume_score=6.375,
        recommendation_reasons="legacy reasons",
        industry="半導體",
        regime_match=True,
        calibrated_probability_bp=6000,
        calibration_model_version="model-v1",
    )

    assert type(legacy.close_price) is Decimal
    assert type(legacy.price_change) is float
    assert legacy.total_score == 18.375
    assert legacy.calibrated_probability_bp == 6000
    with pytest.raises(TypeError, match="Decimal、int"):
        RecommendationItem("2330", rule_score=legacy.total_score)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal、int"):
        FactorContribution("legacy", legacy.indicator_score, "legacy-score", "v1")  # type: ignore[arg-type]


def test_unsupported_payloads_and_unlisted_frozen_dataclasses_are_rejected() -> None:
    @dataclass(frozen=True)
    class ExternalFrozenRecord:
        nested: tuple[str, ...]

    invalid_values = (
        1.25,
        object(),
        io.StringIO("live file handle"),
        lambda: None,
        ExternalFrozenRecord(("not an owned contract",)),
    )
    for value in invalid_values:
        with pytest.raises(TypeError):
            FilterOutcome("x", None, evidence={"value": value})

    with pytest.raises(TypeError, match="mapping key"):
        QualityReport(metrics={1: "not allowed"})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="循環參照"):
        cycle: list[object] = []
        cycle.append(cycle)
        QualityReport(metrics={"cycle": cycle})

    class UniverseReferenceSubclass(UniverseReference):
        pass

    universe_subclass = UniverseReferenceSubclass(policy_id="policy-v1")
    with pytest.raises(TypeError, match="universe_ref"):
        RecommendationItem("2330", universe_ref=universe_subclass)  # type: ignore[arg-type]

    class VersionReferenceSubclass(VersionReference):
        pass

    reference_subclass = VersionReferenceSubclass(ReferenceKind.CONFIG, "config-1")
    with pytest.raises(TypeError, match="config_ref"):
        Request(config_ref=reference_subclass)  # type: ignore[arg-type]


def test_contract_import_is_io_free_and_respects_module_boundaries() -> None:
    scripts = (
        r'''
import os
import sys

def audit(event, args):
    if event == "sqlite3.connect":
        raise AssertionError("contract import attempted a SQLite connection")
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fspath(args[0]).lower()
        if not path.endswith((".py", ".pyc", ".pyd", ".dll")):
            raise AssertionError(f"contract import opened a non-code file: {path}")

sys.addaudithook(audit)
from decision_module.recommendation import contracts
assert contracts.RecommendationItem
assert not any(name == "app_module" or name.startswith("app_module.") for name in sys.modules)
assert "pandas" not in sys.modules
assert "matplotlib" not in sys.modules
''',
        r'''
import os
import sys

def audit(event, args):
    if event == "sqlite3.connect":
        raise AssertionError("contract import attempted a SQLite connection")
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fspath(args[0]).lower()
        if not path.endswith((".py", ".pyc", ".pyd", ".dll")):
            raise AssertionError(f"contract import opened a non-code file: {path}")

sys.addaudithook(audit)
import app_module.recommendation as recommendation_package
from app_module.recommendation import contracts
from app_module.recommendation import (
    MLAvailability,
    MLAvailabilityReason,
    MLAvailabilityStatus,
    MLReceiptBinding,
)
assert contracts.RecommendationExecution
assert MLAvailability is contracts.MLAvailability
assert MLAvailabilityReason is contracts.MLAvailabilityReason
assert MLAvailabilityStatus is contracts.MLAvailabilityStatus
assert MLReceiptBinding is contracts.MLReceiptBinding
assert {
    "MLAvailability",
    "MLAvailabilityReason",
    "MLAvailabilityStatus",
    "MLReceiptBinding",
}.issubset(recommendation_package.__all__)
assert "app_module.recommendation_service" not in sys.modules
assert "app_module.dtos" not in sys.modules
assert "decision_module.scoring_engine" not in sys.modules
assert "pandas" not in sys.modules
assert "matplotlib" not in sys.modules
''',
    )
    for script in scripts:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout


def test_parent_public_exports_keep_order_direct_star_getattr_and_class_identity() -> None:
    script = r'''
import sys
import app_module
import decision_module

expected_app_all = [
    "RecommendationService", "ScreeningService", "RegimeService", "UpdateService",
    "BacktestService", "PortfolioService", "JournalService", "RecommendationDTO",
    "RecommendationResultDTO", "RegimeResultDTO", "BacktestReportDTO",
]
expected_decision_all = [
    "StrategyConfigurator", "ReasonEngine", "IndustryMapper",
    "MarketRegimeDetector", "StockScreener", "ScoringEngine",
]
assert app_module.__all__ == expected_app_all
assert decision_module.__all__ == expected_decision_all
assert all(name not in app_module.__dict__ for name in expected_app_all)
assert all(name not in decision_module.__dict__ for name in expected_decision_all)
assert set(expected_app_all).issubset(dir(app_module))
assert set(expected_decision_all).issubset(dir(decision_module))

app_sources = {
    "RecommendationService": ("app_module.recommendation_service", "RecommendationService"),
    "ScreeningService": ("app_module.screening_service", "ScreeningService"),
    "RegimeService": ("app_module.regime_service", "RegimeService"),
    "UpdateService": ("app_module.update_service", "UpdateService"),
    "BacktestService": ("app_module.backtest_service", "BacktestService"),
    "PortfolioService": ("app_module.portfolio_service", "PortfolioService"),
    "JournalService": ("app_module.journal_service", "JournalService"),
    "RecommendationDTO": ("app_module.dtos", "RecommendationDTO"),
    "RecommendationResultDTO": ("app_module.dtos", "RecommendationResultDTO"),
    "RegimeResultDTO": ("app_module.dtos", "RegimeResultDTO"),
    "BacktestReportDTO": ("app_module.dtos", "BacktestReportDTO"),
}
decision_sources = {
    "StrategyConfigurator": ("decision_module.strategy_configurator", "StrategyConfigurator"),
    "ReasonEngine": ("decision_module.reason_engine", "ReasonEngine"),
    "IndustryMapper": ("decision_module.industry_mapper", "IndustryMapper"),
    "MarketRegimeDetector": ("decision_module.market_regime_detector", "MarketRegimeDetector"),
    "StockScreener": ("decision_module.stock_screener", "StockScreener"),
    "ScoringEngine": ("decision_module.scoring_engine", "ScoringEngine"),
}
import importlib
for name, (module_name, class_name) in app_sources.items():
    source_class = getattr(importlib.import_module(module_name), class_name)
    assert getattr(app_module, name) is source_class
    direct_import = {}
    exec(f"from app_module import {name}", direct_import)
    assert direct_import[name] is source_class
for name, (module_name, class_name) in decision_sources.items():
    source_class = getattr(importlib.import_module(module_name), class_name)
    assert getattr(decision_module, name) is source_class
    direct_import = {}
    exec(f"from decision_module import {name}", direct_import)
    assert direct_import[name] is source_class

from app_module import RecommendationService, RecommendationDTO
from decision_module import StrategyConfigurator
assert RecommendationService is getattr(app_module, "RecommendationService")
assert RecommendationDTO is getattr(app_module, "RecommendationDTO")
assert StrategyConfigurator is getattr(decision_module, "StrategyConfigurator")

app_star = {}
decision_star = {}
exec("from app_module import *", app_star)
exec("from decision_module import *", decision_star)
assert list(name for name in expected_app_all if name in app_star) == expected_app_all
assert list(name for name in expected_decision_all if name in decision_star) == expected_decision_all
for name, (module_name, class_name) in app_sources.items():
    assert app_star[name] is getattr(importlib.import_module(module_name), class_name)
for name, (module_name, class_name) in decision_sources.items():
    assert decision_star[name] is getattr(importlib.import_module(module_name), class_name)
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
