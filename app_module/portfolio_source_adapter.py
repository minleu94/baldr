"""Build source metadata for Portfolio trades created from research artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from app_module.dtos import RecommendationDTO, RecommendationResultDTO


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
