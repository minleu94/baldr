"""
推薦服務 (Recommendation Service)
提供股票推薦的業務邏輯，供 UI 層調用
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Callable, List, Dict, Any, Mapping, Optional, Sequence, TYPE_CHECKING, TypeGuard, cast
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from copy import copy, deepcopy
import hashlib
import json
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo

_STANDARD_DATETIME = datetime


def _is_company_registry_source_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _company_registry_source_contract_hash_matches(
    contract: Mapping[str, Any],
) -> bool:
    """用 company registry 既有 canonical JSON 規則核對封存雜湊。"""

    declared = contract.get("source_contract_sha256")
    if not _is_company_registry_source_sha256(declared):
        return False
    body = dict(contract)
    body.pop("source_contract_sha256", None)
    try:
        canonical = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return False
    return declared == "sha256:" + hashlib.sha256(canonical).hexdigest()


def _withdraw_personal_calibration_fields(
    recommendations: Sequence[RecommendationDTO],
) -> None:
    """在個人模式未適用時移除所有模型衍生數值，保留規則排名。"""

    for recommendation in recommendations:
        recommendation.ranking_score_bp = None
        recommendation.calibrated_probability_bp = None
        recommendation.calibrated_probability_status = "unavailable"
        recommendation.after_cost_profit_probability_bp = None
        recommendation.after_cost_profit_probability_status = "unavailable"
        recommendation.evidence_confidence = ""
        recommendation.sample_size = None
        recommendation.cost_basis_bp = None
        recommendation.calibration_model_version = ""
        recommendation.calibration_dataset_version = ""
        recommendation.calibration_horizon = ""
        recommendation.calibration_status = "rule_only"
        recommendation.calibration_source = "personal_use_policy"
        recommendation.calibration_warnings = ["personal_rule_only_effective"]
        recommendation.calibration_source_trace = []
        recommendation.calibration_probability_transform_id = ""
        recommendation.calibration_probability_baseline_id = ""
        recommendation.calibration_probability_baseline_kind = ""
        recommendation.calibration_probability_baseline_probability_bp = None
        recommendation.calibration_raw_probability_bp = None
        recommendation.calibration_raw_after_cost_probability_bp = None
        recommendation.calibration_provenance = {}


def _is_explicit_personal_rule_only_projection(value: Any) -> bool:
    """辨認無模型機率的明確 rule-only fallback 投影。"""

    to_dict = getattr(value, "to_dict", None)
    if not callable(to_dict):
        return False
    try:
        row = to_dict()
    except (TypeError, ValueError):
        return False
    if not isinstance(row, Mapping):
        return False
    if (
        row.get("status") != "rule_only"
        or row.get("ranking_method") != "rule_only"
        or row.get("calibrated_probability_status") != "unavailable"
        or row.get("after_cost_profit_probability_status") != "unavailable"
        or row.get("probability_baseline_kind") != "unavailable"
        or row.get("provenance_status") != "unavailable"
        or bool(str(row.get("model_version") or "").strip())
        or bool(str(row.get("dataset_version") or "").strip())
    ):
        return False
    if any(
        row.get(field_name) is not None
        for field_name in (
            "calibrated_probability_bp",
            "after_cost_profit_probability_bp",
            "probability_baseline_probability_bp",
            "population_probability_bp",
            "raw_calibrated_probability_bp",
            "raw_after_cost_profit_probability_bp",
        )
    ):
        return False
    warnings = row.get("warnings")
    compatibility = row.get("provenance_compatibility")
    reason = compatibility.get("reason") if isinstance(compatibility, Mapping) else None
    return (
        type(warnings) is list
        and bool(warnings)
        and all(type(item) is str and item.strip() for item in warnings)
        and isinstance(compatibility, Mapping)
        and compatibility.get("status") == "blocked"
        and type(reason) is str
        and bool(reason.strip())
    )

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
from app_module.recommendation.legacy_dtos import RecommendationDTO
from app_module.regime_service import RegimeService
from decision_module.strategies.contracts import StrategySpec
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
from app_module.recommendation_errors import RecommendationUniverseTooSmallError
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
from ml_module.recommendation_cost_scenario import RecommendationCostScenario
from app_module.recommendation.personal_use_policy import (
    PERSONAL_CALIBRATED_PROBABILITY_MODE,
    RULE_ONLY_MODE,
    PersonalCalibrationCandidateV1,
    RecommendationPersonalUsePolicyV1,
    RecommendationPersonalUsePolicyV2,
    load_personal_use_policy_snapshot,
)
from data_module.company_registry import (
    COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR,
    COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION,
)
from data_module.industry_mapper_data_provider import (
    INDUSTRY_INDEX_SOURCE_OBSERVATION_ATTR,
    industry_index_source_observation_hash_matches,
)
from app_module.recommendation.input_preparation import (
    RecommendationInputPreparer,
    RecommendationInputSession,
    minimum_recommendation_history_rows,
)
from app_module.recommendation.current_market_status_preflight import (
    CurrentMarketStatusPreflightResult,
    validate_current_market_status_evidence,
)
from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.recommendation_current_fundamental_provider import (
    CurrentObservedMonthlyRevenueInput,
)
from app_module.recommendation.evaluation_driver import evaluate_candidate_staged
from app_module.recommendation.score_projection import project_legacy_recommendation_score
from app_module.recommendation.source_fact_projection import (
    project_industry_context_fact,
    project_legacy_industry_reason,
    project_current_monthly_revenue_records,
    project_current_pe_observation,
    project_monthly_revenue_records,
    project_optional_final_score,
    project_pe_observation,
    project_required_legacy_decimal,
)
from decision_module.recommendation.evaluate import (
    CandidateCurrentMarketStatusFact,
    CandidatePrefilterFact,
    CandidateEvaluationOutcome,
    CandidateHistoryFacts,
    CandidateSeed,
    DecisionUniverseTooSmallError,
    NeedSourceFact,
    RecommendationEvaluationPolicy,
    RecommendationEvaluationResult,
    RecommendationEvaluator,
    RecommendationScore,
    SourceFactKind,
    SourceFactResponse,
    StrategyEvaluationError,
)
from decision_module.recommendation.contracts import RecommendationItem
from decision_module.recommendation.industry_reasons import (
    build_industry_performance_reason,
)
from decision_module.recommendation.finalization import (
    FinalScoreDisposition,
    FinalScoreFacts,
    RecommendationItemFacts,
    RegimeMatchFacts,
    classify_final_score,
    evaluate_regime_match,
    finalize_candidate_item,
    reason_tags_from_legacy_reasons,
)
from app_module.recommendation.body_result import (
    CandidateRowFacts,
    InvocationLegacyContextOwner,
    LegacyRecommendationSnapshot,
    RecommendationBodyContextFacts,
    RecommendationBodyResult,
    build_candidate_row_payload,
    enrich_evaluation_result,
    strategy_identity_from_payload,
    universe_identity_from_payload,
)
from app_module.recommendation.ml_postcalibration_handoff import (
    CalibrationProjectionStatusV1,
    CalibrationReceiptEventFactsV1,
    CalibrationReceiptStatusV1,
    RecommendationPostCalibrationHandoffSinkV1,
    RecommendationPostCalibrationHandoffV1,
    encode_candidate_identity_event_json_v1,
)
from app_module.recommendation.prepared_runtime_preparation import (
    build_prepared_runtime_input_v1,
    read_source_contract_bytes_for_preparation,
)
from app_module.recommendation.contracts import RecommendationRunEvidenceIdentity
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
    build_inference_provenance_with_source_evidence_v1,
    persist_inference_projection_receipt,
    read_inference_projection_receipt,
    verify_inference_provenance,
)


class _FinalizationFailure(Exception):
    """App-boundary wrapper that preserves the original typed error identity."""

    def __init__(self, error: StrategyEvaluationError) -> None:
        self.error = error
        super().__init__(error.message)


def _post_calibration_receipt_event_v1(
    payload_value: object,
    *,
    attempted: bool,
    persisted: bool = False,
    readback_verified: bool = False,
    identity_verified: bool = False,
    path: str = "",
    receipt_hash: str = "",
    receipt_created_at: str = "",
    error: str = "",
) -> CalibrationReceiptEventFactsV1:
    """將同次 receipt payload 凍結為 typed event facts。"""

    payload = payload_value if isinstance(payload_value, Mapping) else None
    candidate_value = payload.get("candidate_identity") if payload is not None else None
    candidate = candidate_value if isinstance(candidate_value, Mapping) else None
    candidate_id = str(candidate.get("candidate_id") or "") if candidate else ""
    candidate_identity_json = None
    if candidate is not None:
        try:
            candidate_identity_json = encode_candidate_identity_event_json_v1(candidate)
        except (TypeError, ValueError):
            candidate_identity_json = None

    inference_value = payload.get("inference_provenance") if payload is not None else None
    inference = inference_value if isinstance(inference_value, Mapping) else {}
    rows_value = payload.get("projections") if payload is not None else None
    rows = rows_value if isinstance(rows_value, Sequence) and not isinstance(
        rows_value, (str, bytes)
    ) else ()
    stock_codes = tuple(
        str(row.get("stock_code") or "")
        for row in rows
        if isinstance(row, Mapping)
    )
    cost_hash = payload.get("cost_scenario_hash") if payload is not None else None
    cost_id = inference.get("cost_scenario_id")
    return CalibrationReceiptEventFactsV1(
        payload_present=payload is not None,
        attempted=attempted,
        persisted=persisted,
        readback_verified=readback_verified,
        identity_verified=identity_verified,
        path=path,
        receipt_hash=receipt_hash,
        receipt_created_at=receipt_created_at,
        error=error,
        result_id=str(payload.get("result_id") or "") if payload is not None else "",
        decision_date=str(payload.get("decision_date") or "") if payload is not None else "",
        candidate_id=candidate_id,
        candidate_identity_json=candidate_identity_json,
        cost_scenario_hash=str(cost_hash or ""),
        cost_scenario_id=str(cost_id or ""),
        projected_stock_codes=stock_codes,
        projection_rows_sha256=str(
            payload.get("projection_rows_sha256") or ""
        ) if payload is not None else "",
        inference_source_hash=str(inference.get("inference_source_hash") or ""),
        inference_pit_hash=str(inference.get("inference_pit_hash") or ""),
        feature_rows_sha256=str(inference.get("feature_rows_sha256") or ""),
    )


def _assert_prepared_source_contract_bytes_unchanged_v1(
    inference_provenance: Mapping[str, Any],
    source_contract_evidence: Any,
) -> None:
    """在原 receipt 時點重用既有檔案驗證及錯誤語意。"""

    if source_contract_evidence is None:
        return
    verify_inference_provenance(
        inference_provenance,
        expected_decision_date=str(inference_provenance.get("decision_date") or ""),
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )


if TYPE_CHECKING:
    from app_module.recommendation.contracts import (
        RecommendationConfigSnapshot,
        RecommendationExecution,
    )
    from app_module.recommendation.execute import (
        RecommendationPostprocessFacts,
        RecommendationPostprocessInput,
    )
    from app_module.recommendation.live_source_identity import (
        LiveCalibrationSourceIdentityV1,
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


def _recommendation_evidence_identity(
    declared_identity: Mapping[str, object],
) -> RecommendationRunEvidenceIdentity | None:
    """Build typed evidence identity from explicit same-run config inputs."""

    def optional_text(key: str) -> str | None:
        value = declared_identity.get(key)
        if value is None or not str(value).strip():
            return None
        return cast(str, value)

    horizon_value = declared_identity.get("horizon_days")
    horizon_days = (
        cast(Decimal | int | str, horizon_value)
        if horizon_value is not None and str(horizon_value).strip()
        else None
    )
    values = (
        optional_text("cost_model_id"),
        optional_text("benchmark_id"),
        optional_text("industry_benchmark_id"),
        horizon_days,
    )
    if all(value is None for value in values):
        return None
    return RecommendationRunEvidenceIdentity(
        cost_model_id=values[0],
        benchmark_id=values[1],
        industry_benchmark_id=values[2],
        horizon_days=values[3],
    )


def _is_personal_use_policy(
    value: object,
) -> TypeGuard[RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2]:
    """只接受已知、不可替代的政策 DTO 類別。"""

    return type(value) is RecommendationPersonalUsePolicyV1 or type(
        value
    ) is RecommendationPersonalUsePolicyV2


class RecommendationService:
    """推薦服務類"""

    def __init__(
        self,
        config,
        industry_mapper: Optional[IndustryMapper] = None,
        market_data_provider: Optional[MarketFrameProvider] = None,
        regime_detector: Any | None = None,
        calibration_consumer: RecommendationCalibrationConsumer | None = None,
        pit_membership_reader: PITSectorMembershipReader | None = None,
        input_preparer: RecommendationInputPreparer | None = None,
        regime_service: Any | None = None,
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
            from app_module.decision_service_composition import build_industry_mapper

            self.industry_mapper = build_industry_mapper(
                config, constructor=IndustryMapper
            )
        else:
            self.industry_mapper = industry_mapper
        if input_preparer is None:
            raise ValueError(
                "RecommendationService 必須由 application composition 注入 input_preparer"
            )
        if (
            market_data_provider is not None
            and market_data_provider is not input_preparer.market_data_provider
        ):
            raise ValueError("market_data_provider 必須與 input_preparer 使用同一實例")
        self.recommendation_input_preparer = input_preparer
        self.market_data_provider = (
            market_data_provider
            if market_data_provider is not None
            else input_preparer.market_data_provider
        )
        if regime_service is not None:
            self.regime_service = regime_service
        elif regime_detector is not None:
            # Temporary app-side adapter for existing custom/test constructor callers.
            self.regime_service = RegimeService(
                config,
                regime_detector=regime_detector,
                use_persistent_history=True,
            )
        else:
            self.regime_service = RegimeService(
                config,
                use_persistent_history=True,
            )
        self.calibration_consumer = (
            calibration_consumer
            if calibration_consumer is not None
            else build_default_recommendation_calibration_consumer(config)
        )
        self._personal_use_policy: (
            RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2 | None
        ) = None
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
        self._r011_last_state_lock = RLock()
        self._r011_invocation_capture: dict[str, object] | None = None
        self._r026_post_calibration_handoff_sink: (
            RecommendationPostCalibrationHandoffSinkV1 | None
        ) = None

    def with_personal_use_policy(
        self,
        policy: RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2,
    ) -> "RecommendationService":
        """回傳綁定單次明示個人設定的新服務快照。

        個人設定不修改 global shadow pointer。每次呼叫都重讀設定檔，確認其
        revision/hash 仍與呼叫端持有的不可變快照相同，再建立全新的 calibration
        consumer；run context、投影、時鐘與 handoff 能力也不沿用原服務的可變狀態。
        """

        if not _is_personal_use_policy(policy):
            raise TypeError("policy 必須是已知 V1 或 V2 personal-use policy")
        verified_policy: RecommendationPersonalUsePolicyV1 | RecommendationPersonalUsePolicyV2
        if type(policy) is RecommendationPersonalUsePolicyV1 and policy.storage_path is None:
            expected_default = RecommendationPersonalUsePolicyV1.default_rule_only(
                policy.scope_id
            )
            if policy.to_dict() != expected_default.to_dict():
                raise ValueError("未持久化個人設定只允許固定 rule-only baseline")
            verified_policy = expected_default
        else:
            if policy.storage_path is None:
                raise ValueError("V2 個人設定必須由保存 bytes 驗證")
            verified_policy = load_personal_use_policy_snapshot(policy.storage_path)
            if verified_policy.to_dict() != policy.to_dict():
                raise ValueError("個人設定已變更，請重新讀取並確認最新 revision")
            verified_policy.validate_snapshot()

        invocation_service = copy(self)
        invocation_service._personal_use_policy = verified_policy
        invocation_service.last_calibration_projections = {}
        invocation_service.last_screening_matrix = []
        invocation_service.last_excluded_candidates_json = []
        invocation_service.last_why_not_payload_json = []
        invocation_service.last_liquidity_gate_payload_json = []
        invocation_service.last_exclusion_quality = "observed"
        invocation_service.last_exclusion_warnings_json = []
        invocation_service.last_run_context = {}
        invocation_service._personalization_execution_clocks = {}
        invocation_service._r011_last_state_lock = RLock()
        invocation_service._r011_invocation_capture = None
        invocation_service._r026_post_calibration_handoff_sink = None

        if verified_policy.mode == RULE_ONLY_MODE:
            invocation_service.calibration_consumer = None
        elif (
            verified_policy.mode == PERSONAL_CALIBRATED_PROBABILITY_MODE
            and verified_policy.storage_path is not None
        ):
            base_consumer = self.calibration_consumer
            if base_consumer is None:
                base_consumer = build_default_recommendation_calibration_consumer(
                    self.config
                )
            if type(base_consumer) is RecommendationCalibrationConsumer:
                invocation_service.calibration_consumer = RecommendationCalibrationConsumer(
                    pointer_path=verified_policy.storage_path,
                    feature_schema=base_consumer.feature_schema,
                    feature_registry_hash=base_consumer.feature_registry_hash,
                    data_root=base_consumer._loader._data_root,
                    expected_model_family=base_consumer.expected_model_family,
                    personal_use_policy=verified_policy,
                    personal_use_policy_bytes=verified_policy.storage_bytes,
                )
            else:
                # Custom test adapters are not personal artifact authorities.
                invocation_service.calibration_consumer = None
        else:
            raise ValueError("個人設定版本或模式不支援")
        return invocation_service

    def _reset_negative_evidence_buffers(self) -> None:
        self.last_screening_matrix = []
        self.last_excluded_candidates_json = []
        self.last_why_not_payload_json = []
        self.last_liquidity_gate_payload_json = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json = []
        self.last_run_context = {}
        self.last_calibration_projections = {}

    def _record_current_industry_mapping_use(self, usage: str) -> None:
        """封存本次 current-only 公司分類來源與實際用途。"""

        if type(usage) is not str or not usage:
            raise ValueError("current mapper usage 必須是非空字串")
        snapshot = self.last_run_context.get("industry_mapping_source_snapshot")
        if snapshot is None:
            warnings: list[str] = []
            source_contract: dict[str, Any] | None = None
            raw_contract: Any = None
            companies_frame = getattr(self.industry_mapper, "companies_df", None)
            frame_attrs = getattr(companies_frame, "attrs", None)
            if isinstance(frame_attrs, Mapping):
                raw_contract = frame_attrs.get(COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR)
            if isinstance(raw_contract, Mapping):
                try:
                    detached = json.loads(
                        json.dumps(
                            dict(raw_contract),
                            ensure_ascii=False,
                            sort_keys=True,
                            allow_nan=False,
                        )
                    )
                except (TypeError, ValueError):
                    warnings.append(
                        "company_registry_source_contract_not_json_snapshot"
                    )
                else:
                    source_contract = detached
                    contract_scope_is_current = (
                        detached.get("schema_version")
                        == COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION
                        and detached.get("scope") == "current_classification_only"
                        and detached.get("pit_eligible") is False
                        and detached.get("status") in {"captured", "unknown"}
                    )
                    if not contract_scope_is_current:
                        warnings.append(
                            "company_registry_source_contract_scope_unrecognized"
                        )
                    raw_warnings = detached.get("warnings")
                    if isinstance(raw_warnings, list) and all(
                        type(item) is str for item in raw_warnings
                    ):
                        warnings.extend(raw_warnings)
                    if detached.get("status") != "captured":
                        warnings.append("company_registry_source_status_unknown")
                    if (
                        detached.get("source_contract_sha256") is not None
                        and not _company_registry_source_contract_hash_matches(detached)
                    ):
                        warnings.append(
                            "company_registry_source_contract_hash_mismatch"
                        )
            else:
                warnings.append("company_registry_source_contract_missing")

            captured = (
                source_contract is not None
                and source_contract.get("schema_version")
                == COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION
                and source_contract.get("scope") == "current_classification_only"
                and source_contract.get("pit_eligible") is False
                and source_contract.get("status") == "captured"
                and _company_registry_source_contract_hash_matches(source_contract)
            )
            snapshot = {
                "result_id": str(self.last_run_context.get("result_id") or ""),
                "decision_at": None,
                "scope": "current_classification_only",
                "pit_eligible": False,
                "company_registry_source_status": "captured" if captured else "unknown",
                "industry_index_source_status": "not_observed",
                "usage": [],
                "company_registry_source_contract": source_contract,
                "company_registry_source_contract_sha256": (
                    source_contract.get("source_contract_sha256")
                    if source_contract is not None
                    else None
                ),
                "warnings": list(dict.fromkeys(warnings)),
                **(
                    {
                        "schema_version": "recommendation-company-registry-source-snapshot.v2",
                        "decision_date": self.last_run_context.get("as_of_date"),
                        "data_as_of_date": self.last_run_context.get("data_date") or None,
                        "source_id": self.last_run_context.get("source_id"),
                        "market_data_fingerprint": self.last_run_context.get(
                            "market_data_fingerprint"
                        ),
                    }
                    if self.last_run_context.get("personal_live_clock_schema")
                    == "recommendation-personal-live-clock.v1"
                    else {
                        "schema_version": "recommendation-company-registry-source-snapshot.v1",
                        "data_as_of_date": self.last_run_context.get("as_of_date"),
                    }
                ),
            }
            self.last_run_context["industry_mapping_source_snapshot"] = snapshot

        usages = snapshot.get("usage")
        if not isinstance(usages, list):
            raise TypeError("industry mapping source usage 必須是 list")
        if usage not in usages:
            usages.append(usage)
        if usage == "current_industry_index_performance_for_reason":
            snapshot["industry_index_source_status"] = "unknown"
            snapshot_warnings = snapshot.get("warnings")
            if not isinstance(snapshot_warnings, list):
                raise TypeError("industry mapping source warnings 必須是 list")
            warning = "industry_index_source_contract_unavailable_for_current_use"
            if warning not in snapshot_warnings:
                snapshot_warnings.append(warning)
            if "industry_index_source_observation" not in snapshot:
                observation: dict[str, Any] | None = None
                index_frame = getattr(self.industry_mapper, "industry_index_df", None)
                frame_attrs = getattr(index_frame, "attrs", None)
                raw_observation: Any = None
                if isinstance(frame_attrs, Mapping):
                    raw_observation = frame_attrs.get(
                        INDUSTRY_INDEX_SOURCE_OBSERVATION_ATTR
                    )
                if isinstance(raw_observation, Mapping):
                    try:
                        detached = json.loads(
                            json.dumps(
                                dict(raw_observation),
                                ensure_ascii=False,
                                sort_keys=True,
                                allow_nan=False,
                            )
                        )
                    except (TypeError, ValueError):
                        snapshot_warnings.append(
                            "industry_index_source_observation_not_json_snapshot"
                        )
                    else:
                        if (
                            isinstance(index_frame, pd.DataFrame)
                            and industry_index_source_observation_hash_matches(
                                detached, frame=index_frame
                            )
                        ):
                            observation = detached
                        else:
                            snapshot_warnings.append(
                                "industry_index_source_observation_mismatch_for_current_use"
                            )
                else:
                    snapshot_warnings.append(
                        "industry_index_source_observation_missing_for_current_use"
                    )
                snapshot["industry_index_source_observation"] = observation
                snapshot["industry_index_source_observation_sha256"] = (
                    observation.get("observation_sha256")
                    if observation is not None
                    else None
                )
                # This is the reader's observation clock only.  No source
                # publication/availability timestamp is inferred from it.
                snapshot["industry_index_source_time_status"] = "unknown"
                snapshot["industry_index_source_available_at"] = None
                snapshot["industry_index_source_published_at"] = None
                source_time_warning = (
                    "industry_index_source_capture_time_unknown_for_current_use"
                )
                if source_time_warning not in snapshot_warnings:
                    snapshot_warnings.append(source_time_warning)
        self._refresh_current_industry_mapping_snapshot_hash(snapshot)

    def _finalize_current_industry_mapping_snapshot(self) -> None:
        """將 current mapping 快照綁到最後發布的同次執行時鐘與結果。"""

        snapshot = self.last_run_context.get("industry_mapping_source_snapshot")
        if not isinstance(snapshot, dict):
            return
        snapshot["result_id"] = str(self.last_run_context.get("result_id") or "")
        if snapshot.get("schema_version") == "recommendation-company-registry-source-snapshot.v2":
            snapshot["decision_date"] = self.last_run_context.get("as_of_date")
            snapshot["data_as_of_date"] = (
                self.last_run_context.get("data_date") or None
            )
            snapshot["source_id"] = self.last_run_context.get("source_id")
            snapshot["market_data_fingerprint"] = self.last_run_context.get(
                "market_data_fingerprint"
            )
        else:
            snapshot["data_as_of_date"] = self.last_run_context.get("as_of_date")
        snapshot["decision_at"] = self.last_run_context.get("decision_at") or None
        if snapshot["decision_at"] is None:
            warnings = snapshot.get("warnings")
            if not isinstance(warnings, list):
                raise TypeError("industry mapping source warnings 必須是 list")
            warning = "recommendation_decision_clock_unavailable_for_current_mapper_use"
            if warning not in warnings:
                warnings.append(warning)
        self._refresh_current_industry_mapping_snapshot_hash(snapshot)

    @staticmethod
    def _refresh_current_industry_mapping_snapshot_hash(
        snapshot: dict[str, Any],
    ) -> None:
        snapshot.pop("snapshot_sha256", None)
        canonical = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        snapshot["snapshot_sha256"] = "sha256:" + hashlib.sha256(canonical).hexdigest()

    def _apply_recommendation_calibration(
        self,
        recommendations: List[RecommendationDTO],
        *,
        selected_items: Sequence[RecommendationItem] | None = None,
        decision_date: str,
        selection_authority: str = "rule_top_n",
        selection_score_kind: str = "rule_total_score",
        selection_percentile_kind: str = "rule_percentile",
        top_n_changed_by_model: bool = False,
    ) -> LiveCalibrationSourceIdentityV1 | None:
        """Inject the verified active pointer projection into the normal DTO path.

        This is deliberately a read-only adapter.  If the pointer, artifact,
        canonical feature vector, or data quality is unavailable, each row
        remains rule-only and the existing recommendation score is untouched.
        """

        consumer = self.calibration_consumer
        invocation_capture = self._r011_invocation_capture
        post_calibration_sink = self._r026_post_calibration_handoff_sink
        receipt_event_facts: list[CalibrationReceiptEventFactsV1] = []
        active_cost_scenario: RecommendationCostScenario | None = None
        active_identity_for_snapshot: dict[str, Any] = {}

        def publish_post_calibration_handoff(
            *,
            consumer_configured: bool,
            attempted: bool,
            projection_status: CalibrationProjectionStatusV1 | None = None,
            receipt_status: CalibrationReceiptStatusV1 | None = None,
            receipt_error_detail: str | None = None,
        ) -> None:
            if type(post_calibration_sink) is not RecommendationPostCalibrationHandoffSinkV1:
                return
            event = receipt_event_facts[-1] if receipt_event_facts else None
            post_calibration_sink.publish(
                RecommendationPostCalibrationHandoffV1(
                    consumer_configured=consumer_configured,
                    attempted=attempted,
                    projection_status=projection_status,
                    receipt_status=receipt_status,
                    receipt_error_detail=receipt_error_detail,
                    receipt_event=event,
                )
            )

        personal_policy = getattr(self, "_personal_use_policy", None)
        if _is_personal_use_policy(personal_policy):
            # 不讓重用的 service 狀態把前一個 invocation 的來源快照帶入本次結果。
            self.last_run_context.pop("personal_probability_baseline_inputs", None)
            self.last_run_context["personal_use_policy"] = personal_policy.to_dict()
            self.last_run_context["personal_use_requested_mode"] = personal_policy.mode
            self.last_run_context["personal_use_effective_mode"] = RULE_ONLY_MODE
            policy_clock_valid = personal_policy.applicable_at(
                str(self.last_run_context.get("decision_at") or "")
            )
            if personal_policy.mode == RULE_ONLY_MODE or not policy_clock_valid:
                _withdraw_personal_calibration_fields(recommendations)
                self.last_calibration_projections = {}
                self.last_run_context["calibration_projection_status"] = "rule_only"
                if not policy_clock_valid:
                    self.last_run_context.setdefault("warnings", []).append(
                        "personal_use_policy_not_confirmed_by_decision_clock_fail_closed"
                    )
                publish_post_calibration_handoff(
                    consumer_configured=consumer is not None,
                    attempted=False,
                )
                return None

        if isinstance(invocation_capture, dict):
            invocation_capture["calibration_consumer_configured"] = consumer is not None
        if consumer is None:
            if _is_personal_use_policy(personal_policy):
                _withdraw_personal_calibration_fields(recommendations)
                self.last_calibration_projections = {}
                self.last_run_context["calibration_projection_status"] = "unavailable"
                self.last_run_context.setdefault("warnings", []).append(
                    "personal_calibration_consumer_unavailable_fail_closed"
                )
            publish_post_calibration_handoff(
                consumer_configured=False,
                attempted=False,
            )
            return None
        if not decision_date or not recommendations:
            publish_post_calibration_handoff(
                consumer_configured=True,
                attempted=False,
            )
            return None
        if isinstance(invocation_capture, dict):
            invocation_capture["calibration_attempted"] = True
        # The R026 source scope is transient and local to this calibration
        # invocation.  It is intentionally independent of result_id and the
        # legacy staged_invocation_id, and is never written to provenance.
        source_scope_id = f"recommendation-live-{uuid4().hex}"
        live_source_identity: LiveCalibrationSourceIdentityV1 | None = None
        source_contract_evidence: Any = None
        prepared_runtime_capability: Any = None
        prepared_runtime_enabled = False
        handoff_projection_status: CalibrationProjectionStatusV1 | None = None
        receipt_error_detail: str | None = None
        try:
            from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
            from data_module.source_revision_evidence_collector import (
                collect_source_revision_evidence_v1,
            )
            from data_module.contracts.source_revision import (
                SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
                ValidatedSourceEvidenceV1,
            )
            from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
            from ml_module.historical_feature_builder import HistoricalFeatureBuilder

            db_file = getattr(self.config, "db_file", None)
            if db_file is None:
                raise FileNotFoundError("recommendation calibration source database is not configured")
            provider = MLHistoricalSnapshotProvider(db_file)
            cutoff_date = date.fromisoformat(decision_date[:10])
            source_symbols = tuple(
                sorted({str(item.stock_code) for item in recommendations})
            )
            source_database_path = provider.database_path
            history_start_date = str(
                getattr(self.config, "default_start_date", "2014-01-01")
            )[:10]
            with provider.open_read_lease() as lease:
                source_evidence_before = collect_source_revision_evidence_v1(
                    database_path=source_database_path,
                    scope_id=source_scope_id,
                    cutoff_date=cutoff_date,
                    symbols=source_symbols,
                    explicit_path=None,
                )
                if type(source_evidence_before) is not ValidatedSourceEvidenceV1:
                    raise TypeError("source revision collector returned an invalid aggregate")
                if (
                    source_evidence_before.schema_version
                    != SOURCE_REVISION_EVIDENCE_SCHEMA_V1
                    or source_evidence_before.scope_id != source_scope_id
                    or source_evidence_before.cutoff_date != cutoff_date
                ):
                    raise RuntimeError(
                        "source revision evidence identity mismatch before calibration"
                    )

                snapshot = lease.load(
                    decision_date=decision_date,
                    history_start_date=history_start_date,
                    symbols=source_symbols,
                    industry_index_names=(),
                )
                feature_builder = HistoricalFeatureBuilder(
                    CORE_LONG_HISTORY_FEATURE_REGISTRY
                )
                rows = feature_builder.compute(
                    snapshot,
                    industry_index_name_by_symbol={},
                )
                source_evidence_after = collect_source_revision_evidence_v1(
                    database_path=source_database_path,
                    scope_id=source_scope_id,
                    cutoff_date=cutoff_date,
                    symbols=source_symbols,
                    explicit_path=None,
                )
                if type(source_evidence_after) is not ValidatedSourceEvidenceV1:
                    raise TypeError("source revision collector returned an invalid aggregate")
                if (
                    source_evidence_after.schema_version
                    != SOURCE_REVISION_EVIDENCE_SCHEMA_V1
                    or source_evidence_after.scope_id != source_scope_id
                    or source_evidence_after.cutoff_date != cutoff_date
                ):
                    self.last_run_context.setdefault("warnings", []).append(
                        "calibration_source_revision_identity_changed_fail_closed"
                    )
                    raise RuntimeError(
                        "source revision evidence identity mismatch after calibration"
                    )
                if source_evidence_before.digest_sha256 != source_evidence_after.digest_sha256:
                    self.last_run_context.setdefault("warnings", []).append(
                        "calibration_source_revision_changed_fail_closed"
                    )
                    raise RuntimeError("source revision evidence changed during calibration")

                feature_values = {
                    row.symbol: tuple(value for _, value in row.values)
                    for row in rows
                }
                provenance_rows = [
                    {
                        "symbol": row.symbol,
                        "decision_date": getattr(
                            row, "decision_date", snapshot.decision_date
                        ),
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
                active_identity_value = (
                    active_identity_provider(decision_date=decision_date)
                    if callable(active_identity_provider)
                    else None
                )
                active_identity = (
                    active_identity_value
                    if isinstance(active_identity_value, Mapping)
                    else {}
                )
                active_identity_for_snapshot = dict(active_identity)
                if (
                    type(consumer) is RecommendationCalibrationConsumer
                    and selected_items is not None
                    and len(selected_items) == len(recommendations)
                    and bool(self.last_run_context.get("result_id"))
                ):
                    decision_clock_text = str(
                        self.last_run_context.get("decision_at") or ""
                    )
                    try:
                        prepared_decision_clock = _STANDARD_DATETIME.fromisoformat(
                            decision_clock_text
                        )
                    except ValueError:
                        prepared_decision_clock = None
                    if (
                        prepared_decision_clock is not None
                        and prepared_decision_clock.tzinfo is not None
                    ):
                        if isinstance(active_identity_value, Mapping) and active_identity:
                            capability_resolver = getattr(
                                consumer,
                                "resolve_invocation_projection_capability",
                                None,
                            )
                            if callable(capability_resolver):
                                prepared_runtime_capability = capability_resolver(
                                    invocation_scope_id=source_scope_id,
                                    decision_date=decision_date,
                                    expected_identity=active_identity,
                                )
                                prepared_runtime_enabled = (
                                    prepared_runtime_capability is not None
                                )
                        elif active_identity_value is None:
                            no_model_resolver = getattr(
                                consumer,
                                "resolve_invocation_no_model_projection_capability_v1",
                                None,
                            )
                            if callable(no_model_resolver):
                                prepared_runtime_capability = no_model_resolver(
                                    invocation_scope_id=source_scope_id,
                                    decision_date=decision_date,
                                    expected_identity={},
                                )
                                prepared_runtime_enabled = (
                                    prepared_runtime_capability is not None
                                )
                active_cost_provider = getattr(consumer, "active_cost_scenario", None)
                resolved_active_cost_scenario = (
                    active_cost_provider(decision_date=decision_date)
                    if callable(active_cost_provider)
                    else None
                )
                active_cost_scenario = (
                    resolved_active_cost_scenario
                    if type(resolved_active_cost_scenario) is RecommendationCostScenario
                    else None
                )
                active_cost_hash = active_identity.get("cost_scenario_hash")
                active_cost_id = active_identity.get("cost_scenario_id")
                active_cost_version = active_identity.get("cost_scenario_version")
                if active_cost_scenario is not None:
                    active_cost_hash = getattr(
                        active_cost_scenario, "scenario_hash", None
                    )
                    active_cost_id = getattr(active_cost_scenario, "scenario_id", None)
                    active_cost_version = getattr(
                        active_cost_scenario, "scenario_version", None
                    )
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
                source_contract_binding = getattr(
                    self.config, "recommendation_source_contract_binding", None
                )
                if prepared_runtime_enabled:
                    contract_bytes = read_source_contract_bytes_for_preparation(
                        source_contract_binding
                    )
                    inference_provenance, source_contract_evidence = (
                        build_inference_provenance_with_source_evidence_v1(
                            snapshot=snapshot,
                            feature_rows=provenance_rows,
                            feature_schema=inference_feature_schema,
                            feature_registry_hash=inference_feature_registry_hash,
                            feature_builder_schema_hash=feature_builder.load_contract.schema_hash,
                            source_database=str(provider.database_path),
                            history_start_date=history_start_date,
                            cost_scenario_hash=(
                                str(active_cost_hash) if active_cost_hash else None
                            ),
                            cost_scenario_id=(
                                str(active_cost_id) if active_cost_id else None
                            ),
                            cost_scenario_version=(
                                str(active_cost_version) if active_cost_version else None
                            ),
                            probability_transform_id=PROBABILITY_TRANSFORM_ID,
                            source_contract_binding=source_contract_binding,
                            source_contract_file_bytes=contract_bytes,
                        )
                    )
                else:
                    inference_provenance = build_inference_provenance(
                        snapshot=snapshot,
                        feature_rows=provenance_rows,
                        feature_schema=inference_feature_schema,
                        feature_registry_hash=inference_feature_registry_hash,
                        feature_builder_schema_hash=feature_builder.load_contract.schema_hash,
                        source_database=str(provider.database_path),
                        history_start_date=history_start_date,
                        cost_scenario_hash=(
                            str(active_cost_hash) if active_cost_hash else None
                        ),
                        cost_scenario_id=(
                            str(active_cost_id) if active_cost_id else None
                        ),
                        cost_scenario_version=(
                            str(active_cost_version) if active_cost_version else None
                        ),
                        probability_transform_id=PROBABILITY_TRANSFORM_ID,
                        source_contract_binding=source_contract_binding,
                    )

                # Read all active identity/cost baselines inside the lease so
                # the same source observation spans the complete projection.
                after_cost_baseline = None
                baseline_provider = getattr(consumer, "active_after_cost_baseline", None)
                if callable(baseline_provider):
                    after_cost_baseline = baseline_provider(decision_date=decision_date)
                after_cost_rule_probability: dict[str, int] = {}
                after_cost_rule_baseline_ids: dict[str, str] = {}
                if after_cost_baseline is not None:
                    baseline_id, baseline_probability = after_cost_baseline
                    after_cost_rule_probability = {
                        str(item.stock_code): baseline_probability
                        for item in recommendations
                    }
                    after_cost_rule_baseline_ids = {
                        str(item.stock_code): baseline_id
                        for item in recommendations
                    }
                rule_probability = {
                    str(item.stock_code): 5_000 for item in recommendations
                }
                percentiles = {
                    str(item.stock_code): int(item.score_percentile_bp)
                    for item in recommendations
                    if item.score_percentile_bp is not None
                }
                if prepared_runtime_enabled:
                    from app_module.recommendation.prepared_runtime_projector import (
                        project_prepared_ml_runtime_input_v1,
                    )

                    runtime_input = build_prepared_runtime_input_v1(
                        selected_items=selected_items or (),
                        recommendations=recommendations,
                        feature_rows=rows,
                        feature_builder=feature_builder,
                        snapshot=snapshot,
                        capability=prepared_runtime_capability,
                        active_identity=active_identity,
                        result_id=str(self.last_run_context.get("result_id") or ""),
                        history_start_date=history_start_date,
                        invocation_scope_id=source_scope_id,
                        decision_clock=_STANDARD_DATETIME.fromisoformat(
                            str(self.last_run_context.get("decision_at") or "")
                        ),
                        inference_provenance=inference_provenance,
                        source_contract_evidence=source_contract_evidence,
                        rule_probability_by_symbol=rule_probability,
                        after_cost_rule_probability_by_symbol=after_cost_rule_probability,
                        after_cost_rule_baseline_id_by_symbol=after_cost_rule_baseline_ids,
                        selection_authority=selection_authority,
                        selection_score_kind=selection_score_kind,
                        selection_percentile_kind=selection_percentile_kind,
                        top_n_changed_by_model=top_n_changed_by_model,
                    )
                    projections = dict(
                        project_prepared_ml_runtime_input_v1(runtime_input)
                    )
                elif _is_personal_use_policy(personal_policy):
                    # 個人採用必須經過 fresh same-bytes invocation capability。
                    # capability 缺失時不退回會重載 mutable candidate 的 legacy path。
                    projections = {
                        symbol: RecommendationCalibrationProjection.unavailable(
                            stock_code=symbol,
                            warning="personal_invocation_model_capability_unavailable_fail_closed",
                            ranking_percentile_bp=percentiles.get(symbol),
                        )
                        for symbol in feature_values
                    }
                else:
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
                source_evidence_after_projection: ValidatedSourceEvidenceV1 | None = None
                try:
                    candidate_evidence_after_projection = collect_source_revision_evidence_v1(
                        database_path=source_database_path,
                        scope_id=source_scope_id,
                        cutoff_date=cutoff_date,
                        symbols=source_symbols,
                        explicit_path=None,
                    )
                    if type(candidate_evidence_after_projection) is not ValidatedSourceEvidenceV1:
                        raise TypeError(
                            "source revision collector returned an invalid post-projection aggregate"
                        )
                    if (
                        candidate_evidence_after_projection.schema_version
                        != SOURCE_REVISION_EVIDENCE_SCHEMA_V1
                        or candidate_evidence_after_projection.scope_id != source_scope_id
                        or candidate_evidence_after_projection.cutoff_date != cutoff_date
                    ):
                        raise RuntimeError(
                            "source revision evidence identity mismatch after projection"
                        )
                    if (
                        candidate_evidence_after_projection != source_evidence_before
                        or candidate_evidence_after_projection != source_evidence_after
                        or candidate_evidence_after_projection.digest_sha256
                        != source_evidence_before.digest_sha256
                        or candidate_evidence_after_projection.digest_sha256
                        != source_evidence_after.digest_sha256
                    ):
                        raise RuntimeError(
                            "source revision evidence changed during model projection"
                        )
                    source_evidence_after_projection = candidate_evidence_after_projection
                except Exception:
                    # The post-projection sidecar sample is shadow-only.  Its
                    # failure suppresses identity publication, not the legacy
                    # projection or receipt path.
                    source_evidence_after_projection = None
                lease.assert_unchanged()
                # This invocation-local shadow value joins the actual captured
                # rows, the validated sidecar aggregate, and the completed
                # same-connection lease check.  It is deliberately not handed
                # to the consumer, receipt, legacy capture, or provenance yet.
                try:
                    from app_module.recommendation.historical_snapshot_custody import (
                        HistoricalRawSnapshotQueryScopeV1,
                    )
                    from app_module.recommendation.live_source_identity import (
                        SQLiteReadLeaseObservationV1,
                        compose_live_calibration_source_identity_v1,
                    )
                    from data_module.ml_historical_snapshot_provider import (
                        HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
                    )

                    provider_contract_id = snapshot.provider_contract_id
                    if provider_contract_id != HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1:
                        raise ValueError("provider snapshot has no approved contract ID")
                    custody_query_scope = HistoricalRawSnapshotQueryScopeV1(
                        source_id=provider_contract_id,
                        decision_date=cutoff_date,
                        history_start_date=date.fromisoformat(history_start_date),
                        symbols=source_symbols,
                        industry_index_names=(),
                    )
                    if source_evidence_after_projection is None:
                        raise ValueError(
                            "post-projection source evidence is unavailable"
                        )
                    live_source_identity = compose_live_calibration_source_identity_v1(
                        snapshot=snapshot,
                        query_scope=custody_query_scope,
                        source_evidence_before=source_evidence_before,
                        source_evidence_after=source_evidence_after_projection,
                        sqlite_lease_observation=SQLiteReadLeaseObservationV1(
                            provider_contract_id=provider_contract_id,
                            scope_id=source_scope_id,
                        ),
                    )
                except Exception:
                    # Shadow capture is observational only.  A missing or
                    # invalid shadow fact must not change the existing model
                    # projection or receipt path.
                    live_source_identity = None
        except Exception as exc:  # noqa: BLE001 - consumer must fail closed
            self.last_calibration_projections = {}
            for key in (
                "calibration_rule_baseline_id",
                "calibration_after_cost_baseline_id",
                "calibration_projection_source",
                "calibration_projection_rows",
                "calibration_projection_receipt",
                "calibration_projection_receipt_created_at",
                "calibration_projection_receipt_error",
                "calibration_projection_receipt_error_detail",
                "personalization_scope",
                "personalization_delivery_scope",
            ):
                self.last_run_context.pop(key, None)
            self.last_run_context["calibration_projection_status"] = "unavailable"
            self.last_run_context["calibration_projection_receipt_status"] = "unavailable"
            self.last_run_context["calibration_feature_source_error_detail"] = {
                "error_type": type(exc).__name__, "reason": str(exc)[:1000],
                "cutoff_date": decision_date,
                "source_database": str(getattr(self.config, "db_file", "")),
                "historical_pit_relaxed": False,
            }
            self.last_run_context.setdefault("warnings", []).append(
                f"calibration_feature_source_unavailable:{type(exc).__name__}"
            )
            for recommendation in recommendations:
                recommendation.ranking_score_bp = None
                recommendation.calibrated_probability_bp = None
                recommendation.calibrated_probability_status = "unavailable"
                recommendation.after_cost_profit_probability_bp = None
                recommendation.after_cost_profit_probability_status = "unavailable"
                recommendation.evidence_confidence = ""
                recommendation.sample_size = None
                recommendation.cost_basis_bp = None
                recommendation.calibration_model_version = ""
                recommendation.calibration_dataset_version = ""
                recommendation.calibration_horizon = ""
                recommendation.calibration_status = "unavailable"
                recommendation.calibration_source = "recommendation_calibration_consumer"
                recommendation.calibration_warnings = ["feature_vector_source_unavailable_fail_closed"]
                recommendation.calibration_source_trace = []
                recommendation.calibration_probability_transform_id = ""
                recommendation.calibration_probability_baseline_id = ""
                recommendation.calibration_probability_baseline_kind = ""
                recommendation.calibration_probability_baseline_probability_bp = None
                recommendation.calibration_raw_probability_bp = None
                recommendation.calibration_raw_after_cost_probability_bp = None
                recommendation.calibration_provenance = {}
            handoff_projection_status = CalibrationProjectionStatusV1.UNAVAILABLE
            publish_post_calibration_handoff(
                consumer_configured=True,
                attempted=True,
                projection_status=handoff_projection_status,
            )
            return None

        self.last_calibration_projections = dict(projections)
        if _is_personal_use_policy(personal_policy):
            warning_values = self.last_run_context.setdefault("warnings", [])
            if not isinstance(warning_values, list) or any(
                type(item) is not str for item in warning_values
            ):
                raise TypeError("personal calibration context warnings 必須是 str list")
            for projection in projections.values():
                if projection.status == "active_candidate":
                    continue
                for warning in projection.warnings:
                    if type(warning) is not str or not warning.strip():
                        raise TypeError(
                            "personal fallback projection warning 必須是非空 str"
                        )
                    if warning not in warning_values:
                        warning_values.append(warning)
        handoff_projection_status = (
            CalibrationProjectionStatusV1.ACTIVE_CANDIDATE
            if any(item.status == "active_candidate" for item in projections.values())
            else CalibrationProjectionStatusV1.RULE_ONLY
        )
        self.last_run_context["calibration_projection_status"] = (
            handoff_projection_status.value
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
                source_contract_evidence=source_contract_evidence,
                result_id=(
                    str(self.last_run_context.get("result_id") or "") or None
                ),
                selection_authority=selection_authority,
                selection_score_kind=selection_score_kind,
                selection_percentile_kind=selection_percentile_kind,
                top_n_changed_by_model=top_n_changed_by_model,
                invocation_capture=invocation_capture,
                receipt_event_out=receipt_event_facts,
            )
        except (OSError, TypeError, ValueError, RecommendationProvenanceError) as exc:
            receipt_path = None
            receipt_error_detail = str(exc)
            if receipt_event_facts:
                receipt_event_facts[-1] = replace(
                    receipt_event_facts[-1],
                    error=f"{type(exc).__name__}: {exc}",
                )
            else:
                receipt_event_facts.append(
                    _post_calibration_receipt_event_v1(
                        None,
                        attempted=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
            if isinstance(invocation_capture, dict):
                receipt_capture = invocation_capture.setdefault("receipt", {})
                if isinstance(receipt_capture, dict):
                    receipt_capture["error"] = f"{type(exc).__name__}: {exc}"
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
            handoff_projection_status = CalibrationProjectionStatusV1.UNAVAILABLE
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
        if _is_personal_use_policy(personal_policy):
            delivered_codes = tuple(
                recommendation.stock_code for recommendation in recommendations
            )
            selected_codes = (
                tuple(item.stock_code for item in selected_items)
                if selected_items is not None
                else delivered_codes
            )
            delivery_matches_selection = delivered_codes == selected_codes
            candidate = personal_policy.candidate
            candidate_id = (
                candidate.candidate_id
                if type(candidate) is PersonalCalibrationCandidateV1
                else None
            )

            def is_active_projection(code: str) -> bool:
                projection = projections.get(code)
                probability = (
                    getattr(projection, "calibrated_probability_bp", None)
                    if projection is not None
                    else None
                )
                return (
                    projection is not None
                    and projection.status == "active_candidate"
                    and projection.calibrated_probability_status == "active_effective"
                    and type(probability) is int
                    and 0 <= probability <= 10_000
                    and projection.model_version == candidate_id
                )

            active_codes = tuple(
                code for code in delivered_codes if is_active_projection(code)
            )
            fallback_codes = tuple(
                code
                for code in delivered_codes
                if code in projections
                and _is_explicit_personal_rule_only_projection(projections[code])
            )
            delivery_is_classified = (
                delivery_matches_selection
                and len(set(delivered_codes)) == len(delivered_codes)
                and len(set(active_codes)) == len(active_codes)
                and len(set(fallback_codes)) == len(fallback_codes)
                and not (set(active_codes) & set(fallback_codes))
                and set(active_codes) | set(fallback_codes) == set(delivered_codes)
            )
            effective_model = bool(active_codes) and delivery_matches_selection
            mixed_delivery = (
                delivery_is_classified and bool(active_codes) and bool(fallback_codes)
            )
            all_delivered_active = (
                delivery_is_classified
                and bool(active_codes)
                and len(active_codes) == len(delivered_codes)
            )
            self.last_run_context["personal_use_effective_mode"] = (
                PERSONAL_CALIBRATED_PROBABILITY_MODE
                if effective_model
                else RULE_ONLY_MODE
            )
            # 只有真實個人模型投影已連到成功寫入、讀回及候選 identity 驗證的
            # receipt 時，才封存送入同次 projector 的固定基準來源。這裡不把
            # rule score 或模型 projection 誤標為 rule-model probability。
            if (
                effective_model
                and receipt_path is not None
                and receipt_event_facts
                and self.last_run_context["personal_use_effective_mode"]
                == PERSONAL_CALIBRATED_PROBABILITY_MODE
            ):
                receipt_facts = receipt_event_facts[-1]
                projected_codes = receipt_facts.projected_stock_codes
                code_set = set(projected_codes)
                after_cost_ids = dict(after_cost_rule_baseline_ids)
                after_cost_values = dict(after_cost_rule_probability)
                after_cost_supplied = bool(after_cost_ids) or bool(after_cost_values)
                after_cost_valid = (
                    not after_cost_supplied
                    or (
                        set(after_cost_ids) == set(after_cost_values) == code_set
                        and len(set(after_cost_ids.values())) == 1
                        and all(
                            type(code) is str
                            and code
                            and type(after_cost_ids[code]) is str
                            and bool(after_cost_ids[code])
                            and type(after_cost_values[code]) is int
                            and 0 <= after_cost_values[code] <= 10_000
                            for code in after_cost_values
                        )
                    )
                )
                if (
                    receipt_facts.persisted
                    and receipt_facts.readback_verified
                    and receipt_facts.identity_verified
                    and not receipt_facts.error
                    and receipt_facts.result_id
                    == str(self.last_run_context.get("result_id") or "")
                    and receipt_facts.decision_date == decision_date
                    and set(rule_probability) == code_set
                    and all(
                        type(code) is str
                        and bool(code)
                        and type(probability) is int
                        and probability == 5_000
                        for code, probability in rule_probability.items()
                    )
                    and len(projected_codes) == len(code_set)
                    and bool(code_set)
                    and type(receipt_facts.receipt_hash) is str
                    and type(receipt_facts.projection_rows_sha256) is str
                    and type(receipt_facts.cost_scenario_hash) is str
                    and after_cost_valid
                ):
                    after_cost_map: dict[str, int | None] = {
                        code: after_cost_values.get(code) for code in projected_codes
                    }
                    after_cost_id = (
                        next(iter(after_cost_ids.values()))
                        if after_cost_ids
                        else None
                    )
                    if len(set(after_cost_ids.values())) > 1:
                        after_cost_valid = False
                    scenario_payload: dict[str, Any] | None = None
                    active_lineage = active_identity_for_snapshot.get(
                        "probability_lineage"
                    )
                    active_lineage_entries = (
                        [
                            entry
                            for entry in active_lineage
                            if isinstance(entry, Mapping)
                            and entry.get("kind") == "active_model"
                            and entry.get("candidate_id") == candidate_id
                        ]
                        if isinstance(active_lineage, (list, tuple))
                        else []
                    )
                    active_lineage_scenario = (
                        active_lineage_entries[0].get("cost_scenario")
                        if len(active_lineage_entries) == 1
                        else None
                    )
                    scenario_valid = (
                        type(active_cost_scenario) is RecommendationCostScenario
                        and len(active_lineage_entries) == 1
                        and active_cost_scenario.scenario_hash
                        == receipt_facts.cost_scenario_hash
                        and active_lineage_entries[0].get("cost_scenario_hash")
                        == active_cost_scenario.scenario_hash
                        and active_lineage_entries[0].get("cost_scenario_id")
                        == active_cost_scenario.scenario_id
                        and active_lineage_entries[0].get("cost_scenario_version")
                        == active_cost_scenario.scenario_version
                        and isinstance(active_lineage_scenario, Mapping)
                    )
                    if (
                        scenario_valid
                        and active_cost_scenario is not None
                        and isinstance(active_lineage_scenario, Mapping)
                    ):
                        scenario_payload = active_cost_scenario.to_dict(include_hash=True)
                        scenario_valid = (
                            scenario_payload.get("scenario_hash")
                            == receipt_facts.cost_scenario_hash
                            and dict(active_lineage_scenario) == scenario_payload
                        )
                    for code in projected_codes:
                        projection = projections.get(code)
                        if projection is None or projection.stock_code != code:
                            scenario_valid = False
                            continue
                        if code in active_codes and active_cost_scenario is not None:
                            scenario_valid = scenario_valid and (
                                projection.cost_scenario_id
                                == active_cost_scenario.scenario_id
                                and projection.cost_scenario_version
                                == active_cost_scenario.scenario_version
                                and projection.cost_scenario_hash
                                == active_cost_scenario.scenario_hash
                                and type(projection.cost_basis) is str
                                and bool(projection.cost_basis)
                                and projection.cost_basis_bp
                                == (
                                    None
                                    if active_cost_scenario.is_estimated
                                    else active_cost_scenario.fixed_round_trip_cost_bp
                                )
                            )
                        elif code in fallback_codes and active_cost_scenario is not None:
                            # 缺少該列 feature 的明確 rule-only fallback 沒有模型成本列；
                            # 若它帶成本 identity，仍須與同次 lease 一致。
                            projection_hash = projection.cost_scenario_hash
                            scenario_valid = scenario_valid and (
                                projection_hash is None
                                or projection_hash == active_cost_scenario.scenario_hash
                            )
                    active_set = set(active_codes)
                    active_after_cost_ids = {
                        code: after_cost_ids[code]
                        for code in active_codes
                        if code in after_cost_ids
                    }
                    active_after_cost_values = {
                        code: after_cost_values[code]
                        for code in active_codes
                        if code in after_cost_values
                    }
                    active_after_cost_available = (
                        after_cost_supplied
                        and after_cost_valid
                        and set(active_after_cost_ids) == active_set
                        and set(active_after_cost_values) == active_set
                        and len(set(active_after_cost_ids.values())) == 1
                        and all(
                            type(value) is int and 0 <= value <= 10_000
                            for value in active_after_cost_values.values()
                        )
                    )
                    active_after_cost_id = (
                        next(iter(active_after_cost_ids.values()))
                        if active_after_cost_available
                        else None
                    )
                    projected_universe_matches = (
                        set(projected_codes) == set(delivered_codes)
                        and len(projected_codes) == len(delivered_codes)
                    )
                    if (
                        after_cost_valid
                        and scenario_valid
                        and scenario_payload is not None
                        and (all_delivered_active or mixed_delivery)
                        and projected_universe_matches
                    ):
                        self.last_run_context[
                            "personal_probability_baseline_inputs"
                        ] = {
                            "schema_version": "recommendation-personal-probability-baseline-inputs.v3",
                            "result_id": str(self.last_run_context.get("result_id") or ""),
                            "decision_at": str(
                                self.last_run_context.get("decision_at") or ""
                            ),
                            "decision_date": decision_date,
                            "projected_stock_codes": list(projected_codes),
                            "delivered_stock_codes": list(delivered_codes),
                            "model_active_stock_codes": list(active_codes),
                            "rule_only_fallback_stock_codes": list(fallback_codes),
                            "delivered_count": len(delivered_codes),
                            "model_active_count": len(active_codes),
                            "fallback_count": len(fallback_codes),
                            "model_coverage_bp": (
                                len(active_codes) * 10_000 // len(delivered_codes)
                            ),
                            "upside_baseline_kind": "fixed_null_benchmark_50pct",
                            "upside_baseline_id": NULL_BENCHMARK_BASELINE_ID,
                            "upside_probability_bp_by_symbol": {
                                code: rule_probability[code] for code in active_codes
                            },
                            "after_cost_baseline_status": (
                                "available" if active_after_cost_available else "unavailable"
                            ),
                            "after_cost_baseline_id": active_after_cost_id,
                            "after_cost_probability_bp_by_symbol": (
                                active_after_cost_values
                                if active_after_cost_available
                                else {code: None for code in active_codes}
                            ),
                            "cost_scenario": scenario_payload,
                        }
                    elif not (all_delivered_active or mixed_delivery) or not scenario_valid:
                        self.last_run_context.setdefault("warnings", []).append(
                            "personal_probability_baseline_snapshot_unavailable_fail_closed"
                        )
                else:
                    self.last_run_context.setdefault("warnings", []).append(
                        "personal_probability_baseline_snapshot_unavailable_fail_closed"
                    )
        handoff_receipt_status = (
            CalibrationReceiptStatusV1.PERSISTED
            if receipt_path is not None
            else (
                CalibrationReceiptStatusV1.UNAVAILABLE
                if receipt_error_detail is not None or receipt_required
                else None
            )
        )
        publish_post_calibration_handoff(
            consumer_configured=True,
            attempted=True,
            projection_status=handoff_projection_status,
            receipt_status=handoff_receipt_status,
            receipt_error_detail=receipt_error_detail,
        )
        return live_source_identity

    @staticmethod
    def _persist_calibration_projection_receipt(
        *,
        consumer: Any,
        active_identity: Mapping[str, Any] | None = None,
        decision_date: str,
        projections: Mapping[str, Any],
        inference_provenance: Mapping[str, Any],
        source_contract_evidence: Any = None,
        result_id: str | None,
        selection_authority: str,
        selection_score_kind: str,
        selection_percentile_kind: str,
        top_n_changed_by_model: bool,
        invocation_capture: dict[str, Any] | None = None,
        receipt_event_out: list[CalibrationReceiptEventFactsV1] | None = None,
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
        _assert_prepared_source_contract_bytes_unchanged_v1(
            inference_provenance,
            source_contract_evidence,
        )
        if receipt_event_out is not None:
            receipt_event_out.append(
                _post_calibration_receipt_event_v1(None, attempted=False)
            )
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
            source_contract_evidence=source_contract_evidence,
        )
        if receipt_event_out is not None:
            receipt_event_out[-1] = _post_calibration_receipt_event_v1(
                receipt.payload,
                attempted=True,
                receipt_hash=receipt.receipt_hash,
            )
        capture = invocation_capture.setdefault("receipt", {}) if isinstance(invocation_capture, dict) else None
        if isinstance(capture, dict):
            capture.update(
                {
                    "attempted": True,
                    "result_id": str(result_id or ""),
                    "decision_date": str(decision_date),
                    "candidate_identity": {
                        key: str(identity.get(key) or "")
                        for key in (
                            "candidate_id",
                            "candidate_manifest_hash",
                            "candidate_artifact_hash",
                            "candidate_freeze_hash",
                            "pointer_version",
                        )
                    },
                    "receipt_hash": receipt.receipt_hash,
                    "receipt_payload": deepcopy(dict(receipt.payload)),
                    "write_status": "pending",
                }
            )
        path = persist_inference_projection_receipt(Path(pointer_path).parent, receipt)
        if receipt_event_out is not None:
            receipt_event_out[-1] = replace(
                receipt_event_out[-1],
                persisted=True,
                path=str(path),
            )
        if isinstance(capture, dict):
            capture.update(
                {
                    "persisted": True,
                    "path": str(path),
                    "write_status": "persisted",
                }
            )
        receipt_created_at = datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        )
        if isinstance(capture, dict):
            capture["receipt_created_at"] = receipt_created_at
        if receipt_event_out is not None:
            receipt_event_out[-1] = replace(
                receipt_event_out[-1],
                receipt_created_at=receipt_created_at,
            )
        _assert_prepared_source_contract_bytes_unchanged_v1(
            inference_provenance,
            source_contract_evidence,
        )
        verified_receipt = read_inference_projection_receipt(
            path,
            expected_receipt_hash=receipt.receipt_hash,
            expected_decision_date=decision_date,
            expected_candidate_id=candidate_id,
            expected_result_id=result_id,
            expected_cost_scenario_hash=receipt.payload.get("cost_scenario_hash"),
            source_contract_evidence=source_contract_evidence,
        )
        if isinstance(capture, dict):
            capture["readback_verified"] = True
            capture["readback_status"] = "verified"
            capture["receipt_payload"] = deepcopy(dict(verified_receipt.payload))
            capture["receipt_hash"] = verified_receipt.receipt_hash
        if receipt_event_out is not None:
            receipt_event_out[-1] = _post_calibration_receipt_event_v1(
                verified_receipt.payload,
                attempted=True,
                persisted=True,
                readback_verified=True,
                path=str(path),
                receipt_hash=verified_receipt.receipt_hash,
                receipt_created_at=receipt_created_at,
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
        if isinstance(capture, dict):
            capture["identity_verified"] = True
            capture["identity_status"] = "verified"
        if receipt_event_out is not None:
            receipt_event_out[-1] = replace(
                receipt_event_out[-1],
                identity_verified=True,
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
        input_session: RecommendationInputSession,
        stock_code: str,
        decision_date: date,
    ):
        """只讀取有獨立正式 availability mapping 支持的月營收。"""
        return input_session.load_monthly_revenues(
            stock_code=stock_code,
            decision_date=decision_date,
        )

    def _get_fundamental_sqlite_provider(self) -> FundamentalSQLiteProvider | None:
        lock = getattr(self, "_r011_last_state_lock", None)
        if lock is None:
            return self._get_fundamental_sqlite_provider_locked()
        with lock:
            return self._get_fundamental_sqlite_provider_locked()

    def _get_fundamental_sqlite_provider_locked(self) -> FundamentalSQLiteProvider | None:
        return self.recommendation_input_preparer.fundamental_input_provider.get_monthly_revenue_provider()

    def _load_historical_market_frame(self, cutoff: str | None) -> pd.DataFrame:
        """相容 wrapper；資料來源由 composition 注入的 reader 擁有。"""
        return self.recommendation_input_preparer.historical_market_provider(cutoff)

    def _decision_frame(self, frame: pd.DataFrame, cutoff: str | None) -> tuple[pd.DataFrame, str, str]:
        """相容 wrapper；frame 正規化／available-date 規則由 app prep 擁有。"""
        from app_module.recommendation.input_preparation import (
            prepare_recommendation_market,
        )

        prepared = prepare_recommendation_market(
            source_frame=frame,
            cutoff=cutoff,
            market_data_provider=self.market_data_provider,
        )
        return prepared.frame, prepared.stock_column, prepared.decision_cutoff

    def _read_pit_membership_for_recommendation(
        self,
        cutoff: str,
        config: Dict[str, Any],
    ) -> PITMembershipReadResult | None:
        return self.recommendation_input_preparer.pit_membership_provider.read(
            cutoff, config
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
        """由新的單次 execute 用例提供向後相容的 DTO list。"""

        from app_module.recommendation.execute import (
            execute_recommendation,
            project_legacy_recommendations,
            publish_legacy_invocation_state,
        )

        capture: dict[str, Any] = {}
        execution = execute_recommendation(
            self,
            config,
            max_stocks=max_stocks,
            top_n=top_n,
            as_of_date=as_of_date,
            universe=universe,
            result_id=result_id,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
            capture_sink=capture,
        )
        publish_legacy_invocation_state(self, capture)
        error = capture.get("error")
        if error is not None:
            raise error.with_traceback(capture.get("traceback"))
        if execution.status.value != "completed":
            return []
        return project_legacy_recommendations(execution, capture)

    def execute_recommendation(
        self,
        runtime_config: Mapping[str, Any],
        max_stocks: int = 200,
        top_n: int = 50,
        *,
        request_config_snapshot: RecommendationConfigSnapshot,
        postprocess_callback: Callable[
            [RecommendationPostprocessInput], RecommendationPostprocessFacts
        ],
        created_at: datetime | None = None,
        as_of_date: str | date | None = None,
        universe: Optional[List[str]] = None,
        result_id: str | None = None,
        historical_research: bool = False,
        select_latest_available_cutoff: bool = False,
        cancel: Callable[[], bool] | None = None,
        progress: Callable[[str, int], None] | None = None,
    ) -> RecommendationExecution:
        """執行具原 caller snapshot 與同步 postprocess 的完整 capture。"""

        if not callable(postprocess_callback):
            raise TypeError("postprocess_callback 必須是 callable")
        from app_module.recommendation.execute import (
            execute_recommendation as execute_use_case,
        )

        return execute_use_case(
            self,
            runtime_config,
            max_stocks=max_stocks,
            top_n=top_n,
            as_of_date=as_of_date,
            universe=universe,
            result_id=result_id,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
            request_config_snapshot=request_config_snapshot,
            postprocess_callback=postprocess_callback,
            created_at=created_at,
            cancel=cancel,
            progress=progress,
        )

    def _run_recommendation_body_result(
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
        input_session: RecommendationInputSession | None = None,
        invocation_frozen_at: datetime | None = None,
    ) -> RecommendationBodyResult:
        """執行推薦分析並直接回傳同次 invocation 的 typed body result。

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
            RecommendationBodyResult: canonical DecisionBatch 與凍結 legacy DTO sidecar。
        """
        import logging
        logger = logging.getLogger(__name__)
        config = deepcopy(config)
        if input_session is None:
            raise ValueError("推薦計算必須由 execute 注入 invocation-local input_session")
        if max_stocks < 1 or top_n < 0:
            raise ValueError("max_stocks 必須為正數，top_n 不得為負數")
        input_session.validate_cutoff_request(
            runtime_config=config,
            as_of_date=as_of_date,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
        )
        ranking_config, threshold_mode = self._validate_ranking_config(config)
        self._reset_negative_evidence_buffers()
        cutoff_resolution = input_session.resolve_cutoff(
            runtime_config=config,
            as_of_date=as_of_date,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
        )
        cutoff = cutoff_resolution.cutoff
        temporal_mode = cutoff_resolution.temporal_mode
        cutoff_selection = cutoff_resolution.cutoff_selection
        cutoff_policy = cutoff_resolution.cutoff_policy
        current_fundamental_scope = (
            cutoff is None
            and not historical_research
            and invocation_frozen_at is not None
        )
        if invocation_frozen_at is not None and (
            invocation_frozen_at.tzinfo is None
            or invocation_frozen_at.utcoffset() is None
        ):
            raise ValueError("invocation_frozen_at must be timezone-aware")
        if current_fundamental_scope:
            if invocation_frozen_at is None:
                raise RuntimeError("natural current scope requires an invocation freeze")
            invocation_frozen_at = invocation_frozen_at.astimezone(timezone.utc)
        personal_live_clock = (
            self._personal_use_policy is not None
            and cutoff is None
            and as_of_date is None
            and not historical_research
            and not select_latest_available_cutoff
        )
        strategy_identity = build_strategy_config_identity(
            config,
            max_stocks=max_stocks,
            top_n=top_n,
        )
        run_started_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        personal_decision_clock: datetime | None = None
        personal_decision_date: str | None = None
        market_source_frame: pd.DataFrame | None = None
        if personal_live_clock:
            # 先完成一次 live source read，再凍結整次執行共用的 aware 決策時鐘；
            # 後續日期篩選、評估、consumer 與 receipt 都沿用這個決策日。
            if isinstance(input_session, RecommendationInputSession):
                market_source_frame = input_session.load_market_frame_with_minimum_bars(
                    cutoff=None,
                    minimum_bars=minimum_recommendation_history_rows(config),
                )
            else:
                load_market_frame = getattr(input_session, "load_market_frame", None)
                if not callable(load_market_frame):
                    raise TypeError(
                        "personal natural/live input session 必須提供 load_market_frame(cutoff=None)"
                    )
                market_source_frame = load_market_frame(cutoff=None)
            personal_decision_clock = datetime.now(timezone.utc)
            personal_decision_date = personal_decision_clock.astimezone(
                ZoneInfo("Asia/Taipei")
            ).date().isoformat()

        # ✅ 記錄輸入參數
        logger.info(
            f"[RecommendationService] 開始推薦分析: "
            f"max_stocks={max_stocks}, top_n={top_n}, "
            f"產業篩選={config.get('filters', {}).get('industry', '全部')}, "
            f"圖形模式={config.get('patterns', {}).get('selected', [])}, "
            f"技術指標啟用={config.get('technical', {}).get('momentum', {}).get('enabled', False) or config.get('technical', {}).get('trend', {}).get('enabled', False)}"
        )

        if personal_live_clock and isinstance(input_session, RecommendationInputSession):
            prepared_market = input_session.prepare_market_with_minimum_bars(
                cutoff=cutoff,
                minimum_bars=minimum_recommendation_history_rows(config),
                universe=universe,
                decision_date=personal_decision_date,
                source_frame=market_source_frame,
            )
        elif personal_live_clock:
            # 新的決策日／同次來源 frame 只屬明示個人即時模式；舊注入
            # input-session 仍沿用原本的兩參數呼叫契約。
            prepared_market = input_session.prepare_market(
                cutoff=cutoff,
                universe=universe,
                decision_date=personal_decision_date,
                source_frame=market_source_frame,
            )
        elif isinstance(input_session, RecommendationInputSession):
            prepared_market = input_session.prepare_market_with_minimum_bars(
                cutoff=cutoff,
                minimum_bars=minimum_recommendation_history_rows(config),
                universe=universe,
            )
        else:
            prepared_market = input_session.prepare_market(
                cutoff=cutoff,
                universe=universe,
            )
        df = prepared_market.frame
        stock_col = prepared_market.stock_column
        decision_cutoff = prepared_market.decision_cutoff
        source_available_at = (
            personal_decision_clock.isoformat(timespec="microseconds")
            if personal_decision_clock is not None
            else datetime.now(timezone.utc).isoformat(timespec="microseconds")
        )
        # 個人 live invocation 的決策時鐘在資料讀取後已凍結；即使資料為空或
        # 篩選後沒有候選，也必須封存同一時鐘。非個人路徑仍沿用成功路徑
        # 原本較晚設定 decision_at 的行為。
        decision_clock = (
            personal_decision_clock.isoformat(timespec="microseconds")
            if personal_decision_clock is not None
            else ""
        )
        self._personalization_execution_clocks = {
            "run_started_at": run_started_at,
            "available_at": source_available_at,
            "captured_at": source_available_at,
            "personalization_scope_declared_at": run_started_at,
        }
        if personal_decision_clock is not None:
            self._personalization_execution_clocks["decision_at"] = decision_clock
        market_warnings: list[str] = (
            ["industry_membership_not_point_in_time"] if cutoff else []
        )
        if current_fundamental_scope and prepared_market.expected_market_date is not None:
            if (
                prepared_market.market_calendar_status != "current"
                or prepared_market.data_date != prepared_market.expected_market_date
            ):
                market_warnings.append(
                    "natural_market_data_session_insufficient:"
                    f"{prepared_market.market_calendar_status or 'unverified'}:"
                    f"expected={prepared_market.expected_market_date}:"
                    f"observed={prepared_market.data_date or 'missing'}"
                )
        resolved_result_id = str(result_id or config.get("result_id") or "").strip()
        if not resolved_result_id:
            # Allocate the run identity before calibration receipt publication.
            # UUID entropy prevents same-second runs from sharing a saved result
            # or projection receipt identity; the context keeps it stable for
            # every save performed from this run.
            resolved_result_id = f"rec_{uuid4().hex}"
        staged_invocation_id = f"{resolved_result_id}:{uuid4().hex}"
        context_owner = InvocationLegacyContextOwner(staged_invocation_id)
        self.last_run_context = context_owner.mutable_context
        self.last_run_context.update({
            "schema_version": "recommendation-context.v1",
            "as_of_date": decision_cutoff,
            "strategy_config": deepcopy(config),
            "profile_id": str(config.get("profile_id") or ""),
            "profile_version": str(config.get("profile_version") or ""),
            "universe_spec": {"codes": sorted({str(code) for code in universe}) if universe is not None else None, "max_stocks": max_stocks},
            "source_id": prepared_market.source_id,
            "market_data_fingerprint": prepared_market.market_data_fingerprint,
            "fundamental_inputs": [],
            "fundamental_input_requests": [],
            "current_fundamental_observations": [],
            "fundamental_input_scope": (
                "natural_current_observation"
                if current_fundamental_scope
                else "formal_pit"
            ),
            "current_observation_cutoff_at": (
                invocation_frozen_at.isoformat(timespec="microseconds")
                if current_fundamental_scope and invocation_frozen_at is not None
                else None
            ),
            "current_market_status_preflight_diagnostics": [],
            "fundamental_input_diagnostics": [],
            "fundamental_input_diagnostic_source_row_count": 0,
            "fundamental_input_diagnostic_comparator_row_count": 0,
            "data_date": prepared_market.data_date,
            "expected_market_date": prepared_market.expected_market_date,
            "market_calendar_status": prepared_market.market_calendar_status,
            "market_calendar_reason_code": prepared_market.market_calendar_reason_code,
            "warnings": market_warnings,
            "temporal_contract": "recommendation-producer-clock.v1",
            "temporal_mode": temporal_mode,
            "cutoff_selection": cutoff_selection,
            "cutoff_policy": cutoff_policy,
            "decision_clock_timezone": "UTC",
            "market_calendar_timezone": "Asia/Taipei",
            "prediction_decision_anchor": "actual_producer_decision_at",
            "horizon_anchor": "immutable_projection_receipt",
            **strategy_identity,
        })
        if personal_decision_clock is not None:
            personal_policy = self._personal_use_policy
            self.last_run_context.update(
                {
                    "decision_date": decision_cutoff,
                    "decision_at": decision_clock,
                    "personal_live_clock_schema": "recommendation-personal-live-clock.v1",
                    "market_data_date": prepared_market.data_date or None,
                }
            )
            if _is_personal_use_policy(personal_policy):
                # 在任何空資料／零候選 early return 前，先封存此 invocation
                # 的已驗證政策；後續 calibration 可再更新實際 effective mode。
                self.last_run_context.update(
                    {
                        "personal_use_policy": personal_policy.to_dict(),
                        "personal_use_requested_mode": personal_policy.mode,
                        "personal_use_effective_mode": RULE_ONLY_MODE,
                    }
                )
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
            pit_membership = input_session.read_pit_membership(cutoff, config)
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

        candidate_outcomes: list[CandidateEvaluationOutcome] = []
        candidate_facts: list[CandidateRowFacts] = []
        legacy_matrix_codes: list[str] = []
        staged_evaluator = RecommendationEvaluator()
        universe_identity: dict[str, Any] | None = None

        def remember_candidate(
            outcome: CandidateEvaluationOutcome,
            *,
            stock_name: str,
            industry: str = "",
            total_score_text: str = "",
        ) -> None:
            facts = CandidateRowFacts(
                stock_code=outcome.stock_code,
                stock_name=stock_name,
                industry=industry,
                total_score_text=total_score_text,
                threshold_mode=threshold_mode,
                invocation_id=staged_invocation_id,
            )
            candidate_outcomes.append(outcome)
            candidate_facts.append(facts)

        def remember_prefilter(code: str, *, membership_usable: bool) -> None:
            outcome = staged_evaluator.prefilter_outcome(
                CandidatePrefilterFact(
                    invocation_id=staged_invocation_id,
                    stock_code=code,
                    requested_industry=str(industry_filter),
                    point_in_time_required=bool(cutoff),
                    membership_usable=membership_usable,
                    matching_stock_count=0,
                )
            )
            remember_candidate(outcome, stock_name=code)

        def make_batch_policy(decision_date_text: str) -> RecommendationEvaluationPolicy:
            decision_date_value = (
                date.fromisoformat(decision_date_text)
                if decision_date_text
                else None
            )
            return RecommendationEvaluationPolicy(
                invocation_id=staged_invocation_id,
                decision_date=decision_date_value,
                decision_date_text=decision_date_text,
                threshold_mode=threshold_mode,
                top_n=top_n,
                minimum_percentile_bp=(
                    int(ranking_config["recommendation_min_percentile_bp"])
                    if threshold_mode == "quantile"
                    else None
                ),
                minimum_universe_size=(
                    int(ranking_config["recommendation_min_universe_size"])
                    if threshold_mode == "quantile"
                    else None
                ),
                ranking_method=(
                    str(ranking_config["recommendation_ranking_method"])
                    if threshold_mode == "quantile"
                    else "fixed"
                ),
                eligible_universe_date=decision_date_value,
                fundamental_input_scope=(
                    "natural_current_observation"
                    if current_fundamental_scope
                    else "formal_pit"
                ),
                current_observation_cutoff_at=(
                    invocation_frozen_at if current_fundamental_scope else None
                ),
            )

        def evaluate_candidates(
            policy: RecommendationEvaluationPolicy,
        ) -> RecommendationEvaluationResult:
            try:
                return staged_evaluator.evaluate_batch_result(
                    tuple(candidate_outcomes), policy
                )
            except DecisionUniverseTooSmallError as exc:
                raise RecommendationUniverseTooSmallError(
                    exc.actual, exc.minimum
                ) from exc

        def publish_body_result(
            *,
            evaluation_result: RecommendationEvaluationResult,
            policy: RecommendationEvaluationPolicy,
            eligible_universe_size: int,
            legacy_recommendations: list[RecommendationDTO],
        ) -> RecommendationBodyResult:
            self._finalize_current_industry_mapping_snapshot()
            self.last_run_context["eligible_universe_size"] = eligible_universe_size
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "market": prepared_market.market_data_fingerprint,
                        "fundamental": context_owner.mutable_context[
                            "fundamental_inputs"
                        ],
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            self.last_run_context["data_fingerprint"] = fingerprint
            # 只封存同次已接受的來源 frame，不另讀行情或重算均線；缺圖不改推薦。
            if legacy_recommendations and decision_cutoff:
                from app_module.recommendation_saved_chart import build_recommendation_chart_capture

                try:
                    self.last_run_context["saved_technical_charts"] = build_recommendation_chart_capture(
                        frame=prepared_market.frame,
                        stock_column=prepared_market.stock_column,
                        stock_codes=tuple(item.stock_code for item in legacy_recommendations),
                        result_id=resolved_result_id,
                        source_id=str(prepared_market.source_id),
                        market_data_fingerprint=str(prepared_market.market_data_fingerprint),
                        decision_cutoff=datetime.combine(
                            date.fromisoformat(decision_cutoff), datetime.max.time(),
                            tzinfo=ZoneInfo("Asia/Taipei"),
                        ),
                    )
                except (ValueError, TypeError) as exc:
                    self.last_run_context["saved_technical_chart_failure"] = str(exc)
            warning_values = self.last_run_context.get("warnings", [])
            if not isinstance(warning_values, list) or any(
                type(item) is not str for item in warning_values
            ):
                raise TypeError("recommendation context warnings 必須是 str list")
            context = RecommendationBodyContextFacts.capture(
                result_id=resolved_result_id,
                invocation_id=staged_invocation_id,
                as_of_date=decision_cutoff or "",
                data_fingerprint=fingerprint,
                market_data_fingerprint=str(
                    prepared_market.market_data_fingerprint
                ),
                source_id=str(prepared_market.source_id),
                temporal_mode=temporal_mode,
                decision_at=decision_clock,
                eligible_universe_size=eligible_universe_size,
                warnings=tuple(warning_values),
                legacy_context=context_owner.freeze_current_context(),
                evidence_identity=_recommendation_evidence_identity(
                    declared_identity
                ),
                cutoff_selection=cutoff_selection,
                cutoff_policy=cutoff_policy,
                strategy_identity=strategy_identity_from_payload(
                    strategy_identity,
                    strategy_version_id=(
                        (
                            config.get("strategy_version_id")
                            or config.get("strategy_version")
                        )
                        if str(
                            config.get("strategy_version_id")
                            or config.get("strategy_version")
                            or ""
                        ).strip()
                        else None
                    ),
                ),
                universe_identity=universe_identity_from_payload(
                    universe_identity
                ),
                calibration_projection_status=cast(
                    str | None,
                    context_owner.mutable_context.get("calibration_projection_status"),
                ),
                calibration_projection_receipt_status=cast(
                    str | None,
                    context_owner.mutable_context.get(
                        "calibration_projection_receipt_status"
                    ),
                ),
                calibration_projection_receipt_error_detail=cast(
                    str | None,
                    context_owner.mutable_context.get(
                        "calibration_projection_receipt_error_detail"
                    ),
                ),
            )
            enriched_result = enrich_evaluation_result(
                evaluation_result,
                tuple(candidate_facts),
                context,
                policy,
            )

            dispositions_by_code = {
                item.stock_code: item for item in enriched_result.dispositions
            }
            facts_by_code = {
                item.stock_code: item for item in candidate_facts
            }
            projected_matrix: list[Dict[str, Any]] = []
            for code in legacy_matrix_codes:
                projected_matrix.append(
                    cast(
                        Dict[str, Any],
                        build_candidate_row_payload(
                            dispositions_by_code[code],
                            facts_by_code[code],
                            context,
                            policy,
                        ),
                    )
                )
            self.last_screening_matrix = projected_matrix
            self._finalize_negative_evidence_buffers()

            sidecars = tuple(
                LegacyRecommendationSnapshot.capture(
                    recommendation,
                    invocation_id=staged_invocation_id,
                    result_id=resolved_result_id,
                )
                for recommendation in legacy_recommendations
            )
            body_result = RecommendationBodyResult(
                result_id=resolved_result_id,
                invocation_id=staged_invocation_id,
                decision=enriched_result.decision,
                dispositions=enriched_result.dispositions,
                candidate_facts=tuple(candidate_facts),
                context=context,
                legacy_recommendations=sidecars,
            )
            return body_result

        if df.empty:
            empty_policy = make_batch_policy(str(decision_cutoff or ""))
            return publish_body_result(
                evaluation_result=evaluate_candidates(empty_policy),
                policy=empty_policy,
                eligible_universe_size=0,
                legacy_recommendations=[],
            )

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
                for code in all_stocks:
                    stock_code_text = str(code)
                    remember_prefilter(stock_code_text, membership_usable=False)
                    legacy_matrix_codes.append(stock_code_text)
                empty_policy = make_batch_policy(str(decision_cutoff or ""))
                return publish_body_result(
                    evaluation_result=evaluate_candidates(empty_policy),
                    policy=empty_policy,
                    eligible_universe_size=0,
                    legacy_recommendations=[],
                )
            filtered_stocks = pit_industry_codes or set()
            if not filtered_stocks:
                self.last_run_context["warnings"].append("industry_filter_empty")
                for code in all_stocks:
                    stock_code_text = str(code)
                    remember_prefilter(stock_code_text, membership_usable=True)
                    legacy_matrix_codes.append(stock_code_text)
                empty_policy = make_batch_policy(str(decision_cutoff or ""))
                return publish_body_result(
                    evaluation_result=evaluate_candidates(empty_policy),
                    policy=empty_policy,
                    eligible_universe_size=0,
                    legacy_recommendations=[],
                )
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
            self._record_current_industry_mapping_use("current_filter_selection")
            current_filtered_stocks = self.industry_mapper.filter_stocks_by_industry(
                [str(s) for s in all_stocks],
                industry_filter
            )

            if len(current_filtered_stocks) == 0:
                # 提供更詳細的錯誤信息，幫助調試
                self._record_current_industry_mapping_use(
                    "current_filter_empty_industries_diagnostic"
                )
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
                    self._record_current_industry_mapping_use(
                        "current_filter_example_industry_diagnostic"
                    )
                    test_industries = self.industry_mapper.get_stock_industries(str(test_stock))
                    if test_industries:
                        error_msg += f"\n範例：股票 {test_stock} 屬於：{', '.join(test_industries[:3])}"
                        break
                self.last_run_context["warnings"].append("industry_filter_empty")
                for code in all_stocks:
                    remember_prefilter(str(code), membership_usable=True)

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
            source_provider_id=prepared_market.source_id,
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

            if (
                current_fundamental_scope
                and not select_latest_available_cutoff
                and invocation_frozen_at is not None
            ):
                status_reader = getattr(input_session, "get_current_market_status", None)
                if not callable(status_reader):
                    status_result: object | None = None
                    preflight_reason = "current_market_status_reader_unavailable"
                else:
                    try:
                        status_result = status_reader(
                            stock_code_text,
                            cutoff_at=invocation_frozen_at,
                            decision_date=invocation_frozen_at.astimezone(
                                ZoneInfo("Asia/Taipei")
                            ).date(),
                        )
                        preflight_reason = ""
                    except Exception as exc:
                        status_result = None
                        preflight_reason = (
                            "current_market_status_read_failed:"
                            f"{type(exc).__name__}"
                        )

                if status_result is not None:
                    if not isinstance(status_result, CurrentMarketStatusPreflightResult):
                        preflight_reason = "current_market_status_result_invalid"
                    elif status_result.symbol != stock_code_text:
                        preflight_reason = "current_market_status_symbol_mismatch"
                    elif status_result.disposition == "verified_delisted":
                        if (
                            status_result.reason_code != "official_delisted"
                            or status_result.evidence is None
                            or not validate_current_market_status_evidence(
                                status_result.evidence,
                                expected_symbol=stock_code_text,
                                decision_at=invocation_frozen_at,
                            )
                        ):
                            preflight_reason = (
                                "current_market_status_evidence_unverified"
                            )
                        else:
                            delisted_outcome = staged_evaluator.current_market_status_outcome(
                                CandidateCurrentMarketStatusFact(
                                    invocation_id=staged_invocation_id,
                                    stock_code=stock_code_text,
                                    evidence=status_result.evidence,
                                )
                            )
                            stats["skipped_no_result"] += 1
                            remember_candidate(
                                delisted_outcome,
                                stock_name=stock_name_text,
                            )
                            self.last_screening_matrix.append(
                                self._matrix_row(
                                    stock_code=stock_code_text,
                                    stock_name=stock_name_text,
                                    status=delisted_outcome.status,
                                    reason_codes=list(delisted_outcome.reason_codes),
                                    quality=delisted_outcome.quality,
                                    stage=delisted_outcome.stage,
                                    threshold_mode=threshold_mode,
                                )
                            )
                            legacy_matrix_codes.append(stock_code_text)
                            continue
                    elif status_result.disposition == "unavailable":
                        preflight_reason = status_result.reason_code
                    elif status_result.disposition != "not_delisted":
                        preflight_reason = "current_market_status_disposition_invalid"

                if preflight_reason:
                    diagnostic = (
                        "current_market_status_preflight_unavailable:"
                        f"{stock_code_text}:{preflight_reason}"
                    )
                    diagnostics = self.last_run_context[
                        "current_market_status_preflight_diagnostics"
                    ]
                    if not isinstance(diagnostics, list):
                        raise TypeError(
                            "current_market_status_preflight_diagnostics must be a list"
                        )
                    if diagnostic not in diagnostics:
                        diagnostics.append(diagnostic)

            history_outcome = staged_evaluator.preflight_history(
                CandidateHistoryFacts(
                    invocation_id=staged_invocation_id,
                    stock_code=stock_code_text,
                    history_rows=len(stock_df),
                )
            )
            if history_outcome is not None:
                stats['skipped_insufficient_data'] += 1
                remember_candidate(
                    history_outcome,
                    stock_name=stock_name_text,
                )
                row = self._matrix_row(
                    stock_code=stock_code_text,
                    stock_name=stock_name_text,
                    status=history_outcome.status,
                    reason_codes=list(history_outcome.reason_codes),
                    quality=history_outcome.quality,
                    stage=history_outcome.stage,
                    threshold_name=history_outcome.threshold_name,
                    observed_value=history_outcome.observed_value,
                    required_value=history_outcome.required_value,
                    threshold_mode=threshold_mode,
                )
                self.last_screening_matrix.append(row)
                legacy_matrix_codes.append(stock_code_text)
                continue

            stock_df = enrich_latest_market_features(stock_df)

            try:
                # 生成推薦（generate_recommendations 內部會處理篩選，這裡不需要額外篩選）
                strategy_error: StrategyEvaluationError | None = None
                try:
                    result_df = self.strategy_configurator.generate_recommendations(
                        stock_df, deepcopy(config)
                    )
                except Exception as exc:
                    strategy_error = StrategyEvaluationError(
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                    result_df = pd.DataFrame()

                if strategy_error is None:
                    stats['processed'] += 1

                # ✅ 添加調試信息：記錄為什麼返回空 DataFrame
                if strategy_error is None and len(result_df) == 0:
                    # 記錄前3個被過濾的股票詳情
                    if stats['skipped_no_result'] < 3:
                        logger.warning(
                            f"[調試] 股票 {stock_code} 返回空結果: "
                            f"數據筆數={len(stock_df)}, "
                            f"日期範圍={stock_df['日期'].min() if '日期' in stock_df.columns else 'N/A'} ~ "
                            f"{stock_df['日期'].max() if '日期' in stock_df.columns else 'N/A'}"
                        )
                if strategy_error is not None or len(result_df) == 0:
                    early_seed = CandidateSeed(
                        invocation_id=staged_invocation_id,
                        stock_code=stock_code_text,
                        stock_name=stock_name_text,
                        history_rows=len(stock_df),
                        strategy_result_present=False,
                        strategy_error=strategy_error,
                        latest_volume_change_percent=latest_feature_decimal(
                            stock_df,
                            "成交量變化率%",
                        ),
                    )
                    early_policy = RecommendationEvaluationPolicy(
                        invocation_id=staged_invocation_id,
                        decision_date=None,
                        decision_date_text=str(decision_cutoff or ""),
                        volume_change_min_percent=(
                            self._configured_volume_change_min_percent(config)
                        ),
                    )
                    early_step = staged_evaluator.start(early_seed, early_policy)
                    outcome = early_step.outcome
                    if outcome is None:
                        raise RuntimeError("strategy early outcome unexpectedly requested a fact")
                    row = self._matrix_row(
                        stock_code=stock_code_text,
                        stock_name=stock_name_text,
                        status=outcome.status,
                        reason_codes=list(outcome.reason_codes),
                        quality=outcome.quality,
                        stage=outcome.stage,
                        threshold_name=outcome.threshold_name,
                        observed_value=outcome.observed_value,
                        required_value=outcome.required_value,
                        threshold_mode=threshold_mode,
                        warnings=list(outcome.warnings),
                    )
                    self.last_screening_matrix.append(row)
                    legacy_matrix_codes.append(stock_code_text)
                    remember_candidate(
                        outcome,
                        stock_name=stock_name_text,
                    )
                    if strategy_error is not None:
                        stats['skipped_exception'] += 1
                        if stats['skipped_exception'] <= 3:
                            logger.warning(
                                "處理股票 %s 時發生異常: %s (%s)",
                                stock_code,
                                strategy_error.message,
                                strategy_error.error_type,
                            )
                    else:
                        stats['skipped_no_result'] += 1
                    continue

                if len(result_df) > 0:
                    latest_row = result_df.iloc[-1]

                    # 取得決策日期與目前候選政策；實際 PE／月營收門檻由 decision evaluator 判定。
                    raw_date = decision_cutoff
                    pe_ratio_max = to_decimal(
                        config.get('filters', {}).get('pe_ratio_max', "999.0")
                    )
                    revenue_yoy_min = to_decimal(
                        config.get('filters', {}).get(
                            'monthly_revenue_yoy_min', "-100.0"
                        )
                    )
                    pe_threshold = (
                        pe_ratio_max
                        if pe_ratio_max < to_decimal("999.0")
                        else None
                    )
                    revenue_threshold = (
                        revenue_yoy_min
                        if revenue_yoy_min > to_decimal("-100.0")
                        else None
                    )
                    try:
                        decision_date_text = self._normalize_decision_date(raw_date)
                    except (TypeError, ValueError):
                        decision_date_text = ""
                    decision_date_value = (
                        date.fromisoformat(decision_date_text)
                        if decision_date_text
                        else None
                    )

                    final_score = latest_row.get(
                        'FinalScore',
                        latest_row.get('TotalScore', latest_row.get('綜合評分')),
                    )
                    candidate_item: RecommendationItem | None = None
                    candidate_score: RecommendationScore | None = None
                    if final_score is not None:
                        try:
                            score_decimal = to_decimal(final_score)
                        except Exception:
                            score_decimal = None
                        if score_decimal is not None and score_decimal.is_finite():
                            try:
                                score_projection = project_legacy_recommendation_score(
                                    final_score,
                                    include_quantile_score_bp=(
                                        threshold_mode == "quantile"
                                    ),
                                )
                                score_value = score_projection.contract_value
                                candidate_score = score_projection.score
                            except Exception:
                                score_value = score_decimal
                                candidate_score = RecommendationScore(
                                    ordering_value=score_decimal
                                )
                            candidate_item = RecommendationItem(
                                stock_code=stock_code_text,
                                stock_name=stock_name_text,
                                rule_score=score_value,
                            )

                    volume_change_value = latest_feature_decimal(
                        stock_df,
                        "成交量變化率%",
                    )
                    if (
                        volume_change_value is not None
                        and not volume_change_value.is_finite()
                    ):
                        volume_change_value = None
                    candidate_seed = CandidateSeed(
                        invocation_id=staged_invocation_id,
                        stock_code=stock_code_text,
                        stock_name=stock_name_text,
                        history_rows=len(stock_df),
                        strategy_result_present=True,
                        latest_volume_change_percent=volume_change_value,
                        item=candidate_item,
                        score=candidate_score,
                    )
                    candidate_policy = RecommendationEvaluationPolicy(
                        invocation_id=staged_invocation_id,
                        decision_date=decision_date_value,
                        decision_date_text=(decision_date_text or str(raw_date)),
                        pe_ratio_max=pe_threshold,
                        monthly_revenue_yoy_min=revenue_threshold,
                        volume_change_min_percent=(
                            self._configured_volume_change_min_percent(config)
                        ),
                        fundamental_input_scope=(
                            "natural_current_observation"
                            if current_fundamental_scope
                            else "formal_pit"
                        ),
                        current_observation_cutoff_at=(
                            invocation_frozen_at
                            if current_fundamental_scope
                            else None
                        ),
                        industry_context_required=(
                            not bool(cutoff) and decision_date_value is not None
                        ),
                        top_n=top_n,
                    )
                    industry_readback: dict[str, Any] = {
                        "loaded": False,
                        "industries": (),
                        "display": "未知",
                        "reasons": None,
                    }
                    close_col: str | None = None
                    price_change = 0.0
                    output_row_prepared = False

                    def prepare_output_row() -> None:
                        nonlocal latest_row, close_col, price_change, output_row_prepared
                        if output_row_prepared:
                            return
                        close_col = None
                        for candidate_column in ['收盤價', 'Close', 'close']:
                            if candidate_column in latest_row.index:
                                close_col = candidate_column
                                break
                        price_change_value = latest_feature_decimal(
                            stock_df,
                            "漲幅%",
                        )
                        output_volume_change = latest_feature_decimal(
                            stock_df,
                            "成交量變化率%",
                        )
                        price_change = float(
                            price_change_value or Decimal("0")
                        )
                        # DTO / reason DataFrame boundary retains the legacy numeric fields.
                        latest_row = latest_row.copy()
                        latest_row['漲幅%'] = price_change
                        latest_row['成交量變化率%'] = float(
                            output_volume_change or Decimal("0")
                        )
                        output_row_prepared = True

                    def read_candidate_fact(
                        request: NeedSourceFact,
                    ) -> SourceFactResponse:
                        if request.kind in {
                            SourceFactKind.PE,
                            SourceFactKind.MONTHLY_REVENUE,
                        }:
                            self.last_run_context[
                                "fundamental_input_requests"
                            ].append(
                                {
                                    "request_id": request.request_id,
                                    "stock_code": request.stock_code,
                                    "metric": request.kind.value,
                                    "scope": request.fundamental_input_scope,
                                    "decision_date": request.decision_date.isoformat(),
                                    "current_observation_cutoff_at": (
                                        request.current_observation_cutoff_at.isoformat()
                                        if request.current_observation_cutoff_at
                                        is not None
                                        else None
                                    ),
                                }
                            )
                        if request.kind is SourceFactKind.PE:
                            if request.fundamental_input_scope == "natural_current_observation":
                                observation = None
                                diagnostics: tuple[str, ...] = ()
                                cutoff_at = request.current_observation_cutoff_at
                                loader = getattr(input_session, "load_current_pe", None)
                                market_session_current = (
                                    prepared_market.expected_market_date is not None
                                    and prepared_market.data_date
                                    == prepared_market.expected_market_date
                                    and prepared_market.market_calendar_status == "current"
                                )
                                stock_quote_date: str | None = None
                                if not stock_df.empty and "日期" in stock_df.columns:
                                    try:
                                        stock_quote_date = self._normalize_decision_date(
                                            stock_df.iloc[-1].get("日期")
                                        )
                                    except (TypeError, ValueError):
                                        stock_quote_date = None
                                stock_market_session_current = (
                                    market_session_current
                                    and stock_quote_date
                                    == prepared_market.expected_market_date
                                )
                                if (
                                    cutoff_at is not None
                                    and stock_market_session_current
                                    and callable(loader)
                                ):
                                    try:
                                        observation, diagnostics = loader(
                                            stock_code=request.stock_code,
                                            cutoff_at=cutoff_at,
                                            expected_market_date=prepared_market.expected_market_date,
                                        )
                                    except Exception as exc:
                                        logger.error("current PE read failed: %s", exc)
                                        raise
                                else:
                                    if prepared_market.expected_market_date is None:
                                        diagnostics = (
                                            "current_pe_expected_market_date_unverified",
                                        )
                                    elif not market_session_current:
                                        diagnostics = (
                                            "current_pe_market_data_session_not_current:"
                                            f"{prepared_market.market_calendar_status or 'unverified'}:"
                                            f"expected={prepared_market.expected_market_date}:"
                                            f"observed={prepared_market.data_date or 'missing'}",
                                        )
                                    elif not stock_market_session_current:
                                        diagnostics = (
                                            "current_pe_stock_quote_date_not_expected_session:"
                                            f"{request.stock_code}:"
                                            f"expected={prepared_market.expected_market_date}:"
                                            f"observed={stock_quote_date or 'missing'}",
                                        )
                                    else:
                                        diagnostics = ("current_pe_reader_unavailable",)
                                self.last_run_context[
                                    "fundamental_input_diagnostics"
                                ].extend(diagnostics)
                                fact = project_current_pe_observation(observation)
                                if observation is not None and fact.value is not None:
                                    self.last_run_context["fundamental_inputs"].append(
                                        {
                                            "stock_code": request.stock_code,
                                            "metric": "pe",
                                            "scope": request.fundamental_input_scope,
                                            "expected_market_date": prepared_market.expected_market_date,
                                            "market_calendar_session_date": observation.market_calendar_session_date.isoformat(),
                                            "market_calendar_reason_code": observation.market_calendar_reason_code,
                                            "as_of_date": observation.as_of_date.isoformat(),
                                            "available_at": observation.available_at.isoformat(),
                                            "availability_basis": observation.availability_basis,
                                            "source": observation.source,
                                            "source_version": observation.source_version,
                                            "raw_response_sha256": observation.raw_response_sha256,
                                            "market": observation.market,
                                            "formal_pit_eligible": False,
                                            "value": str(observation.value),
                                        }
                                    )
                                return SourceFactResponse(request=request, value=fact)
                            try:
                                observation = input_session.load_pe(
                                    stock_code=request.stock_code,
                                    decision_date=request.decision_date.isoformat(),
                                )
                            except Exception as exc:
                                logger.error("查詢 PE 失敗: %s", exc)
                                raise
                            fact = project_pe_observation(observation)
                            if (
                                observation is not None
                                and observation.value is not None
                                and fact.value is not None
                            ):
                                self.last_run_context["fundamental_inputs"].append(
                                    {
                                        "stock_code": request.stock_code,
                                        "metric": "pe",
                                        **observation.as_context(),
                                    }
                                )
                            return SourceFactResponse(request=request, value=fact)

                        if request.kind is SourceFactKind.MONTHLY_REVENUE:
                            if request.fundamental_input_scope == "natural_current_observation":
                                cutoff_at = request.current_observation_cutoff_at
                                loader = getattr(
                                    input_session,
                                    "load_current_monthly_revenues",
                                    None,
                                )
                                current_records: tuple[
                                    CurrentObservedMonthlyRevenueInput, ...
                                ] = ()
                                comparison_baseline: CurrentObservedMonthlyRevenueInput | None = None
                                monthly_diagnostics: tuple[str, ...] = ()
                                if cutoff_at is not None and callable(loader):
                                    try:
                                        current_result = loader(
                                            stock_code=request.stock_code,
                                            cutoff_at=cutoff_at,
                                        )
                                    except Exception as exc:
                                        logger.error(
                                            "current monthly revenue read failed: %s",
                                            exc,
                                        )
                                        raise
                                    monthly_diagnostics = tuple(current_result.diagnostics)
                                    source_row_count = getattr(
                                        current_result,
                                        "diagnostic_source_row_count",
                                        0,
                                    )
                                    comparator_row_count = getattr(
                                        current_result,
                                        "diagnostic_comparator_row_count",
                                        0,
                                    )
                                    if (
                                        type(source_row_count) is not int
                                        or source_row_count < 0
                                        or type(comparator_row_count) is not int
                                        or comparator_row_count < 0
                                    ):
                                        raise TypeError(
                                            "current monthly diagnostic source counts must be non-negative integers"
                                        )
                                    self.last_run_context[
                                        "fundamental_input_diagnostic_source_row_count"
                                    ] += source_row_count
                                    self.last_run_context[
                                        "fundamental_input_diagnostic_comparator_row_count"
                                    ] += comparator_row_count
                                    if current_result.status == "ready":
                                        current_records = tuple(
                                            current_result.observations
                                        )
                                        comparison_baseline = getattr(
                                            current_result, "comparison_baseline", None
                                        )
                                        lineage_records = list(current_records)
                                        if comparison_baseline is not None:
                                            lineage_records.append(comparison_baseline)
                                        self.last_run_context[
                                            "current_fundamental_observations"
                                        ].extend(
                                            {
                                                "stock_code": record.stock_code,
                                                "metric": "monthly_revenue",
                                                "scope": request.fundamental_input_scope,
                                                "input_role": (
                                                    "same_report_prior_year_comparison_baseline"
                                                    if record is comparison_baseline
                                                    else "reported_period_value"
                                                ),
                                                "parent_report_period": record.parent_report_period,
                                                "period": record.period,
                                                "value": str(record.revenue),
                                                "unit": record.unit,
                                                "period_basis": record.period_basis,
                                                "basis_verified": record.basis_verified,
                                                "aggregate_feature_eligible": record.aggregate_feature_eligible,
                                                "observed_at": record.observed_at.isoformat(),
                                                "source_available_at": (
                                                    record.source_available_at.isoformat()
                                                    if record.source_available_at is not None
                                                    else None
                                                ),
                                                "available_at": record.available_at.isoformat(),
                                                "availability_basis": record.availability_basis,
                                                "source": record.source,
                                                "source_version": record.source_version,
                                                "raw_source_sha256": record.raw_source_sha256,
                                                "market": record.market,
                                                "formal_pit_eligible": False,
                                            }
                                            for record in lineage_records
                                        )
                                        if current_result.latest_period is not None:
                                            year_text, month_text = (
                                                current_result.latest_period.split("-")
                                            )
                                            prior_period = (
                                                f"{int(year_text) - 1:04d}-{int(month_text):02d}"
                                            )
                                            baseline_period_blocked = (
                                                prior_period in current_result.blocked_periods
                                            )
                                            if comparison_baseline is None and not any(
                                                record.period == prior_period
                                                for record in current_records
                                            ):
                                                monthly_diagnostics = (
                                                    *monthly_diagnostics,
                                                    (
                                                        (
                                                            "current_monthly_revenue_exact_prior_year_baseline_blocked:"
                                                            if baseline_period_blocked
                                                            else "current_monthly_revenue_exact_prior_year_baseline_missing:"
                                                        )
                                                        + f"{request.stock_code}:{prior_period}"
                                                    ),
                                                )
                                else:
                                    monthly_diagnostics = (
                                        "current_monthly_revenue_reader_unavailable",
                                    )
                                self.last_run_context[
                                    "fundamental_input_diagnostics"
                                ].extend(monthly_diagnostics)
                                projection_records = list(current_records)
                                if comparison_baseline is not None:
                                    projection_records.append(comparison_baseline)
                                facts = project_current_monthly_revenue_records(
                                    projection_records,
                                    (),
                                    stock_code=request.stock_code,
                                )
                                self.last_run_context["fundamental_inputs"].extend(
                                    {
                                        "stock_code": request.stock_code,
                                        "metric": "monthly_revenue",
                                        "scope": request.fundamental_input_scope,
                                        "input_role": (
                                            "same_report_prior_year_comparison_baseline"
                                            if record.source_version.startswith(
                                                "mops-current-revenue-yoy-comparator.v1:"
                                            )
                                            else "reported_period_value"
                                        ),
                                        "parent_report_period": record.parent_report_period,
                                        "period": record.period,
                                        "available_date": record.available_date.isoformat(),
                                        "available_at": (
                                            record.available_at.isoformat()
                                            if record.available_at is not None
                                            else None
                                        ),
                                        "observed_at": (
                                            record.observed_at.isoformat()
                                            if record.observed_at is not None
                                            else None
                                        ),
                                        "source_available_at": (
                                            record.source_available_at.isoformat()
                                            if record.source_available_at is not None
                                            else None
                                        ),
                                        "availability_basis": record.availability_basis,
                                        "source": record.source,
                                        "source_version": record.source_version,
                                        "raw_source_sha256": record.raw_source_sha256,
                                        "market": record.market,
                                        "unit": record.unit,
                                        "period_basis": record.period_basis,
                                        "basis_verified": record.basis_verified,
                                        "aggregate_feature_eligible": record.aggregate_feature_eligible,
                                        "formal_pit_eligible": record.formal_pit_eligible,
                                        "value": str(record.revenue),
                                    }
                                    for record in facts.records
                                )
                                return SourceFactResponse(
                                    request=request,
                                    value=facts,
                                )
                            try:
                                records = self._load_governed_monthly_revenues(
                                    input_session=input_session,
                                    stock_code=request.stock_code,
                                    decision_date=request.decision_date,
                                )
                            except Exception as exc:
                                logger.error("查詢受治理月營收失敗: %s", exc)
                                raise
                            if records:
                                self.last_run_context["fundamental_inputs"].extend(
                                    {
                                        "stock_code": request.stock_code,
                                        "metric": "monthly_revenue",
                                        "period": record.period,
                                        "available_date": (
                                            record.available_date.isoformat()
                                        ),
                                        "source": record.source,
                                        "source_version": record.source_version,
                                        "value": str(record.revenue),
                                    }
                                    for record in sorted(
                                        records,
                                        key=lambda item: (
                                            item.period,
                                            item.available_date,
                                            item.source_version,
                                        ),
                                    )
                                )
                            return SourceFactResponse(
                                request=request,
                                value=project_monthly_revenue_records(records),
                            )

                        if request.kind is SourceFactKind.INDUSTRY_CONTEXT:
                            prepare_output_row()
                            if not cutoff:
                                self._record_current_industry_mapping_use(
                                    "current_industry_context_display_reason"
                                )
                            stock_industries = self.industry_mapper.get_stock_industries(
                                request.stock_code
                            )
                            industry_display = (
                                ', '.join(stock_industries[:2])
                                if stock_industries
                                else '未知'
                            )
                            if len(stock_industries) > 2:
                                industry_display += '...'
                            reasons = self.reason_engine.generate_reasons(
                                latest_row, config
                            )
                            industry_fact = project_industry_context_fact(
                                tuple(stock_industries)
                            )
                            if stock_industries:
                                for industry in stock_industries[:1]:
                                    if not cutoff:
                                        self._record_current_industry_mapping_use(
                                            "current_industry_index_performance_for_reason"
                                        )
                                    industry_perf = (
                                        self.industry_mapper.get_industry_performance(
                                            industry,
                                            date=decision_date_text,
                                        )
                                    )
                                    if industry_perf:
                                        industry_fact = project_industry_context_fact(
                                            tuple(stock_industries), industry_perf
                                        )
                                        industry_reason = build_industry_performance_reason(
                                            industry_fact
                                        )
                                        if industry_reason is not None:
                                            reasons.append(
                                                project_legacy_industry_reason(
                                                    industry_reason
                                                )
                                            )
                            industry_readback["loaded"] = True
                            industry_readback["industries"] = tuple(
                                stock_industries
                            )
                            industry_readback["display"] = industry_display
                            industry_readback["reasons"] = reasons
                            return SourceFactResponse(
                                request=request,
                                value=industry_fact,
                            )
                        raise ValueError(f"unsupported source fact kind: {request.kind}")

                    candidate_outcome = evaluate_candidate_staged(
                        staged_evaluator,
                        candidate_seed,
                        candidate_policy,
                        read_candidate_fact,
                    )
                    if candidate_outcome.reason_codes not in {
                        ("pending_final_selection",),
                        ("total_score_missing_or_nonfinite",),
                    }:
                        row = self._matrix_row(
                            stock_code=stock_code_text,
                            stock_name=stock_name_text,
                            status=candidate_outcome.status,
                            reason_codes=list(candidate_outcome.reason_codes),
                            quality=candidate_outcome.quality,
                            stage=candidate_outcome.stage,
                            threshold_name=candidate_outcome.threshold_name,
                            observed_value=candidate_outcome.observed_value,
                            required_value=candidate_outcome.required_value,
                            threshold_mode=threshold_mode,
                            warnings=list(candidate_outcome.warnings),
                        )
                        self.last_screening_matrix.append(row)
                        legacy_matrix_codes.append(stock_code_text)
                        remember_candidate(
                            candidate_outcome,
                            stock_name=stock_name_text,
                        )
                        if candidate_outcome.status == "degraded":
                            stats['skipped_exception'] += 1
                        else:
                            stats['skipped_no_result'] += 1
                        continue

                    prepare_output_row()

                    # 獲取股票所屬產業
                    if industry_readback["loaded"]:
                        stock_industries = list(industry_readback["industries"])
                        industry_display = str(industry_readback["display"])
                        reasons = industry_readback["reasons"]
                    else:
                        if cutoff:
                            stock_industries = []
                        else:
                            self._record_current_industry_mapping_use(
                                "current_fallback_display_reason"
                            )
                            stock_industries = self.industry_mapper.get_stock_industries(
                                stock_code
                            )
                        industry_display = ', '.join(stock_industries[:2]) if stock_industries else '未知'
                        if len(stock_industries) > 2:
                            industry_display += '...'

                        # 生成推薦理由（包含市場狀態和產業信息）
                        reasons = self.reason_engine.generate_reasons(latest_row, config)

                        # 無可用 decision date 的 legacy fallback；有效日期都由 staged request 讀取。
                        if stock_industries:
                            for industry in stock_industries[:1]:
                                if not cutoff:
                                    self._record_current_industry_mapping_use(
                                        "current_industry_index_performance_for_reason"
                                    )
                                industry_perf = self.industry_mapper.get_industry_performance(
                                    industry, date=decision_date_text
                                )
                                if industry_perf:
                                    industry_fact = project_industry_context_fact(
                                        tuple(stock_industries), industry_perf
                                    )
                                    industry_reason = build_industry_performance_reason(
                                        industry_fact
                                    )
                                    if industry_reason is not None:
                                        reasons.append(
                                            project_legacy_industry_reason(
                                                industry_reason
                                            )
                                        )

                    reason_text = self.reason_engine.format_reason_text(reasons, max_reasons=3)

                    # 使用 FinalScore（含 Regime Match Factor）作為排序依據
                    final_score = latest_row.get(
                        'FinalScore',
                        latest_row.get('TotalScore', latest_row.get('綜合評分'))
                    )
                    final_score_result = classify_final_score(
                        FinalScoreFacts(
                            invocation_id=staged_invocation_id,
                            stock_code=stock_code_text,
                            score=project_optional_final_score(final_score),
                        )
                    )
                    if (
                        final_score_result.invocation_id != staged_invocation_id
                        or final_score_result.stock_code != stock_code_text
                    ):
                        raise RuntimeError("final score result candidate identity 不一致")
                    if final_score_result.error is not None:
                        raise _FinalizationFailure(final_score_result.error)
                    if final_score_result.disposition is FinalScoreDisposition.MISSING:
                        if (
                            candidate_outcome.invocation_id != staged_invocation_id
                            or candidate_outcome.stock_code != stock_code_text
                            or candidate_outcome.status != "missing"
                            or candidate_outcome.quality != "missing"
                            or candidate_outcome.stage != "strategy_evaluation"
                            or candidate_outcome.reason_codes
                            != ("total_score_missing_or_nonfinite",)
                        ):
                            raise RuntimeError(
                                "missing final score 與 staged evaluator outcome 不一致"
                            )
                        row = self._matrix_row(
                            stock_code=stock_code_text, stock_name=stock_name_text,
                            status=candidate_outcome.status,
                            reason_codes=list(candidate_outcome.reason_codes),
                            quality=candidate_outcome.quality,
                            stage=candidate_outcome.stage,
                            threshold_name=candidate_outcome.threshold_name,
                            observed_value=candidate_outcome.observed_value,
                            required_value=candidate_outcome.required_value,
                            threshold_mode=threshold_mode,
                            warnings=list(candidate_outcome.warnings),
                        )
                        self.last_screening_matrix.append(row)
                        legacy_matrix_codes.append(stock_code_text)
                        stats['skipped_no_result'] += 1
                        remember_candidate(
                            candidate_outcome,
                            stock_name=stock_name_text,
                        )
                        continue

                    if final_score_result.score is None:
                        raise RuntimeError(
                            "ready final score 缺少 canonical Decimal"
                        )
                    regime_enabled = bool(config.get('regime', None))
                    regime_result = evaluate_regime_match(
                        RegimeMatchFacts(
                            invocation_id=staged_invocation_id,
                            stock_code=stock_code_text,
                            final_score=final_score_result.score,
                            enabled=regime_enabled,
                            total_score=(
                                project_required_legacy_decimal(
                                    latest_row.get('TotalScore', 0)
                                )
                                if regime_enabled
                                else None
                            ),
                        )
                    )
                    if (
                        regime_result.invocation_id != staged_invocation_id
                        or regime_result.stock_code != stock_code_text
                    ):
                        raise RuntimeError("regime result candidate identity 不一致")
                    if regime_result.error is not None:
                        raise _FinalizationFailure(regime_result.error)
                    regime_match = regime_result.regime_match

                    legacy_stock_name = latest_row.get(
                        '證券名稱', stock_df.iloc[-1].get('證券名稱', stock_code)
                    )
                    legacy_indicator_score = latest_row.get('IndicatorScore', 0)
                    legacy_pattern_score = latest_row.get('PatternScore', 0)
                    legacy_volume_score = latest_row.get('VolumeScore', 0)
                    candidate_outcome = finalize_candidate_item(
                        candidate_outcome,
                        RecommendationItemFacts(
                            invocation_id=staged_invocation_id,
                            stock_code=stock_code_text,
                            stock_name=str(legacy_stock_name),
                            close_price=(
                                to_decimal(
                                    latest_row.get(
                                        close_col,
                                        stock_df.iloc[-1].get(close_col, 0),
                                    )
                                )
                                if close_col
                                else Decimal("0")
                            ),
                            price_change=to_decimal(price_change),
                            indicator_score=to_decimal(legacy_indicator_score),
                            pattern_score=to_decimal(legacy_pattern_score),
                            volume_score=to_decimal(legacy_volume_score),
                            industry=industry_display,
                            reason_text=reason_text,
                            reasons=reason_tags_from_legacy_reasons(reasons),
                            universe_policy_id=str(
                                universe_identity["universe_policy_id"]
                            ),
                            universe_snapshot_id=str(
                                universe_identity["universe_snapshot_id"]
                            ),
                            universe_as_of_date=(
                                date.fromisoformat(decision_cutoff)
                                if decision_cutoff
                                else None
                            ),
                            universe_members_hash=str(
                                universe_identity[
                                    "universe_snapshot_selected_codes_hash"
                                ]
                            ),
                            regime_match=regime_match,
                        ),
                    )
                    canonical_item = candidate_outcome.item
                    if canonical_item is None:
                        raise RuntimeError(
                            "successful recommendation is missing evaluator item"
                        )
                    recommendation = RecommendationDTO(
                        stock_code=canonical_item.stock_code,
                        stock_name=legacy_stock_name,
                        close_price=cast(Decimal, canonical_item.close_price),
                        price_change=price_change,
                        total_score=final_score,
                        indicator_score=legacy_indicator_score,
                        pattern_score=legacy_pattern_score,
                        volume_score=legacy_volume_score,
                        recommendation_reasons=canonical_item.reason_text or "",
                        industry=canonical_item.industry or "",
                        regime_match=cast(bool, canonical_item.regime_match),
                    )
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
                    remember_candidate(
                        candidate_outcome,
                        stock_name=str(recommendation.stock_name),
                        industry=industry_display,
                        total_score_text=str(final_score),
                    )
                    all_recommendations.append(recommendation)
                    self.last_screening_matrix.append(row)
                    legacy_matrix_codes.append(stock_code_text)
                    stats['success'] += 1
                else:
                    stats['skipped_no_result'] += 1

            except Exception as e:
                # 跳過處理失敗的股票
                stats['skipped_exception'] += 1
                failure = (
                    e.error
                    if isinstance(e, _FinalizationFailure)
                    else StrategyEvaluationError(
                        error_type=type(e).__name__,
                        message=str(e),
                    )
                )
                exception_seed = CandidateSeed(
                    invocation_id=staged_invocation_id,
                    stock_code=stock_code_text,
                    stock_name=stock_name_text,
                    history_rows=len(stock_df),
                    strategy_result_present=False,
                    strategy_error=failure,
                )
                exception_policy = RecommendationEvaluationPolicy(
                    invocation_id=staged_invocation_id,
                    decision_date=None,
                    decision_date_text=str(decision_cutoff or ""),
                )
                exception_step = staged_evaluator.start(
                    exception_seed, exception_policy
                )
                if exception_step.outcome is None:
                    raise RuntimeError(
                        "screening exception unexpectedly requested a source fact"
                    ) from e
                remember_candidate(
                    exception_step.outcome,
                    stock_name=stock_name_text,
                )
                row = self._matrix_row(
                    stock_code=stock_code_text,
                    stock_name=stock_name_text,
                    status="degraded",
                    reason_codes=["screening_exception"],
                    quality="degraded",
                    stage="strategy_evaluation",
                    threshold_name=failure.error_type,
                    observed_value=failure.message,
                    required_value="successful_evaluation",
                    threshold_mode=threshold_mode,
                    warnings=[f"screening_exception:{failure.error_type}"],
                )
                self.last_screening_matrix.append(row)
                legacy_matrix_codes.append(stock_code_text)
                # 記錄前3個異常的詳細信息（避免日誌過多）
                if stats['skipped_exception'] <= 3:
                    import logging
                    import traceback
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"處理股票 {stock_code} 時發生異常: {failure.message}\n"
                        f"異常類型: {failure.error_type}\n"
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
            empty_policy = make_batch_policy(str(decision_cutoff or ""))
            return publish_body_result(
                evaluation_result=evaluate_candidates(empty_policy),
                policy=empty_policy,
                eligible_universe_size=0,
                legacy_recommendations=[],
            )
        if not df.empty and "日期" in df.columns:
            latest_date_str = df["日期"].max().strftime("%Y-%m-%d")
        eligible_universe_date = decision_cutoff or latest_date_str
        batch_policy = make_batch_policy(eligible_universe_date)
        evaluation_result = evaluate_candidates(batch_policy)

        eligible_universe_size = len(all_recommendations)
        recommendations_by_code = {
            rec.stock_code: rec for rec in all_recommendations
        }
        items_by_code = {
            item.stock_code: item for item in evaluation_result.decision.items
        }

        selected_codes = tuple(
            item.stock_code for item in evaluation_result.decision.items
        )
        all_recommendations = [
            recommendations_by_code[code] for code in selected_codes
        ]
        for rec in all_recommendations:
            item = items_by_code.get(rec.stock_code)
            if item is None:
                raise RuntimeError(
                    f"decision evaluator omitted selected item for {rec.stock_code}"
                )
            rec.threshold_mode = item.threshold_mode or threshold_mode
            rec.eligible_universe_size = item.eligible_universe_size
            rec.eligible_universe_date = (
                item.eligible_universe_date.isoformat()
                if item.eligible_universe_date is not None
                else None
            )
            rec.ranking_method = item.ranking_method
            rec.score_percentile_bp = item.score_percentile_bp

        decision_clock = (
            personal_decision_clock.isoformat(timespec="microseconds")
            if personal_decision_clock is not None
            else datetime.now(timezone.utc).isoformat(timespec="microseconds")
        )
        self._personalization_execution_clocks["decision_at"] = decision_clock
        # Persist the actual producer decision clock even when an optional
        # calibration receipt is unavailable.  Downstream forward-custody
        # checks must not infer decision time from the later saved
        # ``RecommendationResultDTO.created_at`` timestamp.
        self.last_run_context["decision_at"] = decision_clock
        self._apply_recommendation_calibration(
            all_recommendations,
            selected_items=evaluation_result.decision.items,
            decision_date=decision_cutoff or latest_date_str,
            selection_authority="rule_top_n",
            selection_score_kind="rule_total_score",
            selection_percentile_kind="rule_percentile",
            top_n_changed_by_model=False,
        )
        return publish_body_result(
            evaluation_result=evaluation_result,
            policy=batch_policy,
            eligible_universe_size=eligible_universe_size,
            legacy_recommendations=all_recommendations,
        )

    def _run_recommendation_body(
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
        input_session: RecommendationInputSession | None = None,
    ) -> List[RecommendationDTO]:
        """Materialize the canonical body result through the legacy list ABI."""

        body_result = self._run_recommendation_body_result(
            config=config,
            max_stocks=max_stocks,
            top_n=top_n,
            as_of_date=as_of_date,
            universe=universe,
            result_id=result_id,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
            input_session=input_session,
        )
        return [snapshot.materialize() for snapshot in body_result.legacy_recommendations]

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
        regime_result = self.regime_service.detect_regime()
        regime = regime_result.regime
        confidence = regime_result.confidence
        details = regime_result.details

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
        return self.regime_service.get_strategy_config(regime)

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

