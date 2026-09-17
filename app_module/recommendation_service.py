"""
推薦服務 (Recommendation Service)
提供股票推薦的業務邏輯，供 UI 層調用
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Mapping, Optional, cast
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from copy import deepcopy
from contextlib import closing
import hashlib
import json
import sqlite3
from uuid import uuid4

# 確保 pd.isna 可用（pandas 兼容性）
if not hasattr(pd, 'isna'):
    pd.isna = pd.isnull

# 方案 A：不搬檔案，service 層內部 import ui_app 模組
# from ui_app.strategy_configurator import StrategyConfigurator
# from ui_app.reason_engine import ReasonEngine
# from ui_app.industry_mapper import IndustryMapper
# from ui_app.market_regime_detector import MarketRegimeDetector
from decision_module.strategy_configurator import StrategyConfigurator
from decision_module.reason_engine import ReasonEngine
from decision_module.industry_mapper import IndustryMapper
from decision_module.market_regime_detector import MarketRegimeDetector
from app_module.dtos import RecommendationDTO
from app_module.strategy_spec import StrategySpec
from app_module.preset_service import PresetService
from app_module.strategy_version_service import StrategyVersionService
from decision_module.derived_market_features import (
    enrich_latest_market_features,
    latest_feature_decimal,
)
from financial_module.units import to_decimal
from app_module.recommendation_run_support import (
    build_negative_evidence_buffers,
    configured_volume_change_min_percent,
    format_decimal_for_payload,
    matrix_row,
    validate_ranking_config,
)
from app_module.recommendation_market_data_provider import (
    DefaultRecommendationMarketDataProvider,
)
from app_module.recommendation_market_frame import normalize_market_frame
from app_module.recommendation_portfolio_dates import parse_stock_dates
from app_module.recommendation_ranking_pipeline import build_ranking_plan
from app_module.application_ports import MarketFrameProvider
from data_module.fundamental_sqlite_provider import FundamentalSQLiteProvider
from app_module.v4_evidence_identity import (
    build_recommendation_universe_identity,
    build_strategy_config_identity,
)
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
    RecommendationCalibrationProjection,
    build_default_recommendation_calibration_consumer,
)
from data_module.pit_sector_membership_reader import (
    PITMembershipReadResult,
    PITSectorMembershipReader,
)
from ml_module.recommendation_probability_transform import (
    NULL_BENCHMARK_BASELINE_ID,
    PROBABILITY_TRANSFORM_ID,
)
from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    build_inference_projection_receipt,
    build_inference_provenance,
    persist_inference_projection_receipt,
    read_inference_projection_receipt,
)


def _industry_names_match(actual: str, requested: str) -> bool:
    """沿用互動篩選的名稱容錯，但輸入必須來自 PIT taxonomy。"""

    actual_text = str(actual or "").strip()
    requested_text = str(requested or "").strip()
    if not actual_text or not requested_text:
        return False

    def normalize(value: str) -> str:
        normalized = value.casefold().strip()
        for suffix in ("類報酬指數", "類指數", "業", "類"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    left = normalize(actual_text)
    right = normalize(requested_text)
    return bool(left and right and (left == right or left in right or right in left))


class RecommendationService:
    """推薦服務類"""

    def __init__(
        self,
        config,
        industry_mapper: Optional[IndustryMapper] = None,
        market_data_provider: Optional[MarketFrameProvider] = None,
        regime_detector: Optional[MarketRegimeDetector] = None,
        calibration_consumer: RecommendationCalibrationConsumer | None = None,
        pit_membership_reader: PITSectorMembershipReader | None = None,
    ):
        """初始化推薦服務

        Args:
            config: TWStockConfig 實例
            industry_mapper: IndustryMapper 實例（可選，如果為 None 則自動創建）
        """
        self.config = config
        self.strategy_configurator = StrategyConfigurator()
        self.reason_engine = ReasonEngine()
        if industry_mapper is None:
            self.industry_mapper = IndustryMapper(config)
        else:
            self.industry_mapper = industry_mapper
        self.market_data_provider = (
            market_data_provider
            if market_data_provider is not None
            else DefaultRecommendationMarketDataProvider(config)
        )
        self.regime_detector = regime_detector or MarketRegimeDetector(config)
        self.calibration_consumer = (
            calibration_consumer
            if calibration_consumer is not None
            else build_default_recommendation_calibration_consumer(config)
        )
        self.pit_membership_reader = pit_membership_reader
        self.last_calibration_projections: Dict[str, Any] = {}
        self.last_screening_matrix: List[Dict[str, Any]] = []
        self.last_excluded_candidates_json: List[Dict[str, Any]] = []
        self.last_why_not_payload_json: List[Dict[str, Any]] = []
        self.last_liquidity_gate_payload_json: List[Dict[str, Any]] = []
        self.last_exclusion_quality: str = "observed"
        self.last_exclusion_warnings_json: List[str] = []
        self.last_run_context: Dict[str, Any] = {}
        self._personalization_execution_clocks: Dict[str, str] = {}
        self._fundamental_sqlite_provider: FundamentalSQLiteProvider | None = None
        self._fundamental_provider_initialization_attempted = False

    def _reset_negative_evidence_buffers(self) -> None:
        self.last_screening_matrix = []
        self.last_excluded_candidates_json = []
        self.last_why_not_payload_json = []
        self.last_liquidity_gate_payload_json = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json = []
        self.last_run_context = {}
        self.last_calibration_projections = {}

    def _apply_recommendation_calibration(
        self,
        recommendations: List[RecommendationDTO],
        *,
        decision_date: str,
        selection_authority: str = "rule_top_n",
        selection_score_kind: str = "rule_total_score",
        selection_percentile_kind: str = "rule_percentile",
        top_n_changed_by_model: bool = False,
    ) -> None:
        """Inject the verified active pointer projection into the normal DTO path.

        This is deliberately a read-only adapter.  If the pointer, artifact,
        canonical feature vector, or data quality is unavailable, each row
        remains rule-only and the existing recommendation score is untouched.
        """

        consumer = self.calibration_consumer
        if consumer is None:
            return
        if not decision_date or not recommendations:
            return
        try:
            from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
            from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
            from ml_module.historical_feature_builder import HistoricalFeatureBuilder

            db_file = getattr(self.config, "db_file", None)
            if db_file is None:
                raise FileNotFoundError("recommendation calibration source database is not configured")
            provider = MLHistoricalSnapshotProvider(db_file)
            snapshot = provider.load(
                decision_date=decision_date,
                history_start_date=str(getattr(self.config, "default_start_date", "2014-01-01"))[:10],
                symbols=tuple(sorted({str(item.stock_code) for item in recommendations})),
                industry_index_names=(),
            )
            feature_builder = HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY)
            rows = feature_builder.compute(
                snapshot,
                industry_index_name_by_symbol={},
            )
            feature_values = {
                row.symbol: tuple(value for _, value in row.values)
                for row in rows
            }
            provenance_rows = [
                {
                    "symbol": row.symbol,
                    "decision_date": getattr(row, "decision_date", snapshot.decision_date),
                    "feature_as_of_date": getattr(
                        row, "feature_as_of_date", snapshot.feature_as_of_date
                    ),
                    "feature_available_date": getattr(
                        row, "feature_available_date", snapshot.decision_date
                    ),
                    "values": row.values,
                    "snapshot_hash": getattr(row, "snapshot_hash", ""),
                }
                for row in rows
            ]
            active_identity_provider = getattr(consumer, "active_identity", None)
            active_identity = (
                active_identity_provider(decision_date=decision_date)
                if callable(active_identity_provider)
                else None
            )
            active_identity = active_identity if isinstance(active_identity, Mapping) else {}
            active_cost_provider = getattr(consumer, "active_cost_scenario", None)
            active_cost_scenario = (
                active_cost_provider(decision_date=decision_date)
                if callable(active_cost_provider)
                else None
            )
            active_cost_hash = active_identity.get("cost_scenario_hash")
            active_cost_id = active_identity.get("cost_scenario_id")
            active_cost_version = active_identity.get("cost_scenario_version")
            if active_cost_scenario is not None:
                active_cost_hash = getattr(active_cost_scenario, "scenario_hash", None)
                active_cost_id = getattr(active_cost_scenario, "scenario_id", None)
                active_cost_version = getattr(active_cost_scenario, "scenario_version", None)
            inference_feature_schema = getattr(
                consumer,
                "feature_schema",
                CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
            )
            inference_feature_registry_hash = str(
                getattr(
                    consumer,
                    "feature_registry_hash",
                    CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
                )
            )
            inference_provenance = build_inference_provenance(
                snapshot=snapshot,
                feature_rows=provenance_rows,
                feature_schema=inference_feature_schema,
                feature_registry_hash=inference_feature_registry_hash,
                feature_builder_schema_hash=feature_builder.load_contract.schema_hash,
                source_database=str(provider.database_path),
                history_start_date=str(
                    getattr(self.config, "default_start_date", "2014-01-01")
                )[:10],
                cost_scenario_hash=(
                    str(active_cost_hash)
                    if active_cost_hash
                    else None
                ),
                cost_scenario_id=(
                    str(active_cost_id)
                    if active_cost_id
                    else None
                ),
                cost_scenario_version=(
                    str(active_cost_version)
                    if active_cost_version
                    else None
                ),
                probability_transform_id=PROBABILITY_TRANSFORM_ID,
                source_contract_binding=getattr(
                    self.config, "recommendation_source_contract_binding", None
                ),
            )
        except Exception as exc:  # noqa: BLE001 - consumer must fail closed
            self.last_run_context["calibration_projection_status"] = "unavailable"
            self.last_run_context.setdefault("warnings", []).append(
                f"calibration_feature_source_unavailable:{type(exc).__name__}"
            )
            for recommendation in recommendations:
                recommendation.calibration_status = "unavailable"
                recommendation.calibration_source = "recommendation_calibration_consumer"
                recommendation.calibration_warnings = ["feature_vector_source_unavailable_fail_closed"]
            return

        rule_probability = {str(item.stock_code): 5_000 for item in recommendations}
        # After-cost is a distinct target.  Only pass its frozen 5,000 bp null
        # benchmark when the active candidate declares that exact contract;
        # declared-but-unpriced baselines remain unavailable.
        after_cost_baseline = None
        baseline_provider = getattr(consumer, "active_after_cost_baseline", None)
        if callable(baseline_provider):
            after_cost_baseline = baseline_provider(decision_date=decision_date)
        after_cost_rule_probability: dict[str, int] = {}
        after_cost_rule_baseline_ids: dict[str, str] = {}
        if after_cost_baseline is not None:
            baseline_id, baseline_probability = after_cost_baseline
            after_cost_rule_probability = {
                str(item.stock_code): baseline_probability for item in recommendations
            }
            after_cost_rule_baseline_ids = {
                str(item.stock_code): baseline_id for item in recommendations
            }
        percentiles = {
            str(item.stock_code): int(item.score_percentile_bp)
            for item in recommendations
            if item.score_percentile_bp is not None
        }
        projections = consumer.project_many(
            feature_values_by_symbol=feature_values,
            rule_probability_by_symbol=rule_probability,
            after_cost_rule_probability_by_symbol=after_cost_rule_probability,
            after_cost_rule_baseline_id_by_symbol=after_cost_rule_baseline_ids,
            ranking_percentile_by_symbol=percentiles,
            decision_date=decision_date,
            data_quality="observed",
            rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
            inference_provenance=inference_provenance,
            selection_authority=selection_authority,
            selection_score_kind=selection_score_kind,
            selection_percentile_kind=selection_percentile_kind,
            top_n_changed_by_model=top_n_changed_by_model,
        )
        self.last_calibration_projections = dict(projections)
        self.last_run_context["calibration_projection_status"] = (
            "active_candidate"
            if any(item.status == "active_candidate" for item in projections.values())
            else "rule_only"
        )
        self.last_run_context["calibration_rule_baseline_id"] = NULL_BENCHMARK_BASELINE_ID
        self.last_run_context["calibration_after_cost_baseline_id"] = (
            after_cost_baseline[0] if after_cost_baseline is not None else ""
        )
        self.last_run_context["calibration_projection_source"] = "RecommendationCalibrationConsumer"
        self.last_run_context["calibration_projection_rows"] = {
            code: projection.to_dict() for code, projection in sorted(projections.items())
        }
        try:
            receipt_path = self._persist_calibration_projection_receipt(
                consumer=consumer,
                active_identity=active_identity,
                decision_date=decision_date,
                projections=projections,
                inference_provenance=inference_provenance,
                result_id=(
                    str(self.last_run_context.get("result_id") or "") or None
                ),
                selection_authority=selection_authority,
                selection_score_kind=selection_score_kind,
                selection_percentile_kind=selection_percentile_kind,
                top_n_changed_by_model=top_n_changed_by_model,
            )
        except (OSError, TypeError, ValueError, RecommendationProvenanceError) as exc:
            receipt_path = None
            self.last_run_context.setdefault("warnings", []).append(
                f"calibration_projection_receipt_unavailable:{type(exc).__name__}"
            )
            self.last_run_context["calibration_projection_receipt_status"] = "unavailable"
            self.last_run_context["calibration_projection_receipt_error"] = type(exc).__name__
            self.last_run_context["calibration_projection_receipt_error_detail"] = str(exc)
        receipt_required = callable(getattr(consumer, "active_identity", None)) and getattr(
            consumer, "pointer_path", None
        ) is not None
        if receipt_required and receipt_path is None:
            # A real active candidate is only allowed to reach the DTO path
            # with a durable, hash-checked receipt.  Keep the rule-selected
            # recommendation list and all rule scores intact, but withdraw
            # every model-derived field when receipt publication fails.
            projections = {
                symbol: RecommendationCalibrationProjection.unavailable(
                    stock_code=symbol,
                    warning="projection_receipt_not_persisted_fail_closed",
                    ranking_percentile_bp=projection.ranking_percentile_bp,
                )
                for symbol, projection in projections.items()
            }
            self.last_calibration_projections = dict(projections)
            self.last_run_context["calibration_projection_status"] = "unavailable"
            self.last_run_context["calibration_projection_receipt_status"] = "unavailable"
        elif receipt_path is not None:
            self.last_run_context["calibration_projection_receipt_status"] = "persisted"
        self.last_run_context["calibration_projection_rows"] = {
            code: projection.to_dict() for code, projection in sorted(projections.items())
        }
        if receipt_path is not None:
            # Persist real execution clocks only when the immutable receipt is
            # actually available for the save/readback path.  This keeps the
            # ordinary rule-only context deterministic while preserving the
            # caller-owned temporal envelope for personal captures.
            self.last_run_context.update(
                getattr(self, "_personalization_execution_clocks", {})
            )
            self.last_run_context["calibration_projection_receipt"] = receipt_path
            receipt_created_at = str(receipt_path.get("receipt_created_at") or "").strip()
            if receipt_created_at:
                self.last_run_context[
                    "calibration_projection_receipt_created_at"
                ] = receipt_created_at
            try:
                from app_module.personalization_save_adapter import (
                    PersonalizationRecommendationSaveAdapter,
                )

                scope = PersonalizationRecommendationSaveAdapter().build_local_scope(
                    context=self.last_run_context,
                    result_id=str(self.last_run_context.get("result_id") or ""),
                    request_id=None,
                    receipt_hash=str(receipt_path.get("receipt_hash") or ""),
                )
                if scope is not None:
                    self.last_run_context["personalization_scope"] = scope.to_dict()
                    self.last_run_context[
                        "personalization_delivery_scope"
                    ] = scope.to_dict()
            except (TypeError, ValueError):
                self.last_run_context.setdefault("warnings", []).append(
                    "personalization_scope_unavailable"
                )
        for recommendation in recommendations:
            projection = projections.get(recommendation.stock_code)
            if projection is None:
                continue
            recommendation.ranking_score_bp = projection.ranking_score_bp
            recommendation.calibrated_probability_bp = projection.calibrated_probability_bp
            recommendation.calibrated_probability_status = projection.calibrated_probability_status
            recommendation.after_cost_profit_probability_bp = projection.after_cost_profit_probability_bp
            recommendation.after_cost_profit_probability_status = projection.after_cost_profit_probability_status
            recommendation.evidence_confidence = projection.evidence_confidence
            recommendation.sample_size = projection.sample_size
            recommendation.cost_basis_bp = projection.cost_basis_bp
            recommendation.calibration_model_version = projection.model_version
            recommendation.calibration_dataset_version = projection.dataset_version
            recommendation.calibration_horizon = projection.horizon
            recommendation.calibration_status = projection.status
            recommendation.calibration_source = "RecommendationCalibrationConsumer"
            recommendation.calibration_source_trace = list(projection.source_trace)
            recommendation.calibration_warnings = list(projection.warnings)
            recommendation.calibration_probability_transform_id = projection.probability_transform_id
            recommendation.calibration_probability_baseline_id = projection.probability_baseline_id
            recommendation.calibration_probability_baseline_kind = projection.probability_baseline_kind
            recommendation.calibration_probability_baseline_probability_bp = (
                projection.probability_baseline_probability_bp
            )
            recommendation.calibration_raw_probability_bp = projection.raw_calibrated_probability_bp
            recommendation.calibration_raw_after_cost_probability_bp = (
                projection.raw_after_cost_profit_probability_bp
            )
            recommendation.calibration_provenance = dict(projection.inference_provenance)
            recommendation.calibration_provenance.update(
                {
                    "training_provenance": dict(projection.training_provenance),
                    "provenance_compatibility": dict(projection.provenance_compatibility),
                    "provenance_status": projection.provenance_status,
                    "projection_contract_hash": projection.projection_contract_hash,
                    "selection_authority": projection.selection_authority,
                    "selection_score_kind": projection.selection_score_kind,
                    "selection_percentile_kind": projection.selection_percentile_kind,
                    "model_ranking_kind": projection.model_ranking_kind,
                }
            )
            if receipt_path is not None:
                recommendation.calibration_provenance["projection_receipt_path"] = receipt_path[
                    "path"
                ]
                recommendation.calibration_provenance["projection_receipt_hash"] = receipt_path[
                    "receipt_hash"
                ]
                if receipt_path.get("result_id"):
                    recommendation.calibration_provenance[
                        "projection_receipt_result_id"
                    ] = receipt_path["result_id"]
            elif receipt_required:
                recommendation.calibration_provenance.update(
                    {
                        "provenance_status": "unavailable",
                        "projection_receipt_status": "not_persisted",
                        "projection_receipt_required": True,
                    }
                )

    @staticmethod
    def _persist_calibration_projection_receipt(
        *,
        consumer: Any,
        active_identity: Mapping[str, Any] | None = None,
        decision_date: str,
        projections: Mapping[str, Any],
        inference_provenance: Mapping[str, Any],
        result_id: str | None,
        selection_authority: str,
        selection_score_kind: str,
        selection_percentile_kind: str,
        top_n_changed_by_model: bool,
    ) -> dict[str, str] | None:
        """Persist the exact bounded projection batch when a real consumer is loaded."""

        identity_provider = getattr(consumer, "active_identity", None)
        pointer_path = getattr(consumer, "pointer_path", None)
        if not callable(identity_provider) or pointer_path is None:
            return None
        identity = (
            active_identity
            if isinstance(active_identity, Mapping)
            else identity_provider(decision_date=decision_date)
        )
        if not isinstance(identity, Mapping) or not identity.get("candidate_id"):
            return None
        candidate_id = str(identity.get("candidate_id") or "")
        identity_training = identity.get("training_provenance")
        if not isinstance(identity_training, Mapping):
            # Preserve the existing candidate-race guard even for a legacy
            # identity that cannot carry the new training custody fields.  A
            # second identity read is still read-only; if it changed, report
            # the race before reporting the missing provenance.
            post_identity = identity_provider(decision_date=decision_date)
            if not isinstance(post_identity, Mapping):
                raise RecommendationProvenanceError(
                    "active candidate identity unavailable after projection receipt"
                )
            for key in (
                "candidate_id",
                "candidate_manifest_hash",
                "candidate_artifact_hash",
                "candidate_freeze_hash",
                "pointer_version",
            ):
                if post_identity.get(key) != identity.get(key):
                    raise RecommendationProvenanceError(
                        "candidate/model race: active candidate changed during projection receipt publication"
                    )
            raise RecommendationProvenanceError(
                "active training provenance is missing from candidate identity"
            )
        training_provenance = dict(identity_training)
        if str(training_provenance.get("status") or "") != "verified":
            raise RecommendationProvenanceError(
                "active training provenance is not verified for projection receipt"
            )
        label_registry_hash = str(
            training_provenance.get("label_registry_hash") or ""
        ).strip()
        label_contract_id = str(
            training_provenance.get("label_contract_id") or ""
        ).strip()
        return_basis = str(training_provenance.get("return_basis") or "").strip()
        if not label_registry_hash or not label_contract_id or not return_basis:
            raise RecommendationProvenanceError(
                "active training label contract provenance is incomplete"
            )
        projection_rows = []
        for _, projection in sorted(projections.items(), key=lambda item: str(item[0])):
            row = projection.to_dict()
            # These immutable fields are custodial data from the verified
            # active training provenance.  A projection may omit them for a
            # rule-only/unavailable row, but it may not contradict the active
            # candidate contract and the receipt never supplies a new label
            # contract from a current global default.
            for key, expected in (
                ("label_registry_hash", label_registry_hash),
                ("label_contract_id", label_contract_id),
                ("return_basis", return_basis),
            ):
                declared = str(row.get(key) or "").strip()
                if declared and declared != expected:
                    raise RecommendationProvenanceError(
                        f"projection {key} conflicts with active training provenance"
                    )
                row[key] = expected
            projection_rows.append(row)
        first = next(iter(projections.values()), None)
        if first is None:
            return None
        compatibility = getattr(first, "provenance_compatibility", {})
        receipt = build_inference_projection_receipt(
            decision_date=decision_date,
            result_id=result_id,
            candidate_identity=identity,
            training_provenance=(
                training_provenance if isinstance(training_provenance, Mapping) else {}
            ),
            inference_provenance=inference_provenance,
            compatibility=(compatibility if isinstance(compatibility, Mapping) else {}),
            projections=projection_rows,
            selection_contract={
                "authority": selection_authority,
                "score_kind": selection_score_kind,
                "percentile_kind": selection_percentile_kind,
                "model_ranking_kind": "model_return_bp",
                "top_n_changed_by_model": bool(top_n_changed_by_model),
            },
        )
        path = persist_inference_projection_receipt(Path(pointer_path).parent, receipt)
        receipt_created_at = datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        )
        read_inference_projection_receipt(
            path,
            expected_receipt_hash=receipt.receipt_hash,
            expected_decision_date=decision_date,
            expected_candidate_id=candidate_id,
            expected_result_id=result_id,
            expected_cost_scenario_hash=receipt.payload.get("cost_scenario_hash"),
        )
        post_identity = identity_provider(decision_date=decision_date)
        if not isinstance(post_identity, Mapping):
            raise RecommendationProvenanceError(
                "active candidate identity unavailable after projection receipt"
            )
        for key in (
            "candidate_id",
            "candidate_manifest_hash",
            "candidate_artifact_hash",
            "candidate_freeze_hash",
            "pointer_version",
        ):
            if post_identity.get(key) != identity.get(key):
                raise RecommendationProvenanceError(
                    "candidate/model race: active candidate changed during projection receipt publication"
                )
        return {
            "path": str(path),
            "receipt_hash": receipt.receipt_hash,
            "result_id": str(result_id or ""),
            "receipt_created_at": receipt_created_at,
        }

    def _matrix_row(
        self,
        *,
        stock_code: str,
        stock_name: str = "",
        status: str,
        reason_codes: List[str],
        quality: str,
        stage: str,
        threshold_name: str = "",
        observed_value: Any = None,
        required_value: Any = None,
        total_score: Any = None,
        score_bp: Optional[int] = None,
        score_percentile_bp: Optional[int] = None,
        eligible_universe_size: Optional[int] = None,
        threshold_mode: str = "fixed",
        warnings: Optional[List[str]] = None,
        industry: str = "",
    ) -> Dict[str, Any]:
        return matrix_row(
            stock_code=stock_code,
            stock_name=stock_name,
            status=status,
            reason_codes=reason_codes,
            quality=quality,
            stage=stage,
            threshold_name=threshold_name,
            observed_value=observed_value,
            required_value=required_value,
            total_score=total_score,
            score_bp=score_bp,
            score_percentile_bp=score_percentile_bp,
            eligible_universe_size=eligible_universe_size,
            threshold_mode=threshold_mode,
            warnings=warnings,
            industry=industry,
        )

    def _finalize_negative_evidence_buffers(self) -> None:
        if self.last_run_context:
            self.last_run_context["data_fingerprint"] = hashlib.sha256(json.dumps(
                {"market": self.last_run_context["market_data_fingerprint"], "fundamental": self.last_run_context["fundamental_inputs"]},
                sort_keys=True, ensure_ascii=False, default=str,
            ).encode("utf-8")).hexdigest()
        for row in self.last_screening_matrix:
            row["as_of_date"] = self.last_run_context.get("as_of_date", "")
            row["data_fingerprint"] = self.last_run_context.get("data_fingerprint", "")
        buffers = build_negative_evidence_buffers(self.last_screening_matrix)
        self.last_excluded_candidates_json = buffers.excluded_candidates
        self.last_why_not_payload_json = buffers.why_not_payload
        self.last_liquidity_gate_payload_json = buffers.liquidity_gate_payload
        self.last_exclusion_quality = buffers.exclusion_quality
        self.last_exclusion_warnings_json = buffers.exclusion_warnings
        if any(row.get("quality") in {"missing", "degraded"} for row in self.last_screening_matrix):
            self.last_exclusion_quality = "degraded"
            self.last_exclusion_warnings_json.append("screening_contains_unknown_evidence")

    @staticmethod
    def _configured_volume_change_min_percent(config: Dict[str, Any]) -> Decimal | None:
        return configured_volume_change_min_percent(config)

    @staticmethod
    def _format_decimal_for_payload(value: Decimal) -> str:
        return format_decimal_for_payload(value)

    @staticmethod
    def _validate_ranking_config(config: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
        return validate_ranking_config(config)

    @staticmethod
    def _normalize_decision_date(raw_date: Any) -> str:
        """將來源日期轉成 PIT 查詢可用的 ISO 日期；無法判讀時 fail-closed。"""
        if isinstance(raw_date, (pd.Timestamp, datetime, date)):
            if pd.isna(raw_date):
                raise ValueError("decision date is missing")
            return raw_date.strftime("%Y-%m-%d")

        date_text = str(raw_date).strip()
        if not date_text:
            raise ValueError("decision date is empty")

        normalized_text = date_text.replace("-", "").replace("/", "")
        if len(normalized_text) != 8 or not normalized_text.isdigit():
            raise ValueError(f"unsupported decision date: {date_text}")
        return datetime.strptime(normalized_text, "%Y%m%d").date().isoformat()

    def _load_governed_monthly_revenues(
        self,
        *,
        stock_code: str,
        decision_date: date,
    ):
        """只讀取有獨立正式 availability mapping 支持的月營收。"""

        provider = self._get_fundamental_sqlite_provider()
        if provider is None:
            return ()
        try:
            return provider.load_monthly_revenues(
                stock_code=stock_code,
                decision_date=decision_date,
            )
        except Exception as exc:
            # 基本面門檻無法建立正式 PIT 證據時，後續流程會以 missing 排除；
            # 不可退回到直接讀 SQLite row 的舊路徑。
            import logging

            logging.getLogger(__name__).error("查詢受治理月營收失敗: %s", exc)
            return ()

    def _get_fundamental_sqlite_provider(self) -> FundamentalSQLiteProvider | None:
        if self._fundamental_sqlite_provider is not None:
            return self._fundamental_sqlite_provider
        if self._fundamental_provider_initialization_attempted:
            return None

        self._fundamental_provider_initialization_attempted = True
        db_file = getattr(self.config, "db_file", None)
        if db_file is None:
            return None
        try:
            db_path = Path(cast(str, db_file))
        except (TypeError, ValueError):
            return None
        if not db_path.is_file():
            return None

        availability_file = getattr(
            self.config,
            "monthly_revenue_availability_file",
            None,
        )
        try:
            availability_path = (
                Path(availability_file) if availability_file is not None else None
            )
        except (TypeError, ValueError):
            availability_file = None
        else:
            availability_file = availability_path

        self._fundamental_sqlite_provider = FundamentalSQLiteProvider(
            db_path,
            monthly_revenue_availability_file=availability_file,
        )
        return self._fundamental_sqlite_provider

    def _load_historical_market_frame(self, cutoff: str | None) -> pd.DataFrame:
        """歷史入口使用決策日窗口及唯讀連線，不初始化 DBManager。"""
        if getattr(self.config, "use_sqlite", False):
            db_path = Path(self.config.db_file).resolve()
            with closing(sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)) as conn:
                conn.execute("PRAGMA query_only=ON")
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if cutoff is None:
                    latest = conn.execute("SELECT MAX(日期) FROM daily_prices").fetchone()[0]
                    if latest is None:
                        return pd.DataFrame(columns=["日期", "證券代號"])
                    cutoff = self._normalize_decision_date(latest)
                start = (pd.Timestamp(cutoff) - pd.Timedelta(days=60)).strftime("%Y%m%d")
                end = cutoff.replace("-", "")
                if "technical_indicators" in tables:
                    query = (
                        "SELECT p.*, t.* FROM daily_prices p LEFT JOIN technical_indicators t "
                        "ON p.證券代號=t.證券代號 AND p.日期=t.日期 "
                    )
                else:
                    query = "SELECT p.* FROM daily_prices p "
                query += "WHERE replace(CAST(p.日期 AS TEXT), '-', '') BETWEEN ? AND ? ORDER BY p.日期, p.證券代號"
                frame = pd.read_sql_query(query, conn, params=(start, end))
                return frame.loc[:, ~frame.columns.duplicated()].copy()
        paths = [getattr(self.config, "all_stocks_data_file", None), getattr(self.config, "stock_data_file", None)]
        for candidate in paths:
            if candidate is not None and candidate.is_file():
                return pd.read_csv(candidate, encoding="utf-8-sig", dtype={"證券代號": str, "股票代號": str})
        raise FileNotFoundError("歷史推薦缺少唯讀行情來源")

    def _decision_frame(self, frame: pd.DataFrame, cutoff: str | None) -> tuple[pd.DataFrame, str, str]:
        frame, stock_col = normalize_market_frame(frame)
        if frame.empty:
            return frame, stock_col, cutoff or ""
        frame["日期"] = parse_stock_dates(frame["日期"])
        frame = frame[frame["日期"].notna()].copy()
        decision_date = cutoff or (frame["日期"].max().strftime("%Y-%m-%d") if not frame.empty else "")
        if decision_date:
            limit = pd.Timestamp(decision_date)
            frame = frame[frame["日期"] <= limit].copy()
            if "available_date" in frame:
                available = parse_stock_dates(frame["available_date"])
                frame = frame[available.notna() & (available <= limit)].copy()
                frame["available_date"] = available.loc[frame.index]
                # 已知修訂優先；未到可得日的修訂不影響歷史窗口。
                frame = frame.sort_values("available_date", kind="stable").drop_duplicates([stock_col, "日期"], keep="last")
        frame[stock_col] = frame[stock_col].astype(str)
        return frame.reset_index(drop=True), stock_col, decision_date

    def _read_pit_membership_for_recommendation(
        self,
        cutoff: str,
        config: Dict[str, Any],
    ) -> PITMembershipReadResult | None:
        reader = self.pit_membership_reader
        if reader is None:
            return None
        decision_date = date.fromisoformat(cutoff)
        configured_cutoff = config.get("pit_decision_at") or config.get("decision_at")
        decision_at = configured_cutoff or reader.default_decision_at(decision_date)
        market_scope = config.get("pit_market_scope") or getattr(
            self.config, "pit_market_scope", None
        )
        try:
            return reader.read(
                as_of_date=decision_date,
                decision_at=decision_at,
                market_scope=market_scope,
            )
        except Exception as exc:  # noqa: BLE001 - recommendation fails closed
            return PITMembershipReadResult(
                as_of_date=decision_date,
                decision_at=reader.default_decision_at(decision_date),
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=(f"pit_membership_reader_error:{type(exc).__name__}",),
                lineage={
                    "reader_schema_version": "pit-sector-membership-reader.v1",
                    "status": "unavailable",
                    "market_scope_requested": None,
                    "error": str(exc),
                },
            )

    @staticmethod
    def _pit_codes_for_industry(
        result: PITMembershipReadResult,
        industry_filter: str,
    ) -> set[str]:
        return {
            row.symbol
            for row in result.rows
            if _industry_names_match(row.industry_category or "", industry_filter)
        }

    def run_recommendation(
        self,
        config: Dict[str, Any],
        max_stocks: int = 200,
        top_n: int = 50,
        *,
        as_of_date: str | date | None = None,
        universe: Optional[List[str]] = None,
        result_id: str | None = None,
        historical_research: bool = False,
        select_latest_available_cutoff: bool = False,
    ) -> List[RecommendationDTO]:
        """執行推薦分析

        這是從 ui_app/main.py 的 _execute_strategy_analysis_thread 提取的核心邏輯

        Args:
            config: 策略配置字典（包含 technical, patterns, signals, filters, regime 等）
            max_stocks: 最大處理股票數量（用於性能優化）
            top_n: 返回前 N 名推薦
            as_of_date: 顯式資料 cutoff；歷史研究必須由 caller 明示提供
            universe: 可選的明示股票母體
            result_id: 可選的既有結果 identity
            historical_research: 將顯式 cutoff 隔離標為歷史研究，不宣稱自然可得
            select_latest_available_cutoff: 由 producer 從實際來源選取最新可得 cutoff；
                不接受 caller 另傳的 cutoff

        Returns:
            List[RecommendationDTO]: 推薦股票列表，按總分降序排列
        """
        import logging
        logger = logging.getLogger(__name__)
        config = deepcopy(config)
        if max_stocks < 1 or top_n < 0:
            raise ValueError("max_stocks 必須為正數，top_n 不得為負數")
        if not isinstance(historical_research, bool):
            raise ValueError("historical_research 必須是布林值")
        if not isinstance(select_latest_available_cutoff, bool):
            raise ValueError("select_latest_available_cutoff 必須是布林值")
        config_cutoff = config.get("as_of_date")
        has_config_cutoff = config_cutoff not in (None, "")
        if historical_research and select_latest_available_cutoff:
            raise ValueError(
                "historical_research 不得與 select_latest_available_cutoff 同時啟用"
            )
        if historical_research and as_of_date is None:
            raise ValueError("historical_research 必須明示 as_of_date")
        if select_latest_available_cutoff and (
            as_of_date is not None or has_config_cutoff
        ):
            raise ValueError(
                "select_latest_available_cutoff 不得搭配 caller cutoff"
            )
        ranking_config, threshold_mode = self._validate_ranking_config(config)
        self._reset_negative_evidence_buffers()
        cutoff_input = (
            as_of_date
            if historical_research
            else None
            if select_latest_available_cutoff
            else as_of_date
            if as_of_date is not None
            else config_cutoff
        )
        cutoff = self._normalize_decision_date(cutoff_input) if cutoff_input is not None else None
        temporal_mode = (
            "historical_research_not_as_if_available"
            if historical_research
            else "natural_producer_clock"
            if select_latest_available_cutoff or not (as_of_date is not None or has_config_cutoff)
            else "explicit_cutoff_not_natural"
        )
        cutoff_selection = (
            "explicit_historical_cutoff"
            if historical_research
            else "producer_selected_latest_available_cutoff"
            if select_latest_available_cutoff or not (as_of_date is not None or has_config_cutoff)
            else "caller_requested_cutoff"
        )
        cutoff_policy = (
            "explicit_historical_research"
            if historical_research
            else "source_latest_available_exact"
            if cutoff_selection == "producer_selected_latest_available_cutoff"
            else "caller_explicit_cutoff_not_natural"
        )
        strategy_identity = build_strategy_config_identity(
            config,
            max_stocks=max_stocks,
            top_n=top_n,
        )
        run_started_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")

        # ✅ 記錄輸入參數
        logger.info(
            f"[RecommendationService] 開始推薦分析: "
            f"max_stocks={max_stocks}, top_n={top_n}, "
            f"產業篩選={config.get('filters', {}).get('industry', '全部')}, "
            f"圖形模式={config.get('patterns', {}).get('selected', [])}, "
            f"技術指標啟用={config.get('technical', {}).get('momentum', {}).get('enabled', False) or config.get('technical', {}).get('trend', {}).get('enabled', False)}"
        )

        source = (
            self._load_historical_market_frame(cutoff)
            if isinstance(self.market_data_provider, DefaultRecommendationMarketDataProvider) and (cutoff or getattr(self.config, "use_sqlite", False))
            else self.market_data_provider()
        )
        df, stock_col, decision_cutoff = self._decision_frame(source, cutoff)
        source_available_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        self._personalization_execution_clocks = {
            "run_started_at": run_started_at,
            "available_at": source_available_at,
            "captured_at": source_available_at,
            "personalization_scope_declared_at": run_started_at,
        }
        if universe is not None and not df.empty:
            df = df[df[stock_col].isin({str(code) for code in universe})].copy()
        canonical = df.sort_values([stock_col, "日期"], kind="stable") if not df.empty else df
        fingerprint_payload = canonical.reindex(sorted(canonical.columns), axis=1).astype(str).to_dict("records")
        self.last_run_context = {
            "schema_version": "recommendation-context.v1",
            "as_of_date": decision_cutoff,
            "strategy_config": deepcopy(config),
            "profile_id": str(config.get("profile_id") or ""),
            "profile_version": str(config.get("profile_version") or ""),
            "universe_spec": {"codes": sorted({str(code) for code in universe}) if universe is not None else None, "max_stocks": max_stocks},
            "source_id": type(self.market_data_provider).__name__,
            "market_data_fingerprint": hashlib.sha256(json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            "fundamental_inputs": [],
            "data_date": canonical["日期"].max().strftime("%Y-%m-%d") if not canonical.empty else "",
            "warnings": ["industry_membership_not_point_in_time"] if cutoff else [],
            "temporal_contract": "recommendation-producer-clock.v1",
            "temporal_mode": temporal_mode,
            "cutoff_selection": cutoff_selection,
            "cutoff_policy": cutoff_policy,
            "decision_clock_timezone": "UTC",
            "market_calendar_timezone": "Asia/Taipei",
            "prediction_decision_anchor": "actual_producer_decision_at",
            "horizon_anchor": "immutable_projection_receipt",
            **strategy_identity,
        }
        resolved_result_id = str(result_id or config.get("result_id") or "").strip()
        if not resolved_result_id:
            # Allocate the run identity before calibration receipt publication.
            # UUID entropy prevents same-second runs from sharing a saved result
            # or projection receipt identity; the context keeps it stable for
            # every save performed from this run.
            resolved_result_id = f"rec_{uuid4().hex}"
        self.last_run_context["result_id"] = resolved_result_id
        declared_identity = {
            "strategy_version_id": config.get("strategy_version_id") or config.get("strategy_version"),
            "cost_model_id": config.get("cost_model_id"),
            "benchmark_id": config.get("benchmark_id"),
            "industry_benchmark_id": config.get("industry_benchmark_id"),
            "horizon_days": config.get("horizon_days") or config.get("expected_horizon_days"),
        }
        self.last_run_context.update({
            key: value
            for key, value in declared_identity.items()
            if value is not None and str(value).strip()
        })
        industry_filter = config.get('filters', {}).get('industry', '全部')
        pit_membership: PITMembershipReadResult | None = None
        pit_industry_codes: set[str] | None = None
        if cutoff and industry_filter and industry_filter != '全部':
            pit_membership = self._read_pit_membership_for_recommendation(
                cutoff, config
            )
            if pit_membership is not None:
                self.last_run_context["industry_membership"] = dict(
                    pit_membership.lineage
                )
                self.last_run_context["industry_membership_status"] = pit_membership.status
                self.last_run_context["industry_membership_quality"] = pit_membership.quality
                self.last_run_context["industry_membership_warnings"] = list(
                    pit_membership.warnings
                )
                self.last_run_context["warnings"].extend(pit_membership.warnings)
                if pit_membership.industry_filter_usable:
                    self.last_run_context["warnings"] = [
                        item
                        for item in self.last_run_context["warnings"]
                        if item != "industry_membership_not_point_in_time"
                    ]
                    self.last_run_context["warnings"].append(
                        "industry_membership_pit_verified"
                    )
                    pit_industry_codes = self._pit_codes_for_industry(
                        pit_membership, str(industry_filter)
                    )
        if df.empty:
            self.last_run_context["eligible_universe_size"] = 0
            self._finalize_negative_evidence_buffers()
            return []

        # ✅ 記錄數據讀取結果
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[RecommendationService] 數據讀取完成: "
            f"總筆數={len(df)}, "
            f"股票數={df[stock_col].nunique()}, "
            f"日期範圍={df['日期'].min()} ~ {df['日期'].max()}"
        )

        # 應用產業篩選（先篩選產業，再限制數量）
        all_stocks = df[stock_col].unique()

        if cutoff and industry_filter and industry_filter != '全部':
            if pit_membership is None or not pit_membership.industry_filter_usable:
                self.last_screening_matrix = [self._matrix_row(
                    stock_code=str(code), status="missing", reason_codes=["industry_membership_pit_unavailable"],
                    quality="missing", stage="universe_gate", threshold_mode=threshold_mode,
                ) for code in all_stocks]
                self.last_run_context["eligible_universe_size"] = 0
                self._finalize_negative_evidence_buffers()
                return []
            filtered_stocks = pit_industry_codes or set()
            if not filtered_stocks:
                self.last_run_context["warnings"].append("industry_filter_empty")
                self.last_screening_matrix = [self._matrix_row(
                    stock_code=str(code), status="excluded", reason_codes=["industry_filter_empty"],
                    quality="observed", stage="universe_gate", threshold_mode=threshold_mode,
                ) for code in all_stocks]
                self.last_run_context["eligible_universe_size"] = 0
                self._finalize_negative_evidence_buffers()
                return []
            stocks = [s for s in all_stocks if str(s) in filtered_stocks]
            stocks = stocks[:max_stocks]

            logger.info(
                f"[RecommendationService] PIT 產業篩選完成: "
                f"產業={industry_filter}, "
                f"篩選前股票數={len(all_stocks)}, "
                f"篩選後股票數={len(stocks)}"
            )
        elif industry_filter and industry_filter != '全部':
            # 只在沒有明確 cutoff 的互動研究路徑使用 current mapper；
            # cutoff 路徑永不回退到 companies.csv。
            # 先從所有股票中篩選出屬於指定產業的股票
            current_filtered_stocks = self.industry_mapper.filter_stocks_by_industry(
                [str(s) for s in all_stocks],
                industry_filter
            )

            if len(current_filtered_stocks) == 0:
                # 提供更詳細的錯誤信息，幫助調試
                all_industries = self.industry_mapper.get_all_industries()
                similar_industries = [ind for ind in all_industries
                                     if industry_filter in ind or ind in industry_filter]
                error_msg = f"在數據中沒有找到屬於「{industry_filter}」產業的股票"
                if similar_industries:
                    error_msg += f"\n\n可能的相似產業名稱：{', '.join(similar_industries[:5])}"
                error_msg += f"\n\n所有可用產業（前20個）：{', '.join(all_industries[:20])}"
                error_msg += f"\n\n總股票數：{len(all_stocks)}"
                # 嘗試檢查是否有部分匹配的股票
                test_stocks = list(all_stocks)[:10]
                for test_stock in test_stocks:
                    test_industries = self.industry_mapper.get_stock_industries(str(test_stock))
                    if test_industries:
                        error_msg += f"\n範例：股票 {test_stock} 屬於：{', '.join(test_industries[:3])}"
                        break
                self.last_run_context["warnings"].append("industry_filter_empty")

            # 只保留屬於該產業的股票
            stocks = [s for s in all_stocks if str(s) in current_filtered_stocks]
            # 限制處理數量（在產業篩選後）
            stocks = stocks[:max_stocks]

            # ✅ 記錄產業篩選結果
            logger.info(
                f"[RecommendationService] 產業篩選完成: "
                f"產業={industry_filter}, "
                f"篩選前股票數={len(all_stocks)}, "
                f"篩選後股票數={len(stocks)}"
            )
        else:
            # 沒有產業篩選，直接限制數量
            stocks = all_stocks[:max_stocks]

        universe_selected_codes = sorted({str(code).strip() for code in stocks if str(code).strip()})
        selection_mode = (
            "explicit_universe"
            if universe is not None
            else "industry_filtered"
            if industry_filter and industry_filter != "全部"
            else "top_max_stocks"
        )
        requested_codes = (
            sorted({str(code).strip() for code in universe if str(code).strip()})
            if universe is not None
            else None
        )
        universe_identity = build_recommendation_universe_identity(
            decision_date=decision_cutoff,
            selection_mode=selection_mode,
            industry_filter=str(industry_filter or "全部"),
            max_stocks=max_stocks,
            requested_codes=requested_codes,
            selected_codes=universe_selected_codes,
            source_provider_id=type(self.market_data_provider).__name__,
        )
        self.last_run_context.update(universe_identity)
        self.last_run_context["universe_spec"].update(
            {
                "selected_codes": universe_selected_codes,
                "selection_mode": selection_mode,
                "industry_filter": str(industry_filter or "全部"),
                "universe_policy_id": universe_identity["universe_policy_id"],
                "universe_policy_hash": universe_identity["universe_policy_hash"],
                "universe_snapshot_id": universe_identity["universe_snapshot_id"],
                "universe_snapshot_hash": universe_identity["universe_snapshot_hash"],
            }
        )

        # 🚀 效能優化：過濾 df 僅保留需要處理的股票，避免在包含所有個股的巨量 DataFrame 上進行高頻 boolean indexing
        df = df[df[stock_col].isin(stocks)].copy()

        # ✅ 記錄處理開始
        logger.info(
            f"[RecommendationService] 開始處理 {len(stocks)} 支股票"
        )

        # 對每支股票執行策略分析
        all_recommendations = []
        matrix_rows_by_stock: Dict[str, Dict[str, Any]] = {}

        # 調試統計
        stats = {
            'total_stocks': len(stocks),
            'processed': 0,
            'skipped_insufficient_data': 0,
            'skipped_no_result': 0,
            'skipped_exception': 0,
            'success': 0
        }

        for idx, stock_code in enumerate(stocks):
            stock_df = df[df[stock_col] == stock_code].copy()
            stock_df = stock_df.sort_values('日期').reset_index(drop=True)
            stock_code_text = str(stock_code)
            stock_name_text = stock_code_text
            if len(stock_df) > 0 and '證券名稱' in stock_df.columns:
                stock_name_text = str(stock_df.iloc[-1].get('證券名稱', stock_code_text))

            # 確保至少有20筆數據才能計算技術指標
            if len(stock_df) < 20:
                stats['skipped_insufficient_data'] += 1
                row = self._matrix_row(
                    stock_code=stock_code_text,
                    stock_name=stock_name_text,
                    status="missing",
                    reason_codes=["insufficient_history"],
                    quality="missing",
                    stage="pre_evaluation",
                    threshold_name="minimum_history_rows",
                    observed_value=len(stock_df),
                    required_value=20,
                    threshold_mode=threshold_mode,
                )
                self.last_screening_matrix.append(row)
                matrix_rows_by_stock[stock_code_text] = row
                continue

            stock_df = enrich_latest_market_features(stock_df)

            try:
                # 生成推薦（generate_recommendations 內部會處理篩選，這裡不需要額外篩選）
                result_df = self.strategy_configurator.generate_recommendations(stock_df, deepcopy(config))

                stats['processed'] += 1

                # ✅ 添加調試信息：記錄為什麼返回空 DataFrame
                if len(result_df) == 0:
                    # 記錄前3個被過濾的股票詳情
                    if stats['skipped_no_result'] < 3:
                        logger.warning(
                            f"[調試] 股票 {stock_code} 返回空結果: "
                            f"數據筆數={len(stock_df)}, "
                            f"日期範圍={stock_df['日期'].min() if '日期' in stock_df.columns else 'N/A'} ~ "
                            f"{stock_df['日期'].max() if '日期' in stock_df.columns else 'N/A'}"
                        )
                    reason_codes = ["strategy_filter_no_signal"]
                    threshold_name = "strategy_configurator_result"
                    observed_value: Any = "empty"
                    required_value: Any = "non_empty"
                    volume_min = self._configured_volume_change_min_percent(config)
                    observed_volume_change = latest_feature_decimal(
                        stock_df,
                        "成交量變化率%",
                    )
                    if (
                        volume_min is not None
                        and observed_volume_change is not None
                        and observed_volume_change < volume_min
                    ):
                        reason_codes = ["liquidity_volume_ratio_below_min"]
                        threshold_name = "liquidity.volume_ratio_min"
                        observed_value = self._format_decimal_for_payload(observed_volume_change)
                        required_value = self._format_decimal_for_payload(volume_min)
                    row = self._matrix_row(
                        stock_code=stock_code_text,
                        stock_name=stock_name_text,
                        status="skipped",
                        reason_codes=reason_codes,
                        quality="degraded",
                        stage="strategy_evaluation",
                        threshold_name=threshold_name,
                        observed_value=observed_value,
                        required_value=required_value,
                        threshold_mode=threshold_mode,
                    )
                    self.last_screening_matrix.append(row)
                    matrix_rows_by_stock[stock_code_text] = row

                if len(result_df) > 0:
                    latest_row = result_df.iloc[-1]

                    # 取得決策日期。基本面篩選只接受可標準化的日期，避免無效日期
                    # 造成 PIT 查詢意外納入未來資料。
                    raw_date = decision_cutoff
                    pe_ratio_max = to_decimal(config.get('filters', {}).get('pe_ratio_max', "999.0"))
                    revenue_yoy_min = to_decimal(config.get('filters', {}).get('monthly_revenue_yoy_min', "-100.0"))
                    fundamental_filters_enabled = (
                        pe_ratio_max < to_decimal("999.0")
                        or revenue_yoy_min > to_decimal("-100.0")
                    )
                    try:
                        decision_date = self._normalize_decision_date(raw_date)
                    except (TypeError, ValueError):
                        if fundamental_filters_enabled:
                            row = self._matrix_row(
                                stock_code=stock_code_text,
                                stock_name=stock_name_text,
                                status="skipped",
                                reason_codes=["fundamental_decision_date_invalid"],
                                quality="degraded",
                                stage="strategy_evaluation",
                                threshold_name="decision_date",
                                observed_value=str(raw_date),
                                required_value="YYYY-MM-DD",
                                threshold_mode=threshold_mode,
                            )
                            self.last_screening_matrix.append(row)
                            matrix_rows_by_stock[stock_code_text] = row
                            stats['skipped_no_result'] += 1
                            continue
                        decision_date = ""

                    # 1. 本益比 PE 過濾
                    if pe_ratio_max < to_decimal("999.0"):
                        pe_val_dec = None
                        try:
                            db_uri = Path(self.config.db_file).resolve().as_uri() + "?mode=ro"
                            with closing(sqlite3.connect(db_uri, uri=True)) as conn:
                                conn.execute("PRAGMA query_only=ON")
                                conn.row_factory = sqlite3.Row
                                cursor = conn.cursor()
                                cursor.execute(
                                    "SELECT value, as_of_date, available_date, source, source_version, quality FROM fundamental_valuation_metrics "
                                    "WHERE stock_code = ? AND metric_name = 'pe' AND available_date <= ? AND as_of_date <= ? AND quality = 'observed' "
                                    "ORDER BY as_of_date DESC, available_date DESC, source_version DESC LIMIT 1",
                                    (stock_code_text, decision_date, decision_date)
                                )
                                row = cursor.fetchone()
                                if row and row['value'] is not None:
                                    pe_val_dec = to_decimal(row['value'])
                                    self.last_run_context["fundamental_inputs"].append({"stock_code": stock_code_text, "metric": "pe", **dict(row)})
                        except Exception as e:
                            logger.error(f"查詢 PE 失敗: {e}")

                        if pe_val_dec is None:
                            # 查不到基本面資料，明確排除
                            row = self._matrix_row(
                                stock_code=stock_code_text,
                                stock_name=stock_name_text,
                                status="skipped",
                                reason_codes=["valuation_pe_missing"],
                                quality="missing",
                                stage="strategy_evaluation",
                                threshold_name="filters.pe_ratio_max",
                                observed_value="missing",
                                required_value=pe_ratio_max,
                                threshold_mode=threshold_mode,
                            )
                            self.last_screening_matrix.append(row)
                            matrix_rows_by_stock[stock_code_text] = row
                            stats['skipped_no_result'] += 1
                            continue

                        if pe_val_dec > pe_ratio_max:
                            row = self._matrix_row(
                                stock_code=stock_code_text,
                                stock_name=stock_name_text,
                                status="skipped",
                                reason_codes=["valuation_pe_above_max"],
                                quality="observed",
                                stage="strategy_evaluation",
                                threshold_name="filters.pe_ratio_max",
                                observed_value=pe_val_dec,
                                required_value=pe_ratio_max,
                                threshold_mode=threshold_mode,
                            )
                            self.last_screening_matrix.append(row)
                            matrix_rows_by_stock[stock_code_text] = row
                            stats['skipped_no_result'] += 1
                            continue

                    # 2. 月營收 YOY% 過濾
                    if revenue_yoy_min > to_decimal("-100.0"):
                        yoy_val_dec = None
                        revenue_records = self._load_governed_monthly_revenues(
                            stock_code=stock_code_text,
                            decision_date=date.fromisoformat(decision_date),
                        )
                        if revenue_records:
                            self.last_run_context["fundamental_inputs"].extend({
                                "stock_code": stock_code_text, "metric": "monthly_revenue", "period": record.period,
                                "available_date": record.available_date.isoformat(), "source": record.source,
                                "source_version": record.source_version, "value": str(record.revenue),
                            } for record in sorted(revenue_records, key=lambda item: (item.period, item.available_date, item.source_version)))
                            latest_revenue = max(
                                revenue_records,
                                key=lambda record: (
                                    record.period,
                                    record.available_date,
                                    record.source_version,
                                ),
                            )
                            year_curr, month_curr = map(
                                int,
                                latest_revenue.period.split("-"),
                            )
                            period_prev = f"{year_curr - 1:04d}-{month_curr:02d}"
                            prior_candidates = [
                                record
                                for record in revenue_records
                                if record.period == period_prev
                            ]
                            if prior_candidates:
                                prior_revenue = max(
                                    prior_candidates,
                                    key=lambda record: (
                                        record.available_date,
                                        record.source_version,
                                    ),
                                )
                                if prior_revenue.revenue > to_decimal("0"):
                                    yoy_val_dec = (
                                        (latest_revenue.revenue - prior_revenue.revenue)
                                        / prior_revenue.revenue
                                    ) * to_decimal("100.0")

                        if yoy_val_dec is None:
                            # 查不到營收或去年同期營收，明確排除
                            row = self._matrix_row(
                                stock_code=stock_code_text,
                                stock_name=stock_name_text,
                                status="skipped",
                                reason_codes=["fundamental_revenue_yoy_missing"],
                                quality="missing",
                                stage="strategy_evaluation",
                                threshold_name="filters.monthly_revenue_yoy_min",
                                observed_value="missing",
                                required_value=revenue_yoy_min,
                                threshold_mode=threshold_mode,
                            )
                            self.last_screening_matrix.append(row)
                            matrix_rows_by_stock[stock_code_text] = row
                            stats['skipped_no_result'] += 1
                            continue

                        if yoy_val_dec < revenue_yoy_min:
                            row = self._matrix_row(
                                stock_code=stock_code_text,
                                stock_name=stock_name_text,
                                status="skipped",
                                reason_codes=["fundamental_revenue_yoy_below_min"],
                                quality="observed",
                                stage="strategy_evaluation",
                                threshold_name="filters.monthly_revenue_yoy_min",
                                observed_value=yoy_val_dec.quantize(to_decimal("0.01")),
                                required_value=revenue_yoy_min,
                                threshold_mode=threshold_mode,
                            )
                            self.last_screening_matrix.append(row)
                            matrix_rows_by_stock[stock_code_text] = row
                            stats['skipped_no_result'] += 1
                            continue

                    # 獲取收盤價
                    close_col = None
                    for col in ['收盤價', 'Close', 'close']:
                        if col in latest_row.index:
                            close_col = col
                            break

                    price_change_value = latest_feature_decimal(stock_df, "漲幅%")
                    volume_change_value = latest_feature_decimal(
                        stock_df,
                        "成交量變化率%",
                    )
                    price_change = float(price_change_value or Decimal("0"))

                    # DTO / reason DataFrame 邊界沿用既有數值欄位型態，不重新計算。
                    latest_row = latest_row.copy()
                    latest_row['漲幅%'] = price_change
                    latest_row['成交量變化率%'] = float(
                        volume_change_value or Decimal("0")
                    )

                    # 獲取股票所屬產業
                    stock_industries = [] if cutoff else self.industry_mapper.get_stock_industries(stock_code)
                    industry_display = ', '.join(stock_industries[:2]) if stock_industries else '未知'
                    if len(stock_industries) > 2:
                        industry_display += '...'

                    # 生成推薦理由（包含市場狀態和產業信息）
                    reasons = self.reason_engine.generate_reasons(latest_row, config)

                    # 添加產業表現理由
                    if stock_industries:
                        for industry in stock_industries[:1]:  # 只取第一個產業
                            industry_perf = self.industry_mapper.get_industry_performance(industry, date=decision_date)
                            if industry_perf:
                                industry_change = industry_perf.get('漲跌百分比', 0)
                                if isinstance(industry_change, str):
                                    try:
                                        industry_change = float(industry_change.replace('%', ''))
                                    except:
                                        industry_change = 0

                                if industry_change > 0:
                                    reasons.append({
                                        'tag': f'{industry}指數上漲',
                                        'evidence': f'{industry}類指數漲幅 {industry_change:.2f}%',
                                        'score_contrib': min(industry_change * 0.5, 10)
                                    })

                    reason_text = self.reason_engine.format_reason_text(reasons, max_reasons=3)

                    # 使用 FinalScore（含 Regime Match Factor）作為排序依據
                    final_score = latest_row.get(
                        'FinalScore',
                        latest_row.get('TotalScore', latest_row.get('綜合評分'))
                    )
                    if final_score is None or not to_decimal(final_score).is_finite():
                        row = self._matrix_row(
                            stock_code=stock_code_text, stock_name=stock_name_text,
                            status="missing", reason_codes=["total_score_missing_or_nonfinite"],
                            quality="missing", stage="strategy_evaluation", threshold_mode=threshold_mode,
                        )
                        self.last_screening_matrix.append(row)
                        matrix_rows_by_stock[stock_code_text] = row
                        stats['skipped_no_result'] += 1
                        continue

                    # 判斷 Regime Match
                    regime = config.get('regime', None)
                    regime_match = False
                    if regime:
                        # 簡單判斷：如果 FinalScore > TotalScore，則匹配
                        total_score = latest_row.get('TotalScore', 0)
                        if to_decimal(final_score) > to_decimal(total_score) * to_decimal("1.05"):  # 允許5%誤差
                            regime_match = True

                    # 創建 DTO
                    recommendation = RecommendationDTO(
                        stock_code=stock_code_text,
                        stock_name=latest_row.get('證券名稱', stock_df.iloc[-1].get('證券名稱', stock_code)),
                        close_price=to_decimal(latest_row.get(close_col, stock_df.iloc[-1].get(close_col, 0))) if close_col else Decimal("0"),
                        price_change=price_change,
                        total_score=final_score,
                        indicator_score=latest_row.get('IndicatorScore', 0),
                        pattern_score=latest_row.get('PatternScore', 0),
                        volume_score=latest_row.get('VolumeScore', 0),
                        recommendation_reasons=reason_text,
                        industry=industry_display,
                        regime_match=regime_match
                    )

                    all_recommendations.append(recommendation)
                    row = self._matrix_row(
                        stock_code=stock_code_text,
                        stock_name=str(recommendation.stock_name),
                        status="fail",
                        reason_codes=["pending_final_selection"],
                        quality="observed",
                        stage="candidate_scored",
                        total_score=final_score,
                        threshold_mode=threshold_mode,
                        industry=industry_display,
                    )
                    self.last_screening_matrix.append(row)
                    matrix_rows_by_stock[stock_code_text] = row
                    stats['success'] += 1
                else:
                    stats['skipped_no_result'] += 1

            except Exception as e:
                # 跳過處理失敗的股票
                stats['skipped_exception'] += 1
                row = self._matrix_row(
                    stock_code=stock_code_text,
                    stock_name=stock_name_text,
                    status="degraded",
                    reason_codes=["screening_exception"],
                    quality="degraded",
                    stage="strategy_evaluation",
                    threshold_name=type(e).__name__,
                    observed_value=str(e),
                    required_value="successful_evaluation",
                    threshold_mode=threshold_mode,
                    warnings=[f"screening_exception:{type(e).__name__}"],
                )
                self.last_screening_matrix.append(row)
                matrix_rows_by_stock[stock_code_text] = row
                # 記錄前3個異常的詳細信息（避免日誌過多）
                if stats['skipped_exception'] <= 3:
                    import logging
                    import traceback
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"處理股票 {stock_code} 時發生異常: {str(e)}\n"
                        f"異常類型: {type(e).__name__}\n"
                        f"堆疊追蹤:\n{traceback.format_exc()}"
                    )
                continue

        # ✅ 記錄處理結果摘要
        logger.info(
            f"[RecommendationService] 推薦分析完成: "
            f"總股票數={stats['total_stocks']}, "
            f"已處理={stats['processed']}, "
            f"成功={stats['success']}, "
            f"返回推薦數={len(all_recommendations)}"
        )

        # 如果沒有找到任何推薦，提供調試信息
        if len(all_recommendations) == 0 and stats['total_stocks'] > 0:
            logger.warning(
                f"推薦分析未找到任何股票。統計："
                f"總股票數={stats['total_stocks']}, "
                f"已處理={stats['processed']}, "
                f"成功={stats['success']}, "
                f"數據不足={stats['skipped_insufficient_data']}, "
                f"無結果={stats['skipped_no_result']}, "
                f"異常={stats['skipped_exception']}"
            )

            # 提供診斷建議
            if stats['skipped_no_result'] > 0:
                logger.warning(
                    f"診斷建議："
                    f"有 {stats['skipped_no_result']} 支股票被篩選過濾。"
                    f"請檢查："
                    f"1. 最小漲幅% 是否過高（當前：{config.get('filters', {}).get('price_change_min', 0)}%）"
                    f"2. 最小成交量比率是否過高（當前：{config.get('filters', {}).get('volume_ratio_min', 1.0)}）"
                    f"3. 技術指標或圖形模式是否過於嚴格"
                )

        latest_date_str = ""
        if not all_recommendations:
            self.last_run_context["eligible_universe_size"] = 0
            self._finalize_negative_evidence_buffers()
            return []
        if not df.empty and "日期" in df.columns:
            latest_date_str = df["日期"].max().strftime("%Y-%m-%d")
        ranking_plan = build_ranking_plan(
            [(rec.stock_code, rec.total_score) for rec in all_recommendations],
            mode=threshold_mode,
            top_n=top_n,
            ranking_config=ranking_config,
            eligible_universe_date=decision_cutoff or latest_date_str,
        )
        self.last_run_context["eligible_universe_size"] = ranking_plan.eligible_universe_size
        recommendations_by_code = {
            rec.stock_code: rec for rec in all_recommendations
        }

        for rec in all_recommendations:
            rec.threshold_mode = ranking_plan.mode
            rec.eligible_universe_size = ranking_plan.eligible_universe_size
            rec.eligible_universe_date = ranking_plan.eligible_universe_date
            rec.ranking_method = ranking_plan.ranking_method
            matrix_row_for_rec = matrix_rows_by_stock.get(rec.stock_code)
            if ranking_plan.mode != "quantile":
                continue
            percentile_bp = ranking_plan.percentiles_bp.get(rec.stock_code, 0)
            if matrix_row_for_rec is not None:
                matrix_row_for_rec["score_percentile_bp"] = percentile_bp
                matrix_row_for_rec["eligible_universe_size"] = (
                    ranking_plan.eligible_universe_size
                )
                matrix_row_for_rec["threshold_name"] = (
                    "recommendation_min_percentile_bp"
                )
                matrix_row_for_rec["observed_value"] = str(percentile_bp)
                matrix_row_for_rec["required_value"] = str(
                    ranking_plan.minimum_percentile_bp
                )
                matrix_row_for_rec["threshold_mode"] = "quantile"
            if rec.stock_code in ranking_plan.ordered_codes:
                rec.score_percentile_bp = percentile_bp
                rec.eligible_universe_size = ranking_plan.eligible_universe_size
                rec.eligible_universe_date = ranking_plan.eligible_universe_date
                rec.ranking_method = ranking_plan.ranking_method
            elif matrix_row_for_rec is not None:
                matrix_row_for_rec["status"] = "fail"
                matrix_row_for_rec["reason_codes"] = [
                    "recommendation_percentile_below_min"
                ]
                matrix_row_for_rec["quality"] = "observed"
                matrix_row_for_rec["stage"] = "threshold_gate"

        ordered_recommendations = [
            recommendations_by_code[code] for code in ranking_plan.ordered_codes
        ]
        selected_codes = set(ranking_plan.selected_codes)
        for rank, rec in enumerate(ordered_recommendations, start=1):
            matrix_row_for_rec = matrix_rows_by_stock.get(rec.stock_code)
            if matrix_row_for_rec is None:
                continue
            if rec.stock_code in selected_codes:
                matrix_row_for_rec["status"] = "pass"
                matrix_row_for_rec["reason_codes"] = ["recommendation_selected"]
                matrix_row_for_rec["stage"] = "final_selection"
            else:
                matrix_row_for_rec["status"] = "fail"
                matrix_row_for_rec["reason_codes"] = [
                    "recommendation_outside_top_n"
                ]
                matrix_row_for_rec["stage"] = "top_n_gate"
                matrix_row_for_rec["threshold_name"] = "top_n"
                matrix_row_for_rec["observed_value"] = str(rank)
                matrix_row_for_rec["required_value"] = str(top_n)
        all_recommendations = [
            recommendations_by_code[code] for code in ranking_plan.selected_codes
        ]
        decision_clock = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        self._personalization_execution_clocks["decision_at"] = decision_clock
        # Persist the actual producer decision clock even when an optional
        # calibration receipt is unavailable.  Downstream forward-custody
        # checks must not infer decision time from the later saved
        # ``RecommendationResultDTO.created_at`` timestamp.
        self.last_run_context["decision_at"] = decision_clock
        self._apply_recommendation_calibration(
            all_recommendations,
            decision_date=decision_cutoff or latest_date_str,
            selection_authority="rule_top_n",
            selection_score_kind="rule_total_score",
            selection_percentile_kind="rule_percentile",
            top_n_changed_by_model=False,
        )
        self._finalize_negative_evidence_buffers()
        return all_recommendations

    def detect_regime(self) -> Dict[str, Any]:
        """檢測市場狀態

        Returns:
            dict: {
                'regime': 'Trend' | 'Reversion' | 'Breakout',
                'confidence': float (0-1),
                'details': dict,
                'regime_name_cn': str
            }
        """
        regime_result = self.regime_detector.detect_regime()
        regime = regime_result.get('regime', 'Trend')
        confidence = regime_result.get('confidence', 0.5)
        details = regime_result.get('details', {})

        regime_name_map = {
            'Trend': '趨勢追蹤',
            'Reversion': '均值回歸',
            'Breakout': '突破準備'
        }
        regime_name_cn = regime_name_map.get(regime, regime)

        return {
            'regime': regime,
            'confidence': confidence,
            'details': details,
            'regime_name_cn': regime_name_cn
        }

    def get_strategy_config_for_regime(self, regime: str) -> Dict[str, Any]:
        """獲取指定市場狀態的策略配置

        Args:
            regime: 'Trend' | 'Reversion' | 'Breakout'

        Returns:
            dict: 策略配置字典
        """
        return self.regime_detector.get_strategy_config(regime)

    def load_strategy_from_preset(
        self,
        preset_id: str,
        preset_service: PresetService
    ) -> Optional[Dict[str, Any]]:
        """
        從 Preset 載入策略配置

        Args:
            preset_id: Preset ID
            preset_service: PresetService 實例

        Returns:
            策略配置字典或 None
        """
        preset = preset_service.load_preset(preset_id)
        if preset is None:
            return None
        preset_meta = preset.meta or {}

        # 構建策略配置字典
        config = {
            'strategy_id': preset.strategy_id,
            'params': preset.params,
            **preset_meta.get('config', {})
        }

        return config

    def load_strategy_from_version(
        self,
        version_id: str,
        strategy_version_service: StrategyVersionService
    ) -> Optional[Dict[str, Any]]:
        """
        從策略版本載入策略配置

        Args:
            version_id: 策略版本 ID
            strategy_version_service: StrategyVersionService 實例

        Returns:
            策略配置字典或 None
        """
        version = strategy_version_service.get_version(version_id)
        if version is None:
            return None

        # 構建策略配置字典
        config = {
            'strategy_id': version.strategy_id,
            'strategy_version': version.strategy_version,
            'params': version.params,
            **version.config
        }

        return config

    def load_strategy_spec_from_preset(
        self,
        preset_id: str,
        preset_service: PresetService
    ) -> Optional[StrategySpec]:
        """
        從 Preset 載入 StrategySpec

        Args:
            preset_id: Preset ID
            preset_service: PresetService 實例

        Returns:
            StrategySpec 對象或 None
        """
        preset = preset_service.load_preset(preset_id)
        if preset is None:
            return None
        preset_meta = preset.meta or {}

        return StrategySpec(
            strategy_id=preset.strategy_id,
            strategy_version=preset_meta.get('strategy_version', '1.0.0'),
            default_params=preset.params,
            config=preset_meta.get('config', {})
        )

    def load_strategy_spec_from_version(
        self,
        version_id: str,
        strategy_version_service: StrategyVersionService
    ) -> Optional[StrategySpec]:
        """
        從策略版本載入 StrategySpec

        Args:
            version_id: 策略版本 ID
            strategy_version_service: StrategyVersionService 實例

        Returns:
            StrategySpec 對象或 None
        """
        version = strategy_version_service.get_version(version_id)
        if version is None:
            return None

        return StrategySpec(
            strategy_id=version.strategy_id,
            strategy_version=version.strategy_version,
            default_params=version.params,
            config=version.config,
            regime=version.regime
        )

