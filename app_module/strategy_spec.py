"""舊策略契約匯入路徑；實作由 decision_module 擁有。"""

from decision_module.strategies.contracts import (
    StrategyExecutor,
    StrategyMeta,
    StrategySpec,
    create_daily_signal_frame,
)

__all__ = ["StrategySpec", "StrategyMeta", "StrategyExecutor", "create_daily_signal_frame"]