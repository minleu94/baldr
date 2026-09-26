from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
from app_module.recommendation.contracts import RecommendationRunEvidenceIdentity
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.journal_service import JournalService
from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
    canonical_payload_hash,
)
from app_module.recommendation.ml_postcalibration_handoff import (
    CalibrationProjectionStatusV1,
    CalibrationReceiptEventFactsV1,
    CalibrationReceiptStatusV1,
    RecommendationPostCalibrationHandoffSinkV1,
    RecommendationPostCalibrationHandoffV1,
    encode_candidate_identity_event_json_v1,
)
from app_module.v4_evidence_identity import build_strategy_config_identity
from app_module.v4_evidence_identity import build_recommendation_universe_identity
from data_module.ml_historical_snapshot_provider import (
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
)
from ml_module.recommendation_inference_provenance import (
    RecommendationInferenceProjectionReceipt,
    build_inference_projection_receipt,
    build_inference_provenance,
    build_training_provenance,
    inference_projection_receipt_path,
    validate_provenance_compatibility,
)
from ml_module.recommendation_probability_transform import PROBABILITY_TRANSFORM_ID


RESULT_ID = "rec_generation_cli_001"
STOCK_CODE = "2330"
PREDICTION_ID = "00000000-0000-0000-0000-000000000020"
SCOPE_ID = "scope_generation_cli_001"
COST_HASH = "sha256:" + ("b" * 64)
DATASET_HASH = "sha256:" + ("d" * 64)
UNIVERSE_HASH = "sha256:" + ("e" * 64)
LABEL_CONTRACT = "label_projection_v1"
RETURN_BASIS = "close_to_close_event_date"


def _receipt() -> RecommendationInferenceProjectionReceipt:
    snapshot = HistoricalRawSnapshot(
        decision_date="2025-02-10",
        feature_as_of_date="2025-02-09",
        prices=(
            HistoricalPriceObservation(
                symbol=STOCK_CODE,
                trading_date="2025-02-09",
                open_price=Decimal("100"),
                high_price=Decimal("101"),
                low_price=Decimal("99"),
                close_price=Decimal("100"),
                volume=1_000,
                turnover_amount_minor=100_000,
            ),
        ),
        technicals=(),
        market=(),
        industries=(),
        source_fingerprint="sha256:" + ("1" * 64),
        query_count=1,
    )
    inference = build_inference_provenance(
        snapshot=snapshot,
        feature_rows=(
            {
                "symbol": STOCK_CODE,
                "decision_date": "2025-02-10",
                "feature_as_of_date": "2025-02-09",
                "feature_available_date": "2025-02-09",
                "values": (("momentum_bp", 100),),
            },
        ),
        feature_schema=(("momentum_bp", "int", "bp"),),
        feature_registry_hash="sha256:" + ("2" * 64),
        cost_scenario_hash=COST_HASH,
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    training = build_training_provenance(lineage_payload=None)
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=COST_HASH,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    return build_inference_projection_receipt(
        decision_date="2025-02-10",
        result_id=RESULT_ID,
        candidate_identity={"candidate_id": "model_generation_cli"},
        training_provenance=training,
        inference_provenance=inference,
        compatibility=compatibility,
        projections=(
            {
                "stock_code": STOCK_CODE,
                "model_version": "model_generation_cli",
                "dataset_version": "dataset_generation_cli",
                "dataset_hash": DATASET_HASH,
                "cost_scenario_hash": COST_HASH,
                "horizon": "20 trading days",
                "prediction_id": PREDICTION_ID,
                "label_contract_id": LABEL_CONTRACT,
                "return_basis": RETURN_BASIS,
                "universe_policy_hash": UNIVERSE_HASH,
                "population_probability_bp": 5000,
                "calibrated_probability_bp": 5200,
                "status": "active_candidate",
            },
        ),
    )


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="local",
        delivery_id="delivery_generation_cli_001",
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
    )


def _persist_test_receipt(root: Path, receipt: RecommendationInferenceProjectionReceipt) -> Path:
    """Write deterministic bytes inside pytest temp without the OS hardlink gate."""

    path = inference_projection_receipt_path(root, receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    if path.exists():
        assert path.read_bytes() == payload
    else:
        path.write_bytes(payload)
    return path


def _publish_test_calibration_handoff(
    producer: Any,
    receipt: RecommendationInferenceProjectionReceipt,
    receipt_path: Path,
) -> None:
    """依本 fixture 實際寫入及精確讀回的 receipt 發布 typed facts。"""

    sink = getattr(producer, "_r026_post_calibration_handoff_sink", None)
    if type(sink) is not RecommendationPostCalibrationHandoffSinkV1:
        # 舊版單獨時鐘測試未建立 execution sink，保留其原相容路徑。
        return
    payload = receipt.payload
    candidate = payload["candidate_identity"]
    inference = payload["inference_provenance"]
    projections = payload["projections"]
    persisted_bytes = receipt_path.read_bytes()
    expected_bytes = (
        json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    assert persisted_bytes == expected_bytes
    assert json.loads(persisted_bytes) == receipt.to_dict()
    receipt_created_at = "2025-02-10T09:01:00.000000+00:00"
    sink.publish(
        RecommendationPostCalibrationHandoffV1(
            consumer_configured=(
                getattr(producer, "calibration_consumer", None) is not None
            ),
            attempted=True,
            projection_status=CalibrationProjectionStatusV1.ACTIVE_CANDIDATE,
            receipt_status=CalibrationReceiptStatusV1.PERSISTED,
            receipt_event=CalibrationReceiptEventFactsV1(
                payload_present=True,
                attempted=True,
                persisted=True,
                readback_verified=True,
                identity_verified=True,
                path=str(receipt_path),
                receipt_hash=receipt.receipt_hash,
                receipt_created_at=receipt_created_at,
                result_id=str(payload.get("result_id") or ""),
                decision_date=str(payload.get("decision_date") or ""),
                candidate_id=str(candidate.get("candidate_id") or ""),
                candidate_identity_json=encode_candidate_identity_event_json_v1(
                    candidate
                ),
                cost_scenario_hash=str(payload.get("cost_scenario_hash") or ""),
                cost_scenario_id=str(inference.get("cost_scenario_id") or ""),
                projected_stock_codes=tuple(
                    str(row.get("stock_code") or "")
                    for row in projections
                    if isinstance(row, Mapping)
                ),
                projection_rows_sha256=str(
                    payload.get("projection_rows_sha256") or ""
                ),
                inference_source_hash=str(
                    inference.get("inference_source_hash") or ""
                ),
                inference_pit_hash=str(inference.get("inference_pit_hash") or ""),
                feature_rows_sha256=str(
                    inference.get("feature_rows_sha256") or ""
                ),
            ),
        )
    )


class _FakeRecommendationProducer:
    calls = 0

    def __init__(
        self,
        config: Any,
        *,
        input_preparer: Any = None,
        regime_service: Any = None,
    ) -> None:
        self.config = config
        self.input_preparer = input_preparer
        self.recommendation_input_preparer = input_preparer
        self.regime_service = regime_service
        self.last_run_context: dict[str, Any] = {}
        self.last_calibration_projections: dict[str, Any] = {}
        self.last_screening_matrix: list[dict[str, Any]] = []
        self.last_excluded_candidates_json: list[dict[str, Any]] = []
        self.last_why_not_payload_json: list[dict[str, Any]] = []
        self.last_liquidity_gate_payload_json: list[dict[str, Any]] = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json: list[str] = []
        self._personalization_execution_clocks: dict[str, str] = {}
        self.calibration_consumer = object()
        self._r011_last_state_lock = None

    def _reset_negative_evidence_buffers(self) -> None:
        self.last_calibration_projections = {}
        self.last_screening_matrix = []
        self.last_excluded_candidates_json = []
        self.last_why_not_payload_json = []
        self.last_liquidity_gate_payload_json = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json = []
        self.last_run_context = {}

    def _get_fundamental_sqlite_provider(self) -> None:
        return None

    def _produce(
        self,
        config: dict[str, Any],
        *,
        max_stocks: int,
        top_n: int,
        as_of_date: str | None,
        universe: list[str] | None,
        result_id: str,
        historical_research: bool,
        select_latest_available_cutoff: bool,
        input_session: Any = None,
    ) -> list[RecommendationDTO]:
        del input_session
        assert result_id == RESULT_ID
        receipt = _receipt()
        receipt_path = _persist_test_receipt(
            self.config.output_root,
            receipt,
        )
        _publish_test_calibration_handoff(self, receipt, receipt_path)
        type(self).calls += 1
        resolved_as_of = as_of_date or "2025-02-10"
        temporal_mode = (
            "historical_research_not_as_if_available"
            if historical_research
            else "natural_producer_clock"
        )
        cutoff_selection = (
            "explicit_historical_cutoff"
            if historical_research
            else "producer_selected_latest_available_cutoff"
        )
        cutoff_policy = (
            "explicit_historical_research"
            if historical_research
            else "source_latest_available_exact"
        )
        strategy_identity = build_strategy_config_identity(
            config,
            max_stocks=max_stocks,
            top_n=top_n,
        )
        universe_identity = build_recommendation_universe_identity(
            decision_date=resolved_as_of,
            selection_mode="explicit_universe" if universe is not None else "top_max_stocks",
            industry_filter="全部",
            max_stocks=max_stocks,
            requested_codes=universe,
            selected_codes=[STOCK_CODE],
            source_provider_id="generation-cli-test-provider",
        )
        self.last_run_context = {
            "schema_version": "recommendation-context.v1",
            "strategy_config": dict(config),
            "universe_spec": {
                "codes": sorted(universe or []) or None,
                "max_stocks": max_stocks,
                "selected_codes": [STOCK_CODE],
                "selection_mode": "explicit_universe" if universe is not None else "top_max_stocks",
                "industry_filter": "全部",
            },
            "result_id": RESULT_ID,
            "as_of_date": resolved_as_of,
            "data_date": resolved_as_of,
            "run_started_at": "2025-02-10T08:50:00.000000+00:00",
            "personalization_scope_declared_at": "2025-02-10T08:50:00.000000+00:00",
            "available_at": "2025-02-10T08:55:00.000000+00:00",
            "captured_at": "2025-02-10T08:55:00.000000+00:00",
            "decision_at": "2025-02-10T09:00:00.000000+00:00",
            "calibration_projection_receipt_created_at": "2025-02-10T09:01:00.000000+00:00",
            "calibration_projection_receipt": {
                "path": str(receipt_path),
                "receipt_hash": receipt.receipt_hash,
                "result_id": RESULT_ID,
                "receipt_created_at": "2025-02-10T09:01:00.000000+00:00",
            },
            "calibration_projection_rows": {
                STOCK_CODE: dict(receipt.payload["projections"][0]),
            },
            "temporal_contract": "recommendation-producer-clock.v1",
            "decision_clock_timezone": "UTC",
            "market_calendar_timezone": "Asia/Taipei",
            "temporal_mode": temporal_mode,
            "cutoff_selection": cutoff_selection,
            "cutoff_policy": cutoff_policy,
            "prediction_decision_anchor": "actual_producer_decision_at",
            "horizon_anchor": "immutable_projection_receipt",
            **strategy_identity,
            **universe_identity,
            "cost_model_id": "cost_generation_cli",
            "benchmark_id": "TAIEX",
            "industry_benchmark_id": "industry_index",
            "horizon_days": 20,
            "evidence_tier": "forward",
            "return_basis": RETURN_BASIS,
        }
        self._personalization_execution_clocks = {
            "run_started_at": self.last_run_context["run_started_at"],
            "available_at": self.last_run_context["available_at"],
            "captured_at": self.last_run_context["captured_at"],
            "personalization_scope_declared_at": self.last_run_context[
                "personalization_scope_declared_at"
            ],
        }
        self.last_screening_matrix = [
            {
                "stock_code": STOCK_CODE,
                "status": "pass",
                "quality": "observed",
                "stage": "strategy_evaluation",
                "reason_codes": [],
                "warnings": [],
            }
        ]
        return [
            RecommendationDTO(
                stock_code=STOCK_CODE,
                stock_name="台積電",
                close_price=Decimal("100.00"),
                price_change=1.0,
                total_score=80.0,
                indicator_score=80.0,
                pattern_score=80.0,
                volume_score=80.0,
                recommendation_reasons="generation CLI test",
                industry="半導體",
                regime_match=True,
            )
        ]

    def _run_recommendation_body_result(
        self, **kwargs: Any
    ) -> RecommendationBodyResult:
        self._reset_negative_evidence_buffers()
        recommendations = self._produce(**kwargs)
        return self._publish_typed_body_result(
            recommendations,
            result_id=str(kwargs["result_id"]),
            top_n=int(kwargs["top_n"]),
        )

    def _publish_typed_body_result(
        self,
        recommendations: list[RecommendationDTO],
        *,
        result_id: str,
        top_n: int,
    ) -> RecommendationBodyResult:
        from datetime import date

        from app_module.recommendation.body_result import (
            CandidateRowFacts,
            InvocationLegacyContextOwner,
            LegacyRecommendationSnapshot,
            RecommendationBodyContextFacts,
            RecommendationBodyResult,
            strategy_identity_from_payload,
            universe_identity_from_payload,
        )
        from decision_module.recommendation.contracts import (
            CandidateAssessment,
            RecommendationItem,
        )
        from decision_module.recommendation.evaluate import (
            CandidateEvaluationOutcome,
            RecommendationEvaluationPolicy,
            RecommendationEvaluator,
            RecommendationScore,
        )

        invocation_id = f"{result_id}:fake:{type(self).calls}"
        as_of_date = str(self.last_run_context["as_of_date"])
        parsed_as_of_date = date.fromisoformat(as_of_date)
        eligible_universe_size = len(recommendations)
        self.last_run_context.update(
            {
                "data_fingerprint": "generation-cli-test-data-fingerprint",
                "market_data_fingerprint": "generation-cli-test-market-fingerprint",
                "source_id": "generation-cli-test-provider",
                "eligible_universe_size": eligible_universe_size,
                "warnings": [],
            }
        )
        context_owner = InvocationLegacyContextOwner(invocation_id)
        context_owner.mutable_context.update(self.last_run_context)
        strategy_version_id = self.last_run_context.get("strategy_version_id")
        body_context = RecommendationBodyContextFacts.capture(
            result_id=result_id,
            invocation_id=invocation_id,
            as_of_date=as_of_date,
            data_fingerprint=str(self.last_run_context["data_fingerprint"]),
            market_data_fingerprint=str(
                self.last_run_context["market_data_fingerprint"]
            ),
            source_id=str(self.last_run_context["source_id"]),
            temporal_mode=str(self.last_run_context["temporal_mode"]),
            decision_at=str(self.last_run_context["decision_at"]),
            eligible_universe_size=eligible_universe_size,
            warnings=(),
            legacy_context=context_owner.freeze_current_context(),
            strategy_identity=strategy_identity_from_payload(
                self.last_run_context,
                strategy_version_id=strategy_version_id if strategy_version_id else None,
            ),
            universe_identity=universe_identity_from_payload(self.last_run_context),
            evidence_identity=RecommendationRunEvidenceIdentity(
                cost_model_id=str(self.last_run_context["cost_model_id"]),
                benchmark_id=str(self.last_run_context["benchmark_id"]),
                industry_benchmark_id=str(
                    self.last_run_context["industry_benchmark_id"]
                ),
                horizon_days=self.last_run_context["horizon_days"],
                evidence_tier=str(self.last_run_context["evidence_tier"]),
                return_basis=str(self.last_run_context["return_basis"]),
            ),
            cutoff_selection=str(self.last_run_context["cutoff_selection"]),
            cutoff_policy=str(self.last_run_context["cutoff_policy"]),
        )
        outcomes: list[CandidateEvaluationOutcome] = []
        candidate_facts: list[CandidateRowFacts] = []
        for recommendation in recommendations:
            score = Decimal(str(recommendation.total_score))
            item = RecommendationItem(
                stock_code=recommendation.stock_code,
                stock_name=recommendation.stock_name,
                rule_score=score,
                close_price=Decimal(str(recommendation.close_price)),
                price_change=Decimal(str(recommendation.price_change)),
                indicator_score=Decimal(str(recommendation.indicator_score)),
                pattern_score=Decimal(str(recommendation.pattern_score)),
                volume_score=Decimal(str(recommendation.volume_score)),
                industry=recommendation.industry,
                reason_text=recommendation.recommendation_reasons,
                regime_match=recommendation.regime_match,
            )
            assessment = CandidateAssessment(
                stock_code=recommendation.stock_code,
                eligible=True,
            )
            outcomes.append(
                CandidateEvaluationOutcome(
                    invocation_id=invocation_id,
                    stock_code=recommendation.stock_code,
                    status="pass",
                    quality="observed",
                    stage="candidate_scored",
                    reason_codes=(),
                    item=item,
                    assessment=assessment,
                    score=RecommendationScore(ordering_value=score),
                )
            )
            candidate_facts.append(
                CandidateRowFacts(
                    stock_code=recommendation.stock_code,
                    stock_name=recommendation.stock_name,
                    industry=recommendation.industry,
                    total_score_text=str(recommendation.total_score),
                    threshold_mode="fixed",
                    invocation_id=invocation_id,
                )
            )
        policy = RecommendationEvaluationPolicy(
            invocation_id=invocation_id,
            decision_date=parsed_as_of_date,
            decision_date_text=as_of_date,
            top_n=top_n,
            eligible_universe_date=parsed_as_of_date,
        )
        evaluation = RecommendationEvaluator().evaluate_batch_result(
            tuple(outcomes),
            policy,
        )
        ranked_recommendations = [
            replace(
                recommendation,
                score_percentile_bp=item.score_percentile_bp,
                eligible_universe_size=item.eligible_universe_size,
                eligible_universe_date=(
                    item.eligible_universe_date.isoformat()
                    if item.eligible_universe_date is not None
                    else None
                ),
                ranking_method=item.ranking_method,
                threshold_mode=item.threshold_mode or "fixed",
            )
            for recommendation, item in zip(
                recommendations,
                evaluation.decision.items,
                strict=True,
            )
        ]
        recommendations[:] = ranked_recommendations
        body_result = RecommendationBodyResult(
            result_id=result_id,
            invocation_id=invocation_id,
            decision=evaluation.decision,
            dispositions=evaluation.dispositions,
            candidate_facts=tuple(candidate_facts),
            context=body_context,
            legacy_recommendations=tuple(
                LegacyRecommendationSnapshot.capture(
                    recommendation,
                    invocation_id=invocation_id,
                    result_id=result_id,
                )
                for recommendation in recommendations
            ),
        )
        # Keep this legacy sidecar coherent with the fake's canonical result.
        # The previous hard-coded stage/reason row did not describe the output
        # produced by the test evaluator and correctly failed the R019 parity gate.
        self.last_screening_matrix = [
            {
                "stock_code": disposition.stock_code,
                "status": disposition.status,
                "quality": disposition.quality,
                "stage": disposition.stage,
                "reason_codes": list(disposition.reason_codes),
                "warnings": list(disposition.warnings),
            }
            for disposition in body_result.dispositions
        ]
        return body_result

    def execute_recommendation(self, runtime_config: dict[str, Any], **kwargs: Any) -> Any:
        from app_module.recommendation.execute import execute_recommendation

        return execute_recommendation(self, runtime_config, **kwargs)

    def run_recommendation(self, config: dict[str, Any], **kwargs: Any) -> list[RecommendationDTO]:
        """Legacy test helper for the isolated clock-contract unit test."""

        return self._produce(config, **kwargs)


def _args(output_root: Path, data_root: Path, config_path: Path) -> list[str]:
    return [
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
        "--config-json",
        str(config_path),
        "--result-id",
        RESULT_ID,
        "--result-name",
        "generation CLI test",
        "--as-of-date",
        "2025-02-10",
        "--scope-id",
        SCOPE_ID,
        "--scope-type",
        "local",
        "--delivery-id",
        "delivery_generation_cli_001",
        "--request-id",
        "request_generation_cli_001",
        "--profile",
        "test",
    ]


def test_generation_cli_explicit_scope_save_ack_and_retry_use_custom_journal(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    monkeypatch.setattr(module, "RecommendationService", _FakeRecommendationProducer)
    _FakeRecommendationProducer.calls = 0
    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")
    custom_journal = tmp_path / "custom" / "journal.jsonl"
    args = _args(output_root, data_root, config_path)
    args.extend(["--journal-path", str(custom_journal), "--evidence-db", str(tmp_path / "evidence.sqlite")])

    first_code = module.main(args)
    first_payload = json.loads(capsys.readouterr().out)
    assert first_code == 0, first_payload
    assert first_payload["ok"] is True
    assert first_payload["delivery_status"] == "delivered"
    assert first_payload["readback"][0]["delivery_status"] == "delivered"
    assert custom_journal.is_file()
    assert not (output_root / "portfolio").exists()
    from scripts.run_personalization_recommendation import _OutputPathConfig
    from app_module.recommendation.composition import build_recommendation_composition

    composition = build_recommendation_composition(
        _OutputPathConfig(output_root / "_test")
    )
    result_bytes = composition.store.read_artifact(RESULT_ID)
    assert result_bytes is not None
    saved = composition.queries.get(RESULT_ID)
    assert saved is not None and saved.execution is not None
    assert saved.execution.events[-1].event_type == "personalization_delivery_capture"
    from app_module.personalization_read_service import PersonalizationReadService
    from app_module.personalization_save_adapter import PersonalizationRecommendationSaveAdapter

    adapter = PersonalizationRecommendationSaveAdapter()
    captures = adapter.captures_from_execution(saved.execution)
    assert len(captures) == 1
    generated_capture_hash = first_payload["generated_capture_hashes"][0]
    assert first_payload["capture_hashes"] == [generated_capture_hash]
    assert first_payload["persisted_capture_hashes"][0] != generated_capture_hash
    assert first_payload["delivered_capture_hashes"][0] != generated_capture_hash
    assert captures[0].capture_hash == generated_capture_hash
    assert saved.persisted_at is not None
    persisted_capture = adapter.capture_service.mark_persisted(
        captures[0],
        persisted_at=saved.persisted_at.isoformat(timespec="microseconds"),
    )
    delivered_capture = adapter.capture_service.mark_delivered(
        persisted_capture,
        delivered_at=first_payload["delivered_at"],
    )
    assert persisted_capture.capture_hash == first_payload["persisted_capture_hashes"][0]
    assert delivered_capture.capture_hash == first_payload["delivered_capture_hashes"][0]

    readback_service = PersonalizationReadService.from_paths(
        output_root=output_root / "_test",
        journal_path=custom_journal,
        evidence_db_path=tmp_path / "evidence.sqlite",
    )
    readback_report = readback_service.inspect_scope(
        scope_id=SCOPE_ID,
        evaluated_as_of="2025-02-10",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
    )
    typed_projection = readback_service.projection_for_last_read(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
    )
    assert readback_report.source_consistency_status == "verified"
    assert typed_projection is not None
    assert typed_projection.status == "linked_prediction"
    assert typed_projection.delivery_status == "delivered"
    receipt_payload = _receipt().payload
    receipt_row = receipt_payload["projections"][0]
    for field_name, expected in {
        "prediction_id": PREDICTION_ID,
        "projection_receipt_hash": captures[0].projection_receipt_hash,
        "projection_receipt_result_id": RESULT_ID,
        "model_id": receipt_row["model_version"],
        "dataset_id": receipt_row["dataset_version"],
        "dataset_hash": receipt_row["dataset_hash"],
        "cost_scenario_hash": receipt_row["cost_scenario_hash"],
        "horizon_days": 20,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
        "universe_policy_hash": UNIVERSE_HASH,
    }.items():
        assert typed_projection.prediction[field_name] == expected
    assert typed_projection.prediction["training_provenance"] == receipt_payload[
        "training_provenance"
    ]

    from dataclasses import replace

    damaged_binding = replace(
        saved.execution.ml_receipt_refs[0],
        model_candidate_id="wrong-candidate",
    )
    damaged_execution = replace(
        saved.execution,
        ml_receipt_refs=(damaged_binding,),
    )
    damaged_read_model = replace(saved, execution=damaged_execution)
    damaged_projection = readback_service.projection_service.build_for_execution(
        read_model=damaged_read_model,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        evaluated_as_of="2025-02-10",
    )
    assert damaged_projection.status == "unavailable"
    assert "execution candidate identity does not match immutable receipt" in (
        damaged_projection.warnings
    )
    assert not (output_root / "recommendation" / "runs" / f"{RESULT_ID}.json").exists()
    journal_bytes = custom_journal.read_bytes()

    retry_code = module.main(args)
    retry_payload = json.loads(capsys.readouterr().out)
    assert retry_code == 0
    assert retry_payload["ok"] is True
    assert retry_payload["delivery_status"] == "already_delivered"
    assert len(
        JournalService(
            cast(Any, SimpleNamespace(output_root=output_root)),
            journal_path=custom_journal,
        ).list_decision_revisions()
    ) == 1
    assert _FakeRecommendationProducer.calls == 1
    assert composition.store.read_artifact(RESULT_ID) == result_bytes
    assert custom_journal.read_bytes() == journal_bytes

    # Simulate an artifact whose index projection was lost after the original
    # create-only publish. Exact query remains fail-closed; the CLI recovery
    # reads the safe opaque-ID artifact, validates its envelope, and reuses the
    # existing same-ID/hash writer without rerunning the producer or appending
    # a duplicate ACK.
    connection = sqlite3.connect(composition.store.database_path)
    try:
        connection.execute(
            "DELETE FROM result_artifact_index WHERE result_id = ?",
            (RESULT_ID,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ExecutionArtifactIntegrityError):
        composition.queries.get(RESULT_ID)

    recovery_code = module.main(args)
    recovery_payload = json.loads(capsys.readouterr().out)
    assert recovery_code == 0, recovery_payload
    assert recovery_payload["write_status"] == "orphan_recovered_and_delivered_or_idempotent"
    assert recovery_payload["write_attempted"] is True
    assert recovery_payload["immutable_result_reused"] is True
    assert recovery_payload["delivery_status"] == "already_delivered"
    assert recovery_payload["payload_hash"] == saved.payload_hash
    assert _FakeRecommendationProducer.calls == 1
    assert composition.store.read_artifact(RESULT_ID) == result_bytes
    assert composition.queries.get(RESULT_ID) == saved
    assert custom_journal.read_bytes() == journal_bytes

    changed_args = [*args, "--top-n", "49"]
    changed_code = module.main(changed_args)
    changed_payload = json.loads(capsys.readouterr().out)
    assert changed_code == 2
    assert changed_payload["ok"] is False
    assert any("canonical_personal_request_limits_conflict" in item for item in changed_payload["diagnostics"])
    assert changed_payload["write_attempted"] is False
    assert _FakeRecommendationProducer.calls == 1
    assert composition.store.read_artifact(RESULT_ID) == result_bytes
    assert custom_journal.read_bytes() == journal_bytes


def _seed_legacy_personal_json_result(
    *,
    module: Any,
    output_root: Path,
    config_payload: dict[str, Any],
    historical_research: bool,
    temporal_overrides: dict[str, Any] | None = None,
) -> tuple[Path, tuple[Any, ...]]:
    from app_module.personalization_save_adapter import (
        PersonalizationRecommendationSaveAdapter,
    )
    from app_module.recommendation_repository import RecommendationRepository

    effective_output_root = module._profiled_root(output_root, "test")
    producer = _FakeRecommendationProducer(
        module._OutputPathConfig(effective_output_root)
    )
    recommendations = producer.run_recommendation(
        config_payload,
        max_stocks=200,
        top_n=50,
        as_of_date="2025-02-10" if historical_research else None,
        universe=None,
        result_id=RESULT_ID,
        historical_research=historical_research,
        select_latest_available_cutoff=not historical_research,
    )
    result = RecommendationResultDTO(
        result_id=RESULT_ID,
        result_name="generation CLI test",
        config=config_payload,
        recommendations=recommendations,
        created_at="2025-02-10T09:00:00+00:00",
        run_context=producer.last_run_context,
    )
    result, captures = PersonalizationRecommendationSaveAdapter().bind_result(
        result,
        personalization_scope=_scope(),
        request_id="request_generation_cli_001",
    )
    assert len(captures) == 1
    if temporal_overrides:
        result.run_context = {**result.run_context, **temporal_overrides}
    repository = RecommendationRepository(
        module._OutputPathConfig(effective_output_root)
    )
    assert repository.save_result_create_only(result) == RESULT_ID
    return repository.runs_dir / f"{RESULT_ID}.json", captures


def test_legacy_personal_json_retry_is_read_only_and_skips_producer(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    config_path = tmp_path / "strategy.json"
    config_payload = {"filters": {}}
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    args = _args(output_root, data_root, config_path)
    custom_journal = tmp_path / "custom" / "journal.jsonl"
    args.extend(
        ["--journal-path", str(custom_journal), "--evidence-db", str(tmp_path / "evidence.sqlite")]
    )

    # Seed a natural-mode legacy result. The JSON bytes remain the retry source.
    _FakeRecommendationProducer.calls = 0
    result_path, captures = _seed_legacy_personal_json_result(
        module=module,
        output_root=output_root,
        config_payload=config_payload,
        historical_research=False,
    )
    result_bytes = result_path.read_bytes()
    monkeypatch.setattr(
        module,
        "RecommendationService",
        lambda *_args, **_kwargs: pytest.fail("legacy exact retry invoked producer"),
    )
    code = module.main(args)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert payload["write_status"] == "existing_capture_reused_and_delivered_or_idempotent"
    assert payload["producer_status"] == "existing_capture_reused"
    assert payload["immutable_result_reused"] is True
    assert payload["delivery_status"] == "delivered"
    assert payload["capture_hashes"] == [captures[0].capture_hash]
    assert _FakeRecommendationProducer.calls == 1
    assert result_path.read_bytes() == result_bytes
    assert custom_journal.is_file()


def test_legacy_historical_retry_requires_matching_temporal_identity(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    config_path = tmp_path / "strategy.json"
    config_payload = {"filters": {}}
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    natural_args = _args(output_root, data_root, config_path)
    custom_journal = tmp_path / "custom" / "journal.jsonl"
    natural_args.extend(
        ["--journal-path", str(custom_journal), "--evidence-db", str(tmp_path / "evidence.sqlite")]
    )

    _FakeRecommendationProducer.calls = 0
    result_path, captures = _seed_legacy_personal_json_result(
        module=module,
        output_root=output_root,
        config_payload=config_payload,
        historical_research=True,
    )
    result_bytes = result_path.read_bytes()
    assert _FakeRecommendationProducer.calls == 1
    monkeypatch.setattr(
        module,
        "RecommendationService",
        lambda *_args, **_kwargs: pytest.fail("legacy historical retry invoked producer"),
    )
    real_writer = module._writer

    def writer_must_not_run(*_args: Any, **_kwargs: Any) -> JournalService:
        pytest.fail("temporal mismatch reached Journal writer")

    monkeypatch.setattr(module, "_writer", writer_must_not_run)
    mismatch_code = module.main(natural_args)
    mismatch_payload = json.loads(capsys.readouterr().out)
    assert mismatch_code == 2
    assert mismatch_payload["ok"] is False
    assert mismatch_payload["write_attempted"] is False
    assert any(
        "existing_result_temporal_contract_conflict:temporal_mode" in item
        for item in mismatch_payload["diagnostics"]
    )
    assert _FakeRecommendationProducer.calls == 1
    assert result_path.read_bytes() == result_bytes
    assert not custom_journal.exists()

    historical_args = [*natural_args, "--historical-research"]
    monkeypatch.setattr(module, "_writer", real_writer)
    success_code = module.main(historical_args)
    success_payload = json.loads(capsys.readouterr().out)
    assert success_code == 0, success_payload
    assert success_payload["temporal_mode"] == "historical_research_not_as_if_available"
    assert success_payload["delivery_status"] == "delivered"
    assert success_payload["readback"][0]["temporal_tier"] == "historical_research_only"
    assert success_payload["capture_hashes"] == [captures[0].capture_hash]
    assert _FakeRecommendationProducer.calls == 1
    assert result_path.read_bytes() == result_bytes
    journal = real_writer(output_root / "_test", custom_journal)
    assert len(
        journal.list_personalization_delivery_acks(
            RESULT_ID,
            STOCK_CODE,
            "delivery_generation_cli_001",
        )
    ) == 1


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("temporal_mode", None),
        ("cutoff_selection", "unknown_cutoff_selection"),
        ("cutoff_policy", "source_latest_available_exact"),
    ],
)
def test_legacy_personal_retry_rejects_incomplete_temporal_identity_before_writer(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
    field_name: str,
    bad_value: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    output_root = tmp_path / "output"
    config_payload = {"filters": {}}
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    args = _args(output_root, tmp_path / "data", config_path)
    args.extend(
        ["--journal-path", str(tmp_path / "custom" / "journal.jsonl"), "--evidence-db", str(tmp_path / "evidence.sqlite"), "--historical-research"]
    )
    _FakeRecommendationProducer.calls = 0
    result_path, _captures = _seed_legacy_personal_json_result(
        module=module,
        output_root=output_root,
        config_payload=config_payload,
        historical_research=True,
        temporal_overrides={field_name: bad_value},
    )
    result_bytes = result_path.read_bytes()
    monkeypatch.setattr(
        module,
        "RecommendationService",
        lambda *_args, **_kwargs: pytest.fail("malformed legacy retry invoked producer"),
    )
    monkeypatch.setattr(
        module,
        "_writer",
        lambda *_args, **_kwargs: pytest.fail("invalid temporal identity reached Journal writer"),
    )

    code = module.main(args)
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["write_attempted"] is False
    assert any(
        f"existing_result_temporal_contract_conflict:{field_name}" in item
        for item in payload["diagnostics"]
    )
    assert _FakeRecommendationProducer.calls == 1
    assert result_path.read_bytes() == result_bytes
    assert not (tmp_path / "custom" / "journal.jsonl").exists()


def test_generation_cli_ack_stream_cas_conflict_retries_without_reexecution(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    monkeypatch.setattr(module, "RecommendationService", _FakeRecommendationProducer)
    _FakeRecommendationProducer.calls = 0
    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")
    custom_journal = tmp_path / "custom" / "journal.jsonl"
    args = _args(output_root, data_root, config_path)
    args.extend(
        ["--journal-path", str(custom_journal), "--evidence-db", str(tmp_path / "evidence.sqlite")]
    )

    real_writer = module._writer

    def stale_history_writer(journal_root: Path, journal_file: Path) -> JournalService:
        journal = real_writer(journal_root, journal_file)

        def reject_stale_history(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("journal_delivery_ack_stream_conflict")

        journal.record_personalization_delivery_acks = reject_stale_history  # type: ignore[method-assign]
        return journal

    monkeypatch.setattr(module, "_writer", stale_history_writer)
    first_code = module.main(args)
    first_payload = json.loads(capsys.readouterr().out)
    assert first_code == 2
    assert first_payload["ok"] is False
    assert first_payload["write_attempted"] is True
    assert any("delivery ACK append failed:RuntimeError" in item for item in first_payload["diagnostics"]), first_payload
    assert _FakeRecommendationProducer.calls == 1

    from scripts.run_personalization_recommendation import _OutputPathConfig
    from app_module.recommendation.composition import build_recommendation_composition

    composition = build_recommendation_composition(
        _OutputPathConfig(output_root / "_test")
    )
    artifact_bytes = composition.store.read_artifact(RESULT_ID)
    saved = composition.queries.get(RESULT_ID)
    assert artifact_bytes is not None
    assert saved is not None and saved.execution is not None
    assert custom_journal.exists() is False

    monkeypatch.setattr(module, "_writer", real_writer)
    retry_code = module.main(args)
    retry_payload = json.loads(capsys.readouterr().out)
    assert retry_code == 0, retry_payload
    assert retry_payload["delivery_status"] == "delivered"
    assert retry_payload["write_status"] == "existing_capture_reused_and_delivered_or_idempotent"
    assert _FakeRecommendationProducer.calls == 1
    assert composition.store.read_artifact(RESULT_ID) == artifact_bytes
    journal = real_writer(output_root / "_test", custom_journal)
    ack_rows = journal.list_personalization_delivery_acks(
        RESULT_ID,
        STOCK_CODE,
        "delivery_generation_cli_001",
    )
    assert len(ack_rows) == 1


def test_temporal_contract_accepts_t_minus_one_cutoff_on_next_taipei_market_day(
    tmp_path: Path,
) -> None:
    import scripts.run_personalization_recommendation as module

    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")
    producer = _FakeRecommendationProducer(SimpleNamespace(output_root=output_root))
    producer.run_recommendation(
        {"filters": {}},
        max_stocks=200,
        top_n=50,
        as_of_date=None,
        universe=None,
        result_id=RESULT_ID,
        historical_research=False,
        select_latest_available_cutoff=True,
    )
    context = dict(producer.last_run_context)
    next_market_day_clocks = {
        "run_started_at": "2025-02-10T16:40:00.000000+00:00",
        "personalization_scope_declared_at": "2025-02-10T16:40:00.000000+00:00",
        "available_at": "2025-02-10T16:45:00.000000+00:00",
        "captured_at": "2025-02-10T16:45:00.000000+00:00",
        "decision_at": "2025-02-10T16:50:00.000000+00:00",
        "calibration_projection_receipt_created_at": "2025-02-10T16:51:00.000000+00:00",
    }
    context.update(next_market_day_clocks)
    receipt_metadata = dict(context["calibration_projection_receipt"])
    receipt_metadata["receipt_created_at"] = next_market_day_clocks[
        "calibration_projection_receipt_created_at"
    ]
    context["calibration_projection_receipt"] = receipt_metadata
    args = module._parser().parse_args(
        _args(output_root, data_root, config_path)
    )

    diagnostics, temporal = module._validate_producer_temporal_contract(
        args,
        producer_context=context,
        as_of_date="2025-02-10",
    )

    assert diagnostics == []
    assert temporal["temporal_mode"] == "natural_producer_clock"
    assert temporal["decision_market_date"] == "2025-02-11"
    assert temporal["available_market_date"] == "2025-02-11"


def test_generation_cli_separates_natural_latest_cutoff_from_historical_research(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    monkeypatch.setattr(module, "RecommendationService", _FakeRecommendationProducer)
    _FakeRecommendationProducer.calls = 0
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")

    natural_output = tmp_path / "natural-output"
    natural_journal = tmp_path / "natural-journal.jsonl"
    natural_args = _args(natural_output, tmp_path / "natural-data", config_path)
    natural_args[natural_args.index("--as-of-date") + 1] = "2025-02-09"
    natural_args.extend(
        [
            "--journal-path",
            str(natural_journal),
            "--evidence-db",
            str(tmp_path / "natural-evidence.sqlite"),
        ]
    )

    natural_code = module.main(natural_args)
    natural_payload = json.loads(capsys.readouterr().out)
    assert natural_code == 2
    assert natural_payload["ok"] is False
    assert any(
        any(item in diagnostic for diagnostic in natural_payload["diagnostics"])
        for item in (
            "producer_as_of_date_mismatch",
            "producer_durable_receipt_unverified:RecommendationProvenanceError",
        )
    )
    assert natural_payload["write_attempted"] is False
    assert not (
        natural_output / "_test" / "recommendation" / "runs" / "execution_artifacts"
    ).exists()
    assert not natural_journal.exists()

    historical_output = tmp_path / "historical-output"
    historical_journal = tmp_path / "historical-journal.jsonl"
    historical_args = _args(historical_output, tmp_path / "historical-data", config_path)
    historical_args.extend(
        [
            "--historical-research",
            "--journal-path",
            str(historical_journal),
            "--evidence-db",
            str(tmp_path / "historical-evidence.sqlite"),
        ]
    )

    historical_code = module.main(historical_args)
    historical_payload = json.loads(capsys.readouterr().out)
    assert historical_code == 0, historical_payload
    assert historical_payload["temporal_mode"] == (
        "historical_research_not_as_if_available"
    )
    assert historical_payload["cutoff_selection"] == "explicit_historical_cutoff"
    assert historical_payload["cutoff_policy"] == "explicit_historical_research"
    assert _FakeRecommendationProducer.calls == 2
