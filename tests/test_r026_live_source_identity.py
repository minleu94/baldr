from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app_module.recommendation import live_source_identity
from app_module.recommendation.historical_snapshot_custody import (
    HistoricalRawSnapshotQueryScopeV1,
    build_historical_raw_snapshot_custody_facts_v1,
)
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationProjection,
)
from app_module.recommendation_service import RecommendationService
from recommendation_test_support import build_recommendation_test_service
from data_module import source_revision_evidence_collector
from data_module.contracts.source_revision import (
    SOURCE_EVIDENCE_NAMESPACE_ORDER_V1,
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
    ValidatedSourceEvidenceV1,
)
from data_module.ml_historical_snapshot_provider import (
    HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
    MLHistoricalSnapshotProvider,
    MLHistoricalSnapshotReadLease,
)
from test_recommendation_service_calibration_integration import (
    _make_database,
    _recommendation,
)


def _empty_sidecar_evidence(scope_id: str, cutoff_date: date) -> ValidatedSourceEvidenceV1:
    return ValidatedSourceEvidenceV1(
        schema_version=SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
        scope_id=scope_id,
        cutoff_date=cutoff_date,
        namespaces=tuple(
            ValidatedNamespaceEvidenceV1(
                namespace=namespace,
                presence=SourceEvidencePresenceV1.EMPTY,
                files=(),
            )
            for namespace in SOURCE_EVIDENCE_NAMESPACE_ORDER_V1
        ),
    )


def _present_market_sidecar_evidence(
    scope_id: str, cutoff_date: date
) -> ValidatedSourceEvidenceV1:
    empty = _empty_sidecar_evidence(scope_id, cutoff_date)
    market = ValidatedNamespaceEvidenceV1(
        namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
        presence=SourceEvidencePresenceV1.PRESENT,
        files=(
            ValidatedEvidenceFileV1(
                role_id="synthetic/run/revision.json",
                sha256="b" * 64,
            ),
        ),
    )
    return ValidatedSourceEvidenceV1(
        schema_version=empty.schema_version,
        scope_id=scope_id,
        cutoff_date=cutoff_date,
        namespaces=(market, *empty.namespaces[1:]),
    )


def _snapshot_and_scope(database: Path):
    provider = MLHistoricalSnapshotProvider(database)
    snapshot = provider.load(
        decision_date="2014-03-31",
        history_start_date="2014-01-01",
        symbols=("AAA",),
        industry_index_names=(),
    )
    scope = HistoricalRawSnapshotQueryScopeV1(
        source_id=HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
        decision_date=date(2014, 3, 31),
        history_start_date=date(2014, 1, 1),
        symbols=("AAA",),
        industry_index_names=(),
    )
    return snapshot, scope


def test_provider_contract_id_is_optional_kw_only_and_does_not_change_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _make_database(database)
    snapshot, scope = _snapshot_and_scope(database)
    no_id = type(snapshot)(
        snapshot.decision_date,
        snapshot.feature_as_of_date,
        snapshot.prices,
        snapshot.technicals,
        snapshot.market,
        snapshot.industries,
        snapshot.source_fingerprint,
        snapshot.query_count,
        snapshot.source_tables,
        snapshot.query_only,
        snapshot.shadow_only,
        snapshot.production_action_allowed,
        snapshot.validated_schema,
        snapshot.validated_query_scope,
    )

    assert snapshot.provider_contract_id == HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1
    assert no_id.provider_contract_id is None
    assert no_id == snapshot
    assert repr(no_id) == repr(snapshot)
    assert hash(no_id) == hash(snapshot)
    assert build_historical_raw_snapshot_custody_facts_v1(
        snapshot=snapshot, query_scope=scope
    ).snapshot_id
    with pytest.raises(ValueError, match="provider contract ID is unsupported"):
        replace(snapshot, provider_contract_id="twstock-historical-sqlite-four-table.v2")
    with pytest.raises(ValueError, match="provider-carried"):
        build_historical_raw_snapshot_custody_facts_v1(
            snapshot=no_id, query_scope=scope
        )


def test_composer_keeps_raw_rows_sidecar_and_lease_observation_separate(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _make_database(database)
    snapshot, scope = _snapshot_and_scope(database)
    evidence = _empty_sidecar_evidence(
        "recommendation-live-0123456789abcdef0123456789abcdef",
        date(2014, 3, 31),
    )
    lease_observation = live_source_identity.SQLiteReadLeaseObservationV1(
        provider_contract_id=HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
        scope_id=evidence.scope_id,
    )

    result = live_source_identity.compose_live_calibration_source_identity_v1(
        snapshot=snapshot,
        query_scope=scope,
        source_evidence_before=evidence,
        source_evidence_after=evidence,
        sqlite_lease_observation=lease_observation,
    )

    assert result.provider_contract_id == HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1
    assert result.raw_snapshot.content_hash.startswith("sha256:")
    assert result.raw_snapshot.row_identity_hash.startswith("sha256:")
    assert result.sidecar_evidence is evidence
    assert result.sidecar_before_digest_sha256 == evidence.digest_sha256
    assert result.sqlite_lease_observation is lease_observation
    assert result.raw_snapshot.query_scope.source_id == result.provider_contract_id
    repeated = live_source_identity.compose_live_calibration_source_identity_v1(
        snapshot=snapshot,
        query_scope=scope,
        source_evidence_before=evidence,
        source_evidence_after=evidence,
        sqlite_lease_observation=lease_observation,
    )
    assert result.identity_digest_sha256 == repeated.identity_digest_sha256
    reference = result.raw_snapshot.to_snapshot_reference()
    assert reference.source_revision is None
    assert reference.source_id == HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1


def test_row_value_mutation_changes_raw_custody_hash_not_sidecar_or_lease_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _make_database(database)
    before_snapshot, scope = _snapshot_and_scope(database)
    scope_id = "recommendation-live-0123456789abcdef0123456789abcdef"
    evidence = _empty_sidecar_evidence(scope_id, date(2014, 3, 31))
    lease_observation = live_source_identity.SQLiteReadLeaseObservationV1(
        provider_contract_id=HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
        scope_id=scope_id,
    )

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE daily_prices SET 收盤價 = ? WHERE 日期 = ? AND 證券代號 = ?",
            ("777", "20140330", "AAA"),
        )
        connection.commit()
    finally:
        connection.close()

    after_snapshot, after_scope = _snapshot_and_scope(database)
    before = live_source_identity.compose_live_calibration_source_identity_v1(
        snapshot=before_snapshot,
        query_scope=scope,
        source_evidence_before=evidence,
        source_evidence_after=evidence,
        sqlite_lease_observation=lease_observation,
    )
    after = live_source_identity.compose_live_calibration_source_identity_v1(
        snapshot=after_snapshot,
        query_scope=after_scope,
        source_evidence_before=evidence,
        source_evidence_after=evidence,
        sqlite_lease_observation=lease_observation,
    )

    assert before.raw_snapshot.query_scope == after.raw_snapshot.query_scope
    assert before.raw_snapshot.row_identity_hash == after.raw_snapshot.row_identity_hash
    assert before.raw_snapshot.content_hash != after.raw_snapshot.content_hash
    assert before.sidecar_evidence.digest_sha256 == after.sidecar_evidence.digest_sha256
    assert before.sqlite_lease_observation == after.sqlite_lease_observation
    assert before.identity_digest_sha256 != after.identity_digest_sha256


def test_composer_rejects_scope_sidecar_and_lease_identity_mismatch(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _make_database(database)
    snapshot, scope = _snapshot_and_scope(database)
    scope_id = "recommendation-live-0123456789abcdef0123456789abcdef"
    evidence = _empty_sidecar_evidence(scope_id, date(2014, 3, 31))
    other = _empty_sidecar_evidence(
        "recommendation-live-fedcba9876543210fedcba9876543210", date(2014, 3, 31)
    )
    lease_observation = live_source_identity.SQLiteReadLeaseObservationV1(
        provider_contract_id=HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
        scope_id=scope_id,
    )

    with pytest.raises(ValueError, match="source ID does not match"):
        live_source_identity.compose_live_calibration_source_identity_v1(
            snapshot=snapshot,
            query_scope=HistoricalRawSnapshotQueryScopeV1(
                source_id="twstock.other-contract.v1",
                decision_date=scope.decision_date,
                history_start_date=scope.history_start_date,
                symbols=scope.symbols,
                industry_index_names=scope.industry_index_names,
            ),
            source_evidence_before=evidence,
            source_evidence_after=evidence,
            sqlite_lease_observation=lease_observation,
        )
    with pytest.raises(ValueError, match="query scope differs"):
        live_source_identity.compose_live_calibration_source_identity_v1(
            snapshot=snapshot,
            query_scope=HistoricalRawSnapshotQueryScopeV1(
                source_id=scope.source_id,
                decision_date=scope.decision_date,
                history_start_date=scope.history_start_date,
                symbols=("BBB",),
                industry_index_names=scope.industry_index_names,
            ),
            source_evidence_before=evidence,
            source_evidence_after=evidence,
            sqlite_lease_observation=lease_observation,
        )
    with pytest.raises(ValueError, match="changed within invocation"):
        live_source_identity.compose_live_calibration_source_identity_v1(
            snapshot=snapshot,
            query_scope=scope,
            source_evidence_before=evidence,
            source_evidence_after=other,
            sqlite_lease_observation=lease_observation,
        )
    with pytest.raises(ValueError, match="sidecar evidence does not match"):
        live_source_identity.compose_live_calibration_source_identity_v1(
            snapshot=snapshot,
            query_scope=scope,
            source_evidence_before=other,
            source_evidence_after=other,
            sqlite_lease_observation=lease_observation,
        )


@pytest.mark.parametrize("composer_fails", (False, True))
def test_service_builds_same_invocation_shadow_after_lease_without_effect_on_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    composer_fails: bool,
) -> None:
    database = tmp_path / "source.db"
    _make_database(database)
    scope_ids: list[str] = []
    receipt_attempts: list[dict[str, object]] = []

    def collect_source_evidence(**kwargs: Any) -> ValidatedSourceEvidenceV1:
        scope_id = str(kwargs["scope_id"])
        scope_ids.append(scope_id)
        return _empty_sidecar_evidence(scope_id, kwargs["cutoff_date"])

    monkeypatch.setattr(
        source_revision_evidence_collector,
        "collect_source_revision_evidence_v1",
        collect_source_evidence,
    )
    captured: list[live_source_identity.LiveCalibrationSourceIdentityV1] = []
    original_compose = live_source_identity.compose_live_calibration_source_identity_v1

    def capture_composer(**kwargs: Any):
        if composer_fails:
            raise RuntimeError("synthetic shadow-only composer failure")
        result = original_compose(**kwargs)
        captured.append(result)
        return result

    monkeypatch.setattr(
        live_source_identity,
        "compose_live_calibration_source_identity_v1",
        capture_composer,
    )

    def persist_receipt(**kwargs: object) -> dict[str, object]:
        receipt_attempts.append(dict(kwargs))
        return {
            "path": str(tmp_path / "projection-receipt.json"),
            "receipt_hash": "a" * 64,
            "receipt_created_at": "2014-03-31T16:00:00+00:00",
        }

    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(persist_receipt),
    )
    consumer = _CaptureConsumer()
    service = build_recommendation_test_service(
        SimpleNamespace(
            db_file=database,
            default_start_date="2014-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
    ),
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    recommendation = _recommendation()
    original_total_score = recommendation.total_score

    captured_identity = service._apply_recommendation_calibration(
        [recommendation], decision_date="2014-03-31"
    )

    assert len(consumer.calls) == 1
    assert len(receipt_attempts) == 1
    assert recommendation.total_score == original_total_score
    assert recommendation.ranking_score_bp == 7_200
    projection = service.last_calibration_projections["AAA"]
    assert (
        projection.status,
        projection.ranking_score_bp,
        projection.calibrated_probability_bp,
        projection.after_cost_profit_probability_bp,
        projection.source_trace,
    ) == (
        "active_candidate",
        7_200,
        5_800,
        5_700,
        ("candidate:candidate-model-1",),
    )
    assert receipt_attempts[0]["projections"] == service.last_calibration_projections
    assert service.last_run_context["calibration_projection_status"] == "active_candidate"
    assert service.last_run_context["calibration_projection_receipt_status"] == "persisted"
    assert service.last_run_context["calibration_projection_receipt"]["receipt_hash"] == "a" * 64
    assert "live_source_identity" not in service.last_run_context
    assert "source_revision" not in service.last_run_context
    assert "source_revision_evidence" not in consumer.calls[0]["inference_provenance"]
    assert len(set(scope_ids)) == 1
    if composer_fails:
        assert captured == []
        assert captured_identity is None
    else:
        assert len(captured) == 1
        assert captured_identity is captured[0]
        item = captured[0]
        assert item.scope_id == scope_ids[0]
        assert item.raw_snapshot.row_count > 0
        assert item.raw_snapshot.content_hash != ""
        expected_snapshot, expected_scope = _snapshot_and_scope(database)
        expected_facts = build_historical_raw_snapshot_custody_facts_v1(
            snapshot=expected_snapshot,
            query_scope=expected_scope,
        )
        assert item.raw_snapshot == expected_facts
        assert item.sidecar_evidence.scope_id == scope_ids[0]
        assert item.sqlite_lease_observation.scope_id == scope_ids[0]


class _CaptureConsumer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def project_many(self, **kwargs: object) -> dict[str, RecommendationCalibrationProjection]:
        self.calls.append(dict(kwargs))
        return {
            "AAA": RecommendationCalibrationProjection(
                stock_code="AAA",
                ranking_score_bp=7_200,
                ranking_percentile_bp=8_100,
                ranking_method="absolute_return_shadow_candidate",
                calibrated_probability_bp=5_800,
                calibrated_probability_status="shadow_candidate",
                after_cost_profit_probability_bp=5_700,
                after_cost_profit_probability_status="shadow_candidate",
                confidence_tier="research_candidate",
                evidence_confidence="shadow_candidate",
                sample_size=120,
                horizon="20 trading days",
                cost_basis="synthetic",
                cost_basis_bp=50,
                model_version="candidate-model-1",
                dataset_version="dataset-1",
                source_trace=("candidate:candidate-model-1",),
                warnings=("shadow-only",),
                status="active_candidate",
                inference_provenance=dict(kwargs["inference_provenance"]),
            )
        }


def test_service_rechecks_sidecar_after_projection_before_sqlite_postcheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_module import source_revision_evidence_collector
    from ml_module.historical_feature_builder import HistoricalFeatureBuilder

    database = tmp_path / "source.db"
    _make_database(database)
    events: list[str] = []
    evidence_calls: list[dict[str, object]] = []
    evidence_results: list[ValidatedSourceEvidenceV1] = []
    captured: list[live_source_identity.LiveCalibrationSourceIdentityV1] = []
    receipt_attempts: list[dict[str, object]] = []
    original_enter = MLHistoricalSnapshotReadLease.__enter__
    original_load = MLHistoricalSnapshotReadLease.load
    original_assert = MLHistoricalSnapshotReadLease.assert_unchanged
    original_exit = MLHistoricalSnapshotReadLease.__exit__
    original_compute = HistoricalFeatureBuilder.compute
    original_compose = live_source_identity.compose_live_calibration_source_identity_v1

    def collect(**kwargs: Any) -> ValidatedSourceEvidenceV1:
        evidence_calls.append(dict(kwargs))
        events.append(f"sidecar.{len(evidence_calls)}")
        evidence = _empty_sidecar_evidence(
            str(kwargs["scope_id"]), kwargs["cutoff_date"]
        )
        evidence_results.append(evidence)
        return evidence

    def recording_enter(self: MLHistoricalSnapshotReadLease):
        lease = original_enter(self)
        events.append("lease.open")
        return lease

    def recording_load(self: MLHistoricalSnapshotReadLease, **kwargs: Any):
        events.append("provider.load")
        return original_load(self, **kwargs)

    def recording_assert(self: MLHistoricalSnapshotReadLease) -> None:
        events.append("lease.assert_unchanged")
        original_assert(self)

    def recording_exit(
        self: MLHistoricalSnapshotReadLease,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        original_exit(self, exc_type, exc, traceback)
        events.append("lease.close")

    def recording_compute(self: HistoricalFeatureBuilder, snapshot: Any, **kwargs: Any):
        events.append("feature.compute")
        return original_compute(self, snapshot, **kwargs)

    def capture_composer(**kwargs: Any):
        events.append("shadow.compose")
        result = original_compose(**kwargs)
        captured.append(result)
        return result

    def persist_receipt(**kwargs: object) -> dict[str, object]:
        events.append("receipt.persist")
        receipt_attempts.append(dict(kwargs))
        return {
            "path": str(tmp_path / "projection-receipt.json"),
            "receipt_hash": "a" * 64,
            "receipt_created_at": "2014-03-31T16:00:00+00:00",
        }

    monkeypatch.setattr(
        source_revision_evidence_collector,
        "collect_source_revision_evidence_v1",
        collect,
    )
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__enter__", recording_enter)
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "load", recording_load)
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "assert_unchanged", recording_assert)
    monkeypatch.setattr(MLHistoricalSnapshotReadLease, "__exit__", recording_exit)
    monkeypatch.setattr(HistoricalFeatureBuilder, "compute", recording_compute)
    monkeypatch.setattr(
        live_source_identity,
        "compose_live_calibration_source_identity_v1",
        capture_composer,
    )
    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(persist_receipt),
    )

    class EventConsumer(_CaptureConsumer):
        def project_many(self, **kwargs: object):
            events.append("projection")
            return super().project_many(**kwargs)

    consumer = EventConsumer()
    service = build_recommendation_test_service(
        SimpleNamespace(
            db_file=database,
            default_start_date="2014-01-01",
            output_root=tmp_path / "output",
            data_root=tmp_path / "formal-data",
        ),
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )

    shadow = service._apply_recommendation_calibration(
        [_recommendation()], decision_date="2014-03-31"
    )

    assert events == [
        "lease.open",
        "sidecar.1",
        "provider.load",
        "feature.compute",
        "sidecar.2",
        "projection",
        "sidecar.3",
        "lease.assert_unchanged",
        "shadow.compose",
        "lease.close",
        "receipt.persist",
    ]
    assert len(evidence_calls) == 3
    assert all(call["scope_id"] == evidence_calls[0]["scope_id"] for call in evidence_calls)
    assert all(call["cutoff_date"] == date(2014, 3, 31) for call in evidence_calls)
    assert all(call["database_path"] == database.resolve() for call in evidence_calls)
    assert shadow is captured[0]
    assert captured[0].sidecar_evidence is evidence_results[2]
    assert len(consumer.calls) == len(receipt_attempts) == 1


@pytest.mark.parametrize("third_result", ("changed", "raises"))
def test_post_projection_sidecar_change_or_error_only_drops_shadow_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    third_result: str,
) -> None:
    from data_module import source_revision_evidence_collector

    database = tmp_path / "source.db"
    _make_database(database)
    evidence_calls: list[dict[str, object]] = []
    receipt_attempts: list[dict[str, object]] = []

    def collect(**kwargs: Any) -> ValidatedSourceEvidenceV1:
        evidence_calls.append(dict(kwargs))
        scope_id = str(kwargs["scope_id"])
        cutoff = kwargs["cutoff_date"]
        if len(evidence_calls) == 3:
            if third_result == "raises":
                raise RuntimeError("synthetic post-projection sidecar failure")
            return _present_market_sidecar_evidence(scope_id, cutoff)
        return _empty_sidecar_evidence(scope_id, cutoff)

    def persist_receipt(**kwargs: object) -> dict[str, object]:
        receipt_attempts.append(dict(kwargs))
        return {
            "path": str(tmp_path / "projection-receipt.json"),
            "receipt_hash": "c" * 64,
            "receipt_created_at": "2014-03-31T16:00:00+00:00",
        }

    monkeypatch.setattr(
        source_revision_evidence_collector,
        "collect_source_revision_evidence_v1",
        collect,
    )
    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(persist_receipt),
    )
    consumer = _CaptureConsumer()
    service = build_recommendation_test_service(
        SimpleNamespace(
            db_file=database,
            default_start_date="2014-01-01",
            output_root=tmp_path / "output",
            data_root=tmp_path / "formal-data",
        ),
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    warnings_before = list(service.last_run_context.get("warnings", []))
    recommendation = _recommendation()
    original_total_score = recommendation.total_score

    shadow = service._apply_recommendation_calibration(
        [recommendation], decision_date="2014-03-31"
    )

    assert len(evidence_calls) == 3
    assert len(consumer.calls) == len(receipt_attempts) == 1
    assert shadow is None
    assert recommendation.total_score == original_total_score
    assert recommendation.ranking_score_bp == 7_200
    assert service.last_calibration_projections["AAA"].status == "active_candidate"
    assert service.last_run_context["calibration_projection_status"] == "active_candidate"
    assert service.last_run_context["calibration_projection_receipt_status"] == "persisted"
    assert service.last_run_context.get("warnings", []) == warnings_before


def test_sqlite_commit_during_projection_still_fails_closed_after_sidecar_recheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_module import source_revision_evidence_collector

    database = tmp_path / "source.db"
    _make_database(database)
    evidence_calls: list[dict[str, object]] = []
    receipt_attempts: list[dict[str, object]] = []

    def collect(**kwargs: Any) -> ValidatedSourceEvidenceV1:
        evidence_calls.append(dict(kwargs))
        return _empty_sidecar_evidence(
            str(kwargs["scope_id"]), kwargs["cutoff_date"]
        )

    def persist_receipt(**kwargs: object) -> dict[str, object]:
        receipt_attempts.append(dict(kwargs))
        return {"path": "unused", "receipt_hash": "d" * 64}

    monkeypatch.setattr(
        source_revision_evidence_collector,
        "collect_source_revision_evidence_v1",
        collect,
    )
    monkeypatch.setattr(
        RecommendationService,
        "_persist_calibration_projection_receipt",
        staticmethod(persist_receipt),
    )

    class CommittingConsumer(_CaptureConsumer):
        def project_many(self, **kwargs: object):
            result = super().project_many(**kwargs)
            with sqlite3.connect(database) as writer:
                writer.execute(
                    "UPDATE daily_prices SET 收盤價 = ? WHERE 日期 = ? AND 證券代號 = ?",
                    ("999", "20140331", "AAA"),
                )
            return result

    consumer = CommittingConsumer()
    service = build_recommendation_test_service(
        SimpleNamespace(
            db_file=database,
            default_start_date="2014-01-01",
            output_root=tmp_path / "output",
            data_root=tmp_path / "formal-data",
        ),
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    recommendation = _recommendation()
    original_total_score = recommendation.total_score

    shadow = service._apply_recommendation_calibration(
        [recommendation], decision_date="2014-03-31"
    )

    assert shadow is None
    assert len(evidence_calls) == 3
    assert len(consumer.calls) == 1
    assert receipt_attempts == []
    assert recommendation.total_score == original_total_score
    assert recommendation.calibration_status == "unavailable"
    assert service.last_run_context["calibration_projection_status"] == "unavailable"
    assert any(
        warning.startswith("calibration_feature_source_unavailable:RuntimeError")
        for warning in service.last_run_context.get("warnings", [])
    )
