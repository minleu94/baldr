"""Build source metadata for Portfolio trades created from research artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Mapping, Optional

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation.contracts import (
    ExecutionStatus,
    IndexStatus,
    RecommendationExecution,
    SaveReceipt,
)
from app_module.recommendation.queries import RecommendationExecutionReadModel
from decision_module.recommendation.contracts import RecommendationItem


@dataclass(frozen=True)
class PortfolioTradeSource:
    """Traceable source metadata attached to append-only Portfolio trades."""

    source_type: str
    source_id: str
    source_snapshot_hash: str
    source_summary: Dict[str, Any]


def stable_snapshot_hash(payload: Mapping[str, Any]) -> str:
    """Return a deterministic hash for JSON-compatible metadata."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_json_value(value: Any) -> Any:
    """Normalize source metadata exactly as Portfolio JSONL will persist it."""

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("source metadata Decimal 必須為有限值")
        return format(value, "f")
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("source metadata float 必須為有限值")
        return format(Decimal(str(value)), "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _source_json_value(value.value)
    if isinstance(value, Mapping):
        return {str(key): _source_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_source_json_value(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError(f"source metadata 不支援 {type(value).__name__}")


def _projection_value(
    projection: Mapping[str, object] | None,
    *source_names: str,
) -> object | None:
    if projection is None:
        return None
    for name in source_names:
        value = projection.get(name)
        if value is not None and value != "":
            return value
    return None


def _projection_string_list(value: object | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (tuple, list)) or not all(
        isinstance(item, str) for item in value
    ):
        raise TypeError("verified calibration 字串欄位格式不正確")
    return list(value)


def _projection_mapping(value: object | None) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("verified calibration provenance 必須是 mapping")
    return {str(key): item for key, item in value.items()}


def _split_reasons(raw: Any) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    for separator in ["；", ";", "、", "\n"]:
        text = text.replace(separator, "|")
    return [part.strip() for part in text.split("|") if part.strip()]


def build_recommendation_trade_source(
    result: RecommendationResultDTO,
    recommendation: RecommendationDTO,
) -> PortfolioTradeSource:
    """Create trace metadata for a trade recorded from a Recommendation row."""

    config = dict(result.config or {})
    regime_snapshot = dict(config.get("regime_snapshot") or {})
    summary: Dict[str, Any] = {
        "result_id": result.result_id,
        "result_name": result.result_name,
        "created_at": result.created_at,
        "stock_code": recommendation.stock_code,
        "stock_name": recommendation.stock_name,
        "close_price": recommendation.close_price,
        "price_change": recommendation.price_change,
        "profile_id": config.get("profile_id") or config.get("selected_profile") or "",
        "profile_version": config.get("profile_version") or "",
        "regime": result.regime or regime_snapshot.get("regime") or config.get("regime") or "",
        "total_score": recommendation.total_score,
        "indicator_score": recommendation.indicator_score,
        "pattern_score": recommendation.pattern_score,
        "volume_score": recommendation.volume_score,
        "recommendation_reasons": recommendation.recommendation_reasons,
        "reasons": _split_reasons(recommendation.recommendation_reasons),
        "industry": recommendation.industry,
        "regime_match": recommendation.regime_match,
        "ranking_score_bp": recommendation.ranking_score_bp,
        "ranking_percentile_bp": recommendation.score_percentile_bp,
        "ranking_method": recommendation.ranking_method,
        "calibrated_probability_bp": recommendation.calibrated_probability_bp,
        "calibrated_probability_status": recommendation.calibrated_probability_status,
        "after_cost_profit_probability_bp": recommendation.after_cost_profit_probability_bp,
        "after_cost_profit_probability_status": recommendation.after_cost_profit_probability_status,
        "evidence_confidence": recommendation.evidence_confidence,
        "sample_size": recommendation.sample_size,
        "cost_basis_bp": recommendation.cost_basis_bp,
        "calibration_model_version": recommendation.calibration_model_version,
        "calibration_dataset_version": recommendation.calibration_dataset_version,
        "calibration_horizon": recommendation.calibration_horizon,
        "calibration_status": recommendation.calibration_status,
        "calibration_source": recommendation.calibration_source,
        "calibration_source_trace": list(recommendation.calibration_source_trace),
        "calibration_warnings": list(recommendation.calibration_warnings),
        "calibration_probability_transform_id": recommendation.calibration_probability_transform_id,
        "calibration_probability_baseline_id": recommendation.calibration_probability_baseline_id,
        "calibration_probability_baseline_kind": recommendation.calibration_probability_baseline_kind,
        "calibration_probability_baseline_probability_bp": recommendation.calibration_probability_baseline_probability_bp,
        "calibration_raw_probability_bp": recommendation.calibration_raw_probability_bp,
        "calibration_raw_after_cost_probability_bp": recommendation.calibration_raw_after_cost_probability_bp,
    }
    return PortfolioTradeSource(
        source_type="recommendation_result",
        source_id=result.result_id,
        source_snapshot_hash=stable_snapshot_hash(summary),
        source_summary=dict(summary),
    )


def _verified_projection_for_item(
    read_model: RecommendationExecutionReadModel,
    recommendation: RecommendationItem,
) -> Mapping[str, object] | None:
    if read_model.ml_read_status != "verified":
        return None
    matches = [
        row
        for row in read_model.ml_projection_rows
        if str(row.get("stock_code") or "").strip() == recommendation.stock_code
    ]
    if len(matches) > 1:
        raise ValueError("已驗證 ML read model 對選定股票有重複 projection 列")
    return matches[0] if matches else None


def build_recommendation_execution_trade_source(
    execution: RecommendationExecution,
    read_model: RecommendationExecutionReadModel,
    receipt: SaveReceipt,
    recommendation: RecommendationItem,
) -> PortfolioTradeSource:
    """從 sealed execution 與同次 verified save/readback 建立 Portfolio 來源。"""

    if type(execution) is not RecommendationExecution:
        raise TypeError("execution 必須是 RecommendationExecution")
    if execution.status is not ExecutionStatus.COMPLETED:
        raise ValueError("只有 completed recommendation execution 可以記錄交易來源")
    if type(read_model) is not RecommendationExecutionReadModel:
        raise TypeError("read_model 必須是 RecommendationExecutionReadModel")
    if read_model.execution is None or read_model.execution != execution:
        raise ValueError("verified read model 必須包含同一份 sealed execution")
    if read_model.integrity_basis != "canonical_payload_and_index_verified":
        raise ValueError("Portfolio 來源只接受已驗證 canonical payload/index")
    if read_model.result_id != execution.result_id:
        raise ValueError("read model result_id 與 sealed execution 不符")
    if type(receipt) is not SaveReceipt or receipt.index_status is not IndexStatus.INDEXED:
        raise ValueError("save receipt 必須是已索引的 canonical SaveReceipt")
    if (
        receipt.result_id != execution.result_id
        or read_model.payload_hash != receipt.payload_hash
        or read_model.artifact_location != receipt.artifact_location
        or read_model.persisted_at != receipt.persisted_at
    ):
        raise ValueError("save receipt 與 verified readback 身分／hash／artifact 不符")
    if not read_model.payload_hash or not read_model.artifact_location:
        raise ValueError("verified readback 缺少 artifact payload hash 或位置")
    if type(recommendation) is not RecommendationItem:
        raise TypeError("recommendation 必須是 RecommendationItem")
    selected_matches = [
        item
        for item in execution.items
        if item.stock_code == recommendation.stock_code
    ]
    if len(selected_matches) != 1 or selected_matches[0] != recommendation:
        raise ValueError("選定股票必須唯一且完全符合同一 execution item")

    projection = _verified_projection_for_item(read_model, recommendation)
    profile_ref = execution.request.profile_ref
    context = execution.context
    decision = execution.decision
    result_name = read_model.label or ""
    universe_snapshot = (
        context.universe_identity.snapshot
        if context.universe_identity is not None
        else None
    )
    if universe_snapshot is not None:
        source_snapshot_id = universe_snapshot.universe_snapshot_id or ""
        source_snapshot_hash = universe_snapshot.universe_snapshot_hash or ""
    elif context.universe_snapshot_ref is not None:
        source_snapshot_id = context.universe_snapshot_ref.reference_id
        source_snapshot_hash = ""
    elif len(context.data_snapshot_refs) == 1:
        source_snapshot_id = context.data_snapshot_refs[0].reference_id
        source_snapshot_hash = ""
    else:
        source_snapshot_id = ""
        source_snapshot_hash = ""
    data_snapshot_ids = [reference.reference_id for reference in context.data_snapshot_refs]
    source_refs = [
        {
            "source_id": reference.source_id,
            "revision": reference.revision,
            "snapshot_id": reference.snapshot_id,
        }
        for reference in context.source_refs
    ]

    def projection_value(*source_names: str) -> object | None:
        return _projection_value(projection, *source_names)

    summary: Dict[str, Any] = {
        "result_id": execution.result_id,
        "result_name": result_name,
        "created_at": context.created_at.isoformat() if context.created_at else None,
        "decision_date": context.as_of_date.isoformat() if context.as_of_date else None,
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_hash": source_snapshot_hash,
        "artifact_location": read_model.artifact_location,
        "payload_hash": read_model.payload_hash,
        "integrity_basis": read_model.integrity_basis,
        "data_snapshot_ids": data_snapshot_ids,
        "source_refs": source_refs,
        "candidate_identity": {
            "stock_code": recommendation.stock_code,
            "rank": recommendation.rank,
        },
        "stock_code": recommendation.stock_code,
        "stock_name": recommendation.stock_name or "",
        "close_price": recommendation.close_price,
        "price_change": recommendation.price_change,
        "profile_id": profile_ref.reference_id if profile_ref else "",
        "profile_version": profile_ref.version or "" if profile_ref else "",
        "regime": decision.regime if decision and decision.regime is not None else "",
        "total_score": recommendation.rule_score,
        "indicator_score": recommendation.indicator_score,
        "pattern_score": recommendation.pattern_score,
        "volume_score": recommendation.volume_score,
        "recommendation_reasons": recommendation.reason_text or "",
        "reasons": list(recommendation.reasons) or _split_reasons(
            recommendation.reason_text
        ),
        "industry": recommendation.industry or "",
        "regime_match": recommendation.regime_match,
        "ranking_score_bp": projection_value("ranking_score_bp"),
        "ranking_percentile_bp": recommendation.score_percentile_bp,
        "ranking_method": recommendation.ranking_method,
        "threshold_mode": recommendation.threshold_mode,
        "calibrated_probability_bp": projection_value("calibrated_probability_bp"),
        "calibrated_probability_status": (
            projection_value("calibrated_probability_status") or "unavailable"
        ),
        "after_cost_profit_probability_bp": projection_value(
            "after_cost_profit_probability_bp"
        ),
        "after_cost_profit_probability_status": (
            projection_value("after_cost_profit_probability_status") or "unavailable"
        ),
        "evidence_confidence": projection_value("evidence_confidence") or "",
        "sample_size": projection_value("sample_size"),
        "cost_basis_bp": projection_value("cost_basis_bp"),
        "calibration_model_version": (
            projection_value("calibration_model_version", "model_version", "model_id") or ""
        ),
        "calibration_dataset_version": (
            projection_value("calibration_dataset_version", "dataset_version", "dataset_id") or ""
        ),
        "calibration_horizon": (
            projection_value("calibration_horizon", "horizon_trading_days", "horizon") or ""
        ),
        "calibration_status": (
            projection_value("calibration_status", "status") or "unavailable"
        ),
        "calibration_source": projection_value("calibration_source", "source") or "",
        "calibration_source_trace": _projection_string_list(
            projection_value("calibration_source_trace", "source_trace")
        ),
        "calibration_warnings": _projection_string_list(
            projection_value("calibration_warnings", "warnings")
        ),
        "calibration_probability_transform_id": (
            projection_value("calibration_probability_transform_id", "probability_transform_id") or ""
        ),
        "calibration_probability_baseline_id": (
            projection_value("calibration_probability_baseline_id", "probability_baseline_id") or ""
        ),
        "calibration_probability_baseline_kind": (
            projection_value("calibration_probability_baseline_kind", "probability_baseline_kind") or ""
        ),
        "calibration_probability_baseline_probability_bp": projection_value(
            "calibration_probability_baseline_probability_bp",
            "probability_baseline_probability_bp",
        ),
        "calibration_raw_probability_bp": projection_value(
            "calibration_raw_probability_bp", "raw_calibrated_probability_bp"
        ),
        "calibration_raw_after_cost_probability_bp": projection_value(
            "calibration_raw_after_cost_probability_bp",
            "raw_after_cost_profit_probability_bp",
        ),
        "calibration_provenance": {
            "training_provenance": _projection_mapping(
                projection_value("training_provenance")
            ),
            "inference_provenance": _projection_mapping(
                projection_value("inference_provenance")
            ),
            "provenance_compatibility": _projection_mapping(
                projection_value("provenance_compatibility")
            ),
            "provenance_status": projection_value("provenance_status") or "unavailable",
        },
    }
    normalized_summary = _source_json_value(summary)
    if not isinstance(normalized_summary, dict):
        raise TypeError("Portfolio source summary 必須是 JSON object")
    return PortfolioTradeSource(
        source_type="recommendation_result",
        source_id=execution.result_id,
        source_snapshot_hash=stable_snapshot_hash(normalized_summary),
        source_summary=normalized_summary,
    )


def _row_value(row: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return default


def build_backtest_trade_source(
    run_id: str,
    run_name: str,
    strategy_id: str,
    validation_status: str,
    trade_row: Mapping[str, Any],
    promoted_version_id: Optional[str] = None,
) -> PortfolioTradeSource:
    """Create trace metadata for a trade recorded from a Backtest trade row."""

    summary: Dict[str, Any] = {
        "run_id": run_id,
        "run_name": run_name,
        "strategy_id": strategy_id,
        "validation_status": validation_status,
        "promoted_version_id": promoted_version_id,
        "stock_code": str(_row_value(trade_row, "股票代號", "證券代號", "stock_code")),
        "stock_name": str(_row_value(trade_row, "股票名稱", "證券名稱", "stock_name")),
        "side": str(_row_value(trade_row, "買賣", "side")),
        "trade_date": str(_row_value(trade_row, "交易日期", "日期", "進場日期", "date", "trade_date")),
        "price": _row_value(trade_row, "價格", "單價", "成交價", "進場價格", "price"),
        "quantity": _row_value(trade_row, "數量", "交易股數", "股數", "quantity", default=""),
        "amount": _row_value(trade_row, "投入金額", "金額", "amount", default=""),
    }
    return PortfolioTradeSource(
        source_type="backtest_run",
        source_id=run_id,
        source_snapshot_hash=stable_snapshot_hash(summary),
        source_summary=dict(summary),
    )
