from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

from app_module.personalization_contract import (
    PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
    canonical_payload_hash,
)
from app_module.personalization_fit_runner import (
    PersonalizationFitArtifactError,
    PersonalizationFitArtifactEnvelope,
    PersonalizationFitArtifactReader,
    PersonalizationFitRequest,
    PersonalizationFitRunner,
    _persist_create_only,
)
from app_module.personalization_contract import PersonalizationEvaluationRow
from app_module.personalization_read_service import (
    PersonalizationReadReport,
    PersonalizationReadService,
)
from scripts.inspect_personalization_contract import (
    _fixture_evaluation_rows,
    _fixture_rows,
)
from tests.test_personalization_read_service import (
    COST_HASH,
    DATASET_HASH,
    LABEL_CONTRACT,
    RETURN_BASIS,
    SCOPE_ID,
    STOCK_CODE,
    UNIVERSE_HASH,
)


class _StubReadService:
    def __init__(self, rows: tuple[PersonalizationEvaluationRow, ...]) -> None:
        fingerprints = (
            {
                "path": "fixture/recommendation.json",
                "before": {
                    "path": "fixture/recommendation.json",
                    "exists": True,
                    "size": 10,
                    "mtime_ns": 1,
                    "sha256": "sha256:" + "1" * 64,
                    "read_error": "",
                },
                "after": {
                    "path": "fixture/recommendation.json",
                    "exists": True,
                    "size": 10,
                    "mtime_ns": 1,
                    "sha256": "sha256:" + "1" * 64,
                    "read_error": "",
                },
                "unchanged": True,
            },
        )
        self.report = PersonalizationReadReport(
            scope_id="scope_fixture_user_001",
            evaluated_as_of="2025-04-01",
            evaluation_cutoff_at="2025-04-01T23:59:00+00:00",
            source_manifest_hash=canonical_payload_hash(
                [{"path": item["path"], "before": item["before"]} for item in fingerprints]
            ),
            source_bytes_unchanged=True,
            source_consistency_status="verified",
            source_completeness_status="verified",
            source_fingerprints=fingerprints,
            recommendation_metadata=(),
            projections=(),
            evaluation_rows=tuple(row.to_dict() for row in rows),
            denominators={"evaluation_row_count": len(rows)},
            cohort={"cohort_status": "ready"},
            inventory={"truncated": False},
            candidate_inventory={},
            diagnostics=(),
        )

    def inspect_scope(self, **_: object) -> PersonalizationReadReport:
        return self.report


def _request(path: Path, **overrides: object) -> PersonalizationFitRequest:
    values: dict[str, Any] = {
        "scope_id": "scope_fixture_user_001",
        "fit_as_of": "2025-01-31",
        "evaluated_as_of": "2025-04-01",
        "evaluation_cutoff_at": "2025-04-01T23:59:00+00:00",
        "output_path": path,
        "result_id": "fixture-result",
        "stock_code": "2330",
    }
    values.update(overrides)
    return PersonalizationFitRequest(**cast(Any, values))


def _runner(
    path: Path,
    *,
    clock: datetime | None = None,
    rows: tuple[PersonalizationEvaluationRow, ...] | None = None,
) -> PersonalizationFitRunner:
    source_rows = rows or (_fixture_rows() + _fixture_evaluation_rows())
    return PersonalizationFitRunner(
        cast(PersonalizationReadService, _StubReadService(source_rows)),
        clock=(lambda: clock) if clock is not None else None,
    )


def _append_real_source_row(
    output_root: Path,
    repository: Any,
    journal: Any,
    *,
    result_id: str,
    prediction_id: str,
    decision_date: str,
    label_available_date: str,
) -> None:
    """用既有 writer 建立一筆獨立的 real-source fit/evaluation row。"""

    from decimal import Decimal
    from types import SimpleNamespace

    from app_module.dtos import RecommendationDTO
    from app_module.evidence_event_dtos import (
        EvidenceDataQuality,
        EvidenceEvent,
        EvidenceEventType,
        EvidenceOutcome,
        EvidenceOutcomeStatus,
    )
    from app_module.evidence_event_repository import EvidenceEventRepository
    from app_module.personalization_contract import PersonalizationDeliveryScope
    from app_module.personalization_save_adapter import (
        PersonalizationRecommendationSaveAdapter,
    )
    from app_module.recommendation_save_coordinator import RecommendationSaveRequest

    decision_at = f"{decision_date}T09:00:00+00:00"
    available_at = f"{decision_date}T08:55:00+00:00"
    receipt_created_at = f"{decision_date}T09:01:00+00:00"
    scope = PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="user",
        delivery_id=f"delivery_{result_id}",
        declared_at=f"{decision_date}T08:50:00+00:00",
        decision_at=decision_at,
        available_at=available_at,
        captured_at=available_at,
        receipt_created_at=receipt_created_at,
    )
    projection_row = {
        "stock_code": STOCK_CODE,
        "model_version": "model_001",
        "dataset_version": "dataset_001",
        "dataset_hash": DATASET_HASH,
        "cost_scenario_hash": COST_HASH,
        "horizon": "20 trading days",
        "prediction_id": prediction_id,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
        "universe_policy_hash": UNIVERSE_HASH,
        "population_probability_bp": 5000,
        "calibrated_probability_bp": 5200,
        "status": "active_candidate",
    }
    receipt_body: dict[str, Any] = {
        "schema_version": PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
        "result_id": result_id,
        "decision_date": decision_date,
        "candidate_identity": {"candidate_id": "model_001"},
        "model_id": "model_001",
        "dataset_id": "dataset_001",
        "dataset_hash": DATASET_HASH,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
        "universe_policy_hash": UNIVERSE_HASH,
        "source_id": "recommendation_service",
        "selection_contract": {
            "authority": "rule_top_n",
            "score_kind": "rule_total_score",
            "percentile_kind": "rule_percentile",
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": False,
        },
        "projections": [projection_row],
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "shadow_only": True,
    }
    receipt = {
        **receipt_body,
        "receipt_hash": canonical_payload_hash(receipt_body),
    }
    context = {
        "as_of_date": decision_date,
        "data_date": decision_date,
        "run_started_at": f"{decision_date}T08:49:00+00:00",
        "personalization_scope_declared_at": scope.declared_at,
        "available_at": scope.available_at,
        "captured_at": scope.captured_at,
        "decision_at": scope.decision_at,
        "calibration_projection_receipt_created_at": scope.receipt_created_at,
        "temporal_contract": "recommendation-producer-clock.v1",
        "temporal_mode": "natural_producer_clock",
        "cutoff_selection": "producer_selected_latest_available_cutoff",
        "cutoff_policy": "source_latest_available_exact",
        "decision_clock_timezone": "UTC",
        "market_calendar_timezone": "Asia/Taipei",
        "prediction_decision_anchor": "actual_producer_decision_at",
        "horizon_anchor": "immutable_projection_receipt",
        "calibration_projection_receipt": receipt,
        "calibration_projection_receipt_metadata": {
            "result_id": result_id,
            "receipt_hash": receipt["receipt_hash"],
            "receipt_created_at": scope.receipt_created_at,
        },
        "calibration_projection_rows": {STOCK_CODE: dict(projection_row)},
    }
    recommendation = RecommendationDTO(
        stock_code=STOCK_CODE,
        stock_name="台積電",
        close_price=Decimal("100.00"),
        price_change=1.0,
        total_score=80.0,
        indicator_score=80.0,
        pattern_score=80.0,
        volume_score=80.0,
        recommendation_reasons="real-source fit runner integration",
        industry="半導體",
        regime_match=True,
        calibration_provenance={"projection_receipt_hash": receipt["receipt_hash"]},
    )
    request = RecommendationSaveRequest(
        result_name=f"personalization fit runner {result_id}",
        config={"_recommendation_run_context": context},
        recommendations=(recommendation,),
        current_profile=None,
        profile_meta={},
        current_regime=None,
        personalization_scope=scope,
        personalization_request_id=f"request_{result_id}",
    )
    outcome = request.persist(
        recommendation_repository=repository,
        universe_service=None,
        recommendation_service=SimpleNamespace(last_run_context={}),
        regime_service=SimpleNamespace(),
    )
    assert outcome.result_id == result_id
    ack = PersonalizationRecommendationSaveAdapter().acknowledge_delivery(
        recommendation_repository=repository,
        journal_service=journal,
        result_id=result_id,
        scope_id=SCOPE_ID,
        delivery_id=outcome.personalization_delivery_id or "",
        persisted_at=decision_at,
        delivered_at=decision_at,
        recorded_at=f"{decision_date}T09:02:00+00:00",
    )
    assert ack.status == "delivered"

    evidence = EvidenceEventRepository(
        object(),
        db_path=output_root.parent / "evidence.sqlite",
    )
    identity = {
        "result_id": result_id,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": prediction_id,
        "prediction_receipt_hash": receipt["receipt_hash"],
        "horizon_days": 20,
        "cost_scenario_hash": COST_HASH,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
    }
    event_id = f"event_{result_id}"
    event = EvidenceEvent(
        event_id=event_id,
        event_hash=canonical_payload_hash({"event_id": event_id}),
        event_date=decision_date,
        decision_date=decision_date,
        symbol=STOCK_CODE,
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="recommendation_service",
        source_id=f"provider-{result_id}",
        available_date=decision_date,
        data_quality=EvidenceDataQuality.OBSERVED,
        metadata=dict(identity),
        created_at=decision_at,
    )
    evidence.insert_event(event)
    outcome_metadata = {
        **identity,
        "label_available_date": label_available_date,
        "label_available_at": f"{label_available_date}T00:00:00+00:00",
        "outcome_recorded_at": f"{label_available_date}T00:00:00+00:00",
        "label": 1,
        "outcome_tier": "natural_forward",
    }
    evidence.upsert_outcome(
        EvidenceOutcome(
            outcome_id=f"outcome_{result_id}",
            event_id=event_id,
            window_days=20,
            return_basis=RETURN_BASIS,
            event_price_date=decision_date,
            outcome_price_date=label_available_date,
            forward_return_bp=800,
            outcome_status=EvidenceOutcomeStatus.READY,
            data_quality=EvidenceDataQuality.OBSERVED,
            calculated_at=f"{label_available_date}T00:00:00+00:00",
            data_as_of_date=label_available_date,
            metadata=outcome_metadata,
        )
    )


def test_real_clock_is_stored_and_retrospective_semantics_are_explicit(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    result = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, 34, 56, 789, tzinfo=timezone.utc),
    ).run(_request(artifact_path))

    assert result.status == "created"
    envelope = PersonalizationFitArtifactReader.read(
        artifact_path,
        expected_scope_id="scope_fixture_user_001",
        expected_artifact_hash=result.artifact_hash,
    )
    assert envelope.artifact.created_at == "2025-04-05T12:34:56.000789+00:00"
    assert envelope.source_binding["fit_creation_clock"] == "runtime_utc"
    temporal = envelope.source_binding["evaluation_temporal_semantics"]
    assert temporal["mode"] == "retrospective_offline"
    assert temporal["prospective"] is False
    assert temporal["natural_forward_credit"] is False
    assert temporal["created_after_evaluation_cutoff"] is True
    assert result.fit_decision_date_count == envelope.artifact.fit_row_count == 2


def test_retry_reuses_immutable_artifact_even_when_runtime_clock_changes(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    first = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    first_bytes = artifact_path.read_bytes()

    second = _runner(
        artifact_path,
        clock=datetime(2025, 4, 6, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))

    assert first.status == "created"
    assert second.status == "idempotent_retry"
    assert second.artifact_hash == first.artifact_hash
    assert artifact_path.read_bytes() == first_bytes
    assert "immutable_artifact_reused" in second.diagnostics


def test_retry_with_explicit_different_creation_clock_is_conflict(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    first = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    conflict = _runner(
        artifact_path,
        clock=datetime(2025, 4, 6, 12, tzinfo=timezone.utc),
    ).run(
        _request(
            artifact_path,
            created_at="2025-04-06T12:00:00.000000+00:00",
        )
    )

    assert first.status == "created"
    assert conflict.status == "blocked"
    assert conflict.blocked_reason == "artifact_output_conflict"


def test_retry_with_changed_fit_parameter_is_conflict(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    first = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    conflict = _runner(
        artifact_path,
        clock=datetime(2025, 4, 6, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path, shrinkage_strength=11))

    assert first.status == "created"
    assert conflict.status == "blocked"
    assert conflict.blocked_reason == "artifact_output_conflict"


def test_retry_with_changed_source_rows_is_source_conflict(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    rows = _fixture_rows() + _fixture_evaluation_rows()
    first = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
        rows=rows,
    ).run(_request(artifact_path))
    changed_fit = replace(rows[0], label=0)
    changed = _runner(
        artifact_path,
        clock=datetime(2025, 4, 6, 12, tzinfo=timezone.utc),
        rows=(changed_fit, *rows[1:]),
    ).run(_request(artifact_path))

    assert first.status == "created"
    assert changed.status == "blocked"
    assert changed.blocked_reason == "artifact_source_conflict"


def test_tampered_or_partial_final_is_blocked_without_overwrite(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    first = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["artifact"]["fit_row_count"] = 999
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _runner(
        artifact_path,
        clock=datetime(2025, 4, 6, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))

    assert first.status == "created"
    assert result.status == "blocked"
    assert result.blocked_reason == "artifact_output_invalid"

    # 模擬程序在 final name 上留下截斷 JSON；retry 只能阻擋並保留原始
    # partial bytes，不能把新 fit 覆蓋到同一路徑。
    partial = b'{"schema_version":"personalization-fit-artifact-envelope.v1"'
    artifact_path.write_bytes(partial)
    partial_result = _runner(
        artifact_path,
        clock=datetime(2025, 4, 7, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    assert partial_result.status == "blocked"
    assert partial_result.blocked_reason == "artifact_output_invalid"
    assert artifact_path.read_bytes() == partial


def test_fsync_interruption_leaves_no_final_or_temporary_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "fit.json"
    first = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    envelope = PersonalizationFitArtifactReader.read(artifact_path)
    artifact_path.unlink()

    def fail_fsync(_: int) -> None:
        raise OSError("simulated fsync interruption")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(PersonalizationFitArtifactError):
        _persist_create_only(artifact_path, envelope)

    assert first.status == "created"
    assert not artifact_path.exists()
    assert list(tmp_path.glob(".fit.json.*.tmp")) == []


def test_partial_stream_interruption_leaves_no_final_or_temp_and_retry_is_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "partial-stream.json"
    first = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    envelope = PersonalizationFitArtifactReader.read(artifact_path)
    artifact_path.unlink()

    real_fdopen = os.fdopen

    class _PartialWriteStream:
        def __init__(self, raw: Any) -> None:
            self._raw = raw

        def __enter__(self) -> "_PartialWriteStream":
            return self

        def __exit__(self, *args: object) -> Any:
            return self._raw.__exit__(*args)

        def write(self, value: bytes) -> int:
            self._raw.write(value[: max(1, len(value) // 2)])
            self._raw.flush()
            raise OSError("simulated partial stream interruption")

        def flush(self) -> Any:
            return self._raw.flush()

        def fileno(self) -> int:
            return int(self._raw.fileno())

    def partial_fdopen(fd: int, mode: str, *args: Any, **kwargs: Any) -> Any:
        return _PartialWriteStream(real_fdopen(fd, mode, *args, **kwargs))

    monkeypatch.setattr(os, "fdopen", partial_fdopen)
    with pytest.raises(PersonalizationFitArtifactError):
        _persist_create_only(artifact_path, envelope)
    assert not artifact_path.exists()
    assert list(tmp_path.glob(".partial-stream.json.*.tmp")) == []

    monkeypatch.undo()
    assert _persist_create_only(artifact_path, envelope) == "created"
    published_bytes = artifact_path.read_bytes()
    assert _persist_create_only(artifact_path, envelope) == "idempotent_retry"
    assert artifact_path.read_bytes() == published_bytes
    assert first.status == "created"


def test_insufficient_research_minimum_does_not_publish_artifact(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    result = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path, min_fit_rows=3))

    assert result.status == "blocked"
    assert result.blocked_reason == "fit_sample_insufficient"
    assert not artifact_path.exists()


def test_scope_and_label_cutoff_contracts_block_before_persistence(tmp_path: Path) -> None:
    rows = _fixture_rows() + _fixture_evaluation_rows()
    scope_path = tmp_path / "scope-conflict.json"
    scope_result = _runner(
        scope_path,
        rows=(replace(rows[0], scope_id="other-scope"), *rows[1:]),
    ).run(_request(scope_path))
    assert scope_result.blocked_reason == "source_row_contract_invalid"
    assert not scope_path.exists()

    label_path = tmp_path / "label-cutoff.json"
    label_result = _runner(
        label_path,
        rows=(
            replace(
                rows[0],
                label_available_date="2025-02-01",
                label_available_at="2025-02-01T00:00:00+00:00",
                outcome_recorded_at="2025-02-01T01:00:00+00:00",
            ),
            *rows[1:],
        ),
    ).run(_request(label_path))
    assert label_result.blocked_reason == "fit_sample_insufficient"
    assert any(
        "label_date_after_fit_as_of" in item for item in label_result.diagnostics
    ), label_result.diagnostics
    assert not label_path.exists()


def test_mixed_lineage_is_rejected_by_existing_evaluator(tmp_path: Path) -> None:
    rows = _fixture_rows() + _fixture_evaluation_rows()
    artifact_path = tmp_path / "mixed-lineage.json"
    result = _runner(
        artifact_path,
        rows=(
            rows[0],
            replace(rows[1], dataset_hash="sha256:" + "9" * 64),
            *rows[2:],
        ),
    ).run(_request(artifact_path))

    assert result.blocked_reason == "fit_contract_blocked"
    assert not artifact_path.exists()


def test_embargo_excludes_boundary_evaluation_row(tmp_path: Path) -> None:
    rows = _fixture_rows() + _fixture_evaluation_rows()
    boundary = replace(rows[2], decision_date="2025-02-02")
    artifact_path = tmp_path / "embargo.json"
    result = _runner(
        artifact_path,
        rows=(rows[0], rows[1], boundary, rows[3]),
    ).run(_request(artifact_path, embargo_days=2))

    assert result.status == "created"
    envelope = PersonalizationFitArtifactReader.read(artifact_path)
    assert tuple(envelope.source_binding["evaluation_row_ids"]) == ("eval_002",)


def test_reader_rejects_noncanonical_or_wrong_scope_envelope(tmp_path: Path) -> None:
    artifact_path = tmp_path / "fit.json"
    result = _runner(
        artifact_path,
        clock=datetime(2025, 4, 5, 12, tzinfo=timezone.utc),
    ).run(_request(artifact_path))
    assert result.status == "created"
    with pytest.raises(PersonalizationFitArtifactError):
        PersonalizationFitArtifactReader.read(
            artifact_path,
            expected_scope_id="other-scope",
        )
    artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")
    with pytest.raises(PersonalizationFitArtifactError):
        PersonalizationFitArtifactReader.read(artifact_path)


def test_real_sources_fit_cli_and_existing_reader_cli_verify_envelope(
    tmp_path: Path,
    capsys: Any,
) -> None:
    from tests.test_personalization_read_service import (
        RESULT_ID,
        SCOPE_ID,
        STOCK_CODE,
        _append_action_and_outcome,
        _save_sources,
    )
    from scripts.inspect_personalization_sources import main as inspect_main
    from scripts.run_personalization_fit import main as fit_main

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    evidence_path = output_root.parent / "evidence.sqlite"
    journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    artifact_path = tmp_path / "fit-envelope.json"

    fit_code = fit_main(
        [
            "--scope-id",
            SCOPE_ID,
            "--fit-as-of",
            "2025-03-05",
            "--evaluated-as-of",
            "2025-03-05",
            "--evaluation-cutoff-at",
            "2025-03-05T00:00:00+00:00",
            "--output-root",
            str(output_root),
            "--output-path",
            str(artifact_path),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--result-id",
            RESULT_ID,
            "--stock-code",
            STOCK_CODE,
            "--min-fit-rows",
            "1",
            "--min-fit-decision-dates",
            "1",
        ]
    )
    fit_payload = json.loads(capsys.readouterr().out)
    assert fit_code == 0, fit_payload
    assert fit_payload["status"] == "created"
    assert fit_payload["scope_id"] == SCOPE_ID
    assert fit_payload["fit_row_count"] == 1
    assert fit_payload["fit_decision_date_count"] == 1
    assert fit_payload["evaluation"] is not None
    assert fit_payload["evaluation"]["rows"] == []
    assert fit_payload["evaluation"]["reason"] == (
        "insufficient_natural_evidence:no_evaluation_rows"
    )
    assert artifact_path.is_file()
    envelope = PersonalizationFitArtifactReader.read(
        artifact_path,
        expected_scope_id=SCOPE_ID,
        expected_artifact_hash=fit_payload["artifact_hash"],
    )
    binding = envelope.source_binding
    assert binding["scope_id"] == SCOPE_ID
    assert binding["source_consistency_status"] == "verified"
    assert binding["source_completeness_status"] == "verified"
    assert binding["source_bytes_unchanged"] is True
    assert binding["fit_row_count"] == 1
    assert binding["fit_decision_date_count"] == 1
    assert tuple(binding["fit_row_ids"]) == envelope.artifact.fit_row_ids
    # 唯一真實來源列落在 fit cohort；runner 的 purge/embargo 會使 evaluation
    # cohort 保持空集合，避免把同一列回灌成 OOS 成效。
    assert tuple(binding["evaluation_row_ids"]) == ()
    assert binding["evaluation_row_count"] == 0
    assert binding["evaluation"]["artifact_id"] == fit_payload["evaluation"]["artifact_id"]
    assert binding["evaluation"]["rows"] == ()
    assert binding["evaluation"]["reason"] == fit_payload["evaluation"]["reason"]
    assert binding["evaluation_temporal_semantics"]["prospective"] is False

    inspect_code = inspect_main(
        [
            "--scope-id",
            SCOPE_ID,
            "--as-of",
            "2025-03-05",
            "--evaluation-cutoff-at",
            "2025-03-05T00:00:00+00:00",
            "--output-root",
            str(output_root),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--result-id",
            RESULT_ID,
            "--stock-code",
            STOCK_CODE,
            "--fit-artifact",
            str(artifact_path),
        ]
    )
    inspect_payload = json.loads(capsys.readouterr().out)
    assert inspect_code == 0
    assert inspect_payload["scope_id"] == SCOPE_ID
    assert inspect_payload["source_consistency_status"] == "verified"
    assert inspect_payload["source_completeness_status"] == "verified"
    assert inspect_payload["fit_artifact_read_status"] == "verified_envelope"
    assert inspect_payload["evaluation"] is not None
    assert inspect_payload["evaluation"]["rows"] == []
    assert inspect_payload["evaluation"]["reason"] == (
        "insufficient_natural_evidence:no_evaluation_rows"
    )
    assert inspect_payload["fit_artifact_binding"] == {
        "fit_row_ids": ["outcome_read_service_001"],
        "evaluation_row_ids": [],
        "fit_overlap_source_row_count": 1,
        "evaluation_row_count": 0,
        "fit_fingerprint_match": True,
        "evaluation_fingerprint_match": True,
        "source_fingerprint_match": True,
        "missing_fit_row_ids": [],
        "missing_evaluation_row_ids": [],
        "status": "verified",
    }
    assert "fit_artifact_fit_overlap_excluded:1" in inspect_payload["diagnostics"]
    assert "fit_artifact_envelope_verified" in inspect_payload["diagnostics"]

    wrong_scope_code = inspect_main(
        [
            "--scope-id",
            "scope_wrong_for_reader",
            "--as-of",
            "2025-03-05",
            "--evaluation-cutoff-at",
            "2025-03-05T00:00:00+00:00",
            "--output-root",
            str(output_root),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--result-id",
            RESULT_ID,
            "--stock-code",
            STOCK_CODE,
            "--fit-artifact",
            str(artifact_path),
        ]
    )
    wrong_scope_payload = json.loads(capsys.readouterr().out)
    assert wrong_scope_code == 2
    assert wrong_scope_payload["blocked_reason"] == "fit_artifact_invalid"
    assert wrong_scope_payload["fit_artifact_read_status"] == "invalid"
    # 即使 envelope 的 evaluation cohort 為空，scope 不相符仍須在 reader
    # 邊界阻擋，不能讓空結果被誤當成 verified binding。
    assert wrong_scope_payload.get("evaluation") is None
    assert "fit_artifact_binding" not in wrong_scope_payload
    assert "fit_artifact_evaluation_binding_verified" not in wrong_scope_payload.get(
        "diagnostics", []
    )

    legacy_path = tmp_path / "legacy-bare-artifact.json"
    legacy_path.write_text(
        json.dumps(PersonalizationFitArtifactReader.read(artifact_path).artifact.to_dict()),
        encoding="utf-8",
    )
    legacy_code = inspect_main(
        [
            "--scope-id",
            SCOPE_ID,
            "--as-of",
            "2025-03-05",
            "--output-root",
            str(output_root),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--result-id",
            RESULT_ID,
            "--stock-code",
            STOCK_CODE,
            "--fit-artifact",
            str(legacy_path),
        ]
    )
    legacy_payload = json.loads(capsys.readouterr().out)
    assert legacy_code == 0
    assert legacy_payload["fit_artifact_read_status"] == "legacy_bare_unverified"
    assert "fit_artifact_unverified_bare_legacy" in legacy_payload["diagnostics"]


def test_real_sources_default_gate_and_oos_reader_evaluation(
    tmp_path: Path,
    capsys: Any,
) -> None:
    from tests.test_personalization_read_service import (
        RESULT_ID,
        SCOPE_ID,
        STOCK_CODE,
        _append_action_and_outcome,
        _save_sources,
    )
    from scripts.inspect_personalization_sources import main as inspect_main
    from scripts.run_personalization_fit import main as fit_main

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    fit_result_id = "rec_read_service_fit_002"
    evaluation_result_id = "rec_read_service_eval_003"
    _append_real_source_row(
        output_root,
        repository,
        journal,
        result_id=fit_result_id,
        prediction_id="00000000-0000-0000-0000-000000000012",
        decision_date="2025-02-12",
        label_available_date="2025-03-04",
    )
    _append_real_source_row(
        output_root,
        repository,
        journal,
        result_id=evaluation_result_id,
        prediction_id="00000000-0000-0000-0000-000000000013",
        decision_date="2025-03-30",
        label_available_date="2025-04-19",
    )
    evidence_path = output_root.parent / "evidence.sqlite"
    journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    artifact_path = tmp_path / "fit-envelope-default-gate.json"

    fit_code = fit_main(
        [
            "--scope-id",
            SCOPE_ID,
            "--fit-as-of",
            "2025-03-05",
            "--evaluated-as-of",
            "2025-05-01",
            "--evaluation-cutoff-at",
            "2025-05-01T00:00:00+00:00",
            "--output-root",
            str(output_root),
            "--output-path",
            str(artifact_path),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--stock-code",
            STOCK_CODE,
        ]
    )
    fit_payload = json.loads(capsys.readouterr().out)
    assert fit_code == 0, fit_payload
    assert fit_payload["status"] == "created"
    assert fit_payload["fit_row_count"] == 2
    assert fit_payload["fit_decision_date_count"] == 2
    assert fit_payload["evaluation_row_count"] == 1
    assert fit_payload["evaluation"] is not None
    assert len(fit_payload["evaluation"]["rows"]) == 1
    assert fit_payload["evaluation"]["rows"][0]["row_id"] == (
        f"outcome_{evaluation_result_id}"
    )
    assert fit_payload["evaluation"]["status"] == "evaluated"
    assert fit_payload["evaluation"]["natural_forward_credit"] is False

    envelope = PersonalizationFitArtifactReader.read(
        artifact_path,
        expected_scope_id=SCOPE_ID,
        expected_artifact_hash=fit_payload["artifact_hash"],
    )
    binding = envelope.source_binding
    assert binding["source_consistency_status"] == "verified"
    assert binding["source_completeness_status"] == "verified"
    assert binding["fit_row_count"] == 2
    assert binding["fit_decision_date_count"] == 2
    assert set(binding["fit_row_ids"]) == {
        "outcome_read_service_001",
        f"outcome_{fit_result_id}",
    }
    assert tuple(binding["evaluation_row_ids"]) == (
        f"outcome_{evaluation_result_id}",
    )
    assert binding["evaluation_row_count"] == 1
    assert binding["evaluation"]["status"] == "evaluated"
    assert binding["evaluation_temporal_semantics"]["prospective"] is False

    inspect_code = inspect_main(
        [
            "--scope-id",
            SCOPE_ID,
            "--as-of",
            "2025-05-01",
            "--evaluation-cutoff-at",
            "2025-05-01T00:00:00+00:00",
            "--output-root",
            str(output_root),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--stock-code",
            STOCK_CODE,
            "--fit-artifact",
            str(artifact_path),
        ]
    )
    inspect_payload = json.loads(capsys.readouterr().out)
    assert inspect_code == 0
    assert inspect_payload["source_consistency_status"] == "verified"
    assert inspect_payload["source_completeness_status"] == "verified"
    assert inspect_payload["fit_artifact_read_status"] == "verified_envelope"
    assert inspect_payload["evaluation"] is not None
    assert inspect_payload["evaluation"]["status"] == "evaluated"
    assert len(inspect_payload["evaluation"]["rows"]) == 1
    assert inspect_payload["evaluation"]["rows"][0]["row_id"] == (
        f"outcome_{evaluation_result_id}"
    )
    assert inspect_payload["fit_artifact_binding"] == {
        "fit_row_ids": [
            "outcome_read_service_001",
            f"outcome_{fit_result_id}",
        ],
        "evaluation_row_ids": [f"outcome_{evaluation_result_id}"],
        "fit_overlap_source_row_count": 2,
        "evaluation_row_count": 1,
        "fit_fingerprint_match": True,
        "evaluation_fingerprint_match": True,
        "source_fingerprint_match": True,
        "missing_fit_row_ids": [],
        "missing_evaluation_row_ids": [],
        "status": "verified",
    }
    assert "fit_artifact_fit_overlap_excluded:2" in inspect_payload["diagnostics"]
    assert "evaluation_failed:PersonalizationCalibrationError" not in inspect_payload[
        "diagnostics"
    ]


def test_inspector_rejects_same_row_id_with_changed_outcome_binding(
    tmp_path: Path,
    capsys: Any,
) -> None:
    from tests.test_personalization_read_service import (
        RESULT_ID,
        SCOPE_ID,
        STOCK_CODE,
        _append_action_and_outcome,
        _save_sources,
    )
    from app_module.evidence_event_repository import EvidenceEventRepository
    from scripts.inspect_personalization_sources import main as inspect_main
    from scripts.run_personalization_fit import main as fit_main

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    evidence_path = output_root.parent / "evidence.sqlite"
    journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    artifact_path = tmp_path / "fit-envelope-tamper.json"
    fit_code = fit_main(
        [
            "--scope-id",
            SCOPE_ID,
            "--fit-as-of",
            "2025-03-05",
            "--evaluated-as-of",
            "2025-03-05",
            "--evaluation-cutoff-at",
            "2025-03-05T00:00:00+00:00",
            "--output-root",
            str(output_root),
            "--output-path",
            str(artifact_path),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--result-id",
            RESULT_ID,
            "--stock-code",
            STOCK_CODE,
            "--min-fit-rows",
            "1",
            "--min-fit-decision-dates",
            "1",
        ]
    )
    capsys.readouterr()
    assert fit_code == 0

    evidence = EvidenceEventRepository(object(), db_path=evidence_path)
    original = evidence.get_outcome(
        "event_read_service_001",
        20,
        RETURN_BASIS,
    )
    assert original is not None
    changed_metadata = dict(original.metadata)
    changed_metadata["label"] = 0
    changed_metadata["tamper_marker"] = "same-row-id-changed-outcome"
    evidence.upsert_outcome(
        replace(
            original,
            forward_return_bp=-800,
            metadata=changed_metadata,
        )
    )

    inspect_code = inspect_main(
        [
            "--scope-id",
            SCOPE_ID,
            "--as-of",
            "2025-03-05",
            "--evaluation-cutoff-at",
            "2025-03-05T00:00:00+00:00",
            "--output-root",
            str(output_root),
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
            "--result-id",
            RESULT_ID,
            "--stock-code",
            STOCK_CODE,
            "--fit-artifact",
            str(artifact_path),
        ]
    )
    inspect_payload = json.loads(capsys.readouterr().out)
    assert inspect_code == 2
    assert inspect_payload["fit_artifact_read_status"] == "verified_envelope"
    assert inspect_payload["fit_artifact_binding"]["status"] == (
        "blocked_source_fingerprint_mismatch"
    )
    assert inspect_payload["fit_artifact_binding"]["source_fingerprint_match"] is False
    assert inspect_payload["evaluation"] is None
    assert "fit_artifact_source_fingerprint_mismatch" in inspect_payload[
        "diagnostics"
    ]
