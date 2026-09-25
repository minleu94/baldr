"""decision strategy owner 與既有 wire/import 契約的回歸檢查。"""

import ast
from pathlib import Path

import pandas as pd
import pytest

import decision_module.strategies
from decision_module.reason_tags import ReasonTagGenerator
from decision_module.strategies.baseline_score_executor import BaselineScoreExecutor
from decision_module.strategies.contracts import (
    DailySignalFrame,
    StrategyExecutor,
    StrategyMeta,
    StrategySpec,
)
from decision_module.strategies.momentum_aggressive_executor import MomentumAggressiveExecutor
from decision_module.strategies.registry import StrategyRegistry
from decision_module.strategies.stable_conservative_executor import StableConservativeExecutor


def test_registry_keeps_existing_ids_order_metadata_and_duplicate_rejection():
    expected_ids = [
        "baseline_score_threshold",
        "momentum_aggressive_v1",
        "stable_conservative_v1",
    ]
    strategies = StrategyRegistry.list_strategies()

    assert list(strategies) == expected_ids
    assert strategies["baseline_score_threshold"]["name"] == "基準分數門檻策略"
    assert strategies["baseline_score_threshold"]["params"]["threshold_mode"]["default"] == "fixed"
    assert strategies["momentum_aggressive_v1"]["name"] == "暴衝策略"
    assert strategies["momentum_aggressive_v1"]["default_params"]["threshold_mode"] == "fixed"
    assert strategies["stable_conservative_v1"]["name"] == "穩健策略"
    assert strategies["stable_conservative_v1"]["default_params"]["threshold_mode"] == "fixed"

    before = list(StrategyRegistry._registry)
    with pytest.raises(ValueError, match="策略 baseline_score_threshold 已經註冊過了"):
        StrategyRegistry.register("baseline_score_threshold", BaselineScoreExecutor)
    assert list(StrategyRegistry._registry) == before


def test_strategy_spec_keys_defaults_and_parameter_roundtrip_are_unchanged():
    spec = StrategySpec(strategy_id="sample", strategy_version="1.2.3")
    expected = {
        "strategy_id": "sample",
        "strategy_version": "1.2.3",
        "data_version": None,
        "name": "",
        "description": "",
        "regime": [],
        "risk_level": "medium",
        "target_type": "stock",
        "default_params": {},
        "config": {},
    }
    assert spec.to_dict() == expected
    assert list(spec.to_dict()) == list(expected)

    saved = StrategySpec(
        strategy_id="momentum_aggressive_v1",
        strategy_version="1.0.0",
        default_params={"threshold_mode": "quantile", "buy_quantile_bp": 8000},
        config={"params": {"threshold_mode": "quantile", "buy_quantile_bp": 8000}},
    ).to_dict()
    assert StrategySpec.from_dict(saved).to_dict() == saved


def test_daily_signal_frame_validation_and_alignment_are_unchanged():
    with pytest.raises(ValueError, match="DataFrame 必須有日期索引或日期欄位"):
        DailySignalFrame.create(
            df=pd.DataFrame({"close": [10.0]}),
            signals=pd.Series([1]),
            scores={},
            reason_tags=pd.Series([[]]),
        )

    dates = pd.date_range("2026-01-01", periods=2, freq="D")
    frame = DailySignalFrame.create(
        df=pd.DataFrame({"close": [10.0, 11.0]}, index=dates),
        signals=pd.Series([1], index=dates[:1]),
        scores={"score": pd.Series([50.0], index=dates[:1])},
        reason_tags=pd.Series([["trend"]], index=dates[:1]),
    )
    assert list(frame["signal"]) == [1, 0]
    assert list(frame["score"]) == [50.0, 0.0]
    assert list(frame["reason_tags"]) == ["trend", ""]
    assert list(frame["regime_match"]) == [False, False]


def test_legacy_app_paths_are_aliases_to_the_single_decision_owner():
    from app_module.daily_signal import DailySignalFrame as LegacyDailySignalFrame
    from app_module.reason_tags import ReasonTagGenerator as LegacyReasonTagGenerator
    from app_module.strategies import BaselineScoreExecutor as LegacyBaselineScoreExecutor
    from app_module.strategies.baseline_score_executor import (
        BaselineScoreExecutor as LegacyExecutorModuleClass,
    )
    from app_module.strategy_executor_adapter import SimpleStrategyExecutor as LegacySimpleStrategyExecutor
    from app_module.strategy_registry import StrategyRegistry as LegacyStrategyRegistry
    from app_module.strategy_spec import (
        StrategyExecutor as LegacyStrategyExecutor,
        StrategyMeta as LegacyStrategyMeta,
        StrategySpec as LegacyStrategySpec,
    )

    assert LegacyDailySignalFrame is DailySignalFrame
    assert LegacyReasonTagGenerator is ReasonTagGenerator
    assert LegacyBaselineScoreExecutor is BaselineScoreExecutor
    assert LegacyExecutorModuleClass is BaselineScoreExecutor
    assert LegacySimpleStrategyExecutor is decision_module.strategies.simple_strategy_executor.SimpleStrategyExecutor
    assert LegacyStrategyRegistry is StrategyRegistry
    assert LegacyStrategyExecutor is StrategyExecutor
    assert LegacyStrategyMeta is StrategyMeta
    assert LegacyStrategySpec is StrategySpec
    assert list(LegacyStrategyRegistry.list_strategies()) == [
        "baseline_score_threshold",
        "momentum_aggressive_v1",
        "stable_conservative_v1",
    ]
    assert StrategyRegistry.get_strategy_meta("baseline_score_threshold")["strategy_id"] == (
        "baseline_score_threshold"
    )


def test_strategy_executor_contract_and_decision_import_direction():
    assert isinstance(BaselineScoreExecutor(StrategySpec("baseline_score_threshold", "1.0")), StrategyExecutor)
    assert isinstance(
        MomentumAggressiveExecutor(StrategySpec("momentum_aggressive_v1", "1.0")),
        StrategyExecutor,
    )
    assert isinstance(
        StableConservativeExecutor(StrategySpec("stable_conservative_v1", "1.0")),
        StrategyExecutor,
    )

    package_root = Path(__file__).resolve().parents[1] / "decision_module"
    source_paths = [*package_root.joinpath("strategies").glob("*.py"), package_root / "reason_tags.py"]
    for source_path in source_paths:
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)
        assert not any(module == "app_module" or module.startswith("app_module.") for module in imported_modules), (
            f"decision strategy source must not depend on app_module: {source_path}"
        )
