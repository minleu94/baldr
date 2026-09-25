"""R016 唯讀消費端使用的推薦 execution query 接線。"""

from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.contracts import ExecutionStatus
from app_module.recommendation.queries import RecommendationExecutionQueries
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection
from data_module.result_artifact_store import ResultArtifactStore


def recommendation_runs_dir(config: Any) -> Path:
    """解析 caller-owned runs 路徑，不建立目錄或資料庫。"""

    resolver = getattr(config, "resolve_output_path", None)
    if callable(resolver):
        return Path(resolver("recommendation/runs"))
    return Path(config.output_root) / "recommendation" / "runs"


def build_recommendation_execution_queries(
    config: Any,
    *,
    runs_dir: Path | None = None,
) -> RecommendationExecutionQueries:
    """建立只讀 query seam；store/persistence 建構子本身不觸碰磁碟。"""

    runs_dir = Path(runs_dir) if runs_dir is not None else recommendation_runs_dir(config)
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    return RecommendationExecutionQueries(RecommendationExecutionPersistence(store))


def execution_result_config(execution: Any) -> dict[str, Any]:
    """讀取 execution 內保存且已由 contract 驗證的 result config。"""

    snapshot = execution.context.result_config_snapshot
    if snapshot is None:
        return {}
    payload = json.loads(snapshot.raw_result_config_json)
    return dict(payload) if isinstance(payload, Mapping) else {}


def verified_saved_calibration_projections(
    read_model: RecommendationExecutionReadModel,
) -> dict[str, RecommendationCalibrationProjection]:
    """投影 query 已驗證的 receipt rows；缺欄、失配或 legacy 時不造 projection。"""

    execution = read_model.execution
    if execution is None or read_model.ml_read_status != "verified":
        return {}
    expected_fields = {item.name for item in fields(RecommendationCalibrationProjection)}
    result: dict[str, RecommendationCalibrationProjection] = {}
    row_index = 0
    for binding in execution.ml_receipt_refs:
        receipt_trace = (
            f"ml_receipt_id:{binding.receipt_ref.reference_id}",
            f"ml_receipt_hash:{binding.receipt_hash}",
            f"ml_candidate_id:{binding.model_candidate_id}",
            f"ml_decision_date:{binding.decision_date.isoformat()}",
            *(
                (f"ml_cost_scenario_hash:{binding.cost_scenario_hash}",)
                if binding.cost_scenario_hash is not None
                else ()
            ),
        )
        for expected_code in binding.projected_stock_codes:
            if row_index >= len(read_model.ml_projection_rows):
                return {}
            raw = read_model.ml_projection_rows[row_index]
            row_index += 1
            if set(raw) != expected_fields:
                continue
            stock_code = raw.get("stock_code")
            trace = raw.get("source_trace")
            warnings = raw.get("warnings")
            if (
                stock_code != expected_code
                or type(stock_code) is not str
                or not isinstance(trace, (list, tuple))
                or any(type(item) is not str for item in trace)
                or not isinstance(warnings, (list, tuple))
                or any(type(item) is not str for item in warnings)
                or not _valid_calibration_projection_row(raw)
            ):
                continue
            payload = dict(raw)
            payload["source_trace"] = tuple(trace) + receipt_trace
            payload["warnings"] = tuple(warnings)
            for name in (
                "training_provenance",
                "inference_provenance",
                "provenance_compatibility",
            ):
                if not isinstance(payload.get(name), Mapping):
                    break
            else:
                try:
                    projection = RecommendationCalibrationProjection(**cast(Any, payload))
                except (TypeError, ValueError):
                    continue
                result[stock_code] = projection
    if row_index != len(read_model.ml_projection_rows):
        return {}
    return result


def select_latest_saved_recommendation(
    read_models: tuple[RecommendationExecutionReadModel, ...],
) -> tuple[RecommendationExecutionReadModel | None, str | None]:
    """選取 query 清單中的最新結果，保留 namespace 時鐘的既有排序界線。"""

    if not read_models:
        return None, None
    canonical = tuple(item for item in read_models if item.execution is not None)
    legacy = tuple(item for item in read_models if item.legacy_result is not None)
    if len(canonical) + len(legacy) != len(read_models):
        return None, "recommendation_latest_selection_unsupported_read_model"
    if canonical and not legacy:
        # RecommendationExecutionQueries.list() 已依 canonical persisted_at 排序。
        return canonical[0], None
    if legacy and not canonical:
        # Query 的 legacy list 沿用 runs.created_at DESC / result_id ASC。
        return legacy[0], None

    clocks: list[tuple[RecommendationExecutionReadModel, datetime]] = []
    for item in read_models:
        persisted_at = item.persisted_at
        if (
            not isinstance(persisted_at, datetime)
            or persisted_at.tzinfo is None
            or persisted_at.utcoffset() is None
        ):
            return None, "recommendation_latest_selection_ambiguous_clock"
        clocks.append((item, persisted_at.astimezone(timezone.utc)))
    latest_time = max(timestamp for _item, timestamp in clocks)
    tied = [item for item, timestamp in clocks if timestamp == latest_time]
    return min(tied, key=lambda item: item.result_id), None


def saved_recommendation_capture_projection(
    read_model: RecommendationExecutionReadModel,
) -> dict[str, object]:
    """投影 coverage/status consumers 所需的已保存 capture 欄位。"""

    result: dict[str, object] = {"result_id": read_model.result_id}
    execution = read_model.execution
    if execution is not None:
        result["created_at"] = (
            execution.context.created_at.isoformat()
            if execution.context.created_at is not None
            else (
                read_model.persisted_at.isoformat()
                if read_model.persisted_at is not None
                else None
            )
        )
        result["decision_date"] = (
            execution.context.as_of_date.isoformat()
            if execution.context.as_of_date is not None
            else (
                execution.request.as_of_date.isoformat()
                if execution.request.as_of_date is not None
                else None
            )
        )
        result["data_as_of_date"] = execution_result_config(execution).get(
            "data_as_of_date"
        )
        result["recommendations_count"] = (
            len(execution.decision.items) if execution.decision is not None else None
        )
        event = next(
            (
                item
                for item in execution.events
                if item.event_type == "legacy_negative_evidence_capture"
            ),
            None,
        )
        details: Mapping[str, object] = (
            event.details
            if event is not None and event.details is not None
            else {}
        )
        for target, source in (
            ("screening_matrix_json", "screening_matrix"),
            ("excluded_candidates_json", "excluded_candidates"),
            ("why_not_payload_json", "why_not_payload"),
            ("liquidity_gate_payload_json", "liquidity_gate_payload"),
            ("exclusion_quality", "exclusion_quality"),
            ("exclusion_warnings_json", "exclusion_warnings"),
        ):
            result[target] = details.get(source)
        return result

    legacy = read_model.legacy_result
    if legacy is None:
        raise ValueError("recommendation read model lacks canonical and legacy result")
    result.update(
        {
            "created_at": legacy.created_at,
            "decision_date": legacy.run_context.get("as_of_date"),
            "data_as_of_date": (
                legacy.run_context.get("data_as_of_date")
                or legacy.run_context.get("data_date")
            ),
            "recommendations_count": len(legacy.recommendations),
            "screening_matrix_json": legacy.screening_matrix_json,
            "excluded_candidates_json": legacy.excluded_candidates_json,
            "why_not_payload_json": legacy.why_not_payload_json,
            "liquidity_gate_payload_json": legacy.liquidity_gate_payload_json,
            "exclusion_quality": legacy.exclusion_quality,
            "exclusion_warnings_json": legacy.exclusion_warnings_json,
        }
    )
    return result


def canonical_scheduled_decision_date(
    read_model: RecommendationExecutionReadModel,
) -> str | None:
    """只辨認 result config 明確標記 scheduled_snapshot 的 canonical 日期。"""

    execution = read_model.execution
    if (
        execution is None
        or execution.status is not ExecutionStatus.COMPLETED
        or execution.decision is None
    ):
        return None
    config = execution_result_config(execution)
    if config.get("scheduled_snapshot") is not True:
        return None
    value = config.get("decision_date")
    if type(value) is not str:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    if parsed.isoformat() != value:
        return None
    sealed_dates = tuple(
        candidate
        for candidate in (
            execution.context.as_of_date,
            execution.request.as_of_date,
        )
        if candidate is not None
    )
    if any(candidate != parsed for candidate in sealed_dates):
        return None
    return parsed.isoformat()


def canonical_manual_decision_date(
    read_model: RecommendationExecutionReadModel,
) -> str | None:
    """辨認具明確 Qt manual provenance 的 canonical execution 日期。"""

    execution = read_model.execution
    if (
        execution is None
        or execution.status is not ExecutionStatus.COMPLETED
        or execution.decision is None
    ):
        return None
    snapshot = execution.request.config_snapshot
    if snapshot is None:
        return None
    try:
        config = json.loads(snapshot.raw_config_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(config, Mapping) or config.get("manual_qt_snapshot") is not True:
        return None
    requested_date = execution.request.as_of_date
    context_date = execution.context.as_of_date
    if requested_date is not None and context_date is not None and requested_date != context_date:
        return None
    decision_date = requested_date or context_date
    return decision_date.isoformat() if decision_date is not None else None


def _valid_calibration_projection_row(row: Mapping[str, object]) -> bool:
    integer_fields = {
        "ranking_score_bp",
        "ranking_percentile_bp",
        "calibrated_probability_bp",
        "after_cost_profit_probability_bp",
        "probability_baseline_probability_bp",
        "raw_calibrated_probability_bp",
        "raw_after_cost_profit_probability_bp",
        "sample_size",
        "cost_basis_bp",
        "research_order_quantity_shares",
    }
    optional_text_fields = {
        "cost_policy_id",
        "cost_policy_version",
        "cost_scenario_hash",
        "policy_estimate_date",
        "research_order_amount_twd",
        "projection_contract_hash",
    }
    required_text_fields = {
        "stock_code",
        "ranking_method",
        "calibrated_probability_status",
        "after_cost_profit_probability_status",
        "confidence_tier",
        "evidence_confidence",
        "horizon",
        "cost_basis",
        "model_version",
        "dataset_version",
        "probability_transform_id",
        "probability_baseline_id",
        "probability_baseline_kind",
        "status",
        "cost_scenario_id",
        "cost_scenario_version",
        "cost_estimate_source",
        "provenance_status",
        "selection_authority",
        "selection_score_kind",
        "selection_percentile_kind",
        "model_ranking_kind",
        "label_registry_hash",
        "label_contract_id",
        "return_basis",
    }
    if any(
        value is not None and (type(value) is not int or isinstance(value, bool))
        for name in integer_fields
        if (value := row.get(name)) is not None
    ):
        return False
    if any(type(row.get(name)) is not str for name in required_text_fields):
        return False
    if any(
        row.get(name) is not None and type(row.get(name)) is not str
        for name in optional_text_fields
    ):
        return False
    return all(
        isinstance(row.get(name), Mapping)
        for name in (
            "training_provenance",
            "inference_provenance",
            "provenance_compatibility",
        )
    )


__all__ = (
    "canonical_manual_decision_date",
    "canonical_scheduled_decision_date",
    "build_recommendation_execution_queries",
    "execution_result_config",
    "recommendation_runs_dir",
    "saved_recommendation_capture_projection",
    "select_latest_saved_recommendation",
    "verified_saved_calibration_projections",
)
