"""R016 唯讀消費端使用的推薦 execution query 接線。"""

from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Mapping, TypedDict, cast

from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.contracts import ExecutionStatus
from app_module.recommendation.queries import RecommendationExecutionQueries
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation.queries import SQLiteLegacyRecommendationRawByteReader
from app_module.recommendation.negative_evidence_projection import (
    LEGACY_NEGATIVE_EVIDENCE_EVENT_TYPE,
    NegativeEvidenceProjectionError,
    assert_legacy_event_matches_projection,
    count_legacy_assessment_outcomes,
    legacy_history_event_projection,
    project_canonical_negative_evidence,
)
from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection
from data_module.result_artifact_store import ResultArtifactStore
from data_module.legacy_recommendation_run_locator import (
    LegacyRecommendationCustodyEvidencePin,
)


# 這筆 2026-09-23 遷移推薦只接受既有 candidate 的逐筆身份證據；
# 固定候選 bytes、大小及身份欄位，其他 legacy rows 一律維持原拒讀行為。
class _LegacyRecommendationCustodySpec(TypedDict):
    relative_path: Path
    sha256: str
    size_bytes: int
    record_pointer: tuple[str, ...]


_LEGACY_CUSTODY_EVIDENCE: dict[str, _LegacyRecommendationCustodySpec] = {
    "scheduled_rec_20260909_051003": {
        "relative_path": Path("output/forward_position_thesis/2026-09-09/candidate_scheduled_rec_20260909_051003_1304.json"),
        "sha256": "sha256:f1049632e3de07918787b94a339f56f35a56c235194c82e6e719a6e6eea0a6e9",
        "size_bytes": 3705,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260910_051003": {
        "relative_path": Path("output/forward_position_thesis/2026-09-10/candidate_scheduled_rec_20260910_051003_1454.json"),
        "sha256": "sha256:f17d42b41cf831a7d8dd1d31433b7fda3e89b750e4cdd1a064a6d2da721b12c4",
        "size_bytes": 3739,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260911_051003": {
        "relative_path": Path("output/forward_position_thesis/2026-09-11/candidate_scheduled_rec_20260911_051003_1528.json"),
        "sha256": "sha256:8c6b866b8d722b96b8befc4a11803ae18cff6df91bb7d21935e16385dcfd1db3",
        "size_bytes": 3743,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260912_051003": {
        "relative_path": Path("output/forward_position_thesis/2026-09-12/candidate_scheduled_rec_20260912_051003_1528.json"),
        "sha256": "sha256:2405c3e1a8b1c1be8716a6d6e528f91188288b915e4e877cd3ae2cbb1c4c17e5",
        "size_bytes": 3743,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260913_051004": {
        "relative_path": Path("output/forward_position_thesis/2026-09-13/candidate_scheduled_rec_20260913_051004_1528.json"),
        "sha256": "sha256:3a64d86196a59e273357cef154b0e61ebf1788209f97548ecf6e1cd4c556bd5c",
        "size_bytes": 3743,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260914_051003": {
        "relative_path": Path("output/forward_position_thesis/2026-09-14/candidate_scheduled_rec_20260914_051003_1528.json"),
        "sha256": "sha256:804c4ddd74790f17c2631f90953a4b45982e756b8d50dde5f4ae4a0dc575d681",
        "size_bytes": 3742,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260917_051002": {
        "relative_path": Path("output/forward_position_thesis/2026-09-17/candidate_scheduled_rec_20260917_051002_1308.json"),
        "sha256": "sha256:eb2b41a690d38743229adb44f730ab6da467a6f1560212f6961d37756b61ff82",
        "size_bytes": 4313,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260918_051002": {
        "relative_path": Path("output/forward_position_thesis/2026-09-18/candidate_scheduled_rec_20260918_051002_1103.json"),
        "sha256": "sha256:da9e05a8342097c71d1f896cdd22ccf7b7b8c5d353efca449bf92df19c7e9ab8",
        "size_bytes": 4338,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260919_051002": {
        "relative_path": Path("output/forward_position_thesis/2026-09-19/candidate_scheduled_rec_20260919_051002_1103.json"),
        "sha256": "sha256:964129574be2c83767387ea6374d4a4d9689164682b9915deba915fca9899993",
        "size_bytes": 4338,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260920_051002": {
        "relative_path": Path("output/forward_position_thesis/2026-09-20/candidate_scheduled_rec_20260920_051002_1103.json"),
        "sha256": "sha256:f8ae4e13d62fc96dfef6a21c5b0b58df1fc6b0c504d97623000605254ec61046",
        "size_bytes": 4338,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260921_051002": {
        "relative_path": Path("output/forward_position_thesis/2026-09-21/candidate_scheduled_rec_20260921_051002_1314.json"),
        "sha256": "sha256:a84f13c2d503b4ab8766bf4e9ca922827df36ab6582d36db4524450d5b12a9b4",
        "size_bytes": 4332,
        "record_pointer": ("recommendation_source",),
    },
    "scheduled_rec_20260923_051003": {
        "relative_path": Path(
            "output/forward_position_thesis/2026-09-23/"
            "candidate_scheduled_rec_20260923_051003_1101.json"
        ),
        "sha256": "sha256:3d5784c24ee92257dfa8b9a66955305fc6800c595df4cfc4b53f746b82706e47",
        "size_bytes": 4337,
        "record_pointer": ("recommendation_source",),
    }
}


def _legacy_recommendation_custody_evidence(
    repository_root: Path | None = None,
) -> dict[str, LegacyRecommendationCustodyEvidencePin]:
    """回傳逐筆固定的 pre-migration 身份證據；證據缺失時 locator 會 fail closed。"""

    root = repository_root or Path(__file__).resolve().parents[1]
    evidence: dict[str, LegacyRecommendationCustodyEvidencePin] = {}
    for result_id, item in _LEGACY_CUSTODY_EVIDENCE.items():
        evidence_path = (root / item["relative_path"]).resolve()
        evidence[result_id] = LegacyRecommendationCustodyEvidencePin(
            evidence_path=evidence_path,
            evidence_sha256=str(item["sha256"]),
            evidence_size_bytes=int(item["size_bytes"]),
            record_pointer=tuple(item["record_pointer"]),
            result_id_field="result_id",
            origin_path_field="path",
            original_sha256_field="file_sha256",
        )
    return evidence


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
    legacy_reader = SQLiteLegacyRecommendationRawByteReader(
        runs_dir,
        runs_dir / "recommendation_runs.db",
        allowed_relocated_custody_tiers=("tier1_independent_pre_migration_file_sha256",),
        relocated_custody_evidence=_legacy_recommendation_custody_evidence(),
        allow_research_only_relocated=True,
    )
    return RecommendationExecutionQueries(
        RecommendationExecutionPersistence(store),
        legacy_reader=legacy_reader,
    )


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

    # 舊 runs.created_at 有些沒有 offset。保留「未知時區」語義，但可用 ±24
    # 小時包住所有 civil timezone；只有時間區間完全分離時才跨 namespace 排序。
    # 這不替舊值補時區，也不會在相鄰／重疊時段猜最新結果。
    unknown_zone_bound = timedelta(hours=24)
    clocks: list[
        tuple[RecommendationExecutionReadModel, datetime, datetime]
    ] = []
    for item in read_models:
        persisted_at = item.persisted_at
        if isinstance(persisted_at, datetime):
            try:
                offset = persisted_at.utcoffset()
            except (OverflowError, ValueError):
                offset = None
            if persisted_at.tzinfo is not None and offset is not None:
                try:
                    instant = persisted_at.astimezone(timezone.utc)
                except (OverflowError, ValueError):
                    return None, "recommendation_latest_selection_ambiguous_clock"
                clocks.append((item, instant, instant))
                continue
            naive_clock = persisted_at.replace(tzinfo=None)
        else:
            legacy_read_model = item.legacy_result
            created_at = getattr(legacy_read_model, "created_at", None)
            if not isinstance(created_at, str) or not created_at.strip():
                return None, "recommendation_latest_selection_ambiguous_clock"
            try:
                naive_clock = datetime.fromisoformat(created_at)
            except ValueError:
                return None, "recommendation_latest_selection_ambiguous_clock"
            try:
                offset = naive_clock.utcoffset()
            except (OverflowError, ValueError):
                offset = None
            if naive_clock.tzinfo is not None and offset is not None:
                try:
                    instant = naive_clock.astimezone(timezone.utc)
                except (OverflowError, ValueError):
                    return None, "recommendation_latest_selection_ambiguous_clock"
                clocks.append((item, instant, instant))
                continue
            naive_clock = naive_clock.replace(tzinfo=None)
        try:
            lower = (naive_clock - unknown_zone_bound).replace(tzinfo=timezone.utc)
            upper = (naive_clock + unknown_zone_bound).replace(tzinfo=timezone.utc)
        except (OverflowError, ValueError):
            return None, "recommendation_latest_selection_ambiguous_clock"
        clocks.append((item, lower, upper))

    definitely_latest = [
        item
        for item, lower, _upper in clocks
        if all(
            lower > other_upper
            for other, _other_lower, other_upper in clocks
            if other is not item
        )
    ]
    if len(definitely_latest) == 1:
        return definitely_latest[0], None

    if any(lower != upper for _item, lower, upper in clocks):
        return None, "recommendation_latest_selection_ambiguous_clock"
    latest_time = max(lower for _item, lower, _upper in clocks)
    tied = [item for item, lower, _upper in clocks if lower == latest_time]
    return min(tied, key=lambda item: item.result_id), None


def saved_recommendation_capture_projection(
    read_model: RecommendationExecutionReadModel,
) -> dict[str, object]:
    """投影 coverage/status consumers 所需的已保存 capture 欄位。"""

    result: dict[str, object] = {
        "result_id": read_model.result_id,
        "integrity_basis": read_model.integrity_basis,
        "source_diagnostics": tuple(read_model.diagnostics),
    }
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
        if execution_result_config(execution).get("scheduled_snapshot") is True:
            result["decision_date"] = canonical_scheduled_decision_date(read_model)
        result["data_as_of_date"] = execution_result_config(execution).get(
            "data_as_of_date"
        )
        result["recommendations_count"] = (
            len(execution.decision.items) if execution.decision is not None else None
        )
        decision = execution.decision
        typed_outcome_count = count_legacy_assessment_outcomes(decision)
        if typed_outcome_count:
            if decision is None:
                raise NegativeEvidenceProjectionError(
                    "typed negative-evidence outcomes 缺少 DecisionBatch"
                )
            projection = project_canonical_negative_evidence(decision)
            events = tuple(
                item
                for item in execution.events
                if item.event_type == LEGACY_NEGATIVE_EVIDENCE_EVENT_TYPE
            )
            if len(events) > 1:
                raise NegativeEvidenceProjectionError(
                    "legacy negative-evidence event 重複"
                )
            if events:
                assert_legacy_event_matches_projection(
                    events[0].details,
                    projection,
                )
            result.update(projection.as_saved_capture_projection())
        else:
            result.update(
                legacy_history_event_projection(
                    execution.events,
                    schema_revision=read_model.schema_revision,
                )
            )
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
    sealed_dates = (execution.context.as_of_date, execution.request.as_of_date)
    data_value = config.get("data_as_of_date")
    if data_value is None:
        # 明確舊同日格式的相容性：沒有分離的資料日期時不得猜測較早 cutoff。
        if any(candidate is not None and candidate != parsed for candidate in sealed_dates):
            return None
    else:
        if type(data_value) is not str:
            return None
        try:
            data_date = date.fromisoformat(data_value)
        except ValueError:
            return None
        if data_date.isoformat() != data_value or data_date > parsed:
            return None
        if any(candidate != data_date for candidate in sealed_dates):
            return None
        decision_at = execution.context.decision_at
        if (decision_at is None or decision_at.tzinfo is None
                or decision_at.utcoffset() is None
                or decision_at.astimezone(ZoneInfo("Asia/Taipei")).date() != parsed):
            return None
        if (config.get("temporal_mode") != "natural_producer_clock"
                or config.get("cutoff_policy") != "source_latest_available_exact"
                or config.get("cutoff_selection") != "producer_selected_latest_available_cutoff"):
            return None
        schema = config.get("date_semantics_schema")
        if schema is not None and (schema != "scheduled-recommendation-date-roles.v1"
                or config.get("decision_timezone") != "Asia/Taipei"
                or config.get("market_cutoff_date") != data_value):
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
