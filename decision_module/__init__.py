"""決策邏輯模組的相容 public API。

保留舊頂層名稱，並避免匯入純 leaf contract 時載入計算服務。
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decision_module.industry_mapper import IndustryMapper
    from decision_module.market_regime_detector import MarketRegimeDetector
    from decision_module.reason_engine import ReasonEngine
    from decision_module.scoring_engine import ScoringEngine
    from decision_module.stock_screener import StockScreener
    from decision_module.strategy_configurator import StrategyConfigurator

__all__ = [
    "StrategyConfigurator",
    "ReasonEngine",
    "IndustryMapper",
    "MarketRegimeDetector",
    "StockScreener",
    "ScoringEngine",
]

_EXPORTS = {
    "StrategyConfigurator": ("decision_module.strategy_configurator", "StrategyConfigurator"),
    "ReasonEngine": ("decision_module.reason_engine", "ReasonEngine"),
    "IndustryMapper": ("decision_module.industry_mapper", "IndustryMapper"),
    "MarketRegimeDetector": ("decision_module.market_regime_detector", "MarketRegimeDetector"),
    "StockScreener": ("decision_module.stock_screener", "StockScreener"),
    "ScoringEngine": ("decision_module.scoring_engine", "ScoringEngine"),
}


def __getattr__(name: str) -> object:
    export = _EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = export
    module = import_module(module_name)
    value: object = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
