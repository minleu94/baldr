"""登記版本沿同次請求固定，既有金融參數與歷史結果不改寫。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.optimizer_service import OptimizerService, ParamRange
from app_module.registered_strategy_spec import registered_strategy_spec
from decision_module.strategies.registry import StrategyRegistry


@pytest.mark.parametrize("strategy_id,version", [
    ("baseline_score_threshold", "1.0"),
    ("momentum_aggressive_v1", "1.0.0"),
    ("stable_conservative_v1", "1.0.0"),
])
def test_real_registry_version_and_config_are_preserved(strategy_id, version):
    config = {"params": {"buy_score": 65}, "technical": {"windows": [5, 20]}}
    spec = registered_strategy_spec(strategy_id, config=config)
    assert spec.strategy_id == strategy_id and spec.strategy_version == version
    assert spec.config == config
    config["params"]["buy_score"] = 99
    config["technical"]["windows"].append(60)
    assert spec.config == {"params": {"buy_score": 65}, "technical": {"windows": [5, 20]}}


@pytest.mark.parametrize("metadata", [
    None,
    {"strategy_id": "other", "version": "1.0"},
    {"strategy_id": "selected"},
    {"strategy_id": "selected", "version": ""},
    {"strategy_id": "selected", "version": " 1.0 "},
    {"strategy_id": "selected", "version": 1},
    {"strategy_id": "selected", "version": "1.0", "strategy_version": "2.0"},
])
def test_missing_ambiguous_or_other_identity_never_gets_default_version(monkeypatch, metadata):
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", lambda _id: metadata)
    with pytest.raises(ValueError):
        registered_strategy_spec("selected", config={})


def test_optimizer_freezes_version_before_market_read_and_all_combinations(monkeypatch):
    metadata = {"strategy_id": "selected", "version": "1.0.0", "name": "selected"}
    calls = []
    def meta(_id):
        calls.append(_id)
        return metadata
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", meta)
    service = MagicMock()
    def load(*args):
        metadata["version"] = "2.0.0"
        return pd.DataFrame({"close": [100]}), "2026-01-02", "2026-01-02"
    service._load_stock_data.side_effect = load
    zero = Decimal("0")
    service.run_backtest.return_value = SimpleNamespace(
        total_return=zero, annual_return=zero, sharpe_ratio=zero, max_drawdown=zero,
        win_rate=zero, total_trades=0, expectancy=zero, details={"profit_factor": zero},
    )
    results = OptimizerService(service, max_workers=1).grid_search(
        stock_code="2330", start_date="2026-01-02", end_date="2026-01-02", strategy_id="selected",
        base_params={}, param_ranges={"buy_score": ParamRange("buy_score", "list", [60, 70])},
    )
    assert len(results) == 2 and calls == ["selected"]
    assert [call.kwargs["strategy_spec"].strategy_version for call in service.run_backtest.call_args_list] == ["1.0.0", "1.0.0"]
    assert {call.kwargs["strategy_spec"].config["params"]["buy_score"] for call in service.run_backtest.call_args_list} == {60, 70}


def test_optimizer_unknown_version_rejected_before_market_read(monkeypatch):
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", lambda _id: None)
    service = MagicMock()
    with pytest.raises(ValueError, match="登記身分"):
        OptimizerService(service, max_workers=1).grid_search(
            stock_code="2330", start_date="2026-01-02", end_date="2026-01-02",
            strategy_id="missing", base_params={}, param_ranges={},
        )
    service._load_stock_data.assert_not_called()
    service.run_backtest.assert_not_called()
