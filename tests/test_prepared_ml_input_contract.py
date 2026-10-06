"""R010 Prepared ML Input 契約特性測試。"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone, tzinfo
import inspect
from pathlib import Path
import subprocess
import sys

import pytest

from app_module.recommendation.ml_adapter import (
    PreparedMLProjector,
    RecommendationMLAdapter,
)
from ml_module.prepared_input_contract import (
    AvailabilityBinding,
    AvailabilityStatus,
    CandidateIdentity,
    CostReceiptBinding,
    DateRange,
    FeatureContract,
    FeatureSchemaItem,
    LibraryVersion,
    MissingInput,
    ModelBinding,
    PermissionStatus,
    PreparedMLInput,
    QuarantineStatus,
    SnapshotKind,
    SnapshotQualityStatus,
    SnapshotReference,
    SnapshotScopeStatus,
)


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
DECISION_DATE = date(2026, 9, 22)
FEATURE_CUTOFF = date(2026, 9, 21)
DECISION_AT = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)


def _availability() -> AvailabilityBinding:
    return AvailabilityBinding(
        status=AvailabilityStatus.KNOWN,
        available_at=datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc),
    )


def _snapshot(
    snapshot_id: str,
    *,
    kind: SnapshotKind = SnapshotKind.BOUNDED,
    dataset_id: str | None = None,
    row_range: DateRange | None = DateRange(
        date(2026, 9, 1), FEATURE_CUTOFF
    ),
    availability: AvailabilityBinding | None = None,
    content_hash: str = HASH_A,
    row_identity_hash: str = HASH_B,
    quality_status: SnapshotQualityStatus = SnapshotQualityStatus.COMPLETE,
    missing_inputs: tuple[MissingInput, ...] | list[MissingInput] = (),
    scope_status: SnapshotScopeStatus = SnapshotScopeStatus.PIT,
) -> SnapshotReference:
    return SnapshotReference(
        snapshot_id=snapshot_id,
        source_id=f"source:{snapshot_id}",
        kind=kind,
        dataset_id=dataset_id,
        schema_version="source-schema.v1",
        content_hash=content_hash,
        row_identity_hash=row_identity_hash,
        row_count=2 if row_range is not None else 0,
        row_range=row_range,
        source_revision="revision-7",
        availability=availability or _availability(),
        quality_status=quality_status,
        missing_inputs=missing_inputs,
        scope_status=scope_status,
    )


def _feature_contract(
    *, schema: tuple[FeatureSchemaItem, ...] | list[FeatureSchemaItem] | None = None
) -> FeatureContract:
    if schema is None:
        schema = (
            FeatureSchemaItem("rsi_14", "int32", "scaled_1e4"),
            FeatureSchemaItem("macd_12_26", "int32", "scaled_1e4"),
        )
    return FeatureContract(
        feature_schema=schema,
        feature_registry_hash=HASH_A,
        transform_contract_id="recommendation-calibration.transform",
        transform_contract_version="v1",
        transform_contract_hash=HASH_B,
        missing_value_policy="missing_is_not_zero",
        mask_policy="observed=0;missing=1",
        normalization_policy="fitted_transform_from_training_release",
    )


def _model_binding(
    *,
    feature_registry_hash: str = HASH_A,
    transform_contract_hash: str = HASH_B,
    library_versions: tuple[LibraryVersion, ...] | list[LibraryVersion] | None = None,
) -> ModelBinding:
    if library_versions is None:
        library_versions = (
            LibraryVersion("python", "3.13.7"),
            LibraryVersion("scikit-learn", "1.7.2"),
        )
    return ModelBinding(
        model_id="model:calibration-7",
        release_id="release:shadow-7",
        model_family="recommendation_absolute_calibration_v1",
        training_dataset_id="dataset:training-17",
        training_dataset_hash=HASH_C,
        feature_registry_hash=feature_registry_hash,
        label_registry_hash=HASH_C,
        transform_contract_hash=transform_contract_hash,
        artifact_hash=HASH_A,
        manifest_hash=HASH_B,
        qualified_class_path="ml_module.recommendation_calibration_training.Model",
        serialization_format="joblib",
        library_versions=library_versions,
        quarantine_status=QuarantineStatus.CLEAR,
        shadow_only=True,
        production_eligible=False,
        production_action_allowed=False,
        permission_status=PermissionStatus.GRANTED,
    )


def _prepared(**overrides: object) -> PreparedMLInput:
    values: dict[str, object] = {
        "result_id": "Rec:case-sensitive/opaque ID",
        "decision_date": DECISION_DATE,
        "decision_at": DECISION_AT,
        "as_of_date": DECISION_DATE,
        "feature_cutoff_date": FEATURE_CUTOFF,
        "mode": "interactive:desk-A",
        "candidate_identities": (
            CandidateIdentity("candidate:opaque-B", "1477"),
            CandidateIdentity("candidate:opaque-A", "1256"),
        ),
        "rule_snapshot_refs": (_snapshot("rule:cut-1"),),
        "ml_snapshot_refs": (_snapshot("ml:bounded-9", content_hash=HASH_C),),
        "feature_contract": _feature_contract(),
        "model_binding": _model_binding(),
        "cost_receipt_binding": CostReceiptBinding(
            scenario_id="cost:fixed-v1",
            scenario_version="1",
            scenario_hash=HASH_C,
            receipt_id="receipt:cost-4",
            receipt_hash=HASH_A,
        ),
    }
    values.update(overrides)
    return PreparedMLInput(**values)  # type: ignore[arg-type]


def test_prepared_input_is_deeply_immutable_and_copies_caller_lists() -> None:
    candidates = [
        CandidateIdentity("candidate:B", "1477"),
        CandidateIdentity("candidate:A", "1256"),
    ]
    feature_items = [
        FeatureSchemaItem("rsi_14", "int32", "scaled_1e4"),
        FeatureSchemaItem("macd_12_26", "int32", "scaled_1e4"),
    ]
    versions = [LibraryVersion("python", "3.13.7")]
    rule_refs = [_snapshot("rule:1")]
    ml_refs = [_snapshot("ml:1")]
    feature_contract = _feature_contract(schema=feature_items)
    model = _model_binding(library_versions=versions)

    prepared = _prepared(
        candidate_identities=candidates,
        feature_contract=feature_contract,
        model_binding=model,
        rule_snapshot_refs=rule_refs,
        ml_snapshot_refs=ml_refs,
    )

    candidates.append(CandidateIdentity("candidate:C", "2321"))
    feature_items.clear()
    versions.clear()
    rule_refs.clear()
    ml_refs.clear()

    assert tuple(item.symbol for item in prepared.candidate_identities) == (
        "1477",
        "1256",
    )
    assert tuple(item.feature_id for item in prepared.feature_contract.feature_schema) == (
        "rsi_14",
        "macd_12_26",
    )
    assert prepared.model_binding.library_versions == (
        LibraryVersion("python", "3.13.7"),
    )
    assert prepared.rule_snapshot_refs[0].snapshot_id == "rule:1"
    assert prepared.ml_snapshot_refs[0].snapshot_id == "ml:1"
    assert prepared.result_id == "Rec:case-sensitive/opaque ID"
    assert prepared.mode == "interactive:desk-A"
    with pytest.raises(FrozenInstanceError):
        prepared.result_id = "rewritten"  # type: ignore[misc]


class _MutableDelta(timedelta):
    def __new__(cls) -> _MutableDelta:
        instance = super().__new__(cls, hours=5)
        instance.fake_days = -1
        return instance

    @property
    def days(self) -> int:
        return self.fake_days


class _MutableTZ(tzinfo):
    def __init__(self) -> None:
        self.offset: timedelta = _MutableDelta()

    def utcoffset(self, _value: datetime | None) -> timedelta:
        return self.offset

    def dst(self, _value: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, _value: datetime | None) -> str:
        return "Mutable/offset"


def test_aware_datetime_tzinfo_and_timedelta_aliases_are_frozen() -> None:
    source_tz = _MutableTZ()
    source_offset = source_tz.offset
    source_datetime = datetime(2026, 9, 21, 9, 0, tzinfo=source_tz)

    binding = AvailabilityBinding(AvailabilityStatus.KNOWN, source_datetime)
    source_offset.fake_days = -1  # type: ignore[attr-defined]
    source_tz.offset = timedelta(hours=9)

    assert binding.available_at is not None
    assert binding.available_at.isoformat().endswith("+05:00")
    assert binding.available_at.tzinfo is not source_tz

    decision_tz = _MutableTZ()
    prepared = _prepared(
        decision_at=datetime(2026, 9, 22, 16, 0, tzinfo=decision_tz)
    )
    decision_tz.offset = timedelta(hours=-8)
    assert prepared.decision_at.isoformat().endswith("+05:00")


def test_candidate_identity_is_ordered_opaque_and_unique() -> None:
    prepared = _prepared(
        result_id="opaque/Result ID A",
        candidate_identities=(
            CandidateIdentity("key:B", "1477"),
            CandidateIdentity("key:A", "1256"),
        ),
    )
    assert prepared.result_id == "opaque/Result ID A"
    assert tuple(item.candidate_id for item in prepared.candidate_identities) == (
        "key:B",
        "key:A",
    )

    with pytest.raises(ValueError, match="candidate_id"):
        _prepared(
            candidate_identities=(
                CandidateIdentity("same", "1477"),
                CandidateIdentity("same", "1256"),
            )
        )
    with pytest.raises(ValueError, match="symbol"):
        _prepared(
            candidate_identities=(
                CandidateIdentity("key:A", "1477"),
                CandidateIdentity("key:B", "1477"),
            )
        )


def test_snapshot_and_feature_hashes_require_sha256_shape() -> None:
    with pytest.raises(ValueError, match="content_hash"):
        _snapshot("bad-hash", content_hash="sha256:ABC")
    with pytest.raises(ValueError, match="feature_registry_hash"):
        FeatureContract(
            feature_schema=(FeatureSchemaItem("f1", "int32", "scaled"),),
            feature_registry_hash="not-a-hash",
            transform_contract_id="transform",
            transform_contract_version="v1",
            transform_contract_hash=HASH_B,
            missing_value_policy="missing_is_not_zero",
            mask_policy="missing=1",
            normalization_policy="fitted",
        )
    with pytest.raises(ValueError, match="artifact_hash"):
        replace(_model_binding(), artifact_hash="wrong")


def test_unknown_available_at_remains_unknown_and_never_gets_defaulted() -> None:
    unknown = AvailabilityBinding(AvailabilityStatus.UNKNOWN, None)
    assert unknown.status is AvailabilityStatus.UNKNOWN
    assert unknown.available_at is None
    assert unknown.available_date is None
    reference = _snapshot("unknown:1", availability=unknown)
    assert reference.availability.available_at is None
    assert _prepared(ml_snapshot_refs=(reference,)).ml_snapshot_refs[0].availability.status is (
        AvailabilityStatus.UNKNOWN
    )

    with pytest.raises(ValueError, match="unknown availability"):
        AvailabilityBinding(
            AvailabilityStatus.UNKNOWN,
            datetime(2026, 9, 20, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="unknown availability"):
        AvailabilityBinding(
            AvailabilityStatus.UNKNOWN,
            available_date=date(2026, 9, 20),
        )
    with pytest.raises(ValueError, match="known availability"):
        AvailabilityBinding(AvailabilityStatus.KNOWN, None)


def test_date_only_availability_keeps_precision_and_does_not_claim_intraday_order() -> None:
    prior_date = AvailabilityBinding(
        AvailabilityStatus.KNOWN,
        available_date=date(2026, 9, 21),
    )
    assert prior_date.available_date == date(2026, 9, 21)
    assert prior_date.available_at is None
    prior_prepared = _prepared(
        rule_snapshot_refs=(_snapshot("date-only:prior", availability=prior_date),)
    )
    assert prior_prepared.rule_snapshot_refs[0].availability.available_at is None

    same_day = AvailabilityBinding(
        AvailabilityStatus.KNOWN,
        available_date=DECISION_DATE,
    )
    same_day_prepared = _prepared(
        ml_snapshot_refs=(_snapshot("date-only:same-day", availability=same_day),)
    )
    resolved = same_day_prepared.ml_snapshot_refs[0].availability
    assert resolved.available_date == DECISION_DATE
    assert resolved.available_at is None


def test_date_only_availability_after_decision_is_rejected() -> None:
    future = _snapshot(
        "date-only:future",
        availability=AvailabilityBinding(
            AvailabilityStatus.KNOWN,
            available_date=date(2026, 9, 23),
        ),
    )
    with pytest.raises(ValueError, match="decision_date"):
        _prepared(rule_snapshot_refs=(future,))


def test_availability_date_and_timestamp_keep_independent_legal_evidence() -> None:
    binding = AvailabilityBinding(
        AvailabilityStatus.KNOWN,
        datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
        available_date=date(2026, 9, 21),
    )
    assert binding.available_at == datetime(
        2026, 9, 20, 9, 0, tzinfo=timezone.utc
    )
    assert binding.available_date == date(2026, 9, 21)
    prepared = _prepared(
        rule_snapshot_refs=(_snapshot("independent-availability", availability=binding),)
    )
    retained = prepared.rule_snapshot_refs[0].availability
    assert retained.available_at == binding.available_at
    assert retained.available_date == date(2026, 9, 21)


def test_known_availability_after_decision_is_rejected_for_either_snapshot_lane() -> None:
    future = _snapshot(
        "future:rule",
        availability=AvailabilityBinding(
            AvailabilityStatus.KNOWN,
            datetime(2026, 9, 23, tzinfo=timezone.utc),
        ),
    )
    with pytest.raises(ValueError, match="decision_at"):
        _prepared(rule_snapshot_refs=(future,))

    future_ml = _snapshot(
        "future:ml",
        availability=AvailabilityBinding(
            AvailabilityStatus.KNOWN,
            datetime(2026, 9, 23, tzinfo=timezone.utc),
        ),
    )
    with pytest.raises(ValueError, match="decision_at"):
        _prepared(ml_snapshot_refs=(future_ml,))

    later_same_day = _snapshot(
        "same-day:after-decision-time",
        availability=AvailabilityBinding(
            AvailabilityStatus.KNOWN,
            datetime(2026, 9, 22, 17, 0, tzinfo=timezone.utc),
        ),
    )
    with pytest.raises(ValueError, match="decision_at"):
        _prepared(ml_snapshot_refs=(later_same_day,))


def test_bounded_snapshot_needs_verifiable_hashes_but_no_dataset_id() -> None:
    bounded = _snapshot("bounded:content-addressed")
    assert bounded.dataset_id is None
    assert bounded.content_hash == HASH_A
    with pytest.raises(ValueError, match="不得編造"):
        _snapshot(
            "bounded:invented-dataset",
            kind=SnapshotKind.BOUNDED,
            dataset_id="made-up-dataset",
        )
    with pytest.raises(ValueError, match="dataset_id"):
        _snapshot(
            "dataset:missing-id",
            kind=SnapshotKind.DATASET,
            dataset_id=None,
        )


def test_snapshot_quality_missing_inputs_and_pit_scope_are_explicit() -> None:
    missing = MissingInput("dividend.adjustment", "source_field_absent")
    missing_inputs = [missing]
    degraded = _snapshot(
        "degraded:one-field",
        quality_status=SnapshotQualityStatus.DEGRADED,
        missing_inputs=missing_inputs,
        scope_status=SnapshotScopeStatus.CURRENT,
    )
    missing_inputs.clear()
    assert degraded.quality_status is SnapshotQualityStatus.DEGRADED
    assert degraded.missing_inputs == (missing,)
    assert degraded.scope_status is SnapshotScopeStatus.CURRENT

    missing_snapshot = _snapshot(
        "missing:one-field",
        quality_status=SnapshotQualityStatus.MISSING,
        missing_inputs=(MissingInput("market.close", "source_row_absent"),),
    )
    assert missing_snapshot.quality_status is SnapshotQualityStatus.MISSING
    assert missing_snapshot.missing_inputs[0].item_id == "market.close"

    pit = _snapshot("pit:verified", scope_status=SnapshotScopeStatus.PIT)
    assert pit.scope_status is SnapshotScopeStatus.PIT

    unknown = _snapshot(
        "unknown:quality-and-scope",
        quality_status=SnapshotQualityStatus.UNKNOWN,
        missing_inputs=(),
        scope_status=SnapshotScopeStatus.UNKNOWN,
    )
    assert unknown.quality_status is SnapshotQualityStatus.UNKNOWN
    assert unknown.missing_inputs == ()
    assert unknown.scope_status is SnapshotScopeStatus.UNKNOWN

    research = _snapshot(
        "research:restated",
        quality_status=SnapshotQualityStatus.COMPLETE,
        scope_status=SnapshotScopeStatus.RESEARCH,
    )
    assert research.scope_status is SnapshotScopeStatus.RESEARCH

    with pytest.raises(ValueError, match="complete quality"):
        _snapshot(
            "invalid:complete-with-missing",
            quality_status=SnapshotQualityStatus.COMPLETE,
            missing_inputs=(missing,),
        )
    with pytest.raises(ValueError, match="必須列出 missing_inputs"):
        _snapshot(
            "invalid:degraded-without-missing",
            quality_status=SnapshotQualityStatus.DEGRADED,
        )
    with pytest.raises(ValueError, match="item_id 不可重複"):
        _snapshot(
            "invalid:duplicate-missing",
            quality_status=SnapshotQualityStatus.MISSING,
            missing_inputs=(missing, missing),
        )
    with pytest.raises(TypeError, match="missing_inputs 含有不支援的 record"):
        _snapshot(
            "invalid:untyped-missing",
            quality_status=SnapshotQualityStatus.DEGRADED,
            missing_inputs=({"item_id": "f1", "reason_code": "absent"},),  # type: ignore[arg-type]
        )


def test_rule_and_ml_snapshots_can_have_distinct_ids_under_shared_cutoff() -> None:
    rule = _snapshot(
        "rule:snapshot-10",
        content_hash=HASH_A,
        row_identity_hash=HASH_B,
    )
    ml = _snapshot(
        "ml:bounded-21",
        content_hash=HASH_C,
        row_identity_hash=HASH_A,
        row_range=DateRange(date(2026, 8, 1), date(2026, 9, 20)),
    )
    prepared = _prepared(rule_snapshot_refs=(rule,), ml_snapshot_refs=(ml,))
    assert prepared.rule_snapshot_refs[0].snapshot_id != prepared.ml_snapshot_refs[0].snapshot_id
    assert prepared.rule_snapshot_refs[0].content_hash != prepared.ml_snapshot_refs[0].content_hash

    future_rule = _snapshot(
        "rule:future-row",
        row_range=DateRange(date(2026, 9, 1), DECISION_DATE),
    )
    with pytest.raises(ValueError, match="feature cutoff"):
        _prepared(rule_snapshot_refs=(future_rule,))

    future_ml = _snapshot(
        "ml:future-row",
        row_range=DateRange(date(2026, 9, 1), DECISION_DATE),
    )
    with pytest.raises(ValueError, match="feature cutoff"):
        _prepared(ml_snapshot_refs=(future_ml,))


def test_feature_and_model_contracts_are_required_and_must_match() -> None:
    with pytest.raises(TypeError, match="feature_contract"):
        _prepared(feature_contract=None)
    with pytest.raises(TypeError, match="model_binding"):
        _prepared(model_binding=None)
    with pytest.raises(ValueError, match="feature_registry_hash"):
        _prepared(model_binding=_model_binding(feature_registry_hash=HASH_C))
    with pytest.raises(ValueError, match="transform_contract_hash"):
        _prepared(model_binding=_model_binding(transform_contract_hash=HASH_C))
    with pytest.raises(ValueError, match="feature_schema"):
        _feature_contract(schema=[])


def test_cost_receipt_identity_is_paired_and_hash_checked() -> None:
    with pytest.raises(ValueError, match="同時提供"):
        CostReceiptBinding(
            scenario_id="cost:v1",
            scenario_version="1",
            scenario_hash=HASH_A,
            receipt_id="receipt:1",
            receipt_hash=None,
        )


def test_ml_leaf_has_no_app_data_provider_database_or_model_io_imports() -> None:
    source_path = Path(__file__).resolve().parents[1] / "ml_module" / "prepared_input_contract.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert all(
        not name.startswith(("app_module", "data_module", "decision_module"))
        for name in imported
    )
    assert all(
        name.split(".", 1)[0]
        not in {"sqlite3", "pathlib", "io", "joblib", "numpy", "sklearn", "requests"}
        for name in imported
    )

    forbidden_calls = {
        "open",
        "connect",
        "read_text",
        "read_bytes",
        "load",
        "load_model",
        "infer",
        "predict",
    }
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in forbidden_calls
        for node in ast.walk(tree)
    )

    code = (
        "import sys; import ml_module.prepared_input_contract; "
        "assert not any(name == 'app_module' or name.startswith('app_module.') "
        "for name in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=source_path.parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_app_adapter_is_protocol_only_and_requires_explicit_mode() -> None:
    prepare = inspect.signature(RecommendationMLAdapter.prepare_input)
    assert prepare.parameters["mode"].default is inspect.Parameter.empty
    assert prepare.parameters["execution"].default is inspect.Parameter.empty
    assert "prepared_input" in inspect.signature(
        PreparedMLProjector.project_prepared_input
    ).parameters

    source_path = (
        Path(__file__).resolve().parents[1]
        / "app_module"
        / "recommendation"
        / "ml_adapter.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any(
        name.split(".", 1)[0]
        in {"sqlite3", "pathlib", "joblib", "numpy", "sklearn", "data_module"}
        for name in imported
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"open", "connect"}
        for node in ast.walk(tree)
    )
def test_model_quarantine_and_permission_statuses_remain_explicit() -> None:
    model = replace(
        _model_binding(),
        quarantine_status=QuarantineStatus.UNKNOWN,
        permission_status=PermissionStatus.UNKNOWN,
    )
    prepared = _prepared(model_binding=model)
    assert prepared.model_binding.quarantine_status is QuarantineStatus.UNKNOWN
    assert prepared.model_binding.permission_status is PermissionStatus.UNKNOWN

    with pytest.raises(ValueError, match="安全狀態衝突"):
        replace(_model_binding(), production_action_allowed=True)


def test_production_action_requires_every_model_safety_gate() -> None:
    authorized = replace(
        _model_binding(),
        quarantine_status=QuarantineStatus.CLEAR,
        shadow_only=False,
        production_eligible=True,
        production_action_allowed=True,
        permission_status=PermissionStatus.GRANTED,
    )
    assert _prepared(model_binding=authorized).model_binding.production_action_allowed

    invalid_statuses = (
        (QuarantineStatus.QUARANTINED, PermissionStatus.GRANTED),
        (QuarantineStatus.UNKNOWN, PermissionStatus.GRANTED),
        (QuarantineStatus.CLEAR, PermissionStatus.DENIED),
        (QuarantineStatus.CLEAR, PermissionStatus.UNKNOWN),
        (QuarantineStatus.QUARANTINED, PermissionStatus.DENIED),
    )
    for quarantine_status, permission_status in invalid_statuses:
        with pytest.raises(ValueError, match="安全狀態衝突"):
            replace(
                _model_binding(),
                quarantine_status=quarantine_status,
                shadow_only=False,
                production_eligible=True,
                production_action_allowed=True,
                permission_status=permission_status,
            )


def test_mode_is_required_and_is_preserved_without_normalization() -> None:
    prepared = _prepared(mode=" Historical Replay ")
    assert prepared.mode == " Historical Replay "
    with pytest.raises(ValueError, match="mode 不可為空白"):
        _prepared(mode="   ")
