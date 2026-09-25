from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from inspect import Parameter, signature
import json
from pathlib import Path

import pytest

import app_module.recommendation.codec as codec
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation.codec import (
    ExecutionCodecError,
    decode_artifact,
    decode_execution,
    decode_execution_envelope,
    decode_legacy_recommendation,
    decode_legacy_result,
    encode_execution,
)
from app_module.recommendation.contracts import (
    Context,
    EXECUTION_SCHEMA_REVISION,
    ExecutionEvent,
    ExecutionStatus,
    MLAvailability,
    MLAvailabilityStatus,
    MLReceiptBinding,
    QualityReport,
    QualityStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    RecommendationUniverseIdentity,
    ReferenceKind,
    Request,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
    SUPPORTED_EXECUTION_SCHEMA_REVISIONS,
    StrategyConfigIdentity,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
    VersionReference,
)
from data_module.contracts.market import SourceRef
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


def _reference(kind: ReferenceKind, reference_id: str) -> VersionReference:
    return VersionReference(kind=kind, reference_id=reference_id, version="v1")


def _raw_config_snapshot(raw_json: str) -> RecommendationConfigSnapshot:
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    return RecommendationConfigSnapshot(raw_json, f"sha256:{digest}")


def _result_config_snapshot(raw_json: str) -> RecommendationResultConfigSnapshot:
    config = json.loads(raw_json)
    canonical = json.dumps(
        config, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return RecommendationResultConfigSnapshot(
        raw_json, "sha256:" + hashlib.sha256(canonical).hexdigest()
    )


def _snapshot_cohort() -> SnapshotCohort:
    return SnapshotCohort(
        cohort_hash="sha256:890a14de7735260bd99586a17608bc745e068e93de537aad4f83aec626292f67",
        requested_symbols=("2317", "2330", "2454"),
        eligible_symbols=("2330",),
        missing_symbols=(),
        degraded_symbols=("2454",),
        excluded_symbols=("2317",),
        requested_count=3,
        eligible_count=1,
        missing_count=0,
        degraded_count=1,
        excluded_count=1,
        coverage_status=SnapshotCohortCoverageStatus.DEGRADED,
        coverage_by_symbol={
            "2317": SnapshotCohortCoverage(
                "excluded", "good", "ranked", ("below_top_n",), ()
            ),
            "2330": SnapshotCohortCoverage(
                "selected",
                "good",
                "recommendation",
                ("recommendation_selected",),
                ("screening_notice",),
            ),
            "2454": SnapshotCohortCoverage(
                "screened", "degraded", "data", ("source_partial",), ("price_gap",)
            ),
        },
    )


def _strategy_identity() -> StrategyConfigIdentity:
    from app_module.v4_evidence_identity import (
        SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        build_strategy_config_identity,
    )

    payload = build_strategy_config_identity(
        {"entry_threshold": "0.0100"}, max_stocks=3, top_n=2
    )
    return StrategyConfigIdentity(
        strategy_version_id=SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        strategy_config_id=str(payload["strategy_config_id"]),
        strategy_config_hash=str(payload["strategy_config_hash"]),
        strategy_config_schema=str(payload["strategy_config_schema"]),
        strategy_config_spec_json=json.dumps(
            payload["strategy_config_spec"], ensure_ascii=False
        ),
    )


def _universe_identity() -> RecommendationUniverseIdentity:
    from app_module.v4_evidence_identity import build_recommendation_universe_identity

    payload = build_recommendation_universe_identity(
        decision_date="2026-09-22",
        selection_mode="explicit",
        industry_filter="半導體",
        max_stocks=3,
        requested_codes=["2317", "2330"],
        selected_codes=["2330"],
        source_provider_id="market-provider-v1",
    )
    policy = UniversePolicyIdentity(
        universe_policy_id=str(payload["universe_policy_id"]),
        universe_policy_hash=str(payload["universe_policy_hash"]),
        universe_policy_schema=str(payload["universe_policy_schema"]),
        universe_policy_spec_json=json.dumps(
            payload["universe_policy_spec"], ensure_ascii=False
        ),
    )
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=str(payload["universe_snapshot_id"]),
        universe_snapshot_hash=str(payload["universe_snapshot_hash"]),
        universe_snapshot_schema=str(payload["universe_snapshot_schema"]),
        universe_snapshot_source_provider_id=str(
            payload["universe_snapshot_source_provider_id"]
        ),
        universe_snapshot_selected_codes_hash=str(
            payload["universe_snapshot_selected_codes_hash"]
        ),
        universe_snapshot_spec_json=json.dumps(
            payload["universe_snapshot_spec"], ensure_ascii=False
        ),
    )
    return RecommendationUniverseIdentity(
        universe_id=str(payload["universe_id"]),
        universe_hash=str(payload["universe_hash"]),
        universe_identity_schema=str(payload["universe_identity_schema"]),
        policy=policy,
        snapshot=snapshot,
    )


def _execution() -> RecommendationExecution:
    result_id = "opaque:Result/Legacy-ID 0042 "
    source_ref = SourceRef("daily-prices", revision=7, snapshot_id="snapshot-2026-09-22")
    item = RecommendationItem(
        stock_code="2330",
        rule_score=Decimal("91.2300"),
        close_price=Decimal("600.1000"),
        price_change=Decimal("2.5000"),
        indicator_score=Decimal("85.00"),
        pattern_score=Decimal("95.000"),
        volume_score=Decimal("90.0"),
        industry="半導體",
        reason_text="trend and volume confirmation",
        factor_contributions=(
            FactorContribution(
                factor_id="momentum",
                value=Decimal("0.00"),
                unit="bp",
                version="factor-v2",
                source_refs=(source_ref,),
            ),
        ),
        rank=0,
        universe_ref=UniverseReference(
            policy_id="all-listed-v1",
            snapshot_id="members-2026-09-22",
            as_of_date=date(2026, 9, 22),
            members_hash="member-hash",
        ),
        reasons=("eligible", "stable tie-break"),
        confidence=Decimal("0.00"),
        stock_name=None,
        score_percentile_bp=0,
        eligible_universe_size=0,
        eligible_universe_date=date(2026, 9, 22),
        ranking_method="nearest_rank",
        threshold_mode="quantile",
        regime_match=False,
    )
    negative = NegativeEvidence(
        evidence_id="liquidity-warning",
        reason="low turnover",
        source_refs=(source_ref,),
        observed_at=datetime(2026, 9, 22, 9, 4, 5, tzinfo=timezone(timedelta(hours=8))),
        details={
            "threshold": Decimal("1000.00"),
            "observed": 0,
            "detail": {"missing": None, "labels": ("turnover", "20d")},
        },
    )
    assessment = CandidateAssessment(
        stock_code="2330",
        eligible=False,
        filter_outcomes={
            "min-turnover": FilterOutcome(
                filter_id="min-turnover",
                passed=False,
                reason="under threshold",
                evidence={"actual": Decimal("0.000"), "expected": 1},
            )
        },
        negative_evidence=(negative,),
        reasons=("insufficient liquidity",),
        liquidity=LiquidityAssessment(
            acceptable=False,
            reasons=("turnover below configured minimum",),
            missing_data=(),
            evidence_refs=(source_ref,),
            observations={"turnover": Decimal("0.000"), "row_count": 0},
        ),
        missing_data=("broker_flow",),
    )
    decision = DecisionBatch(
        items=(item,),
        assessments=(assessment,),
        regime="Trend",
        state_transition=RegimeStateTransition(
            previous_state="Neutral",
            next_state="Trend",
            transition_date=date(2026, 9, 22),
            reasons=("confirmed",),
        ),
    )
    quality = QualityReport(
        status=QualityStatus.DEGRADED,
        warnings=("one optional source missing",),
        metrics={"rows": 1, "missing": 0, "ratio": Decimal("0.0000")},
    )
    ml_receipt_ref = _reference(ReferenceKind.ML_RECEIPT, "receipt-0001")
    receipt = MLReceiptBinding(
        receipt_ref=ml_receipt_ref,
        receipt_hash="sha256:" + "a" * 64,
        result_id=result_id,
        decision_date=date(2026, 9, 22),
        model_candidate_id="candidate-v7",
        projected_stock_codes=("2330",),
        cost_scenario_hash="sha256:" + "b" * 64,
    )
    return RecommendationExecution(
        result_id=result_id,
        request=Request(
            as_of_date=date(2026, 9, 22),
            config_ref=_reference(ReferenceKind.CONFIG, "config-1"),
            profile_ref=_reference(ReferenceKind.PROFILE, "profile-1"),
            strategy_ref=_reference(ReferenceKind.STRATEGY, "strategy-1"),
            policy_ref=_reference(ReferenceKind.POLICY, "policy-1"),
            universe_policy_ref=_reference(ReferenceKind.UNIVERSE_POLICY, "universe-policy-1"),
            config_snapshot=_raw_config_snapshot(
                '{ "entry_threshold" : "0.0100", "ratio": 1.2300, "enabled": true }\n'
            ),
            max_stocks=20,
            top_n=7,
        ),
        context=Context(
            as_of_date=date(2026, 9, 22),
            created_at=datetime(
                2026, 9, 22, 9, 4, 0, tzinfo=timezone(timedelta(hours=8))
            ),
            available_at=datetime(
                2026, 9, 22, 9, 4, 30, tzinfo=timezone(timedelta(hours=8))
            ),
            decision_at=datetime(2026, 9, 22, 9, 5, 6, 700, tzinfo=timezone(timedelta(hours=8))),
            source_refs=(source_ref,),
            data_snapshot_refs=(_reference(ReferenceKind.DATA_SNAPSHOT, "market-snapshot"),),
            config_ref=_reference(ReferenceKind.CONFIG, "config-1"),
            profile_ref=_reference(ReferenceKind.PROFILE, "profile-1"),
            strategy_ref=_reference(ReferenceKind.STRATEGY, "strategy-1"),
            policy_ref=_reference(ReferenceKind.POLICY, "policy-1"),
            universe_policy_ref=_reference(ReferenceKind.UNIVERSE_POLICY, "universe-policy-1"),
            universe_snapshot_ref=_reference(ReferenceKind.UNIVERSE_SNAPSHOT, "universe-snapshot"),
            algorithm_ref=_reference(ReferenceKind.ALGORITHM, "algorithm-v3"),
            input_quality=QualityReport(
                status=QualityStatus.COMPLETE,
                warnings=("source clock captured",),
                metrics={"source_count": 1, "unknown": None},
            ),
            warnings=("captured before execution",),
            strategy_identity=_strategy_identity(),
            universe_identity=_universe_identity(),
            snapshot_cohort=_snapshot_cohort(),
            evidence_identity=RecommendationRunEvidenceIdentity(
                cost_model_id="gross-close-to-close-no-cost-v1",
                benchmark_id="TAIEX",
                horizon_days=Decimal("20.00"),
                evidence_tier="forward",
                return_basis="close_to_close_event_date",
            ),
            result_config_snapshot=_result_config_snapshot(
                '{ "decision_date" : "2026-09-22", '
                '"parameters" : {"threshold":"0.0100","ratio":1.2300}, '
                '"sources" : ["daily-price-v7", "indicator-v3"] }\n'
            ),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=decision,
        quality=quality,
        ml_availability=MLAvailability(status=MLAvailabilityStatus.AVAILABLE),
        events=(
            ExecutionEvent(
                event_type="started",
                message="execution started",
                occurred_at=datetime(2026, 9, 22, 1, 5, 6, tzinfo=timezone.utc),
                details={"attempt": 0, "source": source_ref},
            ),
        ),
        related_references=(
            _reference(ReferenceKind.RUNTIME_RUN, "runtime-run"),
            _reference(ReferenceKind.REPLAY_PARENT, "parent-run"),
            _reference(ReferenceKind.PORTFOLIO_RESULT, "portfolio-result"),
            _reference(ReferenceKind.EVIDENCE, "saved-evidence"),
        ),
        ml_projection_refs=(_reference(ReferenceKind.ML_PROJECTION, "projection-1"),),
        ml_receipt_refs=(receipt,),
    )


def _document(raw: bytes) -> dict[str, object]:
    return json.loads(raw.decode("utf-8"))


def _rehash(document: dict[str, object]) -> bytes:
    material = {
        "schema_version": document["schema_version"],
        "schema_revision": document["schema_revision"],
        "payload": document["payload"],
    }
    canonical = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    document["payload_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_r009_all_contract_fields_round_trip_and_keep_opaque_result_id() -> None:
    expected = _execution()
    raw = encode_execution(expected)
    wire_fields = _document(raw)["payload"]["fields"]
    request_wire = wire_fields["request"]["fields"]
    context_wire = wire_fields["context"]["fields"]
    universe_wire = context_wire["universe_identity"]["fields"]
    cohort_record = context_wire["snapshot_cohort"]
    cohort_wire = cohort_record["fields"]

    decoded = decode_execution(raw)

    assert decoded == expected
    assert decoded.result_id == "opaque:Result/Legacy-ID 0042 "
    assert decoded.context.decision_at.isoformat() == "2026-09-22T09:05:06.000700+08:00"
    assert decoded.decision is not None
    assert decoded.decision.items[0].rule_score == Decimal("91.2300")
    assert decoded.decision.items[0].close_price == Decimal("600.1000")
    assert decoded.decision.items[0].price_change == Decimal("2.5000")
    assert decoded.decision.items[0].indicator_score == Decimal("85.00")
    assert decoded.decision.items[0].pattern_score == Decimal("95.000")
    assert decoded.decision.items[0].volume_score == Decimal("90.0")
    assert decoded.decision.items[0].industry == "半導體"
    assert decoded.decision.items[0].reason_text == "trend and volume confirmation"
    assert decoded.decision.assessments[0].negative_evidence[0].reason == "low turnover"
    assert decoded.request.config_snapshot is not None
    assert decoded.request.config_snapshot.raw_config_json == (
        '{ "entry_threshold" : "0.0100", "ratio": 1.2300, "enabled": true }\n'
    )
    assert decoded.request.config_snapshot.raw_json_sha256 == (
        "sha256:"
        + hashlib.sha256(
            b'{ "entry_threshold" : "0.0100", "ratio": 1.2300, "enabled": true }\n'
        ).hexdigest()
    )
    assert decoded.request.max_stocks == 20 and decoded.request.top_n == 7
    assert decoded.context.result_config_snapshot is not None
    assert decoded.context.result_config_snapshot.raw_result_config_json == (
        '{ "decision_date" : "2026-09-22", '
        '"parameters" : {"threshold":"0.0100","ratio":1.2300}, '
        '"sources" : ["daily-price-v7", "indicator-v3"] }\n'
    )
    assert expected.context.result_config_snapshot is not None
    assert decoded.context.result_config_snapshot == expected.context.result_config_snapshot
    assert decoded.context.strategy_identity == _strategy_identity()
    assert decoded.context.universe_identity == _universe_identity()
    assert decoded.context.snapshot_cohort == _snapshot_cohort()
    assert decoded.context.snapshot_cohort.coverage_status is SnapshotCohortCoverageStatus.DEGRADED
    assert decoded.context.evidence_identity is not None
    assert decoded.context.evidence_identity.horizon_days == Decimal("20.00")
    assert request_wire["config_snapshot"]["$record"] == (
        "recommendation.config-snapshot.v1"
    )
    assert context_wire["result_config_snapshot"]["$record"] == (
        "recommendation.result-config-snapshot.v1"
    )
    assert context_wire["strategy_identity"]["$record"] == (
        "recommendation.strategy-config-identity.v1"
    )
    assert context_wire["universe_identity"]["$record"] == (
        "recommendation.universe-identity.v1"
    )
    assert universe_wire["policy"]["$record"] == (
        "recommendation.universe-policy-identity.v1"
    )
    assert universe_wire["snapshot"]["$record"] == (
        "recommendation.universe-snapshot-identity.v1"
    )
    assert context_wire["evidence_identity"]["$record"] == (
        "recommendation.run-evidence-identity.v1"
    )
    assert cohort_record["$record"] == "recommendation.snapshot-cohort.v1"
    assert cohort_wire["coverage_status"]["$enum"] == (
        "recommendation.snapshot-cohort-coverage-status.v1"
    )
    assert next(iter(cohort_wire["coverage_by_symbol"].values()))[
        "$record"
    ] == "recommendation.snapshot-cohort-coverage.v1"


def test_r009_current_contract_revision_is_explicitly_supported() -> None:
    assert EXECUTION_SCHEMA_REVISION == 2
    assert SUPPORTED_EXECUTION_SCHEMA_REVISIONS == (1, 2)
    raw = encode_execution(_execution())

    assert _document(raw)["schema_revision"] == 2
    assert decode_execution(raw).result_id == _execution().result_id
    envelope = decode_execution_envelope(raw)
    assert envelope.schema_version == "recommendation-execution.v1"
    assert envelope.schema_revision == 2
    assert envelope.payload_hash == _document(raw)["payload_hash"]
    assert envelope.raw_payload == raw
    assert envelope.raw_payload_sha256 == "sha256:" + hashlib.sha256(raw).hexdigest()


def test_r009_canonical_bytes_and_hash_are_deterministic_without_mutable_metadata() -> None:
    execution = _execution()
    raw = encode_execution(execution)
    repeated = encode_execution(execution)

    assert raw == repeated
    document = _document(raw)
    assert set(document) == {"schema_version", "schema_revision", "payload", "payload_hash"}
    assert "metadata" not in document
    hash_material = {
        "schema_version": document["schema_version"],
        "schema_revision": document["schema_revision"],
        "payload": document["payload"],
    }
    canonical = json.dumps(
        hash_material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert document["payload_hash"] == "sha256:" + hashlib.sha256(canonical).hexdigest()


def test_r009_null_zero_decimal_and_offset_wire_values_are_distinct() -> None:
    document = _document(encode_execution(_execution()))
    root_fields = document["payload"]["fields"]
    item = root_fields["decision"]["fields"]["items"][0]["fields"]

    assert item["stock_name"] is None
    assert item["rank"] == 0
    assert item["eligible_universe_size"] == 0
    assert item["confidence"] == {"$decimal": "0.00"}
    assert root_fields["context"]["fields"]["decision_at"] == {
        "$datetime": "2026-09-22T09:05:06.000700+08:00"
    }
    assert item["eligible_universe_date"] == {"$date": "2026-09-22"}

    def assert_no_float(value: object) -> None:
        assert type(value) is not float
        if type(value) is dict:
            for child in value.values():
                assert_no_float(child)
        elif type(value) is list:
            for child in value:
                assert_no_float(child)

    assert_no_float(document)


def test_r009_missing_optional_uses_contract_default_without_rewriting_input() -> None:
    original = encode_execution(_execution())
    document = _document(original)
    fields = document["payload"]["fields"]
    del fields["failure_reason"]
    del fields["events"]
    historical_variant = _rehash(document)
    preserved_bytes = bytes(historical_variant)

    decoded = decode_execution(historical_variant)

    assert decoded.failure_reason is None
    assert decoded.events == ()
    assert historical_variant == preserved_bytes


def test_r009_rev1_fixture_decodes_without_rewriting_source_or_calling_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "recommendation_execution_rev1.json"
    raw = fixture_path.read_bytes()
    before = bytes(raw)
    expected_raw_sha256 = "dbd3c2194ef53c2fee3e41e772187d2453c52237328aa179833282e0cc76a52b"
    expected_payload_hash = (
        "sha256:db61aabb2b388609d49c9daae77ee54ae389a51c9f12acd59f329a7f1cf265b5"
    )
    source_fields = _document(raw)["payload"]["fields"]
    request_fields = source_fields["request"]["fields"]
    context_fields = source_fields["context"]["fields"]
    item_fields = source_fields["decision"]["fields"]["items"][0]["fields"]
    assert "config_snapshot" not in request_fields
    assert "created_at" not in context_fields
    assert "result_config_snapshot" not in context_fields
    assert "close_price" not in item_fields

    def forbidden_writer(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("歷史 rev1 read 不得呼叫 current writer")

    monkeypatch.setattr(codec, "encode_execution", forbidden_writer)
    envelope = decode_execution_envelope(raw)
    decoded = decode_execution(raw)

    assert envelope.schema_version == "recommendation-execution.v1"
    assert envelope.schema_revision == 1
    assert envelope.payload_hash == expected_payload_hash
    assert envelope.raw_payload == before
    assert envelope.raw_payload_sha256 == "sha256:" + expected_raw_sha256
    assert hashlib.sha256(raw).hexdigest() == expected_raw_sha256
    assert fixture_path.read_bytes() == before
    assert decoded == envelope.execution
    assert decoded.result_id == "rev1:baseline/0007 "
    assert decoded.request.config_snapshot is None
    assert decoded.request.max_stocks is None and decoded.request.top_n is None
    assert decoded.context.created_at is None
    assert decoded.context.available_at is None
    assert decoded.context.strategy_identity is None
    assert decoded.context.universe_identity is None
    assert decoded.context.snapshot_cohort is None
    assert decoded.context.evidence_identity is None
    assert decoded.context.result_config_snapshot is None
    assert decoded.decision is not None
    legacy_item = decoded.decision.items[0]
    assert legacy_item.close_price is None
    assert legacy_item.price_change is None
    assert legacy_item.indicator_score is None
    assert legacy_item.pattern_score is None
    assert legacy_item.volume_score is None
    assert legacy_item.industry is None
    assert legacy_item.reason_text is None
    assert legacy_item.rule_score == Decimal("91.2300")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("schema_revision", 0, "schema_revision"),
        ("schema_revision", 3, "schema_revision"),
        ("schema_version", "recommendation-execution.v2", "schema_version"),
    ),
)
def test_r009_reader_rejects_unknown_schema_or_revision(
    field: str, value: object, message: str
) -> None:
    document = _document(encode_execution(_execution()))
    document[field] = value

    with pytest.raises(ExecutionCodecError, match=message):
        decode_execution(_rehash(document))


def test_r009_reader_rejects_unknown_type_and_does_not_import_it() -> None:
    document = _document(encode_execution(_execution()))
    document["payload"]["$record"] = "some.attacker.module.Record"

    with pytest.raises(ExecutionCodecError, match="contract type"):
        decode_execution(_rehash(document))


def test_r009_reader_rejects_unknown_typed_record_field() -> None:
    document = _document(encode_execution(_execution()))
    request_fields = document["payload"]["fields"]["request"]["fields"]
    request_fields["unregistered_wire_field"] = "must reject"

    with pytest.raises(ExecutionCodecError, match="未知欄位"):
        decode_execution(_rehash(document))


def test_r009_reader_rejects_unknown_enum_type() -> None:
    document = _document(encode_execution(_execution()))
    status = document["payload"]["fields"]["status"]
    status["$enum"] = "attacker.module.ExecutionStatus"

    with pytest.raises(ExecutionCodecError, match="enum type 不支援"):
        decode_execution(_rehash(document))


def test_r009_reader_checks_payload_hash_before_contract_decode() -> None:
    raw = encode_execution(_execution()).replace(b"Legacy-ID", b"legacy-ID")

    for reader in (decode_execution, decode_execution_envelope):
        with pytest.raises(ExecutionCodecError, match="hash"):
            reader(raw)


def test_r009_canonical_readers_reject_noncanonical_source_bytes() -> None:
    document = _document(encode_execution(_execution()))
    whitespace_variant = json.dumps(
        document, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")
    reordered_document = dict(reversed(tuple(document.items())))
    reordered_variant = json.dumps(
        reordered_document,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")

    for raw in (whitespace_variant, reordered_variant):
        readers = (
            decode_execution,
            decode_execution_envelope,
            lambda payload: decode_artifact(
                payload, expected_sha256=hashlib.sha256(payload).hexdigest()
            ),
        )
        for reader in readers:
            with pytest.raises(ExecutionCodecError, match="canonical UTF-8 JSON"):
                reader(raw)


def test_r009_legacy_decoder_preserves_chinese_fields_and_calibration_metadata() -> None:
    legacy = {
        "證券代號": "2330",
        "證券名稱": "台積電",
        "收盤價": "600.10",
        "漲幅%": 2.5,
        "總分": 90.0,
        "指標分": 85.0,
        "圖形分": 95.0,
        "成交量分": 90.0,
        "推薦理由": "歷史 fixture",
        "產業": "半導體業",
        "Regime匹配": "是",
        "calibrated_probability_bp": 7200,
        "calibrated_probability_status": "available",
        "calibration_model_version": "legacy-model-4",
        "calibration_warnings": ["small sample"],
        "calibration_provenance": {"source": "historical", "sample_size": 0},
    }

    decoded = decode_legacy_recommendation(legacy)
    assert isinstance(decoded, RecommendationDTO)
    assert decoded.close_price == Decimal("600.10")
    assert decoded.calibrated_probability_bp == 7200
    assert decoded.calibration_warnings == ["small sample"]
    assert decoded.calibration_provenance == {"source": "historical", "sample_size": 0}
    exported = decoded.to_dict()
    assert exported["收盤價"] == Decimal("600.10")
    assert exported["Regime匹配"] == "是"
    assert exported["calibration_provenance"] == {"source": "historical", "sample_size": 0}


def test_r009_legacy_result_hashes_original_english_bytes_before_decode() -> None:
    document = {
        "result_id": "legacy-run-20260922",
        "result_name": "old English envelope",
        "config": {"profile": "legacy"},
        "recommendations": [
            {
                "stock_code": "2330",
                "stock_name": "TSMC",
                "close_price": "600.10",
                "price_change": 2.5,
                "total_score": 90.0,
                "indicator_score": 85.0,
                "pattern_score": 95.0,
                "volume_score": 90.0,
                "recommendation_reasons": "legacy English keys",
                "industry": "semiconductor",
                "regime_match": True,
                "calibrated_probability_bp": 7200,
                "calibration_source": "historical-fit",
            }
        ],
        "regime": "Trend",
        "created_at": "2024-01-02T03:04:05+00:00",
        "excluded_candidates_json": [{"stock_code": "2317", "reason": "filtered"}],
        "why_not_payload_json": [{"stock_code": "2317", "reason": "negative evidence"}],
        "liquidity_gate_payload_json": [{"stock_code": "2330", "status": "pass"}],
    }
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    expected_hash = hashlib.sha256(raw).hexdigest()
    before = bytes(raw)

    decoded = decode_legacy_result(raw, expected_sha256=expected_hash)
    dispatched = decode_artifact(raw, expected_sha256="sha256:" + expected_hash)

    assert isinstance(decoded, RecommendationResultDTO)
    assert isinstance(dispatched, RecommendationResultDTO)
    assert decoded.recommendations[0].close_price == Decimal("600.10")
    assert decoded.recommendations[0].calibrated_probability_bp == 7200
    assert decoded.recommendations[0].calibration_source == "historical-fit"
    assert decoded.why_not_payload_json == [{"stock_code": "2317", "reason": "negative evidence"}]
    assert decoded.excluded_candidates_json == [{"stock_code": "2317", "reason": "filtered"}]
    assert hashlib.sha256(raw).hexdigest() == expected_hash
    assert raw == before


def test_r009_artifact_hash_mismatch_stops_before_json_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def unexpected_parse(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("JSON parsing must not run before original hash check")

    monkeypatch.setattr(codec.json, "loads", unexpected_parse)
    for decoder in (decode_legacy_result, decode_artifact):
        with pytest.raises(ExecutionCodecError, match="尚未解析"):
            decoder(b"not-json", expected_sha256="0" * 64)
    assert called is False


def test_r009_bytes_artifact_readers_require_raw_sha_argument() -> None:
    for reader in (decode_legacy_result, decode_artifact):
        parameter = signature(reader).parameters["expected_sha256"]
        assert parameter.default is Parameter.empty


def test_r009_dto_from_dict_delegates_legacy_decoder_and_missing_defaults() -> None:
    decoded = RecommendationDTO.from_dict(
        {
            "stock_code": "2317",
            "stock_name": "Hon Hai",
            "close_price": "100.20",
            "price_change": 0,
            "total_score": 0,
            "indicator_score": 0,
            "pattern_score": 0,
            "volume_score": 0,
            "recommendation_reasons": "old fixture",
            "industry": "electronics",
            "regime_match": False,
        }
    )

    assert decoded.close_price == Decimal("100.20")
    assert decoded.threshold_mode == "fixed"
    assert decoded.calibration_status == "unavailable"
    assert decoded.calibration_provenance == {}


def test_r009_legacy_export_keeps_dto_subclass_behavior() -> None:
    class SpecializedRecommendationDTO(RecommendationDTO):
        pass

    dto = SpecializedRecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        close_price=Decimal("600.10"),
        price_change=0.0,
        total_score=0.0,
        indicator_score=0.0,
        pattern_score=0.0,
        volume_score=0.0,
        recommendation_reasons="legacy subclass",
        industry="半導體",
        regime_match=False,
    )

    assert dto.to_dict()["證券代號"] == "2330"


def test_r009_codec_has_no_generic_dataclass_conversion_or_arbitrary_import() -> None:
    source = Path(codec.__file__).read_text(encoding="utf-8")
    assert "asdict(" not in source
    assert "__dict__" not in source
    assert "pickle" not in source.lower()
    assert "importlib" not in source
