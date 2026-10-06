"""已驗模型成本情境的有界投影；未知不補零、預測與實際結果分開。"""
from dataclasses import asdict
from datetime import date
import json

import pytest

from app_module.stock_research_report_dtos import StockMLSnapshotDTO
from app_module.stock_research_report_provider_adapters import _manifest_target_costs
from tests.test_stock_research_report_provider_contracts import _ml_candidate, _price_fingerprint, _service
from ui_qt.views.stock_research_report_view import _ml_estimate_summary

TARGET = "benchmark_excess_after_standard_80bp_cost"


def _manifest(**changes):
    costs = {"schema_version": "portfolio-ml-outcome-cost-contract.v1", "cost_unit": "basis_points",
        "total_round_trip_cost_bp": 80, "buy_side_cost_bp": 25, "sell_side_cost_bp": 55}
    costs.update(changes)
    return {"target_contract": {"schema_version": "current-restated-outcome-target.v1",
        "target_metric": TARGET, "cost_contract": costs}}


def _read(costs):
    service = _service()
    service.ml_provider = lambda code, cutoff, context=None: _ml_candidate(**costs)
    return service._read_ml("1477", date(2026, 10, 4), {
        "ml_scope_mode": "current_stock_research", "current_event_date": "2026-10-02",
        "current_price_row_fingerprint_sha256": _price_fingerprint()})


def test_original_cost_scenario_projects_without_changing_forecast_or_qualification():
    total, buy, sell = _manifest_target_costs(_manifest(), TARGET)
    ml = _read({"target_round_trip_cost_bp": total,
        "target_buy_side_cost_bp": buy, "target_sell_side_cost_bp": sell})
    assert (ml.target_round_trip_cost_bp, ml.target_buy_side_cost_bp, ml.target_sell_side_cost_bp) == (80, 25, 55)
    assert ml.predicted_benchmark_excess_return_bp == {"final|CORE19|h5|ridge_logistic": 125}
    text = _ml_estimate_summary(ml)
    assert "本次模型假設總成本0.8%（買進0.25%、賣出0.55%）" in text
    assert "不是你的實際交易成本" in text
    assert "基準名稱、期間的交易日／日曆日定義未提供" in text
    assert ml.h5_gross_stock_return_bp is None and ml.formal_qualified is False


@pytest.mark.parametrize("field,value", [
    ("total_round_trip_cost_bp", None), ("total_round_trip_cost_bp", True),
    ("total_round_trip_cost_bp", 80.0), ("total_round_trip_cost_bp", 90),
    ("buy_side_cost_bp", -1), ("buy_side_cost_bp", False), ("sell_side_cost_bp", 54),
    ("cost_unit", "percent"), ("schema_version", "unknown"),
])
def test_invalid_manifest_costs_remain_unknown(field, value):
    assert _manifest_target_costs(_manifest(**{field: value}), TARGET) == (None, None, None)


def test_missing_or_wrong_target_contract_does_not_supply_costs():
    assert _manifest_target_costs({}, TARGET) == (None, None, None)
    assert _manifest_target_costs(_manifest(), "gross_return") == (None, None, None)
    legacy = _read({})
    assert legacy.target_round_trip_cost_bp is None
    assert "成本情境與數值未提供" in _ml_estimate_summary(legacy)
    # 新欄位有defaults；舊DTO JSON無成本欄仍可重建，None不能变成0。
    payload = json.loads(json.dumps(asdict(StockMLSnapshotDTO())))
    for key in ("target_round_trip_cost_bp", "target_buy_side_cost_bp", "target_sell_side_cost_bp"):
        payload.pop(key)
    assert StockMLSnapshotDTO(**payload).target_round_trip_cost_bp is None


@pytest.mark.parametrize("value", [True, -1, 81, "80", None])
def test_service_rechecks_flat_costs_and_preserves_valid_forecast(value):
    ml = _read({"target_round_trip_cost_bp": value,
        "target_buy_side_cost_bp": 25, "target_sell_side_cost_bp": 55})
    assert ml.target_round_trip_cost_bp is None
    assert ml.predicted_benchmark_excess_return_bp == {"final|CORE19|h5|ridge_logistic": 125}
